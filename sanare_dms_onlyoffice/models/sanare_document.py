from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.onlyoffice_odoo.utils import file_utils

BLANK_EXT = {"docx", "xlsx", "pptx"}

OFFICE_KINDS = [
    ("docx", "Word Document"),
    ("xlsx", "Spreadsheet"),
    ("pptx", "Presentation"),
]


class SanareDocument(models.Model):
    _inherit = "sanare.document"

    office_kind = fields.Selection(
        OFFICE_KINDS, default="docx", string="Office Document Type",
        help="Which kind of blank file to create the first time this "
             "document is opened in ONLYOFFICE. Has no effect once a file "
             "already exists.",
    )

    def _office_ext(self):
        """The extension to use for this document's ONLYOFFICE file.

        Bug fixed here: this used to fall back to `file_extension`, which is
        computed from `file_name` (odoo/models/dms_document.py) - but that's
        always empty before the blank file is created, so every new Office
        Document silently fell through to the "docx" default regardless of
        what the user actually wanted. `file_extension` is still trusted
        first, for a document whose file was uploaded directly (not created
        blank) - only the *fallback* changes, from a hardcoded "docx" to the
        user's own office_kind choice.
        """
        self.ensure_one()
        ext = (self.file_extension or "").lower()
        if ext in BLANK_EXT:
            return ext
        return self.office_kind or "docx"

    def _ensure_office_attachment(self):
        self.ensure_one()
        if self.content_type != "onlyoffice":
            raise UserError(self.env._("This document is not an office document."))
        if self.attachment_id:
            return self.attachment_id
        ext = self._office_ext()
        try:
            data = file_utils.get_default_file_template(self.env.user.lang or "en_US", ext)
        except Exception as exc:  # noqa: BLE001 - surface any template issue to the user
            raise UserError(
                self.env._("Could not load a blank %(ext)s template: %(err)s", ext=ext, err=exc)
            )
        name = self.file_name or "%s.%s" % (self.name, ext)
        if not name.lower().endswith("." + ext):
            name = "%s.%s" % (name, ext)
        attachment = self.env["ir.attachment"].sudo().create({
            "name": name,
            "raw": data,
            "res_model": "sanare.document",
            "res_id": self.id,
            "mimetype": file_utils.get_mime_by_ext(ext),
        })
        self.with_context(dms_skip_version=True).write(
            {"attachment_id": attachment.id, "file_name": name}
        )
        self._snapshot_version(
            changelog=self.env._("Blank %s document created", ext), trigger="upload"
        )
        return attachment

    def action_edit_onlyoffice(self):
        self.ensure_one()
        if not self._user_can_write():
            raise UserError(
                self.env._("You do not have edit rights on this document.")
            )
        attachment = self._ensure_office_attachment()
        return {
            "type": "ir.actions.act_url",
            "url": "/onlyoffice/editor/%s" % attachment.id,
            "target": "new",
        }

    def action_view_onlyoffice(self):
        self.ensure_one()
        if not self.attachment_id:
            raise UserError(self.env._("There is no office file to open yet."))
        return {
            "type": "ir.actions.act_url",
            "url": "/onlyoffice/editor/%s" % self.attachment_id.id,
            "target": "new",
        }

    def action_save_office_version(self):
        self.ensure_one()
        self._snapshot_version(
            changelog=self.env._("Manual version"), trigger="manual", author=self.env.user
        )
        return True
