def migrate(cr, version):
    """The 19.0.1.8.x "/Send Email" experiment (now reverted) seeded an
    "Email Templates" folder + "Introduction Email" document via noupdate
    data. Removing the records from the data file does not delete rows that
    were already created on a live database, and that document's body still
    carries a now-orphaned data-embedded="sanareEmailSend" marker. Drop
    both records here so a reverted install is clean.
    """
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in ("sanare_dms.doc_intro_email", "sanare_dms.doc_folder_email_templates"):
        rec = env.ref(xmlid, raise_if_not_found=False)
        if rec:
            rec.unlink()
