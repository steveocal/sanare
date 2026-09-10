import json
import re

import lxml.etree
import lxml.html
from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_date, format_datetime, html_sanitize

CONTENT_TYPES = [
    ("folder", "Folder"),
    ("onlyoffice", "Office Document"),
    ("html", "Web Page (HTML)"),
    ("markdown", "Markdown"),
    ("knowledge_html", "Knowledge Page (HTML)"),
]

# Types that store their content in content_html and share its versioning/
# approval/embed-picker machinery - "knowledge_html" is a labeled variant of
# "html" for a knowledge-base/wiki use case, not a mechanically different
# field: same widget, same resolver, same everything except the label and
# its place in the New Document menu.
HTML_TYPES = {"html", "knowledge_html"}

# Folders, HTML pages and Markdown pages can all contain nested documents -
# an HTML/Markdown page with children forms one combined document that
# prints as a single unit (see report_document_body's recursion). Office
# Documents and Knowledge Pages can never be containers: they can't have
# children, and they can't be nested inside a non-container document either
# (see _check_container_integrity). Knowledge Pages compose with *other*
# documents purely through in-content includes (_resolve_embedded_refs),
# not the parent/child tree.
CONTAINER_TYPES = {"folder", "html", "markdown"}

# data-embedded name of the email-send control block. A document is "an
# email" purely by carrying this marker in its content_html - no field, no
# type, no form change: subject + To/Cc/Bcc + Send all live in the body,
# rendered by the EmbeddedEmailSend OWL component.
EMAIL_BLOCK_MARKER = "sanareEmailSend"
VIEW_BLOCK_MARKER = "sanareView"

VISIBILITY = [
    ("private", "Private"),
    ("shared", "Shared"),
    ("public", "Public"),
]

# Which Odoo report chrome wraps this document when printed - "external"/
# "internal" reuse Odoo's own web.external_layout/web.internal_layout as-is
# (company letterhead, address block, etc; only the *content* wrapper - see
# report_document in report/dms_report.xml, which branches on the top-level
# printed document's own value only, never a recursed child's).
REPORT_LAYOUTS = [
    ("none", "None"),
    ("internal", "Internal"),
    ("external", "External"),
]


