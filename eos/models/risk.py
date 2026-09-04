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
    risk_score = fields.Integer(
        string='Risk Score', compute='_compute_rating', store=True, aggregator='avg')
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
            if not risk.probability or not risk.impact:
                # Unrated risk: leave blank, mirroring the workbook's IF(C="","",...)
                risk.risk_score = 0
                risk.rating = False
                continue
            score = score_map[risk.probability] * score_map[risk.impact]
            risk.risk_score = score
            if score >= 6:
                risk.rating = 'red'
            elif score >= 3:
                risk.rating = 'yellow'
            else:
                risk.rating = 'green'

    @api.model
    def _get_top_risk(self, market=None):
        """The single highest-priority open risk: highest risk_score, and
        among ties, whichever was logged first (id ascending - the same
        tie-break as the workbook's row-order hack, without needing one).
        Replaces the source formula's INDEX/MATCH/LARGE lookup against the
        Priority Helper column; call .mitigation / .name / etc on the
        result, which is an empty recordset (falsy, blank fields) if there
        are no open risks."""
        domain = [('status', '!=', 'resolved')]
        if market:
            domain.append(('market_id', '=', market.id))
        return self.search(domain, order='risk_score desc, id asc', limit=1)
