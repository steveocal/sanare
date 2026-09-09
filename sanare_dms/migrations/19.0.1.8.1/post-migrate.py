def migrate(cr, version):
    """The 19.0.1.8.0 starter records (Email Templates folder + Introduction
    Email) were seeded with visibility "shared", which - per
    rule_dms_document_user_read - is only readable by the owner and DMS
    managers, so the template never showed up in most users' Templates
    section. Force them to "public" (readable by every internal user). The
    data file is noupdate=1, so this can't be fixed by re-running the data
    load alone.
    """
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in ("sanare_dms.doc_folder_email_templates", "sanare_dms.doc_intro_email"):
        rec = env.ref(xmlid, raise_if_not_found=False)
        if rec and rec.visibility != "public":
            rec.write({"visibility": "public", "visibility_inherited": False})
