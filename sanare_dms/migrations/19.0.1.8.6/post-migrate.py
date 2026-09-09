def migrate(cr, version):
    """Email data moved from folder-scoped Properties to real email_* fields
    on sanare.document.

    - Clear the stale properties_definition 19.0.1.8.5 put on the "Email
      Templates" folder (data/dms_data.xml is noupdate=1 and won't).
    - Seed the "Introduction Email" template's email_subject on installs
      that already have the record (noupdate records aren't rewritten on
      upgrade).
    """
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})

    folder = env.ref("sanare_dms.doc_folder_email_templates", raise_if_not_found=False)
    if folder and folder.properties_definition:
        folder.properties_definition = False

    intro = env.ref("sanare_dms.doc_intro_email", raise_if_not_found=False)
    if intro and not intro.email_subject:
        intro.email_subject = "Introduction from Sanare"
