from odoo import api, fields, models


class EosRisk(models.Model):
    _name = 'eos.risk'
    _description = 'EOS Enterprise Risk'
    _order = 'risk_id'

    name = fields.Char(string='Risk', required=True)
    risk_id = fields.Char(string='Risk ID')
    market_id = fields.Many2one('eos.market', string='Market')
    category = fields.Selection([
        ('regulatory', 'Regulatory'),
        ('financial', 'Financial'),
        ('clinical', 'Clinical'),
        ('supply_chain', 'Supply Chain'),
        ('commercial', 'Commercial'),
        ('compliance', 'Compliance'),
        ('operational', 'Operational'),
        ('other', 'Other'),
    ], string='Category')
    probability = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ], string='Probability')
    impact = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ], string='Impact')
    rating = fields.Selection([
        ('green', 'Green'),
        ('yellow', 'Yellow'),
        ('red', 'Red'),
    ], string='Overall Rating', compute='_compute_rating', store=True)
    risk_score = fields.Integer(string='Risk Score', compute='_compute_rating', store=True)
    owner = fields.Char(string='Owner')
    mitigation = fields.Text(string='Mitigation')
    target_resolution = fields.Date(string='Target Resolution')
    trend = fields.Selection([
        ('improving', 'Improving'),
        ('stable', 'Stable'),
        ('worsening', 'Worsening'),
    ], string='Trend', default='stable')
    status = fields.Selection([
        ('resolved', 'Resolved'),
        ('monitoring', 'Monitoring'),
        ('open', 'Open'),
    ], string='Status', default='open')
    last_update = fields.Date(string='Last Update')

    @api.depends('probability', 'impact')
    def _compute_rating(self):
        score_map = {'low': 1, 'medium': 2, 'high': 3}
        for risk in self:
            score = score_map.get(risk.probability, 1) * score_map.get(risk.impact, 1)
            risk.risk_score = score
            if score <= 2:
                risk.rating = 'green'
            elif score <= 4:
                risk.rating = 'yellow'
            else:
                risk.rating = 'red'
