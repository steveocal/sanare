from datetime import timedelta

from odoo import api, fields, models


class EosKpiBoard(models.TransientModel):
    """The 'Current KPI Snapshot' dashboard: live week/month figures for
    every KPI x market, with buttons to lock the current numbers into
    eos.kpi.value history at week or month cadence."""
    _name = 'eos.kpi.board'
    _description = 'EOS Current KPI Snapshot'

    name = fields.Char(default='Current KPI Snapshot')
    as_of_date = fields.Date(
        string='As Of', required=True, default=fields.Date.context_today)
    week_start = fields.Date(string='Week Beginning', compute='_compute_periods')
    week_end = fields.Date(string='Week Ending', compute='_compute_periods')
    month_start = fields.Date(string='Month Beginning', compute='_compute_periods')
    month_end = fields.Date(string='Month Ending', compute='_compute_periods')
    line_ids = fields.One2many(
        'eos.kpi.board.line', 'board_id', string='KPI Measures')

    @api.depends('as_of_date')
    def _compute_periods(self):
        for board in self:
            d = board.as_of_date or fields.Date.context_today(board)
            board.week_start = d - timedelta(days=d.weekday())
            board.week_end = board.week_start + timedelta(days=6)
            board.month_start = d.replace(day=1)
            next_month = board.month_start.replace(day=28) + timedelta(days=4)
            board.month_end = next_month - timedelta(days=next_month.day)

    @api.model
    def default_get(self, field_list):
        res = super().default_get(field_list)
        if 'line_ids' in field_list:
            as_of = res.get('as_of_date') or fields.Date.context_today(self)
            res['line_ids'] = self._build_lines(as_of)
        return res

    def _build_lines(self, as_of):
        week_start = as_of - timedelta(days=as_of.weekday())
        week_end = week_start + timedelta(days=6)
        month_start = as_of.replace(day=1)
        next_month = month_start.replace(day=28) + timedelta(days=4)
        month_end = next_month - timedelta(days=next_month.day)

        commands = []
        kpis = self.env['eos.kpi'].search([('frequency', '!=', False)], order='name')
        markets = self.env['eos.market'].search([])
        for kpi in kpis:
            for market in markets:
                week_val = kpi._compute_live(market, week_start, week_end)
                month_val = kpi._compute_live(market, month_start, month_end)
                commands.append((0, 0, {
                    'kpi_id': kpi.id,
                    'market_id': market.id,
                    'week_value': week_val or 0.0,
                    'week_is_manual': week_val is None,
                    'month_value': month_val or 0.0,
                    'month_is_manual': month_val is None,
                }))
        return commands

    def action_refresh(self):
        self.ensure_one()
        self.write({'line_ids': [(5, 0, 0)] + self._build_lines(self.as_of_date)})

    def action_save_week(self):
        self.ensure_one()
        return self._save_period('week', self.week_start)

    def action_save_month(self):
        self.ensure_one()
        return self._save_period('month', self.month_start)

    def _save_period(self, period_type, period_start):
        Value = self.env['eos.kpi.value']
        for line in self.line_ids:
            value = line.week_value if period_type == 'week' else line.month_value
            existing = Value.search([
                ('period', '=', period_start), ('period_type', '=', period_type),
                ('market_id', '=', line.market_id.id), ('kpi_id', '=', line.kpi_id.id),
            ], limit=1)
            if existing:
                existing.value = value
            else:
                Value.create({
                    'period': period_start,
                    'period_type': period_type,
                    'market_id': line.market_id.id,
                    'kpi_id': line.kpi_id.id,
                    'value': value,
                })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'KPI Snapshot Saved',
                'message': '%s of %s locked into KPI history (%s rows).' % (
                    period_type.capitalize(), period_start, len(self.line_ids)),
                'type': 'success',
                'sticky': False,
            },
        }


class EosKpiBoardLine(models.TransientModel):
    _name = 'eos.kpi.board.line'
    _description = 'EOS Current KPI Snapshot Line'
    _order = 'kpi_id, market_id'

    board_id = fields.Many2one(
        'eos.kpi.board', string='Snapshot', ondelete='cascade', required=True)
    kpi_id = fields.Many2one('eos.kpi', string='KPI', required=True, readonly=True)
    market_id = fields.Many2one(
        'eos.market', string='Market', required=True, readonly=True)
    source = fields.Char(related='kpi_id.source', string='Source')
    week_value = fields.Float(string='Week (calc)')
    week_is_manual = fields.Boolean(
        string='Week Manual?',
        help='No live formula for this KPI/period - enter the confirmed figure.')
    month_value = fields.Float(string='Month (calc)')
    month_is_manual = fields.Boolean(
        string='Month Manual?',
        help='No live formula for this KPI/period - enter the confirmed figure.')
