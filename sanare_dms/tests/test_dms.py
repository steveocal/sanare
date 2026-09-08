from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, HttpCase, tagged, new_test_user


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
        # the footer (position:fixed, not wkhtmltopdf's separate header/
        # footer pipeline - see report/dms_report.xml) names the printed
        # (parent) document, appears once, and never a nested child's
        self.assertEqual(html.count("position: fixed"), 1)
        footer_start = html.index("position: fixed")
        footer_html = html[footer_start:footer_start + 300]
        self.assertIn("PrintFolder", footer_html)
        self.assertNotIn("Shown", footer_html)

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