class SanareDocument(models.Model):
    _name = "sanare.document"
    _description = "Document"
    _inherit = ["mail.thread", "mail.activity.mixin", "website.published.mixin"]
    _parent_store = True
    _parent_name = "parent_id"
    _order = "is_folder desc, sequence, name"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    # -- hierarchy ---------------------------------------------------------
    parent_id = fields.Many2one(
        "sanare.document", string="Parent", ondelete="cascade", index=True, tracking=True
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many(
        "sanare.document", "parent_id", string="Contents", copy=True
    )
    # One2many defaults to copy=False in Odoo - confirmed empirically via
    # odoo-bin shell (Doc._fields["child_ids"].copy was False before this),
    # not the "cascades by default" behaviour assumed when browser_paste was
    # designed. Explicit copy=True here is what actually makes pasting a
    # folder bring its subtree along.
    child_count = fields.Integer(compute="_compute_child_count")
    complete_name = fields.Char(
        compute="_compute_complete_name", recursive=True, store=True, string="Path"
    )
    display_in_print = fields.Boolean(
        string="Include in Parent Print", default=True,
        help="When a parent folder is printed, its descendant tree is pulled "
             "into one combined document - turn this off to skip this "
             "document (and everything under it) from that rollup. It still "
             "shows normally in the tree and can still be printed on its own.",
    )
    report_layout = fields.Selection(
        REPORT_LAYOUTS, string="Print Layout", default="none",
        help="Report chrome used when this document is printed as the "
             "top-level document. 'None' keeps the plain print already used "
             "today; 'Internal'/'External' wrap it in Odoo's own internal/"
             "external report layout (company letterhead, etc). Only the "
             "printed document's own value matters - a recursed child's is "
             "ignored, same as its name/version already are.",
    )
    is_template = fields.Boolean(
        string="Template", default=False,
        help="Shows up in the browser's separate Templates section and in "
             "the New from Template picker / \"/template\" editor command. "
             "A flag, not a move - the document stays in its own folder and "
             "is still organized/found there exactly as before.",
    )
    article_item = fields.Boolean(
        string="Article Item", default=False, copy=True,
        help="An item is a child document that belongs to its parent but is "
             "kept out of the navigation tree - it only shows in the parent's "
             "detail pane (its \"items\" list). Same document in every other "
             "respect.",
    )

    # -- custom properties ------------------------------------------------
    # Scoped per-folder: a folder defines the schema its own children fill
    # in. A folder nested inside another folder does both - it fills in its
    # parent's schema via `properties`, and defines its own children's
    # schema via `properties_definition`, same model either way.
    properties_definition = fields.PropertiesDefinition(string="Document Properties")
    properties = fields.Properties(
        string="Properties", definition="parent_id.properties_definition"
    )

    # -- type & content --------------------------------------------------
    content_type = fields.Selection(
        CONTENT_TYPES, required=True, default="folder", string="Type"
    )
    is_folder = fields.Boolean(compute="_compute_is_folder", store=True)
    can_have_children = fields.Boolean(
        compute="_compute_is_folder", store=True,
        help="Folders, HTML pages and Markdown pages can contain nested "
             "documents; Office Documents cannot.",
    )

    content_html = fields.Html(sanitize=True, sanitize_overridable=True)
    content_markdown = fields.Text()
    content_markdown_html = fields.Html(
        compute="_compute_content_markdown_html", sanitize=False, string="Rendered Markdown"
    )

    attachment_id = fields.Many2one("ir.attachment", string="Office File", copy=False)
    file_content = fields.Binary(
        compute="_compute_file_content", inverse="_inverse_file_content", string="File"
    )
    file_name = fields.Char()
    file_extension = fields.Char(compute="_compute_file_extension", store=True)
    file_size = fields.Integer(related="attachment_id.file_size", readonly=True)
    mimetype = fields.Char(related="attachment_id.mimetype", readonly=True)

    # -- ownership & visibility ----------------------------------------
    owner_id = fields.Many2one(
        "res.users", string="Owner", required=True, tracking=True,
        default=lambda self: self.env.user,
    )
    visibility = fields.Selection(
        VISIBILITY, default="private", required=True, tracking=True
    )
    visibility_inherited = fields.Boolean(
        string="Inherit Access from Parent", default=True,
        help="Take effective visibility and shares from the parent document.",
    )
    effective_visibility = fields.Selection(
        VISIBILITY, compute="_compute_effective_visibility", recursive=True,
        store=True, string="Effective Visibility",
    )

    category_id = fields.Many2one("sanare.document.category", string="Category", tracking=True)
    tag_ids = fields.Many2many("sanare.document.tag", string="Tags")

    # -- workflow -------------------------------------------------------
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("to_approve", "To Approve"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="draft", required=True, tracking=True, copy=False,
    )
    approval_rule_id = fields.Many2one(
        "sanare.document.approval.rule", compute="_compute_approval_rule_id",
        store=True, recursive=True, string="Approval Rule",
    )
    approval_request_id = fields.Many2one(
        "sanare.document.approval.request", copy=False, string="Current Approval"
    )
    approval_line_ids = fields.One2many(
        related="approval_request_id.line_ids", string="Approval Steps"
    )
    can_submit = fields.Boolean(compute="_compute_workflow_buttons")
    can_approve = fields.Boolean(compute="_compute_workflow_buttons")
    can_reject = fields.Boolean(compute="_compute_workflow_buttons")

    # -- versions -----------------------------------------------------
    version_ids = fields.One2many("sanare.document.version", "document_id", string="Versions")
    version_count = fields.Integer(compute="_compute_version_count")
    version_number = fields.Integer(default=0, copy=False, string="Revision")
    approved_version_id = fields.Many2one(
        "sanare.document.version", copy=False, string="Published Revision"
    )

    # -- sharing ----------------------------------------------------
    access_ids = fields.One2many("sanare.document.access", "document_id", string="Shares")
    allowed_user_ids = fields.Many2many(
        "res.users", "sanare_document_allowed_users_rel", "doc_id", "user_id",
        compute="_compute_allowed_users", store=True, recursive=True,
        string="Allowed Users",
    )
    allowed_write_user_ids = fields.Many2many(
        "res.users", "sanare_document_allowed_write_users_rel", "doc_id", "user_id",
        compute="_compute_allowed_users", store=True, recursive=True,
        string="Allowed Editors",
    )

    # ==================================================================
    # Computes
    # ==================================================================
    @api.depends("name", "parent_id.complete_name")
    def _compute_complete_name(self):
        for doc in self:
            if doc.parent_id:
                doc.complete_name = "%s / %s" % (doc.parent_id.complete_name, doc.name)
            else:
                doc.complete_name = doc.name

    @api.depends("content_type")
    def _compute_is_folder(self):
        for doc in self:
            doc.is_folder = doc.content_type == "folder"
            doc.can_have_children = doc.content_type in CONTAINER_TYPES

    def _compute_child_count(self):
        data = self.env["sanare.document"]._read_group(
            [("parent_id", "in", self.ids)], ["parent_id"], ["__count"]
        )
        mapped = {parent.id: count for parent, count in data}
        for doc in self:
            doc.child_count = mapped.get(doc.id, 0)

    def _compute_version_count(self):
        data = self.env["sanare.document.version"]._read_group(
            [("document_id", "in", self.ids)], ["document_id"], ["__count"]
        )
        mapped = {doc.id: count for doc, count in data}
        for doc in self:
            doc.version_count = mapped.get(doc.id, 0)

    @api.depends("visibility", "visibility_inherited", "parent_id.effective_visibility")
    def _compute_effective_visibility(self):
        for doc in self:
            if doc.visibility_inherited and doc.parent_id:
                doc.effective_visibility = doc.parent_id.effective_visibility
            else:
                doc.effective_visibility = doc.visibility

    @api.depends(
        "visibility_inherited", "access_ids.partner_id", "access_ids.group_id",
        "access_ids.permission", "parent_id.allowed_user_ids",
        "parent_id.allowed_write_user_ids",
    )
    def _compute_allowed_users(self):
        for doc in self:
            read_users = self.env["res.users"]
            write_users = self.env["res.users"]
            for acc in doc.access_ids:
                users = self.env["res.users"]
                if acc.partner_id:
                    users |= acc.partner_id.user_ids
                if acc.group_id:
                    users |= acc.group_id.all_user_ids
                read_users |= users
                if acc.permission in ("write", "approve"):
                    write_users |= users
            if doc.visibility_inherited and doc.parent_id:
                read_users |= doc.parent_id.allowed_user_ids
                write_users |= doc.parent_id.allowed_write_user_ids
            doc.allowed_user_ids = read_users
            doc.allowed_write_user_ids = write_users

    @api.depends("category_id", "category_id.approval_rule_id", "parent_path")
    def _compute_approval_rule_id(self):
        Rule = self.env["sanare.document.approval.rule"]
        for doc in self:
            rule = doc.category_id.approval_rule_id
            if not rule and doc.parent_path:
                ancestor_ids = [int(x) for x in doc.parent_path.split("/") if x]
                ancestor_ids = [i for i in ancestor_ids if i != doc.id]
                if ancestor_ids:
                    rule = Rule.search(
                        [("folder_ids", "in", ancestor_ids)], limit=1, order="id"
                    )
            doc.approval_rule_id = rule

    @api.depends("content_markdown", "content_type")
    def _compute_content_markdown_html(self):
        for doc in self:
            if doc.content_type == "markdown":
                doc.content_markdown_html = self._render_markdown(doc.content_markdown)
            else:
                doc.content_markdown_html = False

    @api.depends("attachment_id", "attachment_id.datas")
    def _compute_file_content(self):
        for doc in self:
            doc.file_content = doc.attachment_id.datas if doc.attachment_id else False

    def _inverse_file_content(self):
        for doc in self:
            if not doc.file_content:
                continue
            name = doc.file_name or (doc.name and doc.name + ".bin") or "file.bin"
            if doc.attachment_id:
                doc.attachment_id.sudo().write({"datas": doc.file_content, "name": name})
            else:
                att = self.env["ir.attachment"].sudo().create({
                    "name": name,
                    "datas": doc.file_content,
                    "res_model": "sanare.document",
                    "res_id": doc.id,
                })
                doc.attachment_id = att.id
            doc._snapshot_version(
                changelog=self.env._("File uploaded"), trigger="upload"
            )

    @api.depends("file_name")
    def _compute_file_extension(self):
        for doc in self:
            name = doc.file_name or ""
            doc.file_extension = name[name.rfind(".") + 1:].lower() if "." in name else ""

    @api.depends_context("uid")
    @api.depends("state", "effective_visibility")
    def _compute_can_publish(self):
        for doc in self:
            doc.can_publish = (
                doc._user_can_write()
                and doc.state == "approved"
                and doc.effective_visibility == "public"
            )

    @api.depends_context("lang")
    def _compute_website_url(self):
        for doc in self:
            doc.website_url = "/documents/%s" % doc.id

    @api.depends_context("uid")
    @api.depends(
        "state", "content_type", "approval_request_id",
        "approval_request_id.line_ids.status", "approval_request_id.line_ids.approver_ids",
    )
    def _compute_workflow_buttons(self):
        for doc in self:
            is_mgr = self.env.user.has_group("sanare_dms.group_dms_manager")
            doc.can_submit = (
                doc.content_type != "folder"
                and doc.state in ("draft", "rejected")
                and doc._user_can_write()
            )
            can_decide = False
            if doc.state == "to_approve" and doc.approval_request_id:
                line = doc.approval_request_id._current_line()
                can_decide = bool(line) and (is_mgr or self.env.user in line.approver_ids)
            doc.can_approve = can_decide
            doc.can_reject = can_decide

    # ==================================================================
    # Helpers
    # ==================================================================
    def _user_can_write(self):
        self.ensure_one()
        user = self.env.user
        return bool(
            user.has_group("sanare_dms.group_dms_manager")
            or user == self.owner_id
            or (self.create_uid and user == self.create_uid)
            or user in self.allowed_write_user_ids
        )

    def _latest_version(self):
        self.ensure_one()
        return self.env["sanare.document.version"].sudo().search(
            [("document_id", "=", self.id)], order="version_number desc", limit=1
        )

    def _ensure_content(self):
        self.ensure_one()
        if self.content_type in HTML_TYPES and not (self.content_html or "").strip():
            raise UserError(self.env._("Add HTML content before submitting for approval."))
        if self.content_type == "markdown" and not (self.content_markdown or "").strip():
            raise UserError(self.env._("Add Markdown content before submitting for approval."))
        if self.content_type == "onlyoffice" and not self.attachment_id:
            raise UserError(self.env._("Create or upload the office file before submitting."))

    def _snapshot_version(self, changelog=False, trigger="manual", author=None):
        Version = self.env["sanare.document.version"].sudo()
        author = author or self.env.user
        for doc in self:
            if doc.content_type == "folder":
                continue
            latest = doc._latest_version()
            vals = {
                "document_id": doc.id,
                "author_id": author.id,
                "changelog": changelog or self.env._("Edited"),
            }
            changed = True
            snap_source = None
            if doc.content_type in HTML_TYPES:
                changed = not (latest and (latest.content_html or "") == (doc.content_html or ""))
                vals["content_html"] = doc.content_html
            elif doc.content_type == "markdown":
                changed = not (
                    latest and (latest.content_markdown or "") == (doc.content_markdown or "")
                )
                vals["content_markdown"] = doc.content_markdown
            elif doc.content_type == "onlyoffice":
                if not doc.attachment_id:
                    changed = False
                elif latest and latest.checksum and latest.checksum == doc.attachment_id.checksum:
                    changed = False
                else:
                    snap_source = doc.attachment_id
                    vals["checksum"] = doc.attachment_id.checksum
                    vals["file_size"] = doc.attachment_id.file_size
            if not changed:
                continue
            vals["version_number"] = doc.version_number + 1
            version = Version.create(vals)
            if snap_source:
                snap = snap_source.sudo().copy({
                    "res_model": "sanare.document.version",
                    "res_id": version.id,
                    "name": doc.file_name or snap_source.name,
                })
                version.attachment_id = snap.id
            doc_vals = {"version_number": vals["version_number"]}
            if trigger not in ("submit", "approval") and doc.state in (
                "approved", "to_approve", "rejected",
            ):
                doc_vals["state"] = "draft"
                if doc.state == "to_approve" and doc.approval_request_id:
                    doc.approval_request_id.sudo().write({"state": "cancelled"})
                    doc._clear_approval_activities()
            doc.with_context(dms_skip_version=True).write(doc_vals)

    # -- markdown rendering ------------------------------------------
    @api.model
    def render_markdown_text(self, text):
        """RPC helper for the ``sanare_markdown`` field widget preview."""
        return self._render_markdown(text)

    @api.model
    def _render_markdown(self, text):
        text = text or ""
        try:
            import markdown as _md

            raw = _md.markdown(
                text,
                extensions=["fenced_code", "tables", "toc", "nl2br", "sane_lists"],
            )
        except Exception:
            raw = self._basic_markdown(text)
        return html_sanitize(raw)

    @api.model
    def _basic_markdown(self, text):
        lines = (text or "").replace("\r\n", "\n").split("\n")
        out = []
        list_stack = []
        para = []
        in_code = False
        code_buf = []

        def close_lists():
            while list_stack:
                out.append("</%s>" % list_stack.pop())

        def flush_para():
            if para:
                out.append("<p>" + "<br/>".join(para) + "</p>")
                para.clear()

        def inline(s):
            s = str(escape(s))
            s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
            s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
            s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
            s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", r'<img alt="\1" src="\2"/>', s)
            s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
            return s

        for raw in lines:
            if raw.strip().startswith("```"):
                if in_code:
                    out.append(
                        "<pre><code>" + str(escape("\n".join(code_buf))) + "</code></pre>"
                    )
                    code_buf = []
                    in_code = False
                else:
                    flush_para()
                    close_lists()
                    in_code = True
                continue
            if in_code:
                code_buf.append(raw)
                continue
            s = raw.strip()
            if not s:
                flush_para()
                close_lists()
                continue
            m = re.match(r"^(#{1,6})\s+(.*)$", s)
            if m:
                flush_para()
                close_lists()
                lvl = len(m.group(1))
                out.append("<h%d>%s</h%d>" % (lvl, inline(m.group(2)), lvl))
                continue
            if re.match(r"^(-{3,}|\*{3,}|_{3,})$", s):
                flush_para()
                close_lists()
                out.append("<hr/>")
                continue
            if s.startswith(">"):
                flush_para()
                close_lists()
                out.append("<blockquote>" + inline(s[1:].strip()) + "</blockquote>")
                continue
            m = re.match(r"^([-*+])\s+(.*)$", s)
            if m:
                flush_para()
                if not list_stack or list_stack[-1] != "ul":
                    close_lists()
                    out.append("<ul>")
                    list_stack.append("ul")
                out.append("<li>" + inline(m.group(2)) + "</li>")
                continue
            m = re.match(r"^(\d+)[.)]\s+(.*)$", s)
            if m:
                flush_para()
                if not list_stack or list_stack[-1] != "ol":
                    close_lists()
                    out.append("<ol>")
                    list_stack.append("ol")
                out.append("<li>" + inline(m.group(2)) + "</li>")
                continue
            para.append(inline(s))
        if in_code:
            out.append("<pre><code>" + str(escape("\n".join(code_buf))) + "</code></pre>")
        flush_para()
        close_lists()
        return "".join(out)

    # ==================================================================
    # CRUD
    # ==================================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("content_type") == "folder":
                vals.update(content_html=False, content_markdown=False)
        docs = super().create(vals_list)
        for doc in docs:
            if doc.content_type != "folder" and not doc.version_ids:
                doc._snapshot_version(
                    changelog=self.env._("Created"), trigger="submit"
                )
        return docs

    def write(self, vals):
        if vals.get("website_published") or vals.get("is_published"):
            for doc in self:
                if not (doc.state == "approved" and doc.effective_visibility == "public"):
                    raise UserError(
                        self.env._(
                            "Only approved documents with Public visibility can be "
                            "published to the website."
                        )
                    )
        if "content_type" in vals:
            for doc in self:
                if doc.version_number and vals["content_type"] != doc.content_type:
                    raise UserError(
                        self.env._("The content type cannot be changed once a document has content.")
                    )
        touching_content = bool({"content_html", "content_markdown"} & set(vals))
        res = super().write(vals)
        if touching_content and not self.env.context.get("dms_skip_version"):
            for doc in self:
                if doc.content_type in HTML_TYPES or doc.content_type == "markdown":
                    doc._snapshot_version(
                        changelog=self.env._("Content edited"), trigger="edit"
                    )
        return res

    def copy_data(self, default=None):
        default = dict(default or {})
        vals_list = super().copy_data(default=default)
        for doc, vals in zip(self, vals_list):
            vals.setdefault("name", self.env._("%s (copy)", doc.name))
            vals.update(
                state="draft",
                version_number=0,
                approved_version_id=False,
                approval_request_id=False,
                is_published=False,
                attachment_id=False,
                # A copy is a real working document, not another template -
                # true whether the copy came from the regular Paste feature
                # or from browser_create_from_template picking a template as
                # its starting point.
                is_template=False,
            )
        return vals_list

    # ==================================================================
    # Workflow actions
    # ==================================================================
    def _schedule_approval_activities(self, users):
        self.ensure_one()
        self._clear_approval_activities()
        for user in users:
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=self.env._("Document approval requested"),
                note=self.env._("Please review and approve “%s”.", self.name),
                user_id=user.id,
            )

    def _clear_approval_activities(self):
        self.activity_unlink(["mail.mail_activity_data_todo"])

    def action_submit(self):
        for doc in self:
            if doc.content_type == "folder":
                raise UserError(self.env._("Folders do not require approval."))
            if doc.state not in ("draft", "rejected"):
                raise UserError(
                    self.env._("Only draft or rejected documents can be submitted.")
                )
            doc._ensure_content()
            doc._snapshot_version(
                changelog=self.env._("Submitted for approval"), trigger="submit"
            )
            req = self.env["sanare.document.approval.request"].sudo().create({
                "document_id": doc.id,
                "rule_id": doc.approval_rule_id.id or False,
                "version_number": doc.version_number,
                "submitted_by": self.env.user.id,
            })
            req._build_lines()
            doc.with_context(dms_skip_version=True).write({
                "state": "to_approve",
                "approval_request_id": req.id,
            })
            req._activate_next_step()
            doc.message_post(body=self.env._("Submitted for approval."))
        return True

    def action_approve(self):
        self.ensure_one()
        if self.state != "to_approve" or not self.approval_request_id:
            raise UserError(self.env._("This document is not awaiting approval."))
        req = self.approval_request_id.sudo()
        line = req._current_line()
        if not line:
            raise UserError(self.env._("There is no pending approval step."))
        is_mgr = self.env.user.has_group("sanare_dms.group_dms_manager")
        if not is_mgr and not line._is_approver(self.env.user):
            raise UserError(
                self.env._("You are not an approver for the current step.")
            )
        if is_mgr and not line._is_approver(self.env.user):
            line.write({
                "status": "approved",
                "decided_by": self.env.user.id,
                "decided_on": fields.Datetime.now(),
            })
            closed = True
        else:
            closed = line._register_decision(self.env.user, "approved")
        self.message_post(body=self.env._("Step approved by %s.", self.env.user.name))
        if closed and all(l.status == "approved" for l in req.line_ids):
            approved_ver = self.version_ids.filtered(
                lambda v: v.version_number == req.version_number
            )[:1]
            req.state = "approved"
            self.with_context(dms_skip_version=True).write({
                "state": "approved",
                "approved_version_id": approved_ver.id or False,
            })
            self._clear_approval_activities()
            self.message_post(
                body=self.env._("Document approved — revision v%s.", req.version_number)
            )
        elif closed:
            req._activate_next_step()
        return True

    def action_reject(self):
        self.ensure_one()
        if self.state != "to_approve":
            raise UserError(self.env._("This document is not awaiting approval."))
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Reject Document"),
            "res_model": "sanare.document.reject.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_document_id": self.id},
        }

    def _apply_rejection(self, reason):
        self.ensure_one()
        req = self.approval_request_id.sudo()
        if req:
            line = req._current_line()
            if line:
                line._register_decision(self.env.user, "rejected", comment=reason)
            req.write({"state": "rejected", "reject_reason": reason})
        self.with_context(dms_skip_version=True).write({"state": "rejected"})
        self._clear_approval_activities()
        self.message_post(
            body=self.env._(
                "Rejected by %(user)s: %(reason)s",
                user=self.env.user.name,
                reason=reason or self.env._("(no reason given)"),
            )
        )

    def action_reset_to_draft(self):
        for doc in self:
            if doc.approval_request_id and doc.approval_request_id.state == "pending":
                doc.approval_request_id.sudo().write({"state": "cancelled"})
            doc._clear_approval_activities()
            doc.with_context(dms_skip_version=True).write({"state": "draft"})
        return True

    # ==================================================================
    # Navigation actions
    # ==================================================================
    def action_open_versions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Versions of %s", self.name),
            "res_model": "sanare.document.version",
            "view_mode": "list,form",
            "domain": [("document_id", "=", self.id)],
            "context": {"default_document_id": self.id},
        }

    def action_open_children(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.complete_name,
            "res_model": "sanare.document",
            "view_mode": "list,kanban,form",
            "domain": [("parent_id", "=", self.id)],
            "context": {
                "default_parent_id": self.id,
                "default_visibility_inherited": True,
            },
        }

    def action_open_website(self):
        self.ensure_one()
        return self.env["website"].get_client_action(self.website_url)

    def _is_publicly_visible(self):
        """The single authoritative "is this document visible to an
        anonymous website visitor" check - shared by the public website
        controller's own gate and by _resolve_embedded_refs(public_only=True)
        so an embedded document is held to exactly the same bar as the page
        embedding it, not a looser one (see _resolve_embedded_refs)."""
        self.ensure_one()
        return (
            self.is_published
            and self.state == "approved"
            and self.effective_visibility == "public"
        )

    def _resolve_embedded_refs(self, html_content, public_only=False, _seen=None):
        """Expand every "Embed Document" marker in ``html_content`` into the
        referenced document's own (recursively resolved) content.

        The marker (see EmbeddedDocRefPlugin/embedded_doc_ref.xml) is an
        empty `<div data-embedded="sanareDocRef" data-embedded-props='{"..."}
        '>` - the *client-side* editor component fetches and fills it in
        live on every mount, but that never happens outside the browser, so
        the stored field itself never contains the actual embedded content.
        Anything rendered server-side (print, download, the public website
        page) needs this method first, or embeds render as nothing.

        public_only=True is for the public website route specifically: that
        route runs everything sudo()'d (anonymous visitors have no ir.rule
        grants at all), so without an extra check here a private or draft
        document embedded inside an otherwise-public one would leak its
        content to anonymous visitors. Backend callers (print, download)
        don't need it - they run unsudo'd, so normal ir.rule access already
        gates each embedded target exactly like opening it directly would
        (same pattern as get_embedded_content).

        _seen accumulates document ids across the recursion so a document
        that transitively embeds itself renders empty at the repeat instead
        of recursing forever.
        """
        self.ensure_one()
        if not html_content or "data-embedded" not in html_content:
            return html_content or ""
        seen = _seen or set()
        if self.id in seen:
            return ""
        seen = seen | {self.id}
        root = lxml.html.fromstring("<div>%s</div>" % html_content)
        for marker in root.xpath('//div[@data-embedded="sanareDocRef"]'):
            replacement_html = self.env._(
                "<p><em>[Referenced document unavailable]</em></p>"
            )
            try:
                props = json.loads(marker.get("data-embedded-props") or "{}")
                target = self.browse(int(props["documentId"])).exists()
            except (ValueError, TypeError, KeyError):
                target = self.browse()
            if target and target.content_type in HTML_TYPES and target.id not in seen:
                if not public_only or target._is_publicly_visible():
                    replacement_html = target._resolve_embedded_refs(
                        target.content_html or "", public_only=public_only, _seen=seen
                    )
            replacement = lxml.html.fromstring("<div>%s</div>" % replacement_html)
            marker.getparent().replace(marker, replacement)
        # The email-send block is an editing tool, not content: drop it from
        # anything rendered server-side (print, download, website, the email
        # body itself). The text the author wrote around it renders normally.
        for marker in root.xpath('//div[@data-embedded="sanareEmailSend"]'):
            marker.getparent().remove(marker)
        # The live OWL view can't render server-side (no JS in wkhtmltopdf) -
        # re-run the captured query and emit a static table instead. Public
        # website renders get the note only (no data to anonymous visitors).
        for marker in root.xpath('//div[@data-embedded="sanareView"]'):
            try:
                props = json.loads(marker.get("data-embedded-props") or "{}")
            except (ValueError, TypeError):
                props = {}
            html = self._render_view_block(props, public_only=public_only)
            repl = lxml.html.fromstring("<div>%s</div>" % html)
            marker.getparent().replace(marker, repl)
        # Markup, not a plain str: t-out/t-field auto-escape a plain string
        # (same as doc.content_html would render as literal "&lt;p&gt;..."
        # text instead of real HTML if this weren't marked safe) - lxml's
        # tostring() only ever returns a plain str, so the safe-marking has
        # to be redone here explicitly.
        return Markup((root.text or "") + "".join(
            lxml.html.tostring(child, encoding="unicode") for child in root
        ))

    # ------------------------------------------------------------------
    # Server-side render of a "sanareView" block (print / download)
    # ------------------------------------------------------------------
    _VIEW_BLOCK_ROW_LIMIT = 200

    @api.model
    def _view_block_note(self, model):
        return "<p><em>%s</em></p>" % escape(
            self.env._("[Embedded view: %s]", model or "?"))

    @api.model
    def _view_block_fields(self, model, view_id):
        """Visible column field names + their {name: label} from the target
        model's list view arch. Literal invisible/column_invisible columns
        and non-stored/relational-heavy fields are skipped."""
        arch = self.env[model].get_view(view_id or False, "list")["arch"]
        node = lxml.etree.fromstring(arch)
        names, order = [], node.get("default_order") or ""
        for f in node.xpath(".//field"):
            name = f.get("name")
            if (not name or name in names
                    or f.get("column_invisible") in ("1", "True", "true")
                    or f.get("invisible") in ("1", "True", "true")):
                continue
            names.append(name)
        meta = self.env[model].fields_get(
            names, ["string", "type", "selection", "currency_field"])
        # Drop x2many columns - a count is rarely what a printout wants.
        names = [n for n in names
                 if meta.get(n, {}).get("type") not in ("one2many", "many2many")]
        return names, meta, order

    def _view_block_cell(self, value, info):
        ftype = info.get("type")
        if value in (False, None, ""):
            return ""
        if ftype == "many2one":
            return value[1] if isinstance(value, (list, tuple)) and len(value) > 1 else ""
        if ftype == "selection":
            return dict(info.get("selection") or []).get(value, value)
        if ftype == "boolean":
            return "✓" if value else ""
        if ftype == "date":
            try:
                return format_date(self.env, value)
            except Exception:
                return str(value)
        if ftype == "datetime":
            try:
                return format_datetime(self.env, value)
            except Exception:
                return str(value)
        if ftype in ("float", "monetary"):
            try:
                return "{:,.2f}".format(value)
            except Exception:
                return str(value)
        if ftype == "integer":
            try:
                return "{:,}".format(value)
            except Exception:
                return str(value)
        return str(value)

    @staticmethod
    def _grp_label(value):
        if isinstance(value, (list, tuple)) and len(value) > 1:
            return str(value[1])
        if value in (False, None):
            return "—"
        return str(value)

    @staticmethod
    def _num(value):
        try:
            f = float(value or 0)
        except (TypeError, ValueError):
            return str(value or "")
        return "{:,.0f}".format(f) if f == int(f) else "{:,.2f}".format(f)

    def _read_group_rows(self, Model, domain, fields, groupby):
        """read_group across Odoo versions -> list of plain dicts keyed by
        the groupby specs and the raw field names."""
        if hasattr(Model, "read_group"):
            try:
                return Model.read_group(domain, fields, groupby, lazy=False)
            except (AttributeError, TypeError):
                pass
        # Odoo 18/19: formatted_read_group(domain, groupby, aggregates)
        aggs = ["__count"] + ["%s:sum" % f for f in fields if f != "__count"]
        raw = Model.formatted_read_group(domain, groupby, aggs)
        out = []
        for g in raw:
            row = dict(g)
            for f in fields:
                if f != "__count" and "%s:sum" % f in row:
                    row[f] = row.pop("%s:sum" % f)
            out.append(row)
        return out

    _VIEW_BLOCK_WRAP = (
        "<div class='o_dms_view_block' style='margin:8px 0'>"
        "<p style='font-weight:bold;margin:0 0 4px'>%s</p>%s</div>"
    )

    def _render_view_block(self, props, public_only=False):
        """Re-run a captured view descriptor as static HTML for print /
        download: a table for a list, a matrix for a pivot, an inline SVG
        for a graph. Falls back to a plain note when it can't (public
        website render, no supported view, no access, unknown model)."""
        model = (props or {}).get("resModel") or ""
        if public_only or not model or model not in self.env:
            return self._view_block_note(model)
        views = props.get("views") or []
        view_types = [v[1] for v in views if isinstance(v, (list, tuple)) and len(v) > 1]
        vt = props.get("viewType")
        context = {k: v for k, v in (props.get("context") or {}).items()
                   if not k.startswith("default_") and k not in (
                       "active_id", "active_ids", "active_model", "params")}
        domain = props.get("domain") or []
        title = escape(props.get("title") or model)
        try:
            Model = self.env[model].with_context(**context)
            # A graph/pivot template renders as a chart/matrix or, if its
            # group-by config wasn't captured (older descriptor), the note -
            # never a raw record list.
            def _vid(t):
                return next((v[0] for v in views
                             if isinstance(v, (list, tuple)) and v[1] == t), False)
            if vt == "graph":
                inner = self._render_graph_block(
                    Model, domain, props.get("graph") or {}, _vid("graph"))
            elif vt == "pivot":
                inner = self._render_pivot_block(
                    Model, domain, props.get("pivot") or {}, _vid("pivot"))
            elif vt == "list" or "list" in view_types:
                list_view_id = next(
                    (v[0] for v in views if isinstance(v, (list, tuple)) and v[1] == "list"),
                    False)
                inner = self._render_list_block(Model, model, domain, list_view_id)
            else:
                return self._view_block_note(model)
        except Exception:  # noqa: BLE001 - any failure degrades to the note
            return self._view_block_note(model)
        if not inner:
            return self._view_block_note(model)
        return self._VIEW_BLOCK_WRAP % (title, inner)

    def _render_list_block(self, Model, model, domain, list_view_id):
        names, meta, order = self._view_block_fields(model, list_view_id)
        if not names:
            return ""
        total = Model.search_count(domain)
        rows = Model.search_read(
            domain, names, limit=self._VIEW_BLOCK_ROW_LIMIT, order=order or None)
        cell = "border:1px solid #d0d0d0;padding:3px 7px;text-align:left;vertical-align:top"
        head = "".join(
            "<th style='%s;background:#f3f3f3;font-weight:bold'>%s</th>"
            % (cell, escape(meta.get(n, {}).get("string") or n)) for n in names)
        body = "".join(
            "<tr>%s</tr>" % "".join(
                "<td style='%s'>%s</td>"
                % (cell, escape(self._view_block_cell(r.get(n), meta.get(n, {}))))
                for n in names)
            for r in rows)
        more = ""
        if total > len(rows):
            more = ("<p style='color:#666;font-size:11px;margin:3px 0 0'>%s</p>"
                    % escape(self.env._("Showing %(shown)s of %(total)s records.",
                                        shown=len(rows), total=total)))
        return ("<table style='border-collapse:collapse;width:100%%;font-size:12px'>"
                "<thead><tr>%s</tr></thead><tbody>%s</tbody></table>%s") % (head, body, more)

    def _render_pivot_block(self, Model, domain, cfg, view_id=False):
        """First row group-by x optional first col group-by, all active
        measures. Deeper nesting is flattened to the first level."""
        rows_gb = (cfg.get("rowGroupBys") or [])[:1]
        cols_gb = (cfg.get("colGroupBys") or [])[:1]
        measures = [m for m in (cfg.get("measures") or []) if m]
        if not rows_gb and not cols_gb:
            arch = self._arch_dims(Model._name, view_id, "pivot")
            rows_gb, cols_gb = arch["row"][:1], arch["col"][:1]
            if arch["measure"] and not measures:
                measures = [arch["measure"]]
        measures = measures or ["__count"]
        if not rows_gb and not cols_gb:
            return ""  # no dimensions -> note
        mlabels = self._view_block_measure_labels(Model._name, measures)
        groupby = rows_gb + cols_gb
        agg_fields = [m for m in measures if m != "__count"]
        groups = self._read_group_rows(Model, domain, agg_fields, groupby) if groupby \
            else [{}]
        cell = "border:1px solid #d0d0d0;padding:3px 7px;text-align:right"
        rk = rows_gb[0] if rows_gb else None
        ck = cols_gb[0] if cols_gb else None

        def mval(g, m):
            return g.get("__count", 0) if m == "__count" else (g.get(m) or 0)

        col_keys = []
        matrix = {}
        row_order = []
        for g in groups:
            rl = self._grp_label(g.get(rk)) if rk else self.env._("Total")
            cl = self._grp_label(g.get(ck)) if ck else ""
            if rl not in matrix:
                matrix[rl] = {}
                row_order.append(rl)
            if cl not in col_keys:
                col_keys.append(cl)
            matrix[rl][cl] = {m: mval(g, m) for m in measures}

        head_cells = ["<th style='%s;text-align:left;background:#f3f3f3'>%s</th>"
                      % (cell, escape(self._grp_label(rk) if rk else ""))]
        for cl in col_keys:
            for m in measures:
                lbl = (escape(cl) + " · " if cl else "") + escape(mlabels[m])
                head_cells.append("<th style='%s;background:#f3f3f3'>%s</th>" % (cell, lbl))
        body_rows = []
        totals = {(cl, m): 0.0 for cl in col_keys for m in measures}
        for rl in row_order:
            tds = ["<td style='%s;text-align:left'>%s</td>" % (cell, escape(rl))]
            for cl in col_keys:
                for m in measures:
                    v = matrix[rl].get(cl, {}).get(m, 0) or 0
                    totals[(cl, m)] += float(v or 0)
                    tds.append("<td style='%s'>%s</td>" % (cell, escape(self._num(v))))
            body_rows.append("<tr>%s</tr>" % "".join(tds))
        tot_tds = ["<td style='%s;text-align:left;font-weight:bold'>%s</td>"
                   % (cell, escape(self.env._("Total")))]
        for cl in col_keys:
            for m in measures:
                tot_tds.append("<td style='%s;font-weight:bold'>%s</td>"
                               % (cell, escape(self._num(totals[(cl, m)]))))
        body_rows.append("<tr>%s</tr>" % "".join(tot_tds))
        return ("<table style='border-collapse:collapse;width:100%%;font-size:12px'>"
                "<thead><tr>%s</tr></thead><tbody>%s</tbody></table>") % (
                    "".join(head_cells), "".join(body_rows))

    def _arch_dims(self, model, view_id, view_type):
        """Default row / col group-bys and measure from a graph or pivot
        view arch (<field type="row|col|measure" interval="..."/>). Used as
        the fallback when the client capture didn't include them (a global
        cog-menu item can't reach the graph/pivot view model)."""
        try:
            arch = self.env[model].get_view(view_id or False, view_type)["arch"]
            node = lxml.etree.fromstring(arch)
        except Exception:
            return {"row": [], "col": [], "measure": None, "mode": None}
        row, col, measure = [], [], None
        for f in node.xpath(".//field"):
            name = f.get("name")
            if not name:
                continue
            interval = f.get("interval")
            spec = "%s:%s" % (name, interval) if interval else name
            t = f.get("type")
            if t == "measure":
                measure = name
            elif t == "col":
                col.append(spec)
            elif t == "row":
                row.append(spec)
            elif view_type == "graph" and not t:
                # In a graph arch a <field> with no type is a row dimension.
                row.append(spec)
        return {"row": row, "col": col, "measure": measure,
                "mode": node.get("type")}

    def _view_block_measure_labels(self, model, measures):
        out = {}
        real = [m for m in measures if m != "__count"]
        meta = self.env[model].fields_get(real, ["string"]) if real else {}
        for m in measures:
            out[m] = self.env._("Count") if m == "__count" else (
                meta.get(m, {}).get("string") or m)
        return out

    def _render_graph_block(self, Model, domain, cfg, view_id=False):
        """A pure HTML/CSS horizontal bar chart - divs with inline
        width/background. No SVG / data-URI (they don't survive the report
        HTML pipeline). bar/line/pie all render as bars; pie shows shares."""
        gb = (cfg.get("groupBy") or [])[:1]
        measure = cfg.get("measure")
        mode = cfg.get("mode")
        if not gb or not measure or not mode:
            arch = self._arch_dims(Model._name, view_id, "graph")
            gb = gb or arch["row"][:1]
            measure = measure or arch["measure"]
            mode = mode or arch["mode"]
        measure = measure or "__count"
        mode = (mode or "bar").lower()
        if not gb:
            return ""
        agg_fields = [] if measure == "__count" else [measure]
        groups = self._read_group_rows(Model, domain, agg_fields, gb)
        pairs = []
        for g in groups:
            label = self._grp_label(g.get(gb[0]))
            val = g.get("__count", 0) if measure == "__count" else (g.get(measure) or 0)
            try:
                pairs.append((label, float(val or 0)))
            except (TypeError, ValueError):
                continue
        pairs = pairs[:30]
        if not pairs:
            return ""
        total = sum(v for _, v in pairs) or 1
        maxv = max((v for _, v in pairs), default=0) or 1
        rows = []
        for label, v in pairs:
            pct_of_max = 100.0 * v / maxv
            disp = (escape("%.0f%%" % (100.0 * v / total)) if mode == "pie"
                    else escape(self._num(v)))
            rows.append(
                "<tr>"
                "<td style='padding:1px 6px;font-size:11px;white-space:nowrap;"
                "text-align:right;width:1%%'>%s</td>"
                "<td style='padding:1px 6px;width:70%%'>"
                "<span style='display:inline-block;height:11px;background:#3465a4;"
                "width:%.1f%%'></span></td>"
                "<td style='padding:1px 6px;font-size:11px;white-space:nowrap'>%s</td>"
                "</tr>" % (escape(label[:32]), max(pct_of_max, 0.5), disp))
        return ("<table style='border-collapse:collapse;width:100%%;"
                "table-layout:fixed'><tbody>%s</tbody></table>") % "".join(rows)

    @api.constrains("parent_id")
    def _check_parent_recursion(self):
        if self._has_cycle():
            raise ValidationError(
                self.env._("A document cannot be placed inside itself.")
            )

    @api.constrains("content_type", "parent_id", "child_ids")
    def _check_container_integrity(self):
        """Non-container types (Office Documents, Knowledge Pages - anything
        outside CONTAINER_TYPES) can't act as a container in either
        direction: they can't have children, and they can't be filed under
        another non-container document. On top of that, Office Documents
        specifically can only go directly inside a folder - not even under
        an html/markdown container - since they don't participate in the
        "children form one printed document" composition those container
        types support; Knowledge Pages have no such extra restriction, since
        their composition is via in-content includes, not the tree.

        Checked from both sides deliberately, not just the "obvious" one:
        creating a new child under an existing non-container document writes
        only the *child's* own parent_id, and @api.constrains re-validates
        the records actually written to, not other records an inverse
        one2many happens to affect - so a parent-side-only check
        (doc.child_ids) would silently miss that case. Checking
        doc.parent_id.content_type from the child's own perspective always
        fires, since the child is always in the written recordset whenever
        its parent_id changes. The child_ids-based check stays too, since it
        still catches the reverse direction: an existing folder holding
        children gets retyped into a non-container type (content_type is a
        trigger field, so the folder itself re-validates and does a fresh,
        live read of its own child_ids)."""
        for doc in self:
            if doc.content_type not in CONTAINER_TYPES and doc.child_ids:
                raise ValidationError(
                    self.env._("This document type cannot contain other documents.")
                )
            if doc.parent_id and doc.parent_id.content_type not in CONTAINER_TYPES:
                raise ValidationError(
                    self.env._(
                        "This document can only be placed directly inside a "
                        "folder, HTML page, or Markdown page."
                    )
                )
            if (
                doc.content_type == "onlyoffice"
                and doc.parent_id
                and doc.parent_id.content_type != "folder"
            ):
                raise ValidationError(
                    self.env._(
                        "An Office Document can only be placed directly inside "
                        "a folder, not inside another document."
                    )
                )

    # ==================================================================
    # Tree browser  (client action "sanare_dms.browser")
    # ==================================================================
    @api.model
    def browser_tree_children(self, parent_id=False):
        """All direct children - folders *and* documents - under
        ``parent_id`` (falsy = top level), for the nested tree pane.
        Contrast with browser_contents, which returns the same set with
        richer columns for the flat detail table. A container (folder, html
        or markdown - see CONTAINER_TYPES) can have has_children True;
        Office Documents are always leaves. Article items (article_item=True)
        are omitted - they only live in their parent's detail pane."""
        recs = self.search(
            [("parent_id", "=", parent_id or False), ("article_item", "=", False)],
            order="is_folder desc, sequence, name",
        )
        data = self._read_group(
            [("parent_id", "in", recs.filtered("can_have_children").ids),
             ("article_item", "=", False)],
            ["parent_id"], ["__count"],
        )
        counts = {parent.id: count for parent, count in data}
        return [
            {
                "id": r.id,
                "name": r.name,
                "is_folder": r.is_folder,
                "can_have_children": r.can_have_children,
                "content_type": r.content_type,
                "has_children": bool(counts.get(r.id)) if r.can_have_children else False,
            }
            for r in recs
        ]

    @api.model
    def browser_templates(self):
        """Flat list of every is_template=True document the caller can see,
        for the browser's separate Templates section. Flat, not a tree - a
        template keeps its real parent_id (it's a flag, not a move, see
        is_template's help text), so a hierarchical view here would just
        reproduce the main tree with most of it filtered out; a flat list
        of "here are your templates" is what the feature is actually for."""
        recs = self.search([("is_template", "=", True)], order="name")
        ctypes = dict(CONTENT_TYPES)
        return [
            {
                "id": r.id,
                "name": r.name,
                "is_folder": r.is_folder,
                "content_type": r.content_type,
                "content_type_label": ctypes.get(r.content_type),
                "parent_name": r.parent_id.display_name,
            }
            for r in recs
        ]

    def browser_set_template(self, is_template):
        """Toggle the Template flag - the drop handler when something is
        dragged onto the Templates section calls this (with is_template=True)
        instead of browser_move, since dropping there tags, it doesn't
        reparent. Also reachable from a per-row icon for anyone who doesn't
        think to drag."""
        self.write({"is_template": is_template})
        return True

    @api.model
    def browser_create_from_template(self, template_id, parent_id=False, name=False):
        """New from Template: a real copy of ``template_id`` (not a live
        reference - see get_template_content for that distinction), filed
        under ``parent_id``. copy_data() already resets state/version/
        approval/publish/is_template on any copy, so this is pure wiring,
        same shape as browser_paste."""
        template = self.browse(template_id).exists()
        if not template:
            raise UserError(self.env._("This template no longer exists."))
        target = self.browse(parent_id) if parent_id else self.browse()
        if target and not target.can_have_children:
            raise UserError(
                self.env._("Items can only be created inside a folder, HTML page or "
                            "Markdown page.")
            )
        vals = {"parent_id": target.id if target else False}
        if name and name.strip():
            vals["name"] = name.strip()
        return template.copy(vals).id

    @api.model
    def get_template_content(self, document_id):
        """RPC target for the "/template" editor command - a one-time paste
        of the template's content as regular, independently-editable HTML
        (no ongoing link to the template). Returns the RAW content_html:
        embedded blocks (email-send, view, doc-ref) are pasted verbatim so
        they keep working in the new document - the editor re-hydrates them
        on insert, same as a "New from Template" copy. Only documents
        flagged is_template are offered."""
        doc = self.browse(int(document_id)).exists()
        if not doc:
            return {"error": "not_found"}
        if not doc.is_template or doc.content_type not in HTML_TYPES:
            return {"error": "unsupported_type"}
        return {"name": doc.name, "content_html": doc.content_html or ""}

    @api.model
    def _browser_breadcrumb(self, parent_id):
        crumbs = []
        rec = self.browse(parent_id) if parent_id else self.browse()
        guard = 0
        while rec and guard < 100:
            crumbs.insert(0, {"id": rec.id, "name": rec.name})
            rec = rec.parent_id
            guard += 1
        return crumbs

    @api.model
    def get_embedded_content(self, document_id):
        """RPC target for the "embed another document" editor plugin.

        Deliberately runs under the requesting user's own env (no sudo):
        accessing `content_html` below goes through the normal read path,
        so the same ir.rule visibility rules that gate opening the document
        directly also gate embedding it - a Private document embedded by
        someone who can't see it raises AccessError same as it would if
        they tried to open it, rather than leaking content through the
        embed.
        """
        doc = self.browse(int(document_id)).exists()
        if not doc:
            return {"error": "not_found"}
        if doc.content_type not in HTML_TYPES:
            return {"error": "unsupported_type"}
        return {
            "name": doc.name,
            # Resolved, not raw: if this document itself embeds another one,
            # that nested embed's marker would otherwise render as an empty
            # div here - this simple read-only card doesn't re-scan its own
            # t-out'd HTML for embedded components the way the full editor
            # does, so without resolving here a chain more than one level
            # deep would silently stop at the first hop.
            "content_html": doc._resolve_embedded_refs(doc.content_html or ""),
            "write_date": fields.Datetime.to_string(doc.write_date),
        }

    @api.model
    def browser_contents(self, parent_id=False):
        recs = self.search(
            [("parent_id", "=", parent_id or False)], order="is_folder desc, sequence, name"
        )
        container = self.browse(parent_id) if parent_id else self.browse()
        ctypes = dict(CONTENT_TYPES)
        states = dict(self._fields["state"].selection)
        return {
            "breadcrumb": self._browser_breadcrumb(parent_id),
            "container_content_type": container.content_type if container else False,
            "records": [
                {
                    "id": r.id,
                    "name": r.name,
                    "is_folder": r.is_folder,
                    "can_have_children": r.can_have_children,
                    "content_type": r.content_type,
                    "content_type_label": ctypes.get(r.content_type),
                    "state": r.state,
                    "state_label": states.get(r.state),
                    "owner": r.owner_id.display_name,
                    "visibility": r.effective_visibility,
                    "child_count": r.child_count if r.can_have_children else 0,
                    "updated": fields.Datetime.to_string(r.write_date),
                    "sequence": r.sequence,
                    "display_in_print": r.display_in_print,
                    "is_published": r.is_published,
                    "can_publish": r.can_publish,
                    "is_template": r.is_template,
                    "article_item": r.article_item,
                }
                for r in recs
            ],
        }

    @api.model
    def browser_detail(self, document_id):
        """Lightweight probe for the browser's detail pane. A non-folder
        document gets the inline form editor (mounted client-side); a
        folder has no detail and the pane keeps showing its contents list."""
        doc = self.browse(int(document_id)).exists()
        if not doc:
            return False
        return {"id": doc.id, "name": doc.name, "is_folder": doc.is_folder}

    @api.model
    def save_view_block_state(self, document_id, props):
        """Persist the zoom / height / viewType a user set on a
        data-embedded="sanareView" block, without a full form save -
        updates the marker's data-embedded-props in place. No version
        snapshot (dms_skip_version)."""
        doc = self.browse(int(document_id)).exists()
        if not doc or VIEW_BLOCK_MARKER not in (doc.content_html or ""):
            return False
        keep = {k: v for k, v in (props or {}).items()
                if k in ("zoom", "height", "viewType")}
        if not keep:
            return False
        root = lxml.html.fromstring("<div>%s</div>" % doc.content_html)
        for marker in root.xpath('//div[@data-embedded="sanareView"]'):
            try:
                cur = json.loads(marker.get("data-embedded-props") or "{}")
            except (ValueError, TypeError):
                cur = {}
            cur.update(keep)
            marker.set("data-embedded-props", json.dumps(cur))
        new_html = (root.text or "") + "".join(
            lxml.html.tostring(c, encoding="unicode") for c in root)
        doc.with_context(dms_skip_version=True).write({"content_html": new_html})
        return True

    @api.model
    def browser_move(self, doc_ids, target_parent_id):
        docs = self.browse(doc_ids).exists()
        if not docs:
            return False
        target = self.browse(target_parent_id) if target_parent_id else self.browse()
        if target:
            if not target.can_have_children:
                raise UserError(
                    self.env._("Items can only be moved into a folder, HTML page or "
                                "Markdown page.")
                )
            if target.content_type != "folder" and any(
                d.content_type == "onlyoffice" for d in docs
            ):
                raise UserError(
                    self.env._("Office Documents can only be moved directly into "
                                "a folder.")
                )
            if target in docs:
                raise UserError(self.env._("You cannot move a folder into itself."))
        docs.write({"parent_id": target.id if target else False})
        return True

    @api.model
    def browser_reorder(self, doc_ids_in_order, parent_id=False):
        """Rewrite sequence (10, 20, 30...) for a sibling group under
        ``parent_id`` (falsy = top level), in the order given. Only ids that
        are actually children of ``parent_id`` are touched - a stray id from
        a stale client-side list is silently ignored rather than letting it
        move a document into a sibling group it doesn't belong to."""
        docs = self.browse(doc_ids_in_order).exists().filtered(
            lambda d: d.parent_id.id == (parent_id or False)
        )
        for i, doc in enumerate(docs):
            doc.sequence = (i + 1) * 10
        return True

    @api.model
    def browser_paste(self, doc_ids, target_parent_id):
        """Copy each of ``doc_ids`` into ``target_parent_id`` (falsy = top
        level). All the reset-on-duplicate logic (state back to draft,
        version/approval/publish cleared) already lives in copy_data - this
        is pure wiring. Folders bring their whole subtree with them for
        free: Odoo's default copy() already cascades one2many child_ids."""
        docs = self.browse(doc_ids).exists()
        if not docs:
            return []
        target = self.browse(target_parent_id) if target_parent_id else self.browse()
        if target:
            if not target.can_have_children:
                raise UserError(
                    self.env._("Items can only be pasted into a folder, HTML page or "
                                "Markdown page.")
                )
            if target.content_type != "folder" and any(
                d.content_type == "onlyoffice" for d in docs
            ):
                raise UserError(
                    self.env._("Office Documents can only be pasted directly into "
                                "a folder.")
                )
        pasted = docs.copy({"parent_id": target.id if target else False})
        return pasted.ids

    def browser_toggle_publish(self):
        """Flip is_published for a single document from a browser row
        action. write()'s existing guard (state=approved + visibility=public)
        already protects this - no new validation needed here."""
        self.ensure_one()
        self.write({"is_published": not self.is_published})
        return self.is_published

    # ==================================================================
    # Email-send block  (data-embedded="sanareEmailSend", lives in the body)
    # ==================================================================
    def _email_body_html(self):
        """This document's content, embedded refs expanded (same pipeline as
        print/website - which also strips the email block itself), wrapped
        in an explicit light ground so a mail client doesn't inherit the
        editor's dark theme."""
        self.ensure_one()
        inner = Markup(self._resolve_embedded_refs(self.content_html or ""))
        return Markup(
            '<div style="background:#ffffff;color:#111827;'
            'font-family:Arial,Helvetica,sans-serif;font-size:14px;'
            'line-height:1.5;padding:16px">{}</div>'
        ).format(inner)

    @api.model
    def send_email_block(self, document_id, payload):
        """RPC for the Send button of a sanareEmailSend block. payload:
        {subject, to_ids, cc_ids, bcc_ids}. The body is taken from the saved
        document, not the client. Returns {state, date, error, message_id,
        mail_id}, or {error:'no_email', partners_without_email, partner_ids}
        when a recipient has no address.
        """
        doc = self.browse(int(document_id)).exists()
        if not doc:
            raise UserError(self.env._("This document no longer exists."))
        if EMAIL_BLOCK_MARKER not in (doc.content_html or ""):
            raise UserError(self.env._("This document has no email block."))

        Partner = self.env["res.partner"]
        to = Partner.browse(payload.get("to_ids") or []).exists()
        cc = Partner.browse(payload.get("cc_ids") or []).exists()
        bcc = Partner.browse(payload.get("bcc_ids") or []).exists()
        if not to:
            raise UserError(self.env._("Add at least one “To” recipient."))
        subject = (payload.get("subject") or "").strip()
        if not subject:
            raise UserError(self.env._("Add a subject."))
        missing = (to | cc | bcc).filtered(lambda p: not p.email)
        if missing:
            return {
                "error": "no_email",
                "partners_without_email": missing.mapped("display_name"),
                "partner_ids": missing.ids,
            }

        body = doc._email_body_html()
        Mail = self.env["mail.mail"].sudo()
        common = {
            "subject": subject,
            "body_html": body,
            "email_from": self.env.user.email_formatted
            or self.env.company.email_formatted,
            "author_id": self.env.user.partner_id.id,
            "auto_delete": False,
        }
        primary = Mail.create(dict(
            common,
            email_to=", ".join(to.mapped("email_formatted")),
            email_cc=", ".join(cc.mapped("email_formatted")) or False,
        ))
        # mail.mail has no Bcc field - one blind copy per Bcc partner.
        bcc_mails = Mail.browse()
        for partner in bcc:
            bcc_mails |= Mail.create(dict(common, email_to=partner.email_formatted))

        mails = primary | bcc_mails
        mails.send(raise_exception=False)
        mails.invalidate_recordset(["state", "failure_reason"])

        states = mails.mapped("state")
        error = ""
        if any(s == "exception" for s in states):
            outcome = "failed"
            error = next(
                (m.failure_reason for m in mails if m.state == "exception" and m.failure_reason),
                self.env._("unknown error"),
            )
        elif all(s == "sent" for s in states):
            outcome = "sent"
        else:
            outcome = "sent"  # queued (no mail server, e.g. tests)
            error = self.env._("Queued for delivery.")

        cc_suffix = self.env._(" (cc: %s)", ", ".join(cc.mapped("name"))) if cc else ""
        doc.message_post(body=self.env._(
            "Email “%(subject)s” sent to %(to)s%(cc)s — %(outcome)s",
            subject=subject, to=", ".join(to.mapped("name")), cc=cc_suffix,
            outcome=(self.env._("Sent") if outcome == "sent" else self.env._("Failed")),
        ))
        return {
            "state": outcome,
            "date": fields.Datetime.to_string(fields.Datetime.now()),
            "error": error,
            "message_id": primary.mail_message_id.message_id or "",
            "mail_id": primary.id,
        }

    # ==================================================================
    # "Save as View Template"  (data-embedded="sanareView", lives in the body)
    # ==================================================================
    @api.model
    def _view_templates_folder(self):
        folder = self.env.ref(
            "sanare_dms.doc_folder_view_templates", raise_if_not_found=False
        )
        if not folder:
            folder = self.search(
                [("name", "=", "View Templates"), ("content_type", "=", "folder")],
                limit=1,
            ) or self.create({
                "name": "View Templates",
                "content_type": "folder",
                "visibility": "public",
                "visibility_inherited": False,
            })
        return folder

    @api.model
    def create_view_template(self, descriptor):
        """RPC for the "Save as View Template" cog-menu action. `descriptor`
        is a self-contained {resModel, viewType, views, domain, context,
        searchState, title}. Creates a knowledge_html template document
        under the "View Templates" folder whose body carries a
        data-embedded="sanareView" marker, and returns an action opening it.
        """
        if not descriptor or not descriptor.get("resModel"):
            raise UserError(self.env._("Nothing to capture from this view."))
        title = descriptor.get("title") or descriptor["resModel"]
        name = self.env._("%s (view template)", title)
        folder = self._view_templates_folder()
        marker = (
            '<div data-embedded="sanareView" data-oe-protected="true" '
            'contenteditable="false" class="o-contenteditable-false" '
            'data-embedded-props="%s"></div>'
        ) % escape(json.dumps(descriptor))
        doc = self.create({
            "name": name,
            "content_type": "knowledge_html",
            "is_template": True,
            "parent_id": folder.id,
            "visibility": "public",
            "visibility_inherited": False,
            "content_html": "<h1>%s</h1>%s<p><br/></p>" % (escape(name), marker),
        })
        return {
            "action": {
                "type": "ir.actions.act_window",
                "res_model": "sanare.document",
                "res_id": doc.id,
                "views": [[False, "form"]],
                "target": "current",
            }
        }

    def action_report(self):
        """Print entry point for the custom browser (which has no generic
        framework print menu of its own) - mirrors the action_print pattern
        used for eos_dashboard's board records."""
        self.ensure_one()
        return self.env.ref("sanare_dms.action_report_dms_document").report_action(self)

    def action_download(self):
        """Download entry point for both the classic form and the custom
        browser - a plain URL action so the browser handles the file
        download natively rather than round-tripping through the ORM."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "/sanare_dms/document/%s/download" % self.id,
            "target": "self",
        }

    def _print_content(self, use_approved):
        """This node's own html/markdown content for the given
        approved/live choice - the same version-resolution _download_response
        used for a single document, factored out so _iter_display_subtree
        can reuse it per node when bundling a parent with its children.
        html/knowledge_html content is resolved (any embedded document
        references expanded in place) before it's returned - the raw stored
        value only ever contains an empty marker div, never actual content
        (see _resolve_embedded_refs)."""
        self.ensure_one()
        version = self.approved_version_id if use_approved else False
        if self.content_type in HTML_TYPES:
            raw = (version.content_html if version else False) or self.content_html or ""
            return self._resolve_embedded_refs(raw)
        if self.content_type == "markdown":
            return (version.content_markdown if version else False) or self.content_markdown or ""
        return ""

    def _iter_display_subtree(self, level=1):
        """Yield (doc, level) for self then every display_in_print-flagged
        descendant, in tree order - the same traversal `report_document_body`
        uses for recursive print, reused here so downloading a parent
        document bundles its children exactly like printing does."""
        self.ensure_one()
        yield self, level
        for child in self.child_ids.filtered(lambda c: c.display_in_print).sorted(
            key=lambda c: c.sequence
        ):
            yield from child._iter_display_subtree(level + 1)

    def _download_response(self, use_approved=False):
        """Shared by the public /documents/<id>/download route (existing,
        refactored to call this) and the new authenticated backend one - same
        content-type branching either way, only the *version* selected
        differs. Public downloads always serve the approved/published
        snapshot (``use_approved=True``, matching the site's existing
        behaviour); the authenticated route serves whatever is currently on
        the record, draft or not, since that's what "download this document
        I'm working on" means.

        html/markdown downloads bundle every display_in_print-flagged
        descendant into the one file, same set and order as recursive print -
        a parent with nested pages downloads as one combined document, not
        just its own top-level content."""
        from odoo import http
        from odoo.http import request

        self.ensure_one()
        version = self.approved_version_id if use_approved else False
        if self.content_type == "onlyoffice":
            attachment = (version.attachment_id if version else False) or self.attachment_id
            if not attachment:
                raise UserError(self.env._("This document has no file to download."))
            return self.env["ir.binary"]._get_stream_from(
                attachment, "raw"
            ).get_response(as_attachment=True)
        if self.content_type in HTML_TYPES:
            parts = [
                node._print_content(use_approved)
                for node, level in self._iter_display_subtree()
            ]
            data = "\n<hr/>\n".join(parts).encode()
            filename = "%s.html" % self.name
        elif self.content_type == "markdown":
            parts = [
                "%s %s\n\n%s" % ("#" * min(level, 4), node.name, node._print_content(use_approved))
                for node, level in self._iter_display_subtree()
            ]
            data = "\n\n---\n\n".join(parts).encode()
            filename = "%s.md" % self.name
        else:
            raise UserError(self.env._("Folders can't be downloaded directly."))
        return request.make_response(
            data,
            headers=[
                ("Content-Type", "application/octet-stream"),
                ("Content-Disposition", http.content_disposition(filename)),
            ],
        )

    @api.model
    def browser_create_folder(self, name, parent_id=False):
        folder = self.create(
            {
                "name": (name or "").strip() or self.env._("New Folder"),
                "content_type": "folder",
                "parent_id": parent_id or False,
            }
        )
        return folder.id
