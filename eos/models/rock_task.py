from odoo import api, fields, models


class EosRock(models.Model):
    _name = 'eos.rock'
    _description = 'EOS Rock (Quarterly Priority)'
    _order = 'quarter, sequence, name'

    name = fields.Char(string='Rock', required=True)
    rock_id = fields.Char(string='Rock ID', help="e.g. R1, R25")
    sequence = fields.Integer(default=10)
    market_id = fields.Many2one('eos.market', string='Market')
    quarter = fields.Selection([
        ('q1', 'Q1'),
        ('q2', 'Q2'),
        ('q3', 'Q3'),
        ('q4', 'Q4'),
    ], string='Quarter')
    phase = fields.Char(string='Phase', help="e.g. Aug-Oct 2026")
    accountable_owner = fields.Char(string='Accountable Owner')
    due_date = fields.Date(string='Due Date')
    definition_of_done = fields.Text(string='Definition of Done')
    status = fields.Selection([
        ('not_started', 'Not Started'),
        ('on_track', 'On Track'),
        ('at_risk', 'At Risk'),
        ('off_track', 'Off Track'),
        ('complete', 'Complete'),
        ('deferred', 'Deferred'),
    ], string='Status', default='not_started')
    health = fields.Selection([
        ('green', 'Green'),
        ('yellow', 'Yellow'),
        ('red', 'Red'),
    ], string='Health', help='Management judgment, distinct from task completion.')
    percent_complete = fields.Float(
        string='% Complete', compute='_compute_percent_complete', store=True,
        help='Average % complete of non-deferred tasks.')
    last_update = fields.Date(string='Last Update')
    next_milestone = fields.Char(string='Next Milestone')
    top_issue = fields.Text(string='Top Issue / Blocker')
    ids_required = fields.Boolean(string='IDS Required?')
    notes = fields.Text(string='Notes')
    task_ids = fields.One2many('eos.task', 'rock_id', string='Tasks')

    @api.depends('task_ids.status', 'task_ids.percent_complete')
    def _compute_percent_complete(self):
        for rock in self:
            tasks = rock.task_ids.filtered(lambda t: t.status != 'deferred')
            if tasks:
                rock.percent_complete = sum(tasks.mapped('percent_complete')) / len(tasks)
            else:
                rock.percent_complete = 0.0


class EosTask(models.Model):
    _name = 'eos.task'
    _description = 'EOS Task'
    _order = 'rock_id, sequence, id'

    task_id = fields.Char(string='Task ID', help='Original numeric / A / S identifier')
    name = fields.Char(string='Task', required=True)
    sequence = fields.Integer(default=10)
    rock_id = fields.Many2one('eos.rock', string='Rock', ondelete='cascade')
    priority = fields.Selection([
        ('critical', 'Critical'),
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ], string='Priority')
    owner = fields.Char(string='Task Owner')
    due_date = fields.Date(string='Due Date')
    status = fields.Selection([
        ('not_started', 'Not Started'),
        ('on_track', 'On Track'),
        ('at_risk', 'At Risk'),
        ('off_track', 'Off Track'),
        ('complete', 'Complete'),
        ('deferred', 'Deferred'),
    ], string='Status', default='not_started')
    percent_complete = fields.Float(string='% Complete', compute='_compute_percent_complete', store=True)
    dependency = fields.Char(string='Dependency', help='Free-text predecessor reference.')
    critical_path = fields.Selection([
        ('critical', 'Critical'),
        ('parallel', 'Parallel'),
        ('post_launch', 'Post-Launch'),
    ], string='Critical Path')
    task_type = fields.Selection([
        ('source', 'Source Task'),
        ('eos', 'EOS Task'),
    ], string='Task Type')
    health = fields.Selection([
        ('green', 'Green'),
        ('yellow', 'Yellow'),
        ('red', 'Red'),
    ], string='Health', compute='_compute_health', store=True)
    last_update = fields.Date(string='Last Update')
    next_action = fields.Char(string='Next Action')
    blocker = fields.Text(string='Blocker / IDS')
    notes = fields.Text(string='Notes')
    definition_of_done = fields.Text(string='Definition of Done / Completion Criteria')

    @api.depends('status')
    def _compute_percent_complete(self):
        mapping = {
            'not_started': 0.0,
            'on_track': 50.0,
            'at_risk': 50.0,
            'off_track': 50.0,
            'complete': 100.0,
            'deferred': 0.0,
        }
        for task in self:
            task.percent_complete = mapping.get(task.status, 0.0)

    @api.depends('status')
    def _compute_health(self):
        mapping = {
            'not_started': 'green',
            'on_track': 'green',
            'complete': 'green',
            'at_risk': 'yellow',
            'off_track': 'red',
            'deferred': False,
        }
        for task in self:
            task.health = mapping.get(task.status)
