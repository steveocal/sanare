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
    view_descriptor = fields.Json()
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
        elif self.content_type == "odoo_view":
            vals["view_descriptor"] = self.view_descriptor
        elif self.content_type == "onlyoffice" and self.attachment_id:
            if doc.attachment_id:
                # Re-triggers ir_attachment.py's write hook
                # (_sync_office_html + a fresh snapshot) synchronously, so
                # doc.content_html is already the freshly re-converted
                # equivalent of this version's own by the time this method
                # returns - nothing else to set here.
                doc.attachment_id.sudo().write({"datas": self.attachment_id.datas})
            else:
                att = self.attachment_id.sudo().copy({
                    "res_model": "sanare.document",
                    "res_id": doc.id,
                })
                vals["attachment_id"] = att.id
                # No attachment write fires the usual hook for a copied
                # attachment - this version's own content_html (rendered
                # from the exact file being restored) is the only thing
                # that sets doc's, so use it directly rather than
                # re-hitting the conversion API for an identical result.
                vals["content_html"] = self.content_html
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
