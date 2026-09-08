{
    "name": "Sanare Document Management — Sale",
    "version": "19.0.1.0.1",
    "category": "Document Management",
    "author": "Sanare",
    "license": "LGPL-3",
    "summary": "Attach a Sanare document before and/or after a sale order's own "
    "content when printed.",
    "description": "Bridges sanare_dms with sale: two fields on the sale "
    "order, Pre Document and Post Document, referencing sanare.document "
    "records (Web Page or Knowledge Page only). When the order is printed, "
    "each selected document's resolved content (embedded-document references "
    "expanded, same as sanare_dms's own print/download) is rendered "
    "immediately before/after the order's own content - no approval or "
    "publish gating, whatever is selected prints.",
    "depends": ["sanare_dms", "sale"],
    "data": [
        "views/sale_order_views.xml",
        "report/sale_report_templates.xml",
    ],
    "installable": True,
    "auto_install": True,
}
