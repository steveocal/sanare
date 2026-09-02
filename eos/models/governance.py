from odoo import api, fields, models


class EosLaunchWorkstream(models.Model):
    _name = 'eos.launch.workstream'
    _description = 'EOS Launch Readiness Workstream'
    _order = 'market_id, sequence'

    sequence = fields.Integer(default=10)
    market_id = fields.Many2one('eos.market', string='Market', required=True)
    workstream = fields.Selection([
        ('corporate', 'Corporate'),
        ('finance', 'Finance'),
        ('manufacturer', 'Manufacturer'),
        ('regulatory', 'Regulatory'),
        ('supply_chain', 'Supply Chain'),
        ('clinical', 'Clinical'),
        ('hospitals', 'Hospitals'),
        ('commercial', 'Commercial'),
        ('compliance', 'Compliance'),
    ], string='Workstream', required=True)
    weight = fields.Float(string='Weight')
    readiness = fields.Float(string='Readiness %')
    status = fields.Selection([
        ('green', 'Green'),
        ('yellow', 'Yellow'),
        ('red', 'Red'),
    ], string='Status')
    key_gate = fields.Text(string='Key Gate / Evidence')
    owner = fields.Char(string='Owner')
    source_key = fields.Char(string='Source Key')


class EosCloseStep(models.Model):
    _name = 'eos.close.step'
    _description = 'EOS Month-End Close Step'
    _order = 'sequence'

    sequence = fields.Integer(required=True)
    activity = fields.Char(string='Close Activity', required=True)
    owner = fields.Char(string='Owner')
    due = fields.Char(string='Due')
    status = fields.Selection([
        ('not_started', 'Not Started'),
        ('complete', 'Complete'),
    ], string='Status', default='not_started')
    evidence = fields.Char(string='Evidence / Source')
    issue = fields.Char(string='Issue / Exception')
    completed_date = fields.Date(string='Completed Date')
    notes = fields.Text(string='Notes')


class EosMonthlyReport(models.Model):
    _name = 'eos.monthly.report'
    _description = 'EOS Monthly Control / Report'
    _order = 'reporting_month desc'

    name = fields.Char(string='Report', compute='_compute_name', store=True)
    reporting_month = fields.Date(string='Reporting Month', required=True)
    report_date = fields.Date(string='Report Date')
    prepared_by_id = fields.Many2one('res.users', string='Prepared By')
    overall_health = fields.Selection([
        ('green', 'Green'), ('yellow', 'Yellow'), ('red', 'Red'),
    ], string='Overall Business Health')
    thailand_launch_health = fields.Selection([
        ('green', 'Green'), ('yellow', 'Yellow'), ('red', 'Red'),
    ], string='Thailand Launch Health')
    singapore_launch_health = fields.Selection([
        ('green', 'Green'), ('yellow', 'Yellow'), ('red', 'Red'),
    ], string='Singapore Launch Health')
    financial_health = fields.Selection([
        ('green', 'Green'), ('yellow', 'Yellow'), ('red', 'Red'),
    ], string='Financial Position Health')
    report_status = fields.Selection([
        ('draft', 'Draft'),
        ('ceo_review', 'CEO Review'),
        ('approved', 'Approved'),
        ('sent', 'Sent'),
    ], string='Report Status', default='draft')
    active_quarter = fields.Selection([
        ('q1', 'Q1'), ('q2', 'Q2'), ('q3', 'Q3'), ('q4', 'Q4'),
    ], string='Active EOS Quarter')
    current_quarter = fields.Selection([
        ('q1', 'Q1'), ('q2', 'Q2'), ('q3', 'Q3'), ('q4', 'Q4'),
    ], string='Current Quarter')
    executive_summary = fields.Text(string='Executive Summary')
    what_went_well = fields.Text(string='What Went Well')
    misses_slippage = fields.Text(string='Misses / Slippage')
    corrective_actions = fields.Text(string='Corrective Actions')
    key_decisions = fields.Text(string='Key Decisions')

    @api.depends('reporting_month')
    def _compute_name(self):
        for report in self:
            report.name = report.reporting_month.strftime('%B %Y') if report.reporting_month else 'Report'


class EosMilestone(models.Model):
    _name = 'eos.milestone'
    _description = 'EOS Milestone'
    _order = 'sequence'

    sequence = fields.Integer()
    name = fields.Char(string='Milestone', required=True)
    definition = fields.Text(string='Definition')
    target_date = fields.Date(string='Target Date')
    owner = fields.Char(string='Owner')
    status = fields.Selection([
        ('not_started', 'Not Started'),
        ('on_track', 'On Track'),
        ('complete', 'Complete'),
    ], string='Status', default='not_started')
    percent_complete = fields.Float(string='% Complete')
    notes = fields.Text(string='Notes')


class EosL10(models.Model):
    _name = 'eos.l10'
    _description = 'EOS Weekly L10 Meeting'
    _order = 'week_of desc'

    week_of = fields.Date(string='Week Of', required=True)
    attendees = fields.Char(string='Attendees')
    scorecard_notes = fields.Text(string='Scorecard Notes')
    rock_review_notes = fields.Text(string='Rock Review Notes')
    customer_notes = fields.Text(string='Customer / Clinical Notes')
    people_notes = fields.Text(string='People Notes')
    ids_line_ids = fields.One2many('eos.ids', 'l10_id', string='IDS Issues')


class EosIds(models.Model):
    _name = 'eos.ids'
    _description = 'EOS IDS Issue'
    _order = 'due_date'

    l10_id = fields.Many2one('eos.l10', string='L10 Meeting', ondelete='cascade')
    issue = fields.Text(string='Issue', required=True)
    owner = fields.Char(string='IDS Owner')
    resolution = fields.Text(string='Resolution / To-Do')
    due_date = fields.Date(string='Due Date')
    complete = fields.Boolean(string='Complete?')
    notes = fields.Text(string='Notes')
