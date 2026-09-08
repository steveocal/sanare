{
    "name": "Sanare Document Management",
    "version": "19.0.1.4.1",
    "category": "Document Management",
    "author": "Sanare",
    "license": "LGPL-3",
    "summary": "Hierarchical documents with owners, Private/Shared/Public visibility, "
    "version control, a configurable approval workflow, categories, tags, "
    "HTML and Markdown editing, and public website exposure.",
    "description": "A hierarchical document store where every node is a "
    "sanare.document - a folder or a document of one content type: Office "
    "(edited in place with ONLYOFFICE, via sanare_dms_onlyoffice), HTML "
    "(Odoo web editor, code view included) or Markdown (Odoo ACE editor with "
    "live preview). Owner plus Private / Shared / Public visibility with "
    "inheritance, per-document version history with restore, a configurable "
    "multi-step approval workflow, hierarchical categories, tags, and "
    "publishing approved documents to the public website.",
    "depends": ["mail", "html_editor", "website", "portal"],
    "data": [
        "security/dms_groups.xml",
        "security/ir.model.access.csv",
        "security/dms_rules.xml",
        "data/dms_data.xml",
        "wizard/dms_reject_wizard_views.xml",
        "views/dms_category_views.xml",
        "views/dms_tag_views.xml",
        "views/dms_approval_views.xml",
        "views/dms_document_views.xml",
        "views/dms_browser_views.xml",
        "views/dms_menus.xml",
        "report/dms_report.xml",
        "views/dms_portal_templates.xml",
        "views/dms_website_templates.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sanare_dms/static/src/scss/dms.scss",
            "sanare_dms/static/src/markdown_field/markdown_field.scss",
            "sanare_dms/static/src/markdown_field/markdown_field.js",
            "sanare_dms/static/src/markdown_field/markdown_field.xml",
            "sanare_dms/static/src/browser/dms_browser.scss",
            "sanare_dms/static/src/browser/dms_browser.js",
            "sanare_dms/static/src/browser/dms_browser.xml",
            "sanare_dms/static/src/html_field/section_heading_plugin.js",
            "sanare_dms/static/src/html_field/page_break_plugin.js",
            "sanare_dms/static/src/html_field/embedded_doc_ref/embedded_doc_ref.xml",
            "sanare_dms/static/src/html_field/embedded_doc_ref/embedded_doc_ref.js",
            "sanare_dms/static/src/html_field/embedded_doc_ref/embedded_doc_ref_plugin.js",
            "sanare_dms/static/src/html_field/snippet_panel/snippet_panel.scss",
            "sanare_dms/static/src/html_field/snippet_panel/snippet_blocks.js",
            "sanare_dms/static/src/html_field/snippet_panel/snippet_panel.xml",
            "sanare_dms/static/src/html_field/snippet_panel/snippet_panel.js",
            "sanare_dms/static/src/html_field/sanare_html_field.xml",
            "sanare_dms/static/src/html_field/sanare_html_field.js",
        ],
        "web.assets_frontend": [
            "sanare_dms/static/src/scss/dms_frontend.scss",
        ],
    },
    "installable": True,
    "application": True,
    "post_init_hook": "post_init_hook",
}
