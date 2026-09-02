from odoo import fields, models


class EosPhysician(models.Model):
    _name = 'eos.physician'
    _description = 'EOS Physician / KOL'
    _order = 'name'

    name = fields.Char(string='Physician / KOL', required=True)
    partner_id = fields.Many2one(
        'res.partner', string='Contact', domain=[('is_physician', '=', True)])
    market_id = fields.Many2one('eos.market', string='Market')
    hospital_id = fields.Many2one(
        'res.partner', string='Hospital', domain=[('is_hospital', '=', True)])
    specialty = fields.Char(string='Specialty')
    relationship_stage = fields.Selection([
        ('identified', 'Identified'),
        ('engaged', 'Engaged'),
        ('evaluating', 'Evaluating'),
        ('active', 'Active'),
        ('kol', 'KOL / Advisor'),
    ], string='Relationship Stage', default='identified')
    training_status = fields.Selection([
        ('not_scheduled', 'Not Scheduled'),
        ('scheduled', 'Scheduled'),
        ('trained', 'Trained'),
        ('certified', 'Certified'),
    ], string='Training Status', default='not_scheduled')
    first_case_date = fields.Date(string='First Case Date')
    cases_mtd = fields.Integer(string='Cases MTD')
    cm2_mtd = fields.Float(string='cm2 MTD')
    cases_ytd = fields.Integer(string='Cases YTD')
    cm2_ytd = fields.Float(string='cm2 YTD')
    repeat_user = fields.Boolean(string='Repeat User?')
    owner = fields.Char(string='Owner')
    notes = fields.Text(string='Notes')
