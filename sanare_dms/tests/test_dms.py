from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, HttpCase, tagged, new_test_user

from odoo.addons.mail.tests.common import MailCommon


@tagged("post_install", "-at_install")
class TestSanareDms(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(
            cls.env, "dms_mgr", groups="sanare_dms.group_dms_manager"
        )
        cls.user = new_test_user(
            cls.env, "dms_usr", groups="sanare_dms.group_dms_user"
        )
        cls.Doc = cls.env["sanare.document"]

    @staticmethod
    def _embed_marker(target_id, name="Embedded"):
        """The exact marker EmbeddedDocRefPlugin stores in content_html -
        see embedded_doc_ref.xml's EmbeddedDocRefBlueprint."""
        return (
            '<div data-embedded="sanareDocRef" '
            'data-embedded-props=\'{"documentId": %d, "documentName": "%s"}\'></div>'
        ) % (target_id, name)

    @staticmethod
    def _render_report_html(report, res_ids):
        """report._render_qweb_html() (not a bare ir.qweb._render) - layouts
        like web.internal_layout/external_layout need context helpers
        (context_timestamp, is_html_empty, ...) only the real report-
        rendering pipeline injects. May return bytes depending on Odoo
        version/report_type, so normalize to str."""
        html, _report_type = report._render_qweb_html(report.report_name, res_ids)
        return html.decode() if isinstance(html, bytes) else html

    def test_hierarchy_and_visibility_inheritance(self):
        folder = self.Doc.create(
            {"name": "F", "content_type": "folder", "visibility": "public"}
        )
        child = self.Doc.create(
            {"name": "C", "content_type": "markdown", "parent_id": folder.id,
             "content_markdown": "# hi"}
        )
        self.assertEqual(child.effective_visibility, "public")
        folder.visibility = "private"
        child.invalidate_recordset()
        self.assertEqual(child.effective_visibility, "private")

    def test_versioning_on_edit_and_restore(self):
        doc = self.Doc.create(
            {"name": "V", "content_type": "markdown", "content_markdown": "one"}
        )
        self.assertEqual(doc.version_number, 1)
        doc.content_markdown = "one two"
        self.assertEqual(doc.version_number, 2)
        # identical write does not create a version
        doc.write({"content_markdown": "one two"})
        self.assertEqual(doc.version_number, 2)
        v1 = doc.version_ids.filtered(lambda v: v.version_number == 1)
        v1.action_restore()
        self.assertEqual(doc.version_number, 3)
        self.assertEqual(doc.content_markdown, "one")

    def test_approval_flow_manager_fallback(self):
        doc = self.Doc.with_user(self.user).create(
            {"name": "A", "content_type": "html", "content_html": "<p>x</p>"}
        )
        doc.action_submit()
        self.assertEqual(doc.state, "to_approve")
        with self.assertRaises(UserError):
            doc.with_user(self.user).action_approve()
        doc.with_user(self.manager).action_approve()
        self.assertEqual(doc.state, "approved")
        self.assertTrue(doc.approved_version_id)

    def test_edit_after_approval_reverts_to_draft_but_keeps_published(self):
        doc = self.Doc.create(
            {"name": "P", "content_type": "markdown", "visibility": "public",
             "visibility_inherited": False, "content_markdown": "v1"}
        )
        doc.action_submit()
        doc.with_user(self.manager).action_approve()
        published = doc.approved_version_id
        doc.write({"website_published": True})
        self.assertTrue(doc.is_published)
        doc.content_markdown = "v2"
        self.assertEqual(doc.state, "draft")
        self.assertEqual(doc.approved_version_id, published)

    def test_publish_requires_approved_public(self):
        doc = self.Doc.create(
            {"name": "NP", "content_type": "html", "content_html": "<p>x</p>"}
        )
        with self.assertRaises(UserError):
            doc.write({"website_published": True})

    def test_markdown_renderer_fallback(self):
        html = self.Doc._basic_markdown("# T\n\n**b** `c`\n\n- x\n- y\n")
        self.assertIn("<h1>T</h1>", html)
        self.assertIn("<strong>b</strong>", html)
        self.assertIn("<li>x</li>", html)

    def test_browser_tree_contents_and_move(self):
        root = self.Doc.create({"name": "Root", "content_type": "folder"})
        a = self.Doc.create({"name": "A", "content_type": "folder", "parent_id": root.id})
        b = self.Doc.create({"name": "B", "content_type": "folder", "parent_id": root.id})
        doc = self.Doc.create(
            {"name": "d1", "content_type": "markdown", "parent_id": a.id,
             "content_markdown": "x"}
        )
        # tree
        top = self.Doc.browser_tree_children(False)
        self.assertIn("Root", [f["name"] for f in top])
        kids = self.Doc.browser_tree_children(root.id)
        self.assertEqual({f["name"] for f in kids}, {"A", "B"})
        self.assertTrue(all(f["is_folder"] for f in kids))
        # d1 (a document, not a folder) now shows up as a leaf under A
        a_children = self.Doc.browser_tree_children(a.id)
        self.assertEqual([f["name"] for f in a_children], ["d1"])
        self.assertFalse(a_children[0]["is_folder"])
        self.assertFalse(a_children[0]["has_children"])
        # contents + breadcrumb
        res = self.Doc.browser_contents(a.id)
        self.assertEqual([r["name"] for r in res["records"]], ["d1"])
        self.assertEqual([c["name"] for c in res["breadcrumb"]], ["Root", "A"])
        # move doc A -> B
        self.Doc.browser_move([doc.id], b.id)
        self.assertEqual(doc.parent_id, b)
        # move to root (unfile)
        self.Doc.browser_move([doc.id], False)
        self.assertFalse(doc.parent_id)
        # cannot move a folder into itself / its descendant
        with self.assertRaises(Exception):
            self.Doc.browser_move([root.id], a.id)
        # html/markdown documents are containers too now - dropping onto one
        # succeeds
        self.Doc.browser_move([b.id], doc.id)
        self.assertEqual(b.parent_id, doc)
        # ...but an Office Document is never a valid drop target
        office = self.Doc.create({"name": "office1", "content_type": "onlyoffice"})
        with self.assertRaises(UserError):
            self.Doc.browser_move([b.id], office.id)

    def test_html_markdown_containers(self):
        page = self.Doc.create(
            {"name": "Page", "content_type": "html", "content_html": "<p>x</p>"}
        )
        sub = self.Doc.create(
            {"name": "Sub", "content_type": "markdown", "parent_id": page.id,
             "content_markdown": "y"}
        )
        self.assertTrue(page.can_have_children)
        self.assertFalse(page.is_folder)
        top = self.Doc.browser_tree_children(False)
        entry = next(f for f in top if f["id"] == page.id)
        self.assertTrue(entry["can_have_children"])
        self.assertTrue(entry["has_children"])
        kids = self.Doc.browser_tree_children(page.id)
        self.assertEqual([f["name"] for f in kids], ["Sub"])
        # browser_paste can target an html/markdown container too
        target = self.Doc.create({"name": "Target", "content_type": "markdown",
                                   "content_markdown": "z"})
        pasted_ids = self.Doc.browser_paste([sub.id], target.id)
        self.assertEqual(self.Doc.browse(pasted_ids).parent_id, target)

    def test_onlyoffice_cannot_contain_or_be_contained(self):
        office = self.Doc.create({"name": "Office", "content_type": "onlyoffice"})
        page = self.Doc.create(
            {"name": "Page", "content_type": "html", "content_html": "<p>x</p>"}
        )
        folder = self.Doc.create({"name": "F", "content_type": "folder"})
        # an Office Document cannot have children
        with self.assertRaises(ValidationError):
            self.Doc.create({"name": "child", "content_type": "html",
                              "content_html": "<p>x</p>", "parent_id": office.id})
        # an Office Document cannot be nested inside another document
        with self.assertRaises(ValidationError):
            office.parent_id = page.id
        # ...but directly inside a folder is fine
        office.parent_id = folder.id
        self.assertEqual(office.parent_id, folder)
        # the browser RPCs give a friendly UserError for the same cases
        with self.assertRaises(UserError):
            self.Doc.browser_move([office.id], page.id)
        with self.assertRaises(UserError):
            self.Doc.browser_paste([office.id], page.id)

    def test_knowledge_html_shares_html_versioning_and_approval(self):
        doc = self.Doc.create(
            {"name": "K", "content_type": "knowledge_html", "content_html": "<p>one</p>"}
        )
        self.assertEqual(doc.version_number, 1)
        doc.content_html = "<p>two</p>"
        self.assertEqual(doc.version_number, 2)
        doc.action_submit()
        self.assertEqual(doc.state, "to_approve")
        doc.with_user(self.manager).action_approve()
        self.assertEqual(doc.state, "approved")

    def test_knowledge_html_cannot_have_children_or_be_parented_under_onlyoffice(self):
        office = self.Doc.create({"name": "Office2", "content_type": "onlyoffice"})
        kb = self.Doc.create(
            {"name": "KB", "content_type": "knowledge_html", "content_html": "<p>x</p>"}
        )
        with self.assertRaises(ValidationError):
            self.Doc.create({"name": "child", "content_type": "html",
                              "content_html": "<p>x</p>", "parent_id": kb.id})
        with self.assertRaises(ValidationError):
            kb.parent_id = office.id
        # ...but a folder (or an html/markdown page) is fine, same as html
        folder = self.Doc.create({"name": "F2", "content_type": "folder"})
        kb.parent_id = folder.id
        self.assertEqual(kb.parent_id, folder)

    def test_resolve_embedded_refs_expands_simple_embed(self):
        target = self.Doc.create(
            {"name": "Target", "content_type": "html", "content_html": "<p>target-marker</p>"}
        )
        host = self.Doc.create(
            {"name": "Host", "content_type": "knowledge_html",
             "content_html": self._embed_marker(target.id)}
        )
        resolved = host._resolve_embedded_refs(host.content_html)
        self.assertIn("target-marker", resolved)

    def test_resolve_embedded_refs_expands_nested_chain(self):
        # A embeds B, B embeds C - resolving A should pull in C's content
        # too, not stop after one hop.
        c = self.Doc.create(
            {"name": "C", "content_type": "html", "content_html": "<p>c-marker</p>"}
        )
        b = self.Doc.create(
            {"name": "B", "content_type": "knowledge_html",
             "content_html": self._embed_marker(c.id)}
        )
        a = self.Doc.create(
            {"name": "A", "content_type": "knowledge_html",
             "content_html": self._embed_marker(b.id)}
        )
        resolved = a._resolve_embedded_refs(a.content_html)
        self.assertIn("c-marker", resolved)

    def test_resolve_embedded_refs_cycle_guard(self):
        a = self.Doc.create(
            {"name": "SelfA", "content_type": "knowledge_html",
             "content_html": "<p>placeholder</p>"}
        )
        a.content_html = self._embed_marker(a.id) + "<p>after-marker</p>"
        # must not hang or crash on a document that embeds itself
        resolved = a._resolve_embedded_refs(a.content_html)
        self.assertIn("after-marker", resolved)

    def test_get_embedded_content_resolves_nested_embed(self):
        c = self.Doc.create(
            {"name": "C2", "content_type": "html", "content_html": "<p>c2-marker</p>"}
        )
        b = self.Doc.create(
            {"name": "B2", "content_type": "knowledge_html",
             "content_html": self._embed_marker(c.id)}
        )
        data = self.Doc.get_embedded_content(b.id)
        self.assertIn("c2-marker", data["content_html"])

    def test_templates_browse_flag_and_create_from_template(self):
        folder = self.Doc.create({"name": "TplFolder", "content_type": "folder"})
        tpl = self.Doc.create(
            {"name": "Tpl", "content_type": "html", "parent_id": folder.id,
             "content_html": "<p>tpl-marker</p>"}
        )
        other = self.Doc.create(
            {"name": "NotATemplate", "content_type": "html", "content_html": "<p>x</p>"}
        )
        # not a template until flagged - scoped to this doc's own id, not a
        # global emptiness check: browser_templates() reflects whatever else
        # is already flagged in the database (e.g. a real user's templates),
        # which this test must not assume away.
        self.assertNotIn(tpl.id, [t["id"] for t in self.Doc.browser_templates()])

        self.Doc.browse(tpl.id).browser_set_template(True)
        self.assertTrue(tpl.is_template)
        templates = self.Doc.browser_templates()
        matches = [t for t in templates if t["id"] == tpl.id]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["parent_name"], "TplFolder")
        # flagging doesn't move it - still filed where it always was
        self.assertEqual(tpl.parent_id, folder)

        target = self.Doc.create({"name": "Target", "content_type": "folder"})
        new_id = self.Doc.browser_create_from_template(tpl.id, target.id)
        new_doc = self.Doc.browse(new_id)
        self.assertEqual(new_doc.parent_id, target)
        self.assertEqual(new_doc.content_html, tpl.content_html)
        # the copy is a real document, not itself a template
        self.assertFalse(new_doc.is_template)
        # the original is untouched
        self.assertTrue(tpl.is_template)

        # get_template_content only serves documents actually flagged
        data = self.Doc.get_template_content(other.id)
        self.assertEqual(data.get("error"), "unsupported_type")
        data = self.Doc.get_template_content(tpl.id)
        self.assertIn("tpl-marker", data["content_html"])

        self.Doc.browse(tpl.id).browser_set_template(False)
        self.assertNotIn(tpl.id, [t["id"] for t in self.Doc.browser_templates()])

    def test_public_page_does_not_leak_private_embedded_content(self):
        private_doc = self.Doc.create(
            {"name": "PrivateSecret", "content_type": "html",
             "content_html": "<p>secret-marker</p>", "visibility": "private"}
        )
        public_doc = self.Doc.create(
            {"name": "PublicHost", "content_type": "knowledge_html",
             "content_html": self._embed_marker(private_doc.id),
             "visibility": "public", "visibility_inherited": False}
        )
        public_doc.action_submit()
        public_doc.with_user(self.manager).action_approve()
        public_doc.write({"website_published": True})
        resolved = public_doc._resolve_embedded_refs(
            public_doc.content_html, public_only=True
        )
        self.assertNotIn("secret-marker", resolved)

    def test_parent_recursion_blocked(self):
        f1 = self.Doc.create({"name": "f1", "content_type": "folder"})
        f2 = self.Doc.create({"name": "f2", "content_type": "folder", "parent_id": f1.id})
        with self.assertRaises(Exception):
            f1.parent_id = f2.id

    def test_browser_reorder(self):
        folder = self.Doc.create({"name": "ReorderFolder", "content_type": "folder"})
        c1 = self.Doc.create({"name": "c1", "content_type": "folder", "parent_id": folder.id})
        c2 = self.Doc.create({"name": "c2", "content_type": "folder", "parent_id": folder.id})
        c3 = self.Doc.create({"name": "c3", "content_type": "folder", "parent_id": folder.id})
        self.Doc.browser_reorder([c3.id, c1.id, c2.id], folder.id)
        self.assertLess(c3.sequence, c1.sequence)
        self.assertLess(c1.sequence, c2.sequence)
        # a stray id that isn't actually a child of folder is silently
        # ignored - not an error, and it can't smuggle itself into this
        # sibling group or have its own parent/sequence touched
        other = self.Doc.create({"name": "elsewhere", "content_type": "folder"})
        self.Doc.browser_reorder([c2.id, other.id, c1.id], folder.id)
        self.assertFalse(other.parent_id)

    def test_browser_paste_cascades_children(self):
        folder = self.Doc.create({"name": "PasteFolder", "content_type": "folder"})
        self.Doc.create(
            {"name": "child", "content_type": "html", "parent_id": folder.id,
             "content_html": "<p>hi</p>"}
        )
        target = self.Doc.create({"name": "Target", "content_type": "folder"})
        pasted_ids = self.Doc.browser_paste([folder.id], target.id)
        pasted = self.Doc.browse(pasted_ids)
        self.assertEqual(pasted.parent_id, target)
        self.assertEqual(pasted.child_count, 1)
        self.assertEqual(pasted.child_ids.state, "draft")

    def test_recursive_print_respects_display_flag(self):
        folder = self.Doc.create({"name": "PrintFolder", "content_type": "folder"})
        shown = self.Doc.create(
            {"name": "Shown", "content_type": "html", "parent_id": folder.id,
             "content_html": "<p>shown-marker</p>"}
        )
        hidden = self.Doc.create(
            {"name": "Hidden", "content_type": "html", "parent_id": folder.id,
             "content_html": "<p>hidden-marker</p>", "display_in_print": False}
        )
        html = self.env["ir.qweb"]._render(
            "sanare_dms.report_document_body", {"doc": folder}
        )
        self.assertIn("shown-marker", html)
        self.assertNotIn("hidden-marker", html)
        self.assertTrue(shown.display_in_print)
        self.assertFalse(hidden.display_in_print)

    def test_print_combines_children_flow_with_parent_footer(self):
        folder = self.Doc.create({"name": "PrintFolder", "content_type": "folder"})
        self.Doc.create(
            {"name": "Shown", "content_type": "html", "parent_id": folder.id,
             "content_html": "<p>shown-marker</p>"}
        )
        html = self.env["ir.qweb"]._render("sanare_dms.report_document", {"docs": folder})
        # parent + child render into a single wkhtmltopdf "body" (one
        # .article), not one per node, and nothing forces a page break
        # between them - they should print as one combined, flowing document.
        self.assertEqual(html.count('class="article"'), 1)
        self.assertNotIn("page-break-before", html)
        # the footer (a genuine class="footer" div, extracted into
        # wkhtmltopdf's real footer pass - see report/dms_report.xml) names
        # the printed (parent) document, appears once, and never a nested
        # child's
        self.assertEqual(html.count('class="footer"'), 1)
        footer_start = html.index('class="footer"')
        footer_html = html[footer_start:footer_start + 300]
        self.assertIn("PrintFolder", footer_html)
        self.assertNotIn("Shown", footer_html)

    def test_report_layout_branches(self):
        doc = self.Doc.create(
            {"name": "LayoutDoc", "content_type": "html", "content_html": "<p>layout-marker</p>"}
        )
        report = self.env.ref("sanare_dms.action_report_dms_document")
        none_html = self._render_report_html(report, doc.ids)
        self.assertIn("layout-marker", none_html)
        self.assertIn('class="footer"', none_html)
        self.assertNotIn("o_report_layout_standard", none_html)

        doc.report_layout = "internal"
        internal_html = self._render_report_html(report, doc.ids)
        self.assertIn("layout-marker", internal_html)
        self.assertIn('class="header"', internal_html)
        self.assertIn('class="footer"', internal_html)
        self.assertIn("LayoutDoc", internal_html)

        doc.report_layout = "external"
        external_html = self._render_report_html(report, doc.ids)
        self.assertIn("layout-marker", external_html)
        # Which concrete theme (standard/bubble/boxed/...) is just whatever
        # this company is configured with - assert on the generic
        # external_layout marker, not a specific theme name.
        self.assertIn("o_report_layout_", external_html)
        # The name belongs only in the footer, never as a body heading -
        # layout_document_title is deliberately never set (see
        # report_document's comment), so external_layout's own <h2>
        # renders empty.
        h2_start = external_html.index("<h2")
        h2_end = external_html.index("</h2>", h2_start)
        self.assertNotIn("LayoutDoc", external_html[h2_start:h2_end])
        # 'external' reuses Odoo's own single footer div (display_name_in_
        # footer=True) instead of adding a second one - see report_document's
        # comment on why exactly one footer div per document matters.
        self.assertEqual(external_html.count('class="footer'), 1)
        footer_start = external_html.index('class="footer')
        self.assertIn("LayoutDoc", external_html[footer_start:footer_start + 500])

    def test_download_bundles_children_like_print(self):
        page = self.Doc.create(
            {"name": "Page", "content_type": "html", "content_html": "<p>parent-marker</p>"}
        )
        shown = self.Doc.create(
            {"name": "Shown", "content_type": "markdown", "parent_id": page.id,
             "content_markdown": "shown-marker"}
        )
        self.Doc.create(
            {"name": "Hidden", "content_type": "html", "parent_id": page.id,
             "content_html": "<p>hidden-marker</p>", "display_in_print": False}
        )
        # same set/order/flag-filtering _iter_display_subtree uses, which
        # _download_response bundles a parent's own file with
        subtree = list(page._iter_display_subtree())
        self.assertEqual([(d.name, level) for d, level in subtree], [("Page", 1), ("Shown", 2)])
        self.assertIn("shown-marker", shown._print_content(False))

    def test_record_rule_hides_private_docs(self):
        self.Doc.create(
            {"name": "secret", "content_type": "html", "owner_id": self.manager.id,
             "content_html": "<p>s</p>", "visibility": "private"}
        )
        found = self.Doc.with_user(self.user).search([("name", "=", "secret")])
        self.assertFalse(found)

    # -- email-send block ---------------------------------------------
    _EMAIL_MARKER = '<div data-embedded="sanareEmailSend" data-embedded-props="{}"></div>'

    def test_send_email_block_requires_marker(self):
        p = self.env["res.partner"].create({"name": "P", "email": "p@example.com"})
        doc = self.Doc.create({
            "name": "Plain", "content_type": "html", "content_html": "<p>hi</p>",
        })
        with self.assertRaises(UserError):
            doc.send_email_block(doc.id, {"subject": "x", "to_ids": p.ids})

    def test_send_email_block_missing_email(self):
        noemail = self.env["res.partner"].create({"name": "No Email Person"})
        doc = self.Doc.create({
            "name": "E", "content_type": "knowledge_html",
            "content_html": self._EMAIL_MARKER + "<p>body</p>",
        })
        before = self.env["mail.mail"].search([])
        res = doc.send_email_block(doc.id, {"subject": "Hi", "to_ids": noemail.ids})
        self.assertEqual(res["error"], "no_email")
        self.assertIn("No Email Person", res["partners_without_email"])
        self.assertFalse(self.env["mail.mail"].search([]) - before)

    def test_email_body_strips_block_and_wraps_light(self):
        doc = self.Doc.create({
            "name": "E", "content_type": "knowledge_html",
            "content_html": self._EMAIL_MARKER + "<p>visible-body</p>",
        })
        body = doc._email_body_html()
        self.assertNotIn("sanareEmailSend", body)
        self.assertIn("visible-body", body)
        self.assertIn("background:#ffffff", body)

    # -- "Save as View Template" ------------------------------------
    def test_create_view_template(self):
        res = self.Doc.create_view_template({
            "resModel": "res.partner", "viewType": "list",
            "views": [[False, "list"], [False, "search"]],
            "domain": [["is_company", "=", True]], "context": {},
            "searchState": None, "title": "Companies",
        })
        doc = self.Doc.browse(res["action"]["res_id"])
        self.assertTrue(doc.exists())
        self.assertEqual(doc.content_type, "knowledge_html")
        self.assertTrue(doc.is_template)
        self.assertEqual(doc.parent_id.name, "View Templates")
        self.assertIn('data-embedded="sanareView"', doc.content_html)
        self.assertIn("res.partner", doc.content_html)
        # a second call reuses the same folder
        res2 = self.Doc.create_view_template({
            "resModel": "crm.lead", "viewType": "kanban", "views": [],
            "domain": [], "context": {}, "title": "Leads",
        })
        self.assertEqual(
            self.Doc.browse(res2["action"]["res_id"]).parent_id, doc.parent_id)

    _PNG_1PX = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAA"
                "fFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

    def test_save_view_block_snapshot(self):
        doc = self.Doc.create({
            "name": "Snap", "content_type": "knowledge_html",
            "content_html": '<div data-embedded="sanareView" data-embedded-props="{}"></div>',
        })
        res = doc.save_view_block_snapshot(doc.id, {"png": self._PNG_1PX, "old_id": False})
        att = self.env["ir.attachment"].browse(res["attachment_id"])
        self.assertTrue(att.exists())
        self.assertEqual((att.res_model, att.res_id), ("sanare.document", doc.id))
        self.assertEqual(att.mimetype, "image/png")
        # replacing unlinks the old one
        res2 = doc.save_view_block_snapshot(
            doc.id, {"png": self._PNG_1PX, "old_id": res["attachment_id"]})
        self.assertFalse(att.exists())
        self.assertNotEqual(res2["attachment_id"], res["attachment_id"])

    def test_view_block_prints_snapshot(self):
        import json
        doc = self.Doc.create({
            "name": "SnapDoc", "content_type": "knowledge_html", "content_html": "<p>x</p>",
        })
        att = self.env["ir.attachment"].create({
            "name": "s.png", "datas": self._PNG_1PX.split(",", 1)[1],
            "mimetype": "image/png", "res_model": "sanare.document", "res_id": doc.id,
        })
        props = json.dumps({
            "resModel": "res.partner", "viewType": "graph",
            "views": [[False, "graph"]], "domain": [], "context": {},
            "title": "Snapped", "snapshot_id": att.id,
        })
        doc.content_html = (
            "<div data-embedded=\"sanareView\" data-embedded-props='%s'></div>"
            "<p>tail</p>" % props)
        rendered = doc._resolve_embedded_refs(doc.content_html)
        self.assertIn("/web/image/%s" % att.id, rendered)
        self.assertNotIn("sanareView", rendered)
        self.assertIn("tail", rendered)
        # public render must not embed the snapshot
        pub = doc._resolve_embedded_refs(doc.content_html, public_only=True)
        self.assertNotIn("/web/image/", pub)

    def test_view_block_no_list_view_falls_back_to_note(self):
        marker = ('<div data-embedded="sanareView" '
                  'data-embedded-props="{&#34;resModel&#34;: &#34;crm.lead&#34;}"></div>')
        doc = self.Doc.create({
            "name": "V", "content_type": "knowledge_html",
            "content_html": marker + "<p>around-marker</p>",
        })
        rendered = doc._resolve_embedded_refs(doc.content_html)
        self.assertNotIn("sanareView", rendered)
        self.assertIn("Embedded view", rendered)
        self.assertIn("around-marker", rendered)

    def test_view_block_renders_list_table(self):
        import json
        self.env["res.partner"].create({"name": "ZZ Table Test Co", "email": "zz@x.com"})
        props = json.dumps({
            "resModel": "res.partner", "viewType": "list",
            "views": [[False, "list"], [False, "search"]],
            "domain": [["name", "=", "ZZ Table Test Co"]],
            "context": {}, "title": "Partners",
        })
        doc = self.Doc.create({
            "name": "VT", "content_type": "knowledge_html",
            "content_html": (
                "<div data-embedded=\"sanareView\" data-embedded-props='%s'></div>"
                "<p>after-block</p>" % props),
        })
        rendered = doc._resolve_embedded_refs(doc.content_html)
        self.assertNotIn("sanareView", rendered)
        self.assertIn("<table", rendered)
        self.assertIn("ZZ Table Test Co", rendered)
        self.assertIn("after-block", rendered)
        # public website render must not leak record data
        pub = doc._resolve_embedded_refs(doc.content_html, public_only=True)
        self.assertNotIn("ZZ Table Test Co", pub)
        self.assertIn("Embedded view", pub)

    def _view_block_doc(self, descriptor):
        import json
        return self.Doc.create({
            "name": "VB", "content_type": "knowledge_html",
            "content_html": (
                "<div data-embedded=\"sanareView\" data-embedded-props='%s'></div>"
                % json.dumps(descriptor)),
        })

    def test_view_block_renders_graph_bars(self):
        P = self.env["res.partner"]
        P.create({"name": "GA", "is_company": True})
        P.create({"name": "GB", "is_company": False})
        doc = self._view_block_doc({
            "resModel": "res.partner", "viewType": "graph",
            "views": [[False, "graph"]], "domain": [], "context": {}, "title": "By type",
            "graph": {"mode": "bar", "measure": "__count", "groupBy": ["is_company"]},
        })
        rendered = doc._resolve_embedded_refs(doc.content_html)
        self.assertNotIn("sanareView", rendered)
        self.assertNotIn("base64", rendered)
        self.assertIn("background:#3465a4", rendered)

    def test_view_block_renders_pivot_matrix(self):
        doc = self._view_block_doc({
            "resModel": "res.partner", "viewType": "pivot",
            "views": [[False, "pivot"]], "domain": [], "context": {}, "title": "P",
            "pivot": {"rowGroupBys": ["is_company"], "colGroupBys": [], "measures": ["__count"]},
        })
        rendered = doc._resolve_embedded_refs(doc.content_html)
        self.assertNotIn("sanareView", rendered)
        self.assertIn("<table", rendered)
        self.assertIn("Total", rendered)


