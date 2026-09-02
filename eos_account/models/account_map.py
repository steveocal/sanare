from odoo import api, fields, models

# Report categories mirroring the "Financial Inputs" / Report 07 workbook lines.
PL_CATEGORIES = [
    ('revenue', 'Revenue'),
    ('cogs', 'COGS'),
    ('payroll', 'Payroll & Benefits'),
    ('regulatory', 'Regulatory'),
    ('legal_prof', 'Legal & Professional'),
    ('sales_marketing', 'Sales & Marketing'),
    ('travel', 'Travel'),
    ('office_it_ga', 'Office / IT / G&A'),
    ('inventory_purchases', 'Inventory Purchases'),
    ('other_capex', 'Other CapEx'),
    ('other_opex', 'Other Operating'),
    ('other_cash', 'Other Cash Uses'),
]
BALANCE_CATEGORIES = [
    ('cash', 'Cash'),
    ('ar', 'Accounts Receivable'),
    ('inventory_value', 'Inventory Value'),
    ('capital_in', 'Capital Received'),
]
ALL_CATEGORIES = PL_CATEGORIES + BALANCE_CATEGORIES

# Sensible defaults so the map produces output on any chart of accounts before
# the user refines it per account.
DEFAULT_TYPE_CATEGORY = {
    'income': 'revenue',
    'income_other': 'revenue',
    'expense_direct_cost': 'cogs',
    'expense_depreciation': 'other_capex',
    'expense': 'other_opex',
    'asset_cash': 'cash',
    'asset_current': 'inventory_value',
    'asset_prepayments': 'inventory_value',
    'asset_fixed': 'other_capex',
    'equity': 'capital_in',
    'equity_unaffected': 'capital_in',
    'liability_current': 'capital_in',
    'liability_non_current': 'capital_in',
}


class EosAccountMap(models.Model):
    _name = 'eos.account.map'
    _description = 'EOS GL Account → Report Category Mapping'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company)
    account_id = fields.Many2one(
        'account.account', string='Account',
        help='Highest-priority match: this exact account.')
    account_prefix = fields.Char(
        string='Account Code Prefix',
        help='Match accounts whose code starts with this. Longest prefix wins.')
    account_type = fields.Selection(
        selection='_selection_account_type', string='Account Type',
        help='Fallback: any account of this type not matched above.')
    category = fields.Selection(ALL_CATEGORIES, string='Report Category', required=True)

    @api.model
    def _selection_account_type(self):
        return self.env['account.account']._fields['account_type'].selection

    @api.model
    def _category_for_account(self, account):
        """Resolve one account.account to a report category (string) or False."""
        company = self.env.company
        maps = self.search([
            '|', ('company_id', '=', company.id), ('company_id', '=', False),
        ])
        # 1) exact account
        for m in maps:
            if m.account_id and m.account_id.id == account.id:
                return m.category
        # 2) longest prefix
        best = None
        for m in maps:
            if m.account_prefix and (account.code or '').startswith(m.account_prefix):
                if best is None or len(m.account_prefix) > len(best.account_prefix):
                    best = m
        if best:
            return best.category
        # 3) account type override
        for m in maps:
            if m.account_type and m.account_type == account.account_type:
                return m.category
        # 4) built-in default
        return DEFAULT_TYPE_CATEGORY.get(account.account_type)
