{
    'name': 'EOS - Financial Reporting',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'author': 'Sanare',
    'license': 'LGPL-3',
    'summary': 'Financial pages of the Sanare Management Reporting Engine, '
               'computed from the General Ledger as the single source of truth.',
    'description': '''
Adds the workbook's financial layer on top of Odoo Accounting.

- eos.account.map: classify GL accounts into report categories (Revenue, COGS,
  Payroll, Regulatory, Legal & Professional, Sales & Marketing, Travel,
  Office / IT / G&A, Inventory Purchases, CapEx, ...).
- eos.financial.period: one month of P&L, cash, burn and runway, computed
  from posted account.move.line - never re-keyed.
- eos.budget.line / eos.use.of.funds: the plan side (budget-vs-actual,
  investor use-of-funds).
- QWeb pack: Monthly & YTD Financial Position (Report 07), Use of Funds
  (Report 08), and a combined Investor Report; figures also flow into
  eos.monthly.report.
    ''',
    'depends': ['eos', 'account', 'purchase'],
    'data': [
        'security/ir.model.access.csv',
        'data/account_map_default.xml',
        'views/account_map_views.xml',
        'views/financial_period_views.xml',
        'views/budget_views.xml',
        'views/use_of_funds_views.xml',
        'views/monthly_report_views.xml',
        'report/financial_report.xml',
        'report/investor_report.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