@tagged("post_install", "-at_install")
class TestSanareDmsEmailSend(MailCommon):
    _EMAIL_MARKER = '<div data-embedded="sanareEmailSend" data-embedded-props="{}"></div>'

    def test_send_builds_primary_plus_bcc_copies(self):
        Doc = self.env["sanare.document"]
        P = self.env["res.partner"]
        a = P.create({"name": "Alice", "email": "alice@example.com"})
        b = P.create({"name": "Bob", "email": "bob@example.com"})
        c = P.create({"name": "Cara", "email": "cara@example.com"})
        d = P.create({"name": "Dan", "email": "dan@example.com"})
        doc = Doc.create({
            "name": "Intro", "content_type": "knowledge_html",
            "content_html": self._EMAIL_MARKER + "<p>Hello there</p>",
        })
        before = self.env["mail.mail"].search([])
        with self.mock_mail_gateway():
            res = doc.send_email_block(doc.id, {
                "subject": "Nice to meet you",
                "to_ids": (a | b).ids, "cc_ids": c.ids, "bcc_ids": d.ids,
            })
        self.assertIn(res["state"], ("sent",))
        mails = self.env["mail.mail"].search([]) - before
        self.assertEqual(len(mails), 2)  # To+Cc on one, one blind copy for Bcc
        primary = mails.filtered(lambda m: m.email_cc)
        self.assertEqual(len(primary), 1)
        self.assertIn("alice@example.com", primary.email_to)
        self.assertIn("cara@example.com", primary.email_cc)
        self.assertIn("background:#ffffff", primary.body_html)
        self.assertIn("Hello there", primary.body_html)
        self.assertNotIn("sanareEmailSend", primary.body_html)
        bcc = mails - primary
        self.assertIn("dan@example.com", bcc.email_to)
        self.assertFalse(bcc.email_cc)
        self.assertTrue(doc.message_ids.filtered(lambda m: "sent to" in (m.body or "")))


@tagged("post_install", "-at_install")
class TestSanareDmsWebsite(HttpCase):
    def test_public_document_page(self):
        doc = self.env["sanare.document"].create(
            {"name": "Web Doc", "content_type": "markdown", "visibility": "public",
             "visibility_inherited": False,
             "content_markdown": "# Public\n\nbody **here**\n"}
        )
        admin = self.env.ref("base.user_admin")
        doc.action_submit()
        doc.with_user(admin).action_approve()
        doc.write({"website_published": True})

        res = self.url_open("/documents")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Web Doc", res.text)

        res = self.url_open("/documents/%s" % doc.id)
        self.assertEqual(res.status_code, 200)
        self.assertIn("body <strong>here</strong>", res.text)

        # an unpublished document 404s
        draft = self.env["sanare.document"].create(
            {"name": "Hidden", "content_type": "html", "content_html": "<p>no</p>"}
        )
        res = self.url_open("/documents/%s" % draft.id)
        self.assertEqual(res.status_code, 404)
