from odoo import fields, models


class EosMarket(models.Model):
    _name = 'eos.market'
    _description = 'EOS Market / Entity'
    _order = 'code'

    name = fields.Char(string='Market', required=True)
    code = fields.Char(string='Code', required=True, help="Short code, e.g. TH / SG")
    country_id = fields.Many2one('res.country', string='Country')
    active = fields.Boolean(default=True)
