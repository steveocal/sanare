from odoo import api, fields, models
from .account_map import PL_CATEGORIES


class EosBudgetLine(models.Model):
    _name = 'eos.budget.line'
    _description = 'EOS Monthly Budget Line'
    _order = 'period_date desc, category'

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    period_date = fields.Date(
        string='Month', required=True,
        help='Any date within the budgeted month.')
    category = fields.Selection(PL_CATEGORIES, string='Category', required=True)
    amount = fields.Monetary(string='Budget Amount', currency_field='currency_id')
    currency_id = fields.Many2one(
        related='company_id.currency_id', string='Currency')
    note = fields.Char(string='Note')

    _uniq_line = models.Constraint(
        'unique(company_id, period_date, category)',
        'One budget line per company, month and category.',
    )

    @api.model
    def _budget_for(self, company, category, date_from, date_to):
        rows = self.search([
            ('company_id', '=', company.id),
            ('category', '=', category),
            ('period_date', '>=', date_from),
            ('period_date', '<=', date_to),
        ])
        return sum(rows.mapped('amount'))
