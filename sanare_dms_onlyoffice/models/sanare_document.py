from odoo import models
from odoo.exceptions import UserError

from odoo.addons.onlyoffice_odoo.utils import file_utils

BLANK_EXT = {"docx", "xlsx", "pptx"}


class SanareDocument(models.Model):
    _inherit = "sanare.document"

    def _office_ext(self):
        self.ensure_one()
        ext = (self.file_extension or "docx").lower()
        return ext if ext in BLANK_EXT else "docx"

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
