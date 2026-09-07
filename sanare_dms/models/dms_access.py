from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SanareDocumentAccess(models.Model):
    _name = "sanare.document.access"
    _description = "Document Share"
    _rec_name = "partner_id"

    document_id = fields.Many2one(
        "sanare.document", required=True, ondelete="cascade", index=True
    )
    partner_id = fields.Many2one("res.partner", string="Person")
    group_id = fields.Many2one("res.groups", string="Group")
    permission = fields.Selection(
        [("read", "Can Read"), ("write", "Can Edit"), ("approve", "Can Approve")],
        default="read",
        required=True,
    )

    @api.constrains("partner_id", "group_id")
    def _check_target(self):
        for acc in self:
            if bool(acc.partner_id) == bool(acc.group_id):
                raise ValidationError(
                    self.env._("A share must target either a person or a group, not both.")
                )
