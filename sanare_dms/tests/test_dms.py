from odoo.exceptions import UserError
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
        top = self.Doc.browser_folders(False)
        self.assertIn("Root", [f["name"] for f in top])
        kids = self.Doc.browser_folders(root.id)
        self.assertEqual({f["name"] for f in kids}, {"A", "B"})
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
        # cannot drop onto a non-folder
        with self.assertRaises(UserError):
            self.Doc.browser_move([b.id], doc.id)

    def test_parent_recursion_blocked(self):
        f1 = self.Doc.create({"name": "f1", "content_type": "folder"})
        f2 = self.Doc.create({"name": "f2", "content_type": "folder", "parent_id": f1.id})
        with self.assertRaises(Exception):
            f1.parent_id = f2.id

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
