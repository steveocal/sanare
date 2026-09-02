from odoo import api, fields, models

UOF_CATEGORIES = [
    ('regulatory', 'Regulatory'),
    ('inventory', 'Inventory'),
    ('payroll', 'Payroll'),
    ('sales_marketing', 'Sales & Marketing'),
    ('legal_prof', 'Legal & Professional'),
    ('operations_ga', 'Operations / G&A'),
    ('technology', 'Technology'),
    ('travel', 'Travel'),
    ('other', 'Other'),
]

# Map a use-of-funds bucket to the P&L/report categories used by eos.account.map.
UOF_TO_REPORT = {
    'regulatory': ['regulatory'],
    'inventory': ['inventory_purchases'],
    'payroll': ['payroll'],
    'sales_marketing': ['sales_marketing'],
    'legal_prof': ['legal_prof'],
    'operations_ga': ['office_it_ga', 'other_opex'],
    'technology': ['office_it_ga'],
    'travel': ['travel'],
    'other': ['other_capex', 'other_cash'],
}


class EosUseOfFunds(models.Model):
    _name = 'eos.use.of.funds'
    _description = 'EOS Investor Use of Funds'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    category = fields.Selection(UOF_CATEGORIES, string='Category', required=True)
    since_date = fields.Date(
        string='Track Spend Since', required=True,
        help='Cumulative actual spend is summed from posted entries on/after this date.')
    approved_budget = fields.Monetary(currency_field='currency_id')
    spent_to_date = fields.Monetary(
        currency_field='currency_id', readonly=True,
        help='Cumulative posted actuals for this bucket. Press Refresh to recompute.')
    committed = fields.Monetary(
        currency_field='currency_id',
        help='Approved / contracted future cash for this bucket not yet spent.')
    remaining = fields.Monetary(
        currency_field='currency_id', compute='_compute_amounts', store=True)
    percent_used = fields.Float(
        string='% Used', compute='_compute_amounts', store=True)
    last_refresh = fields.Datetime(readonly=True)

    @api.depends('approved_budget', 'committed', 'spent_to_date')
    def _compute_amounts(self):
        for rec in self:
            rec.remaining = rec.approved_budget - rec.spent_to_date - rec.committed
            rec.percent_used = (
                (rec.spent_to_date / rec.approved_budget * 100.0)
                if rec.approved_budget else 0.0)

    def action_refresh(self):
        Map = self.env['eos.account.map']
        AML = self.env['account.move.line']
        for rec in self:
            report_cats = UOF_TO_REPORT.get(rec.category, [])
            groups = AML._read_group(
                [('parent_state', '=', 'posted'),
                 ('company_id', '=', rec.company_id.id),
                 ('date', '>=', rec.since_date)],
                groupby=['account_id'], aggregates=['balance:sum'])
            total = 0.0
            for acc, bal in groups:
                if Map._category_for_account(acc) in report_cats:
                    total += bal
            rec.spent_to_date = total
            rec.last_refresh = fields.Datetime.now()
        return True
