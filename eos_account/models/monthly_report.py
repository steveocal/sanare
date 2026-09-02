from odoo import api, fields, models


class EosMonthlyReport(models.Model):
    _inherit = 'eos.monthly.report'

    financial_period_id = fields.Many2one(
        'eos.financial.period', string='Financial Period',
        compute='_compute_financial_period', store=True, readonly=False)
    ending_cash = fields.Monetary(
        related='financial_period_id.ending_cash', string='Ending Cash')
    available_capital = fields.Monetary(
        related='financial_period_id.available_capital')
    net_cash_burn = fields.Monetary(
        related='financial_period_id.net_cash_burn', string='Net Cash Burn')
    runway_months = fields.Float(
        related='financial_period_id.runway_months', string='Runway (Months)')
    gross_margin_pct = fields.Float(
        related='financial_period_id.gross_margin_pct', string='Gross Margin %')
    capital_received = fields.Monetary(
        related='financial_period_id.capital_received')
    currency_id = fields.Many2one(
        related='financial_period_id.currency_id')

    financial_health_suggestion = fields.Selection(
        [('green', 'Green'), ('yellow', 'Yellow'), ('red', 'Red')],
        string='Suggested Financial Health', compute='_compute_health_suggestion',
        help='Advisory, from runway. Does not overwrite the manual rating.')

    @api.depends('reporting_month')
    def _compute_financial_period(self):
        for report in self:
            if not report.reporting_month:
                report.financial_period_id = False
                continue
            report.financial_period_id = self.env['eos.financial.period'].search([
                ('date_from', '<=', report.reporting_month),
                ('date_to', '>=', report.reporting_month),
            ], limit=1)

    @api.depends('financial_period_id.runway_months')
    def _compute_health_suggestion(self):
        for report in self:
            runway = report.financial_period_id.runway_months or 0.0
            if not report.financial_period_id:
                report.financial_health_suggestion = False
            elif runway >= 12:
                report.financial_health_suggestion = 'green'
            elif runway >= 6:
                report.financial_health_suggestion = 'yellow'
            else:
                report.financial_health_suggestion = 'red'
