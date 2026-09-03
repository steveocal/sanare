from datetime import timedelta

from odoo import api, fields, models
from .account_map import PL_CATEGORIES

OPEX_CATEGORIES = [
    'payroll', 'regulatory', 'legal_prof', 'sales_marketing',
    'travel', 'office_it_ga', 'other_opex',
]
_ZERO_FIELDS = [
    'revenue', 'cogs', 'gross_margin', 'gross_margin_pct', 'total_opex',
    'operating_result', 'net_cash_burn', 'beginning_cash', 'ending_cash',
    'accounts_receivable', 'inventory_value', 'committed_unspent',
    'available_capital', 'runway_months', 'capital_received',
    'inventory_purchases', 'other_capex', 'other_cash',
] + OPEX_CATEGORIES


class EosFinancialPeriod(models.Model):
    _name = 'eos.financial.period'
    _description = 'EOS Monthly Financial Position'
    _order = 'date_to desc, company_id'

    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_from = fields.Date(string='From', required=True)
    date_to = fields.Date(string='To', required=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('confirmed', 'Confirmed')],
        default='draft', required=True)
    prior_period_id = fields.Many2one(
        'eos.financial.period', string='Prior Period',
        compute='_compute_prior_period', store=True)
    last_refresh = fields.Datetime(string='Last Refreshed', readonly=True)

    use_manual_committed = fields.Boolean(string='Enter Committed Manually')
    committed_unspent_manual = fields.Monetary(
        string='Committed but Unspent (manual)', currency_field='currency_id')

    revenue = fields.Monetary(currency_field='currency_id', store=True, compute='_compute_actuals')
    cogs = fields.Monetary(currency_field='currency_id', store=True, compute='_compute_actuals')
    gross_margin = fields.Monetary(currency_field='currency_id', store=True, compute='_compute_actuals')
    gross_margin_pct = fields.Float(string='Gross Margin %', store=True, compute='_compute_actuals')
    payroll = fields.Monetary(currency_field='currency_id', store=True, compute='_compute_actuals')
    regulatory = fields.Monetary(currency_field='currency_id', store=True, compute='_compute_actuals')
    legal_prof = fields.Monetary(string='Legal & Professional', currency_field='currency_id',
                                 store=True, compute='_compute_actuals')
    sales_marketing = fields.Monetary(string='Sales & Marketing', currency_field='currency_id',
                                      store=True, compute='_compute_actuals')
    travel = fields.Monetary(currency_field='currency_id', store=True, compute='_compute_actuals')
    office_it_ga = fields.Monetary(string='Office / IT / G&A', currency_field='currency_id',
                                   store=True, compute='_compute_actuals')
    other_opex = fields.Monetary(string='Other Operating', currency_field='currency_id',
                                 store=True, compute='_compute_actuals')
    total_opex = fields.Monetary(string='Total Operating Expense', currency_field='currency_id',
                                 store=True, compute='_compute_actuals')
    operating_result = fields.Monetary(string='Operating Result', currency_field='currency_id',
                                       store=True, compute='_compute_actuals')

    inventory_purchases = fields.Monetary(currency_field='currency_id', store=True,
                                          compute='_compute_actuals')
    other_capex = fields.Monetary(currency_field='currency_id', store=True, compute='_compute_actuals')
    other_cash = fields.Monetary(string='Other Cash Uses', currency_field='currency_id',
                                 store=True, compute='_compute_actuals')
    capital_received = fields.Monetary(currency_field='currency_id', store=True,
                                       compute='_compute_actuals')
    net_cash_burn = fields.Monetary(
        string='Net Cash Burn', currency_field='currency_id', store=True,
        compute='_compute_actuals',
        help='COGS + operating expense + inventory purchases + CapEx + other cash '
             'uses - revenue. A P&L-derived approximation, not a full indirect '
             'cash-flow statement.')

    beginning_cash = fields.Monetary(currency_field='currency_id', store=True,
                                     compute='_compute_actuals')
    ending_cash = fields.Monetary(
        currency_field='currency_id', store=True, compute='_compute_actuals',
        help='Balance of Bank & Cash accounts at period end.')
    accounts_receivable = fields.Monetary(currency_field='currency_id', store=True,
                                          compute='_compute_actuals')
    inventory_value = fields.Monetary(currency_field='currency_id', store=True,
                                      compute='_compute_actuals')
    committed_unspent = fields.Monetary(currency_field='currency_id', store=True,
                                        compute='_compute_actuals')
    available_capital = fields.Monetary(currency_field='currency_id', store=True,
                                        compute='_compute_actuals')
    runway_months = fields.Float(string='Runway (Months)', store=True,
                                 compute='_compute_actuals')

    line_ids = fields.One2many('eos.financial.period.line', 'period_id',
                               string='Category Lines')

    _uniq_period = models.Constraint(
        'unique(company_id, date_from, date_to)',
        'A financial period for this company and date range already exists.',
    )

    # ================================================================
    @api.depends('date_from')
    def _compute_name(self):
        for p in self:
            p.name = p.date_from.strftime('%b %Y') if p.date_from else 'Period'

    @api.depends('company_id', 'date_from')
    def _compute_prior_period(self):
        for p in self:
            p.prior_period_id = p.search([
                ('company_id', '=', p.company_id.id),
                ('date_to', '<', p.date_from),
            ], order='date_to desc', limit=1)

    # ----------------------------------------------------------------
    def _categorize(self, account_ids):
        Map = self.env['eos.account.map']
        out = {}
        for acc in self.env['account.account'].browse(list(account_ids)):
            out[acc.id] = Map._category_for_account(acc)
        return out

    def _sum_balance(self, domain):
        groups = self.env['account.move.line']._read_group(
            domain, groupby=['account_id'], aggregates=['balance:sum'])
        return {acc.id: bal for acc, bal in groups}

    @api.depends('date_from', 'date_to', 'company_id',
                 'use_manual_committed', 'committed_unspent_manual')
    def _compute_actuals(self):
        for p in self:
            if not (p.date_from and p.date_to and p.company_id):
                for f in _ZERO_FIELDS:
                    p[f] = 0.0
                continue

            base = [('parent_state', '=', 'posted'),
                    ('company_id', '=', p.company_id.id)]
            window_bal = p._sum_balance(
                base + [('date', '>=', p.date_from), ('date', '<=', p.date_to)])
            end_bal = p._sum_balance(base + [('date', '<=', p.date_to)])
            cat_of = p._categorize(set(window_bal) | set(end_bal))

            # ---- P&L movement in the window ----
            bucket = dict.fromkeys([c[0] for c in PL_CATEGORIES] + ['capital_in'], 0.0)
            for acc_id, bal in window_bal.items():
                cat = cat_of.get(acc_id)
                if cat in bucket:
                    bucket[cat] += bal

            p.revenue = -bucket['revenue']
            p.cogs = bucket['cogs']
            p.gross_margin = p.revenue - p.cogs
            p.gross_margin_pct = (p.gross_margin / p.revenue * 100.0) if p.revenue else 0.0
            p.payroll = bucket['payroll']
            p.regulatory = bucket['regulatory']
            p.legal_prof = bucket['legal_prof']
            p.sales_marketing = bucket['sales_marketing']
            p.travel = bucket['travel']
            p.office_it_ga = bucket['office_it_ga']
            p.other_opex = bucket['other_opex']
            p.total_opex = sum(bucket[c] for c in OPEX_CATEGORIES)
            p.operating_result = p.gross_margin - p.total_opex
            p.inventory_purchases = bucket['inventory_purchases']
            p.other_capex = bucket['other_capex']
            p.other_cash = bucket['other_cash']
            p.capital_received = -bucket['capital_in']
            p.net_cash_burn = (p.cogs + p.total_opex + p.inventory_purchases
                               + p.other_capex + p.other_cash - p.revenue)

            # ---- balances at period end ----
            acc_by_type = {}
            for a in self.env['account.account'].browse(list(end_bal)):
                acc_by_type[a.account_type] = acc_by_type.get(a.account_type, 0.0) + end_bal[a.id]
            p.ending_cash = acc_by_type.get('asset_cash', 0.0)
            p.accounts_receivable = acc_by_type.get('asset_receivable', 0.0)
            p.inventory_value = sum(
                bal for acc_id, bal in end_bal.items()
                if cat_of.get(acc_id) == 'inventory_value')

            if p.prior_period_id:
                p.beginning_cash = p.prior_period_id.ending_cash
            else:
                prev = p._sum_balance(
                    base + [('date', '<=', p.date_from - timedelta(days=1)),
                            ('account_id.account_type', '=', 'asset_cash')])
                p.beginning_cash = sum(prev.values())

            # ---- committed but unspent ----
            if p.use_manual_committed:
                p.committed_unspent = p.committed_unspent_manual
            else:
                pos = self.env['purchase.order'].search([
                    ('company_id', '=', p.company_id.id),
                    ('state', 'in', ('draft', 'sent', 'purchase')),
                    ('invoice_status', '!=', 'invoiced'),
                ])
                p.committed_unspent = sum(pos.mapped('amount_total'))
            p.available_capital = p.ending_cash - p.committed_unspent

            # ---- runway ----
            trail = self.search([
                ('company_id', '=', p.company_id.id),
                ('date_to', '<=', p.date_to),
            ], order='date_to desc', limit=3)
            burns = [x.net_cash_burn for x in trail if x.id != p.id] + [p.net_cash_burn]
            avg = sum(burns) / len(burns) if burns else 0.0
            p.runway_months = (p.available_capital / avg) if avg > 0 else 0.0

    # ================================================================
    def action_refresh(self):
        for p in self:
            p.invalidate_recordset()
            p._compute_actuals()
            p._rebuild_lines()
            p.last_refresh = fields.Datetime.now()
        return True

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def _rebuild_lines(self):
        self.ensure_one()
        self.line_ids.unlink()
        ytd_from = self.date_from.replace(month=1, day=1)
        vals = []
        for code, _label in PL_CATEGORIES:
            vals.append({
                'period_id': self.id,
                'category': code,
                'actual': self[code],
                'budget': self._budget_for(code, self.date_from, self.date_to),
                'ytd_actual': self._category_ytd(code, ytd_from, self.date_to),
                'ytd_budget': self._budget_for(code, ytd_from, self.date_to),
            })
        self.env['eos.financial.period.line'].create(vals)

    def _budget_for(self, category, date_from, date_to):
        """Planned amount for one EOS category over ``[date_from, date_to]``.

        Reads ``base_account_budget`` lines under the budgetary position
        tagged with this ``eos_category`` and prorates each line by the
        fraction of its own span that overlaps the requested window.
        """
        self.ensure_one()
        post = self.env['account.budget.post'].search([
            ('eos_category', '=', category),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not post:
            return 0.0
        lines = self.env['budget.lines'].search([
            ('general_budget_id', '=', post.id),
            ('date_from', '<=', date_to),
            ('date_to', '>=', date_from),
        ])
        total = 0.0
        for line in lines:
            if not (line.date_from and line.date_to):
                continue
            span_days = (line.date_to - line.date_from).days + 1
            if span_days <= 0:
                continue
            lo = max(line.date_from, date_from)
            hi = min(line.date_to, date_to)
            overlap_days = (hi - lo).days + 1
            if overlap_days <= 0:
                continue
            total += line.planned_amount * overlap_days / span_days
        return total

    def _category_ytd(self, code, date_from, date_to):
        self.ensure_one()
        bal = self._sum_balance([
            ('parent_state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
            ('date', '>=', date_from), ('date', '<=', date_to),
        ])
        cat_of = self._categorize(set(bal))
        total = sum(b for acc_id, b in bal.items() if cat_of.get(acc_id) == code)
        return -total if code == 'revenue' else total

    @api.model
    def _cron_refresh(self):
        self.search([('state', '=', 'draft')]).action_refresh()
