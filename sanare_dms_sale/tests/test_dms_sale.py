from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDmsSale(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Doc = cls.env["sanare.document"]
        cls.partner = cls.env["res.partner"].create({"name": "DMS Sale Test Partner"})
        cls.report = cls.env.ref("sale.action_report_saleorder")

    @staticmethod
    def _render_report_html(report, res_ids):
        """report._render_qweb_html() (not a bare ir.qweb._render) -
        web.external_layout needs context helpers (is_html_empty, ...) only
        the real report-rendering pipeline injects. May return bytes
        depending on Odoo version/report_type, so normalize to str."""
        html, _report_type = report._render_qweb_html(report.report_name, res_ids)
        return html.decode() if isinstance(html, bytes) else html

    def test_pre_post_document_render_in_report(self):
        pre = self.Doc.create(
            {"name": "PreDoc", "content_type": "html", "content_html": "<p>pre-marker</p>"}
        )
        post = self.Doc.create(
            {"name": "PostDoc", "content_type": "html", "content_html": "<p>post-marker</p>"}
        )
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "dms_pre_document_id": pre.id,
            "dms_post_document_id": post.id,
        })
        html = self._render_report_html(self.report, order.ids)
        self.assertIn("pre-marker", html)
        self.assertIn("post-marker", html)

    def test_pre_post_document_optional(self):
        # neither set - report still renders fine, no stray empty divs error
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        html = self._render_report_html(self.report, order.ids)
        self.assertNotIn("sanare_dms_pre_document", html)
        self.assertNotIn("sanare_dms_post_document", html)

    def test_field_domain_excludes_non_html_types(self):
        self.assertEqual(
            self.env["sale.order"]._fields["dms_pre_document_id"].domain,
            [("content_type", "in", ("html", "knowledge_html"))],
        )
        self.assertEqual(
            self.env["sale.order"]._fields["dms_post_document_id"].domain,
            [("content_type", "in", ("html", "knowledge_html"))],
        )
