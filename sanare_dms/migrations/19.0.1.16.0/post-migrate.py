def migrate(cr, version):
    """Every document must now have a Parent (see _check_parent_required /
    BASE_FOLDER_KEYS in dms_document.py) - the only exceptions are the three
    permanent base folders (My Documents / Shared / Public) themselves.
    data/dms_data.xml (noupdate=1) already created "Shared"/"Public" fresh
    on this upgrade and re-parented "Email Templates"/"View Templates" under
    "Public" in the file - but noupdate=1 means that parent_id change is NOT
    applied to the already-existing rows on a live database, and neither is
    anything for the many other root-level documents this database already
    had (Untitled folders, "My Docs", "Public Categloques", etc. - whatever
    a real user created before this feature existed). This re-parents all
    of that: by visibility, public/shared root docs move under
    "Public"/"Shared"; private ones move under their own owner's
    "My Documents" (created here per-owner as needed, mirroring
    _get_base_folder("my_documents") but for each existing owner rather
    than the current migration-running user).
    """
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    Doc = env["sanare.document"]

    public_folder = env.ref("sanare_dms.doc_folder_public", raise_if_not_found=False)
    shared_folder = env.ref("sanare_dms.doc_folder_shared", raise_if_not_found=False)
    if not public_folder or not shared_folder:
        # Data file didn't run yet for some reason - nothing safe to do.
        return

    for xmlid in ("sanare_dms.doc_folder_email_templates", "sanare_dms.doc_folder_view_templates"):
        rec = env.ref(xmlid, raise_if_not_found=False)
        if rec and not rec.parent_id:
            rec.parent_id = public_folder.id

    my_documents_by_owner = {}

    def my_documents_for(owner):
        if owner.id not in my_documents_by_owner:
            folder = Doc.search([
                ("base_folder_key", "=", "my_documents"),
                ("owner_id", "=", owner.id),
            ], limit=1)
            if not folder:
                folder = Doc.create({
                    "name": "My Documents",
                    "content_type": "folder",
                    "base_folder_key": "my_documents",
                    "owner_id": owner.id,
                    "visibility": "private",
                    "visibility_inherited": False,
                })
            my_documents_by_owner[owner.id] = folder
        return my_documents_by_owner[owner.id]

    orphans = Doc.search([
        ("parent_id", "=", False),
        ("base_folder_key", "=", False),
    ])
    for doc in orphans:
        if doc.visibility == "public":
            doc.parent_id = public_folder.id
        elif doc.visibility == "shared":
            doc.parent_id = shared_folder.id
        else:
            doc.parent_id = my_documents_for(doc.owner_id).id
