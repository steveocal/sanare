{
    "name": "EOS - Dashboard (Report 03 Thailand)",
    "version": "19.0.1.0.0",
    "category": "Sales/CRM",
    "author": "Sanare",
    "license": "LGPL-3",
    "summary": "Report 03 - Thailand Launch Readiness: a live backend screen and a "
               "QWeb report that faithfully port the spreadsheet's "
               "'Launch Readiness' formulae to Python over eos.rock / eos.task.",
    "description": "Ports the 'Report 03 Thailand' tab of the Sanare Management "
                   "Reporting Engine workbook to Odoo. models/readiness_engine.py "
                   "is a dependency-free re-implementation of the Launch Readiness "
                   "formulae (workstream Readiness %, Red/Yellow/Green Health, "
                   "overall weighted readiness, Red/Yellow counts) shared by the "
                   "Odoo model and by scripts/verify_vs_spreadsheet.py. "
                   "eos.thailand.readiness is a transient model plus form view for "
                   "the live on-screen board; report_03_thailand is a QWeb "
                   "HTML/PDF report bound to eos.monthly.report reproducing the "
                   "one-page layout. The parity checker loads the real .xlsx, runs "
                   "the ported functions against the Task Tracker rows and asserts "
                   "every figure matches the workbook's own cached cell values.",
    "depends": ["eos", "eos_account", "web"],
    "data": [
        "security/ir.model.access.csv",
        "report/report_layout.xml",
        "report/monthly_reports.xml",
        "report/report_03_thailand.xml",
        "views/thailand_readiness_views.xml",
        "data/sample_data.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
