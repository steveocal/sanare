# -*- coding: utf-8 -*-
"""Helpers on ``eos.monthly.report`` used by the Report 01-09 QWeb templates.

The templates query the ``eos.*`` models directly (like eos_account's
``report_investor``); these helpers cover the few things that need Python:
the Thailand readiness engine, the active quarter, and the period label.
"""
from odoo import api, fields, models

from .readiness_engine import compute_thailand_readiness
from .thailand_readiness import task_rows_from_db

_QUARTER_LABEL = {"q1": "Q1", "q2": "Q2", "q3": "Q3", "q4": "Q4"}


class EosMonthlyReport(models.Model):
    _inherit = "eos.monthly.report"

    def _period_label(self):
        self.ensure_one()
        d = self.reporting_month or fields.Date.context_today(self)
        return d.strftime("%B %Y")

    def _report_quarter(self):
        """Best available EOS quarter for rock filtering."""
        self.ensure_one()
        if self.active_quarter:
            return self.active_quarter
        if self.current_quarter:
            return self.current_quarter
        d = self.reporting_month or fields.Date.context_today(self)
        # workbook: Q1 = Aug-Oct, Q2 = Nov-Jan, Q3 = Feb-Apr, Q4 = May-Jul
        return {8: "q1", 9: "q1", 10: "q1", 11: "q2", 12: "q2", 1: "q2",
                2: "q3", 3: "q3", 4: "q3", 5: "q4", 6: "q4", 7: "q4"}.get(d.month, "q1")

    def _quarter_label(self):
        return _QUARTER_LABEL.get(self._report_quarter(), "")

    def _thailand_readiness_data(self):
        """Report 03 payload - see ``readiness_engine.compute_thailand_readiness``."""
        self.ensure_one()
        as_of = self.reporting_month or fields.Date.context_today(self)
        return compute_thailand_readiness(task_rows_from_db(self.env), today=as_of)

    def _financial_period(self):
        self.ensure_one()
        return self.financial_period_id or self.env["eos.financial.period"].search(
            [], order="date_to desc", limit=1)

    @api.model
    def action_print_monthly_pack(self):
        """Menu entry: print the pack for the most recent monthly report."""
        report = self.search([], order="reporting_month desc", limit=1)
        if not report:
            report = self.create({"reporting_month": fields.Date.context_today(self)})
        return self.env.ref("eos_dashboard.action_report_monthly_pack").report_action(report)
