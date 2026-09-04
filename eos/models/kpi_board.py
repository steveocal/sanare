from datetime import timedelta

from odoo import api, fields, models


class EosKpiBoard(models.TransientModel):
    """The 'Current KPI Snapshot' dashboard: for one market and one cadence
    (week or month):
      - Previous Period: the saved history value for the period before the
        one below (pure reference, read-only).
      - This Period: the latest period actually locked into KPI History -
        fully editable (including a note), and what Save writes back to
        history. Between period-end cron runs this is normally the period
        that just closed; it's also where a human corrects a cron-computed
        figure or fills in a KPI that has no live formula.
      - Current Period (to date): the period in progress as of "As Of",
        live-calculated for reference only - not itself saved. The
        week/month-end cron is what turns "current" into "this period" at
        the boundary.
    """
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

    prev_period_start = fields.Date(string='Previous Period Began', compute='_compute_periods')
    prev_period_end = fields.Date(string='Previous Period Ended', compute='_compute_periods')
    this_period_start = fields.Date(string='This Period Began', compute='_compute_periods')
    this_period_end = fields.Date(string='This Period Ended', compute='_compute_periods')
    current_period_start = fields.Date(string='Current Period Began', compute='_compute_periods')
    current_period_end = fields.Date(string='Current, To Date', compute='_compute_periods')

    line_ids = fields.One2many(
        'eos.kpi.board.line', 'board_id', string='KPI Measures')

    @api.depends('as_of_date', 'period_type', 'market_id')
    def _compute_periods(self):
        for board in self:
            if not board.market_id:
                board.prev_period_start = board.prev_period_end = False
                board.this_period_start = board.this_period_end = False
                board.current_period_start = board.current_period_end = False
                continue
            this_start, this_end, cur_start, cur_end, prev_start, prev_end = \
                board._resolve_periods(board.market_id, board.period_type, board.as_of_date)
            board.this_period_start, board.this_period_end = this_start, this_end
            board.current_period_start, board.current_period_end = cur_start, cur_end
            board.prev_period_start, board.prev_period_end = prev_start, prev_end

    def _resolve_periods(self, market, period_type, as_of):
        """Work out This/Current/Previous the same way for the form's
        display fields and for _build_lines."""
        Kpi = self.env['eos.kpi']
        as_of = as_of or fields.Date.context_today(self)
        cur_start, cur_end = Kpi._period_bounds(period_type, as_of)

        latest = self.env['eos.kpi.value'].search([
            ('market_id', '=', market.id), ('period_type', '=', period_type),
        ], order='period desc', limit=1)
        if latest:
            this_start, this_end = latest.period, latest.period_end
        else:
            this_start, this_end = Kpi._period_before(period_type, cur_start)

        prev_start, prev_end = Kpi._period_before(period_type, this_start)
        return this_start, this_end, cur_start, cur_end, prev_start, prev_end

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
        this_start, this_end, cur_start, cur_end, prev_start, __prev_end = \
            self._resolve_periods(market, period_type, as_of)

        Value = self.env['eos.kpi.value']
        Kpi = self.env['eos.kpi']

        def value_at(period_start):
            return Value.search([
                ('period', '=', period_start), ('period_type', '=', period_type),
                ('market_id', '=', market.id), ('kpi_id', '=', kpi.id),
            ], limit=1)

        commands = []
        for kpi in Kpi.search([('frequency', '!=', False)], order='name'):
            prev_row = value_at(prev_start)
            this_row = value_at(this_start)
            current_live = kpi._compute_live(market, cur_start, cur_end)
            commands.append((0, 0, {
                'kpi_id': kpi.id,
                'previous_value': prev_row.value if prev_row else 0.0,
                'previous_exists': bool(prev_row),
                'this_value': this_row.value if this_row else 0.0,
                'this_notes': this_row.notes if this_row else False,
                'this_exists': bool(this_row),
                'current_value': current_live or 0.0,
                'current_is_manual': current_live is None,
            }))
        return commands

    def action_refresh(self):
        self.ensure_one()
        if not self.market_id:
            return
        self.write({'line_ids': [(5, 0, 0)] + self._build_lines(
            self.market_id, self.period_type, self.as_of_date)})

    def action_save_this_period(self):
        self.ensure_one()
        Value = self.env['eos.kpi.value']
        for line in self.line_ids:
            Value._upsert(
                self.market_id, line.kpi_id, self.period_type,
                self.this_period_start, line.this_value, notes=line.this_notes or False)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'KPI History Updated',
                'message': '%s of %s saved for %s (%s rows).' % (
                    self.period_type.capitalize(), self.this_period_start,
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
        help='Whether a value was actually locked into history for the '
             'previous period, as opposed to defaulting to zero.')

    this_value = fields.Float(
        string='This Period',
        help='The period last locked into KPI History. Freely editable - '
             'correct a cron-computed figure or fill in a KPI with no live '
             'formula, then Save to History.')
    this_notes = fields.Text(string='Notes')
    this_exists = fields.Boolean(
        string='Already Saved?',
        help='Whether this period already has a history row (from the '
             'week/month-end cron or a previous save) or Save will create one.')

    current_value = fields.Float(
        string='Current, To Date', readonly=True,
        help='Live figure for the period in progress, as of the As Of date. '
             'Reference only - the week/month-end cron locks this into '
             'history once the period actually ends.')
    current_is_manual = fields.Boolean(
        string='No Formula?',
        help='No live formula for this KPI - it will need a manual figure '
             'once this period closes.')
