{
    'name': 'EOS - Sanare Management & Reporting',
    'version': '19.0.2.0.0',
    'category': 'Sales/CRM',
    'author': 'Sanare',
    'license': 'LGPL-3',
    'summary': 'EOS (Entrepreneurial Operating System) cadence: Rocks, Tasks, Commercial Pipeline, Clinical, Supply Chain, Risks, KPI and monthly-report governance.',
    'description': '''
Sanare International EOS operating & reporting engine.

Replaces the Excel "Management Reporting Engine" workbook with Odoo models.

- EOS execution: Markets, Rocks, Tasks (auto % complete & health)
- CRM extension: Sanare stages + commercial cm2 pipeline on crm.lead
- Clinical: Physician / KOL tracker
- Supply chain: SKU inventory (reads Odoo Inventory as source of truth)
- Enterprise risk register (auto rating & score)
- KPI dictionary + monthly KPI history
- Launch readiness workstreams, month-end close checklist, monthly control, milestones and weekly L10 / IDS meeting capture

Financial layer (D) is intentionally deferred: accounting will feed the
financial reports in a later phase.
''',
    'depends': ['base', 'crm', 'product', 'stock', 'resource', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'data/markets.xml',
        'data/crm_stages.xml',
        'data/rocks.xml',
        'data/tasks.xml',
        'data/kpi_dict.xml',
        'data/launch_workstreams.xml',
        'data/close_steps.xml',
        'data/milestones.xml',
        'views/market_views.xml',
        'views/rock_task_views.xml',
        'views/project_plan_views.xml',
        'views/physician_views.xml',
        'views/supply_chain_views.xml',
        'views/risk_views.xml',
        'views/kpi_views.xml',
        'views/governance_views.xml',
        'views/crm_views.xml',
        'views/menus.xml',
        'views/gantt_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'eos/static/src/gantt/eos_gantt.scss',
            'eos/static/src/gantt/eos_gantt.xml',
            'eos/static/src/gantt/eos_gantt.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
