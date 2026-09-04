from datetime import timedelta

from odoo import api, fields, models


class EosKpiBoard(models.TransientModel):
    """The 'Current KPI Snapshot' dashboard: for one market and one cadence
    (week or month), show the last locked period's actual next to the
    current period's live figure (to date), with a button to lock the
    current period into eos.kpi.value history."""
    _name = 'eos.kpi.board'
    _description = 'EOS Current KPI Snapshot'

    name = fields.Char(default='Current KPI Snapshot')
    market_id = fields.Many2one(
        'eos.market', string='Market', required=True,
        default=lambda self: self.env['eos.market'].search([], limit=1).id)
    period_type = fields.Selection([
        ('week', 'Weekly'),
        ('month', 'Monthly'),
    ], string='Period', required=True, default='month')
    as_of_date = fields.Date(
        string='As Of', required=True, default=fields.Date.context_today)

    period_start = fields.Date(
        string='This Period Began', compute='_compute_periods')
    period_end = fields.Date(
        string='To Date', compute='_compute_periods')
    prev_period_start = fields.Date(
        string='Previous Period Began', compute='_compute_periods')
    prev_period_end = fields.Date(
        string='Previous Period Ended', compute='_compute_periods')

    line_ids = fields.One2many(
        'eos.kpi.board.line', 'board_id', string='KPI Measures')

    @api.depends('as_of_date', 'period_type')
    def _compute_periods(self):
        for board in self:
            start, end, prev_start, prev_end = board._period_bounds(
                board.period_type, board.as_of_date)
            board.period_start = start
            board.period_end = end
            board.prev_period_start = prev_start
            board.prev_period_end = prev_end

    @api.model
    def _period_bounds(self, period_type, as_of):
        d = as_of or fields.Date.context_today(self)
        if period_type == 'week':
            start = d - timedelta(days=d.weekday())
            end = start + timedelta(days=6)
            prev_end = start - timedelta(days=1)
            prev_start = prev_end - timedelta(days=6)
        else:
            start = d.replace(day=1)
            next_month = start.replace(day=28) + timedelta(days=4)
            end = next_month - timedelta(days=next_month.day)
            prev_end = start - timedelta(days=1)
            prev_start = prev_end.replace(day=1)
        return start, end, prev_start, prev_end

    @api.model
    def default_get(self, field_list):
        res = super().default_get(field_list)
        if 'line_ids' in field_list:
            market_id = (res.get('market_id')
                         or self.env.context.get('default_market_id')
                         or self.env['eos.market'].search([], limit=1).id)
            period_type = (res.get('period_type')
                           or self.env.context.get('default_period_type') or 'month')
            as_of = (res.get('as_of_date')
                     or self.env.context.get('default_as_of_date')
                     or fields.Date.context_today(self))
            if isinstance(as_of, str):
                as_of = fields.Date.from_string(as_of)
            if market_id:
                market = self.env['eos.market'].browse(market_id)
                res['line_ids'] = self._build_lines(market, period_type, as_of)
        return res

    @api.onchange('market_id', 'period_type', 'as_of_date')
    def _onchange_refresh(self):
        for board in self:
            if board.market_id:
                board.line_ids = [(5, 0, 0)] + board._build_lines(
                    board.market_id, board.period_type,
                    board.as_of_date or fields.Date.context_today(board))

    def _build_lines(self, market, period_type, as_of):
        start, end, prev_start, _prev_end = self._period_bounds(
            period_type, as_of)
        Value = self.env['eos.kpi.value']
        commands = []
        kpis = self.env['eos.kpi'].search([('frequency', '!=', False)], order='name')
        for kpi in kpis:
            current = kpi._compute_live(market, start, end)
            prev_row = Value.search([
                ('period', '=', prev_start), ('period_type', '=', period_type),
                ('market_id', '=', market.id), ('kpi_id', '=', kpi.id),
            ], limit=1)
            commands.append((0, 0, {
                'kpi_id': kpi.id,
                'previous_value': prev_row.value if prev_row else 0.0,
                'previous_exists': bool(prev_row),
                'current_value': current or 0.0,
                'is_manual': current is None,
            }))
        return commands

    def action_refresh(self):
        self.ensure_one()
        if not self.market_id:
            return
        self.write({'line_ids': [(5, 0, 0)] + self._build_lines(
            self.market_id, self.period_type, self.as_of_date)})

    def action_save_period(self):
        self.ensure_one()
        Value = self.env['eos.kpi.value']
        for line in self.line_ids:
            existing = Value.search([
                ('period', '=', self.period_start), ('period_type', '=', self.period_type),
                ('market_id', '=', self.market_id.id), ('kpi_id', '=', line.kpi_id.id),
            ], limit=1)
            if existing:
                existing.value = line.current_value
            else:
                Value.create({
                    'period': self.period_start,
                    'period_type': self.period_type,
                    'market_id': self.market_id.id,
                    'kpi_id': line.kpi_id.id,
                    'value': line.current_value,
                })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'KPI Snapshot Saved',
                'message': '%s of %s locked for %s (%s rows).' % (
                    self.period_type.capitalize(), self.period_start,
                    self.market_id.name, len(self.line_ids)),
                'type': 'success',
                'sticky': False,
            },
        }


class EosKpiBoardLine(models.TransientModel):
    _name = 'eos.kpi.board.line'
    _description = 'EOS Current KPI Snapshot Line'
    _order = 'kpi_id'

    board_id = fields.Many2one(
        'eos.kpi.board', string='Snapshot', ondelete='cascade', required=True)
    kpi_id = fields.Many2one('eos.kpi', string='KPI', required=True, readonly=True)
    source = fields.Char(related='kpi_id.source', string='Source')
    previous_value = fields.Float(string='Previous Period', readonly=True)
    previous_exists = fields.Boolean(
        string='Previous Saved?',
        help='Whether a prior-period value was actually locked into history, '
             'as opposed to defaulting to zero.')
    current_value = fields.Float(string='This Period (to date)')
    is_manual = fields.Boolean(
        string='Manual?',
        help='No live formula for this KPI - enter the confirmed figure.')
