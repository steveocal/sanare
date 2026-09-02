from odoo import fields, models


class EosKpi(models.Model):
    _name = 'eos.kpi'
    _description = 'EOS KPI Dictionary'
    _order = 'name'

    name = fields.Char(string='KPI', required=True)
    code = fields.Char(string='Code', required=True)
    definition = fields.Text(string='Definition')
    calculation = fields.Text(string='Calculation / Logic')
    source = fields.Char(string='Primary Source')
    owner = fields.Char(string='Owner')
    frequency = fields.Selection([
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('weekly_monthly', 'Weekly / Monthly'),
    ], string='Frequency')
    target = fields.Char(string='Target / Threshold')
    report_section = fields.Char(string='Report Section')
    notes = fields.Text(string='Notes')


class EosKpiValue(models.Model):
    _name = 'eos.kpi.value'
    _description = 'EOS KPI Monthly Value (History)'
    _order = 'period desc, market_id, kpi_id'

    period = fields.Date(string='Month', required=True)
    market_id = fields.Many2one('eos.market', string='Market', required=True)
    kpi_id = fields.Many2one('eos.kpi', string='KPI', required=True)
    value = fields.Float(string='Value', aggregator='sum')
    notes = fields.Text(string='Notes')

    _period_market_kpi_uniq = models.Constraint(
        'unique(period, market_id, kpi_id)',
        'Only one KPI value per market per month.',
    )
