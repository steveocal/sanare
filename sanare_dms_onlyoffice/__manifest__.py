{
    "name": "Sanare Document Management — ONLYOFFICE",
    "version": "19.0.1.0.1",
    "category": "Document Management",
    "author": "Sanare",
    "license": "LGPL-3",
    "summary": "Edit Sanare documents of type 'Office Document' in place with "
    "ONLYOFFICE Docs, with real-time co-editing and automatic versioning.",
    "description": "Bridges sanare_dms with the ONLYOFFICE connector "
    "(onlyoffice_odoo): an Edit in ONLYOFFICE button on office documents that "
    "opens the connector's editor on the document's backing ir.attachment "
    "(permissions come from the sanare.document record rules; concurrent "
    "editors co-author in real time), blank docx/xlsx/pptx creation from the "
    "connector's shipped templates, and a new sanare.document.version snapshot "
    "each time the editor saves back (once per co-editing session).",
    "depends": ["sanare_dms", "onlyoffice_odoo"],
    "data": [
        "views/dms_document_views.xml",
    ],
    "installable": True,
    "auto_install": True,
}
