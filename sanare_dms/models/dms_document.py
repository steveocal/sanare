import re

from markupsafe import escape

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html_sanitize

CONTENT_TYPES = [
    ("folder", "Folder"),
    ("onlyoffice", "Office Document"),
    ("html", "Web Page (HTML)"),
    ("markdown", "Markdown"),
]

VISIBILITY = [
    ("private", "Private"),
    ("shared", "Shared"),
    ("public", "Public"),
]


class SanareDocument(models.Model):
    _name = "sanare.document"
    _description = "Document"
    _inherit = ["mail.thread", "mail.activity.mixin", "website.published.mixin"]
    _parent_store = True
    _parent_name = "parent_id"
    _order = "is_folder desc, name"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)

    # -- hierarchy ---------------------------------------------------------
    parent_id = fields.Many2one(
        "sanare.document", string="Parent", ondelete="cascade", index=True, tracking=True
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("sanare.document", "parent_id", string="Contents")
    child_count = fields.Integer(compute="_compute_child_count")
    complete_name = fields.Char(
        compute="_compute_complete_name", recursive=True, store=True, string="Path"
    )

    # -- type & content --------------------------------------------------
    content_type = fields.Selection(
        CONTENT_TYPES, required=True, default="folder", string="Type"
    )
    is_folder = fields.Boolean(compute="_compute_is_folder", store=True)

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
        if self.content_type == "html" and not (self.content_html or "").strip():
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
            if doc.content_type == "html":
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
                if doc.content_type in ("html", "markdown"):
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

    @api.constrains("parent_id")
    def _check_parent_recursion(self):
        if self._has_cycle():
            raise ValidationError(
                self.env._("A document cannot be placed inside itself.")
            )

    # ==================================================================
    # Tree browser  (client action "sanare_dms.browser")
    # ==================================================================
    @api.model
    def browser_folders(self, parent_id=False):
        """Folders directly under ``parent_id`` (falsy = top level)."""
        folders = self.search(
            [("content_type", "=", "folder"), ("parent_id", "=", parent_id or False)],
            order="name",
        )
        sub = dict(
            self._read_group(
                [("content_type", "=", "folder"), ("parent_id", "in", folders.ids)],
                ["parent_id"],
                ["__count"],
            )
        )
        return [
            {"id": f.id, "name": f.name, "has_subfolders": bool(sub.get(f))}
            for f in folders
        ]

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
    def browser_contents(self, parent_id=False):
        recs = self.search(
            [("parent_id", "=", parent_id or False)], order="is_folder desc, name"
        )
        ctypes = dict(CONTENT_TYPES)
        states = dict(self._fields["state"].selection)
        return {
            "breadcrumb": self._browser_breadcrumb(parent_id),
            "records": [
                {
                    "id": r.id,
                    "name": r.name,
                    "is_folder": r.is_folder,
                    "content_type": r.content_type,
                    "content_type_label": ctypes.get(r.content_type),
                    "state": r.state,
                    "state_label": states.get(r.state),
                    "owner": r.owner_id.display_name,
                    "visibility": r.effective_visibility,
                    "child_count": r.child_count if r.is_folder else 0,
                    "updated": fields.Datetime.to_string(r.write_date),
                }
                for r in recs
            ],
        }

    @api.model
    def browser_move(self, doc_ids, target_parent_id):
        docs = self.browse(doc_ids).exists()
        if not docs:
            return False
        target = self.browse(target_parent_id) if target_parent_id else self.browse()
        if target:
            if target.content_type != "folder":
                raise UserError(self.env._("Items can only be moved into a folder."))
            if target in docs:
                raise UserError(self.env._("You cannot move a folder into itself."))
        docs.write({"parent_id": target.id if target else False})
        return True

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
