from odoo import fields, models

# Only types _resolve_embedded_refs (sanare_dms/models/dms_document.py)
# knows how to render - picking a folder/markdown/onlyoffice document here
# would silently print nothing, so they're excluded from the domain rather
# than left to fail quietly at print time.
DOCUMENT_DOMAIN = [("content_type", "in", ("html", "knowledge_html"))]


class SaleOrder(models.Model):
    _inherit = "sale.order"

    dms_pre_document_id = fields.Many2one(
        "sanare.document", string="Pre Document", domain=DOCUMENT_DOMAIN,
        help="Printed immediately before this order's own content. No "
             "approval or publish gating - whatever is selected prints.",
    )
    dms_post_document_id = fields.Many2one(
        "sanare.document", string="Post Document", domain=DOCUMENT_DOMAIN,
        help="Printed immediately after this order's own content. No "
             "approval or publish gating - whatever is selected prints.",
    )
