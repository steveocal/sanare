from odoo import fields, models


class CrmStage(models.Model):
    _inherit = 'crm.stage'

    sanare_stage = fields.Selection([
        ('identified', 'Identified'),
        ('engaged', 'Engaged'),
        ('evaluating', 'Evaluating'),
        ('contracting', 'Contracting'),
        ('approved', 'Approved'),
        ('ordering', 'Ordering'),
        ('repeat_ordering', 'Repeat Ordering'),
    ], string='Sanare Stage')
    sanare_probability = fields.Float(string='Sanare Default Probability %')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_hospital = fields.Boolean(string='Is Hospital')
    is_physician = fields.Boolean(string='Is Physician / KOL')
    market_id = fields.Many2one('eos.market', string='Market')
    hospital_type = fields.Selection([
        ('public', 'Public'),
        ('private', 'Private'),
        ('university', 'University'),
        ('other', 'Other'),
    ], string='Hospital Type')
    vendor_registration_status = fields.Selection([
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('complete', 'Complete'),
    ], string='Vendor Registration')


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    market_id = fields.Many2one('eos.market', string='Market')
    hospital_id = fields.Many2one(
        'res.partner', string='Hospital / Account', domain=[('is_hospital', '=', True)])
    primary_physician_id = fields.Many2one('eos.physician', string='Primary Physician / KOL')
    est_annual_cm2 = fields.Float(string='Est. Annual cm2')
    expected_first_order = fields.Date(string='Expected First Order')
    contracted = fields.Boolean(string='Contracted?')
    ordering = fields.Boolean(string='Ordering?')
    repeat_ordering = fields.Boolean(string='Repeat Ordering?')
    next_action = fields.Char(string='Next Action')
    sanare_stage = fields.Selection(
        related='stage_id.sanare_stage', string='Sanare Stage', readonly=True)
