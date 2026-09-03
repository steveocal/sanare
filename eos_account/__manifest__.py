{
    'name': 'EOS - Financial Reporting',
    'version': '19.0.2.0.0',
    'category': 'Accounting/Accounting',
    'author': 'Sanare',
    'license': 'LGPL-3',
    'summary': 'Management & investor reporting layer on top of base_accounting_kit: '
               'monthly financial position, burn, runway and use of funds, '
               'computed from the General Ledger as the single source of truth.',
    'description': '''
EOS Financial Reporting
=======================

A thin management-reporting layer that sits on top of the community accounting
stack (``base_accounting_kit`` + ``base_account_budget``). The statutory
statements - P&L, Balance Sheet, General Ledger, Trial Balance, Aged
Receivable/Payable, Cash Flow - are produced by ``base_accounting_kit``; this
module adds only what the Sanare Management Reporting Engine needs on top:

- ``eos.account.map``: classify GL accounts into EOS report categories
  (Revenue, COGS, Payroll, Regulatory, Legal & Professional, Sales & Marketing,
  Travel, Office / IT / G&A, Inventory Purchases, CapEx, ...).
- ``eos.financial.period``: one stored month of P&L, cash, burn and runway,
  computed from posted ``account.move.line`` - never re-keyed. Prior-period
  chained so beginning/ending cash and trailing burn line up.
- Budget vs actual: the plan side now lives in ``base_account_budget``
  (``budget.budget`` / ``budget.lines``). Each EOS category is tagged onto an
  ``account.budget.post`` (``eos_category``); the monthly period prorates the
  matching budget lines onto its window.
- ``eos.use.of.funds``: the investor use-of-funds tracker (approved vs spent
  vs committed), cumulative actuals read through the same account mapping.
- QWeb pack: Monthly & YTD Financial Position, plus a combined Investor Report;
  figures also flow into ``eos.monthly.report``.
    ''',
    'depends': [
        'eos',
        'account',
        'purchase',
        'base_accounting_kit',
        'base_account_budget',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/account_map_default.xml',
        'views/account_map_views.xml',
        'views/financial_period_views.xml',
        'views/budget_post_views.xml',
        'views/use_of_funds_views.xml',
        'views/monthly_report_views.xml',
        'report/financial_report.xml',
        'report/investor_report.xml',
        'views/menus.xml',
    ],
    'post_init_hook': 'post_init_seed_budget_posts',
    'installable': True,
    'application': True,
    'auto_install': False,
}
