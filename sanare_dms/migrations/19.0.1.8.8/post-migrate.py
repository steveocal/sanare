def migrate(cr, version):
    """Earlier email-feature attempts (19.0.1.8.5-8.6, since reverted) left
    an "Email Templates" folder + "Introduction Email" document on live
    databases. data/dms_data.xml is noupdate=1, so reloading it won't give
    the existing "Introduction Email" the new sanareEmailSend body block.
    Drop both so the data load recreates them fresh.
    """
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in ("sanare_dms.doc_intro_email", "sanare_dms.doc_folder_email_templates"):
        rec = env.ref(xmlid, raise_if_not_found=False)
        if rec:
            rec.unlink()
