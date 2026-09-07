from odoo import api, fields, models


class SanareDocumentCategory(models.Model):
    _name = "sanare.document.category"
    _description = "Document Category"
    _parent_store = True
    _parent_name = "parent_id"
    _order = "complete_name"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    parent_id = fields.Many2one(
        "sanare.document.category", string="Parent Category", ondelete="cascade", index=True
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("sanare.document.category", "parent_id", string="Sub-categories")
    complete_name = fields.Char(
        compute="_compute_complete_name", recursive=True, store=True, string="Full Category"
    )
    color = fields.Integer()
    approval_rule_id = fields.Many2one(
        "sanare.document.approval.rule",
        string="Approval Rule",
        help="Documents filed under this category use this approval workflow.",
    )
    document_count = fields.Integer(compute="_compute_document_count")

    @api.depends("name", "parent_id.complete_name")
    def _compute_complete_name(self):
        for cat in self:
            if cat.parent_id:
                cat.complete_name = "%s / %s" % (cat.parent_id.complete_name, cat.name)
            else:
                cat.complete_name = cat.name

    def _compute_document_count(self):
        data = self.env["sanare.document"]._read_group(
            [("category_id", "in", self.ids)], ["category_id"], ["__count"]
        )
        mapped = {cat.id: count for cat, count in data}
        for cat in self:
            cat.document_count = mapped.get(cat.id, 0)

    @api.constrains("parent_id")
    def _check_category_recursion(self):
        if self._has_cycle():
            from odoo.exceptions import ValidationError

            raise ValidationError(self.env._("You cannot create recursive categories."))

    def action_view_documents(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.complete_name,
            "res_model": "sanare.document",
            "view_mode": "list,kanban,form",
            "domain": [("category_id", "child_of", self.id)],
            "context": {"default_category_id": self.id},
        }
