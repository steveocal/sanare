from odoo import models


class EosKpi(models.Model):
    """Financial KPIs, sourced from eos.financial.period rather than raw
    move lines - keeps the KPI board reconciled to the same monthly
    snapshot used by the Financial Position / Investor reports."""
    _inherit = 'eos.kpi'

    def _period_for(self, company, date_to):
        return self.env['eos.financial.period'].search([
            ('company_id', '=', company.id),
            ('date_from', '<=', date_to), ('date_to', '>=', date_to),
        ], limit=1)

    def _live_cash_on_hand(self, market, date_from, date_to):
        period = self._period_for(self.env.company, date_to)
        return period.ending_cash if period else None

    def _live_monthly_net_burn(self, market, date_from, date_to):
        period = self._period_for(self.env.company, date_to)
        return period.net_cash_burn if period else None

    def _live_runway(self, market, date_from, date_to):
        period = self._period_for(self.env.company, date_to)
        return period.runway_months if period else None

    def _live_gross_margin(self, market, date_from, date_to):
        period = self._period_for(self.env.company, date_to)
        return period.gross_margin_pct if period else None
