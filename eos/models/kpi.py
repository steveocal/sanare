from datetime import timedelta

from odoo import api, fields, models


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

    # ------------------------------------------------------------------
    # Live computation. Each module that owns the underlying data
    # (eos, eos_account, ...) extends this method: check self.code for the
    # codes it knows how to compute, otherwise fall back to super(). A KPI
    # whose code isn't handled anywhere returns None - the board/history UI
    # then treats it as a manual figure (matching the source workbook, which
    # flags several of these as "enter confirmed total" until a finer-grained
    # log exists).
    #
    # date_from/date_to bound the requested period (a calendar week or
    # month around the "as of" date). Most of these KPIs are point-in-time
    # gauges (active hospitals, pipeline, readiness...) evaluated as of
    # date_to regardless of cadence - that's intentional, not a bug: a
    # snapshot taken weekly and one taken monthly read the same live state,
    # they just get saved at a different cadence. A few (cases, cm2 used)
    # only exist as physician-level month-to-date counters in this system
    # (no case-level log), so the week figure reuses the same MTD counter -
    # documented on the KPI record itself.
    # ------------------------------------------------------------------
    def _compute_live(self, market, date_from, date_to):
        """Return the live value of this KPI for one market/window, or None
        if it can only be entered manually."""
        self.ensure_one()
        method = getattr(self, '_live_%s' % self.code, None)
        if method:
            return method(market, date_from, date_to)
        return None

    def _live_cm2_used(self, market, date_from, date_to):
        physicians = self.env['eos.physician'].search([('market_id', '=', market.id)])
        return sum(physicians.mapped('cm2_mtd'))

    def _live_cases(self, market, date_from, date_to):
        physicians = self.env['eos.physician'].search([('market_id', '=', market.id)])
        return sum(physicians.mapped('cases_mtd'))

    def _live_active_hospitals(self, market, date_from, date_to):
        leads = self.env['crm.lead'].search([
            ('market_id', '=', market.id), ('ordering', '=', True),
        ])
        return len(leads.mapped('hospital_id'))

    def _live_active_physicians(self, market, date_from, date_to):
        return self.env['eos.physician'].search_count([
            ('market_id', '=', market.id), ('cases_ytd', '>', 0),
        ])

    def _live_qualified_pipeline_cm2(self, market, date_from, date_to):
        leads = self.env['crm.lead'].search([
            ('market_id', '=', market.id), ('probability', '>=', 50),
            ('active', '=', True),
        ])
        return sum(l.est_annual_cm2 * l.probability / 100.0 for l in leads)

    def _live_reorder_rate(self, market, date_from, date_to):
        ordering = self.env['crm.lead'].search_count([
            ('market_id', '=', market.id), ('ordering', '=', True),
        ])
        if not ordering:
            return 0.0
        repeat = self.env['crm.lead'].search_count([
            ('market_id', '=', market.id), ('repeat_ordering', '=', True),
        ])
        return repeat / ordering * 100.0

    def _live_weeks_of_supply(self, market, date_from, date_to):
        skus = self.env['eos.sku'].search([('market_id', '=', market.id)])
        return sum(skus.mapped('weeks_supply')) / len(skus) if skus else 0.0

    def _live_open_critical_regulatory_issues(self, market, date_from, date_to):
        keywords = ['regulat', 'tfda', 'approval', 'import']
        domain = [
            ('rock_id.market_id', '=', market.id),
            ('priority', '=', 'critical'),
            ('status', 'in', ('at_risk', 'off_track')),
        ]
        tasks = self.env['eos.task'].search(domain)
        return len(tasks.filtered(
            lambda t: any(k in (t.name or '').lower() for k in keywords)))

    def _live_rocks_on_track(self, market, date_from, date_to):
        rocks = self.env['eos.rock'].search([('market_id', '=', market.id)])
        if not rocks:
            return 0.0
        on_track = rocks.filtered(lambda r: r.status in ('on_track', 'complete'))
        return len(on_track) / len(rocks) * 100.0

    def _live_thailand_launch_readiness(self, market, date_from, date_to):
        return self._readiness_for_market_code('TH')

    def _live_singapore_launch_readiness(self, market, date_from, date_to):
        return self._readiness_for_market_code('SG')

    def _readiness_for_market_code(self, code):
        workstreams = self.env['eos.launch.workstream'].search(
            [('market_id.code', '=ilike', code)])
        total_weight = sum(workstreams.mapped('weight'))
        if not total_weight:
            return 0.0
        return sum(w.readiness * w.weight for w in workstreams) / total_weight


class EosKpiValue(models.Model):
    _name = 'eos.kpi.value'
    _description = 'EOS KPI Value (History)'
    _order = 'period desc, period_type, market_id, kpi_id'

    period_type = fields.Selection([
        ('week', 'Week'),
        ('month', 'Month'),
    ], string='Type', required=True, default='month')
    period = fields.Date(
        string='Period Start', required=True,
        help='First day of the week (Monday) or month this value was saved for.')
    period_end = fields.Date(
        string='Period End', compute='_compute_period_end', store=True)
    market_id = fields.Many2one('eos.market', string='Market', required=True)
    kpi_id = fields.Many2one('eos.kpi', string='KPI', required=True)
    value = fields.Float(string='Value', aggregator='sum')
    notes = fields.Text(string='Notes')

    _period_market_kpi_uniq = models.Constraint(
        'unique(period, period_type, market_id, kpi_id)',
        'Only one KPI value per market, period type and period start.',
    )

    @api.depends('period', 'period_type')
    def _compute_period_end(self):
        for rec in self:
            if not rec.period:
                rec.period_end = False
            elif rec.period_type == 'week':
                rec.period_end = rec.period + timedelta(days=6)
            else:
                next_month = rec.period.replace(day=28) + timedelta(days=4)
                rec.period_end = next_month - timedelta(days=next_month.day)
