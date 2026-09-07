from odoo import fields, models


class SanareDocumentTag(models.Model):
    _name = "sanare.document.tag"
    _description = "Document Tag"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    color = fields.Integer()
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint("unique(name)", "Tag names must be unique.")
