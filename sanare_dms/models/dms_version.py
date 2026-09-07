from odoo import api, fields, models


class SanareDocumentVersion(models.Model):
    _name = "sanare.document.version"
    _description = "Document Version"
    _order = "document_id, version_number desc"

    document_id = fields.Many2one(
        "sanare.document", required=True, ondelete="cascade", index=True
    )
    version_number = fields.Integer(required=True, string="Revision")
    name = fields.Char(compute="_compute_name", string="Version")
    content_type = fields.Selection(related="document_id.content_type", store=True)

    content_html = fields.Html(sanitize=False)
    content_markdown = fields.Text()
    attachment_id = fields.Many2one("ir.attachment", string="File Snapshot")
    checksum = fields.Char()
    file_size = fields.Integer()

    changelog = fields.Char()
    author_id = fields.Many2one("res.users", string="Author")
    create_date = fields.Datetime(string="Saved On")

    is_current = fields.Boolean(compute="_compute_flags")
    is_approved = fields.Boolean(compute="_compute_flags")

    @api.depends("version_number")
    def _compute_name(self):
        for ver in self:
            ver.name = "v%s" % ver.version_number

    @api.depends(
        "document_id.version_number", "document_id.approved_version_id"
    )
    def _compute_flags(self):
        for ver in self:
            ver.is_current = ver.version_number == ver.document_id.version_number
            ver.is_approved = ver == ver.document_id.approved_version_id

    def action_restore(self):
        self.ensure_one()
        doc = self.document_id
        vals = {}
        if self.content_type == "html":
            vals["content_html"] = self.content_html
        elif self.content_type == "markdown":
            vals["content_markdown"] = self.content_markdown
        elif self.content_type == "onlyoffice" and self.attachment_id:
            if doc.attachment_id:
                doc.attachment_id.sudo().write({"datas": self.attachment_id.datas})
            else:
                att = self.attachment_id.sudo().copy({
                    "res_model": "sanare.document",
                    "res_id": doc.id,
                })
                vals["attachment_id"] = att.id
        if vals:
            doc.with_context(dms_skip_version=True).write(vals)
        doc._snapshot_version(
            changelog=self.env._("Restored from v%s", self.version_number),
            trigger="restore",
        )
        doc.message_post(
            body=self.env._("Content restored from revision v%s.", self.version_number)
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "sanare.document",
            "res_id": doc.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": "sanare.document.version",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
