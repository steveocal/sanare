from odoo import models

_CONTENT_KEYS = {"raw", "datas", "db_datas"}


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("dms_skip_version"):
            return res
        if not (_CONTENT_KEYS & set(vals)):
            return res
        docs = self.env["sanare.document"].sudo().search(
            [("attachment_id", "in", self.ids), ("content_type", "=", "onlyoffice")]
        )
        for doc in docs:
            doc._snapshot_version(
                changelog=self.env._("Edited in ONLYOFFICE"),
                trigger="onlyoffice",
                author=self.env.user,
            )
        return res
