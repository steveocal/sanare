from odoo import api, fields, models
from .account_map import PL_CATEGORIES


class EosFinancialPeriodLine(models.Model):
    _name = 'eos.financial.period.line'
    _description = 'EOS Financial Period Category Line'
    _order = 'period_id, category'

    period_id = fields.Many2one(
        'eos.financial.period', string='Period', required=True,
        ondelete='cascade', index=True)
    company_id = fields.Many2one(related='period_id.company_id', store=True)
    currency_id = fields.Many2one(related='period_id.currency_id')
    date_to = fields.Date(related='period_id.date_to', store=True)
    category = fields.Selection(PL_CATEGORIES, string='Category', required=True)

    actual = fields.Monetary(currency_field='currency_id', aggregator='sum')
    budget = fields.Monetary(currency_field='currency_id', aggregator='sum')
    variance = fields.Monetary(
        currency_field='currency_id', compute='_compute_variance',
        store=True, aggregator='sum')
    variance_pct = fields.Float(
        string='Variance %', compute='_compute_variance', store=True)
    ytd_actual = fields.Monetary(currency_field='currency_id', aggregator='sum')
    ytd_budget = fields.Monetary(currency_field='currency_id', aggregator='sum')

    @api.depends('actual', 'budget')
    def _compute_variance(self):
        for line in self:
            line.variance = line.actual - line.budget
            line.variance_pct = (
                (line.variance / abs(line.budget) * 100.0) if line.budget else 0.0)
