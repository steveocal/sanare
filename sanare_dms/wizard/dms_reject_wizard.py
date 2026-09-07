from odoo import fields, models


class SanareDocumentRejectWizard(models.TransientModel):
    _name = "sanare.document.reject.wizard"
    _description = "Reject Document"

    document_id = fields.Many2one("sanare.document", required=True)
    reason = fields.Text(required=True, string="Reason for rejection")

    def action_confirm(self):
        self.ensure_one()
        self.document_id._apply_rejection(self.reason)
        return {"type": "ir.actions.act_window_close"}
