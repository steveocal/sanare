# -*- coding: utf-8 -*-
"""On-screen dashboards for every monthly-report tab (01-09).

One generic model, ``eos.dashboard.board``, keyed by ``report_key``. Each board
renders the *same* body template as the printed report (``report_NN_body``) into
an HTML field so the screen matches the PDF, keeps three headline metrics for
the history/trend list + graph, and exposes the monthly-report commentary
fields for inline editing.

Report 03 keeps its own dedicated board (``eos.thailand.readiness``) as well -
this model's ``thailand`` key is the consistent entry in the Dashboards menu.
"""
from datetime import date

from odoo import api, fields, models

REPORT_KEYS = [
    ("exec", "01 · Executive"),
    ("eos", "02 · EOS Execution"),
    ("thailand", "03 · Thailand Readiness"),
    ("commercial", "04 · Commercial"),
    ("clinical", "05 · Clinical & KOL"),
    ("reg_supply", "06 · Regulatory & Supply"),
    ("financial", "07 · Financial"),
    ("use_of_funds", "08 · Use of Funds"),
    ("risks", "09 · Enterprise Risks"),
]

# report_key -> printed report action xml id (for the "Print PDF" button)
_PRINT_ACTION = {
    "exec": "action_report_01_executive",
    "eos": "action_report_02_eos",
    "thailand": "action_report_03_thailand_monthly",
    "commercial": "action_report_04_commercial",
    "clinical": "action_report_05_clinical",
    "reg_supply": "action_report_06_reg_supply",
    "financial": "action_report_07_financial",
    "use_of_funds": "action_report_08_use_of_funds",
    "risks": "action_report_09_risks",
}


class EosDashboardBoard(models.Model):
    _name = "eos.dashboard.board"
    _description = "EOS Dashboard Board"
    _order = "report_key, reporting_month desc, id desc"

    report_key = fields.Selection(REPORT_KEYS, string="Report", required=True, index=True)
    name = fields.Char(compute="_compute_name", store=True)
    monthly_report_id = fields.Many2one(
        "eos.monthly.report", string="Monthly Report",
        help="Data context for this board. Defaults to the most recent monthly report.")
    reporting_month = fields.Date(
        related="monthly_report_id.reporting_month", store=True, string="Month")
    period_label = fields.Char(compute="_compute_name", store=True)
    as_of_date = fields.Date(
        string="As of", required=True, default=fields.Date.context_today,
        help="Only affects Report 03's Health column (the spreadsheet's TODAY()).")
    computed_on = fields.Datetime(
        string="Last Computed", compute="_compute_metrics", store=True)

    board_html = fields.Html(
        string="Dashboard", sanitize=False, compute="_compute_board_html")

    primary_label = fields.Char(compute="_compute_metrics", store=True)
    primary_metric = fields.Float(compute="_compute_metrics", store=True, aggregator="avg")
    secondary_label = fields.Char(compute="_compute_metrics", store=True)
    secondary_metric = fields.Float(compute="_compute_metrics", store=True, aggregator="avg")
    tertiary_label = fields.Char(compute="_compute_metrics", store=True)
    tertiary_metric = fields.Float(compute="_compute_metrics", store=True, aggregator="avg")

    # ------------------------------------------------------------------
    # Native-widget report fields (replace the injected board_html for the
    # on-screen view). Non-stored, always live - same fidelity characteristic
    # as board_html/_headline_metrics before them: current state, not a
    # dated snapshot, except where the source helper is itself month-scoped
    # (_financial_period, _thailand_readiness_data).
    currency_id = fields.Many2one("res.currency", compute="_compute_report_fields")

    # 01 · Executive
    exec_overall_health = fields.Char(compute="_compute_report_fields")
    exec_thailand_readiness_pct = fields.Float(compute="_compute_report_fields")
    exec_active_quarter = fields.Char(compute="_compute_report_fields")
    exec_report_status = fields.Char(compute="_compute_report_fields")
    exec_rocks_on_track = fields.Integer(compute="_compute_report_fields")
    exec_rocks_at_risk = fields.Integer(compute="_compute_report_fields")
    exec_ending_cash = fields.Monetary(compute="_compute_report_fields", currency_field="currency_id")
    exec_runway_months = fields.Float(compute="_compute_report_fields")
    exec_hospitals_engaged = fields.Integer(compute="_compute_report_fields")
    exec_hospitals_ordering = fields.Integer(compute="_compute_report_fields")
    exec_qualified_pipeline_cm2 = fields.Float(compute="_compute_report_fields")

    # 02 · EOS Execution
    eos_rocks_on_track = fields.Integer(compute="_compute_report_fields")
    eos_rocks_at_risk = fields.Integer(compute="_compute_report_fields")
    eos_rocks_off_track = fields.Integer(compute="_compute_report_fields")
    eos_rocks_complete = fields.Integer(compute="_compute_report_fields")
    rock_ids = fields.Many2many("eos.rock", compute="_compute_report_fields")

    # 04 · Commercial
    commercial_qualified_pipeline_cm2 = fields.Float(compute="_compute_report_fields")
    commercial_ordering_hospitals = fields.Integer(compute="_compute_report_fields")
    commercial_stage_identified = fields.Integer(compute="_compute_report_fields")
    commercial_stage_engaged = fields.Integer(compute="_compute_report_fields")
    commercial_stage_evaluating = fields.Integer(compute="_compute_report_fields")
    commercial_stage_contracting = fields.Integer(compute="_compute_report_fields")
    commercial_stage_approved = fields.Integer(compute="_compute_report_fields")
    commercial_stage_ordering = fields.Integer(compute="_compute_report_fields")
    commercial_stage_repeat_ordering = fields.Integer(compute="_compute_report_fields")
    commercial_stage_contracted = fields.Integer(compute="_compute_report_fields")
    pipeline_lead_ids = fields.Many2many("crm.lead", compute="_compute_report_fields")

    # 05 · Clinical & KOL
    clinical_kol_count = fields.Integer(compute="_compute_report_fields")
    clinical_active_count = fields.Integer(compute="_compute_report_fields")
    clinical_trained_certified = fields.Integer(compute="_compute_report_fields")
    clinical_cases_ytd = fields.Integer(compute="_compute_report_fields")
    clinical_cm2_ytd = fields.Float(compute="_compute_report_fields")
    physician_ids = fields.Many2many("eos.physician", compute="_compute_report_fields")

    # 06 · Regulatory & Supply
    reg_status = fields.Char(compute="_compute_report_fields")
    reg_tasks_complete = fields.Integer(compute="_compute_report_fields")
    reg_tasks_open = fields.Integer(compute="_compute_report_fields")
    reg_percent_complete = fields.Float(compute="_compute_report_fields")
    regulatory_task_ids = fields.Many2many("eos.task", compute="_compute_report_fields")
    sku_ids = fields.Many2many("eos.sku", compute="_compute_report_fields")

    # 07 · Financial / 08 · Use of Funds (financial_period_id is shared).
    # Plain computed (not related=) - financial_period_id is itself a
    # non-stored compute field, and Odoo can't build a recompute-dependency
    # graph through a non-searchable related target. Setting these directly
    # in _compute_report_fields sidesteps that entirely.
    financial_period_id = fields.Many2one("eos.financial.period", compute="_compute_report_fields")
    fp_ending_cash = fields.Monetary(
        compute="_compute_report_fields", currency_field="currency_id", string="Ending Cash")
    fp_available_capital = fields.Monetary(
        compute="_compute_report_fields", currency_field="currency_id", string="Available Capital")
    fp_net_cash_burn = fields.Monetary(
        compute="_compute_report_fields", currency_field="currency_id", string="Net Cash Burn")
    fp_runway_months = fields.Float(compute="_compute_report_fields", string="Runway (Months)")
    fp_gross_margin_pct = fields.Float(compute="_compute_report_fields", string="Gross Margin %")
    fp_capital_received = fields.Monetary(
        compute="_compute_report_fields", currency_field="currency_id", string="Capital Received")
    fp_committed_unspent = fields.Monetary(
        compute="_compute_report_fields", currency_field="currency_id", string="Committed but Unspent")
    financial_line_ids = fields.Many2many("eos.financial.period.line", compute="_compute_report_fields")

    # 08 · Use of Funds
    use_of_funds_ids = fields.Many2many("eos.use.of.funds", compute="_compute_report_fields")

    # 09 · Enterprise Risks
    risks_open_red = fields.Integer(compute="_compute_report_fields")
    risks_open_yellow = fields.Integer(compute="_compute_report_fields")
    risks_worsening = fields.Integer(compute="_compute_report_fields")
    top_risk_ids = fields.Many2many("eos.risk", compute="_compute_report_fields")

    # editable, write-through to the monthly report
    executive_summary = fields.Text(related="monthly_report_id.executive_summary", readonly=False)
    what_went_well = fields.Text(related="monthly_report_id.what_went_well", readonly=False)
    misses_slippage = fields.Text(related="monthly_report_id.misses_slippage", readonly=False)
    corrective_actions = fields.Text(related="monthly_report_id.corrective_actions", readonly=False)
    key_decisions = fields.Text(related="monthly_report_id.key_decisions", readonly=False)

    _key_report_uniq = models.Constraint(
        "unique(report_key, monthly_report_id)",
        "There is already a dashboard board for this report tab and month.")

    # ------------------------------------------------------------------
    @api.depends("report_key", "monthly_report_id.reporting_month")
    def _compute_name(self):
        labels = dict(REPORT_KEYS)
        for b in self:
            d = b.monthly_report_id.reporting_month
            b.period_label = d.strftime("%B %Y") if d else ""
            b.name = "%s — %s" % (labels.get(b.report_key, b.report_key or ""),
                                       b.period_label or "no period")

    def _render_ctx(self, o):
        ctx = {"o": o, "docs": o, "report_key": self.report_key}
        if self.report_key == "thailand":
            ctx.update(d=o._thailand_readiness_data(),
                       c_changed=o.executive_summary, c_actions=o.corrective_actions)
        return ctx

    @api.depends("report_key", "as_of_date", "monthly_report_id",
                 "monthly_report_id.executive_summary", "monthly_report_id.what_went_well",
                 "monthly_report_id.misses_slippage", "monthly_report_id.corrective_actions",
                 "monthly_report_id.key_decisions")
    def _compute_board_html(self):
        for b in self:
            o = b.monthly_report_id
            if not o or not b.report_key:
                b.board_html = (
                    "<p style='color:#8a94a0;font-style:italic'>Link a Monthly Report "
                    "(EOS &#9656; Reporting &#9656; Monthly Reports) to populate this dashboard.</p>")
                continue
            b.board_html = self.env["ir.qweb"]._render(
                "eos_dashboard.board_screen_doc", b._render_ctx(o))

    def _headline_metrics(self, o):
        """Return [(label, value), (label, value), (label, value)] for report_key."""
        env = self.env
        Rock = env["eos.rock"]
        Lead = env["crm.lead"]
        Risk = env["eos.risk"]
        Phys = env["eos.physician"]
        Sku = env["eos.sku"]
        q = o._report_quarter()
        k = self.report_key
        if k == "exec":
            return [("Thailand Readiness %", o._thailand_readiness_data()["overall_readiness"] * 100.0),
                    ("Rocks On Track", Rock.search_count([("quarter", "=", q), ("status", "=", "on_track")])),
                    ("Runway (Months)", o.runway_months or 0.0)]
        if k == "eos":
            return [("Rocks On Track", Rock.search_count([("quarter", "=", q), ("status", "=", "on_track")])),
                    ("Rocks At Risk", Rock.search_count([("quarter", "=", q), ("status", "=", "at_risk")])),
                    ("Rocks Off Track", Rock.search_count([("quarter", "=", q), ("status", "=", "off_track")]))]
        if k == "thailand":
            dd = o._thailand_readiness_data()
            return [("Overall Weighted Readiness %", dd["overall_readiness"] * 100.0),
                    ("Red Workstreams", dd["red_count"]), ("Yellow Workstreams", dd["yellow_count"])]
        if k == "commercial":
            qual = Lead.search([("probability", ">=", 50)])
            return [("Qualified Pipeline cm²", sum(l.est_annual_cm2 * (l.probability / 100.0) for l in qual)),
                    ("Hospitals Engaged+", Lead.search_count([("sanare_stage", "in", ["engaged", "evaluating", "contracting", "approved", "ordering", "repeat_ordering"])])),
                    ("Ordering Hospitals", Lead.search_count([("sanare_stage", "in", ["ordering", "repeat_ordering"])]))]
        if k == "clinical":
            rows = Phys.search([])
            return [("cm² YTD", sum(rows.mapped("cm2_ytd"))),
                    ("Active KOLs", Phys.search_count([("relationship_stage", "in", ["active", "kol"])])),
                    ("Trained / Certified", Phys.search_count([("training_status", "in", ["trained", "certified"])]))]
        if k == "reg_supply":
            reg = Rock.search([("rock_id", "in", ["R6", "R06"])], limit=1)
            return [("Regulatory % Complete", reg.percent_complete or 0.0),
                    ("Reg Tasks Open", len(reg.task_ids.filtered(lambda t: t.status not in ("complete", "deferred")))),
                    ("Red-Risk SKUs", Sku.search_count([("stockout_risk", "=", "red")]))]
        if k == "financial":
            fp = o._financial_period()
            return [("Runway (Months)", fp.runway_months or 0.0),
                    ("Ending Cash", fp.ending_cash or 0.0),
                    ("Gross Margin %", fp.gross_margin_pct or 0.0)]
        if k == "use_of_funds":
            uof = env["eos.use.of.funds"].search([])
            approved = sum(uof.mapped("approved_budget"))
            spent = sum(uof.mapped("spent_to_date"))
            return [("% Used", (spent / approved * 100.0) if approved else 0.0),
                    ("Approved Budget", approved),
                    ("Remaining", sum(uof.mapped("remaining")))]
        if k == "risks":
            return [("Open Red Risks", Risk.search_count([("rating", "=", "red"), ("status", "!=", "resolved")])),
                    ("Open Yellow Risks", Risk.search_count([("rating", "=", "yellow"), ("status", "!=", "resolved")])),
                    ("Worsening Risks", Risk.search_count([("trend", "=", "worsening"), ("status", "!=", "resolved")]))]
        return [("", 0.0), ("", 0.0), ("", 0.0)]

    @api.depends("report_key", "as_of_date", "monthly_report_id")
    def _compute_metrics(self):
        for b in self:
            o = b.monthly_report_id
            if not o or not b.report_key:
                b.primary_label = b.secondary_label = b.tertiary_label = ""
                b.primary_metric = b.secondary_metric = b.tertiary_metric = 0.0
                b.computed_on = False
                continue
            m = b._headline_metrics(o)
            b.primary_label, b.primary_metric = m[0][0], float(m[0][1])
            b.secondary_label, b.secondary_metric = m[1][0], float(m[1][1])
            b.tertiary_label, b.tertiary_metric = m[2][0], float(m[2][1])
            b.computed_on = fields.Datetime.now()

    @api.depends("report_key", "as_of_date", "monthly_report_id")
    def _compute_report_fields(self):
        """Fill the native-widget fields (tiles + list relations) for the
        board's own report_key. Reuses the same env lookups and query
        fragments already written in _headline_metrics - this fills in the
        rest of what that method already half-computes for the top-3
        headline numbers, it isn't new query logic."""
        env = self.env
        Rock = env["eos.rock"]
        Task = env["eos.task"]
        Lead = env["crm.lead"]
        Risk = env["eos.risk"]
        Phys = env["eos.physician"]
        Sku = env["eos.sku"]
        Uof = env["eos.use.of.funds"]
        FpLine = env["eos.financial.period.line"]

        for b in self:
            # Reset everything to its empty value; only the branch matching
            # report_key below fills anything in.
            b.currency_id = False
            b.exec_overall_health = b.exec_active_quarter = b.exec_report_status = ""
            b.exec_thailand_readiness_pct = b.exec_runway_months = 0.0
            b.exec_rocks_on_track = b.exec_rocks_at_risk = 0
            b.exec_ending_cash = 0.0
            b.exec_hospitals_engaged = b.exec_hospitals_ordering = 0
            b.exec_qualified_pipeline_cm2 = 0.0
            b.eos_rocks_on_track = b.eos_rocks_at_risk = 0
            b.eos_rocks_off_track = b.eos_rocks_complete = 0
            b.rock_ids = Rock.browse()
            b.commercial_qualified_pipeline_cm2 = 0.0
            b.commercial_ordering_hospitals = 0
            b.commercial_stage_identified = b.commercial_stage_engaged = 0
            b.commercial_stage_evaluating = b.commercial_stage_contracting = 0
            b.commercial_stage_approved = b.commercial_stage_ordering = 0
            b.commercial_stage_repeat_ordering = b.commercial_stage_contracted = 0
            b.pipeline_lead_ids = Lead.browse()
            b.clinical_kol_count = b.clinical_active_count = 0
            b.clinical_trained_certified = b.clinical_cases_ytd = 0
            b.clinical_cm2_ytd = 0.0
            b.physician_ids = Phys.browse()
            b.reg_status = ""
            b.reg_tasks_complete = b.reg_tasks_open = 0
            b.reg_percent_complete = 0.0
            b.regulatory_task_ids = Task.browse()
            b.sku_ids = Sku.browse()
            b.financial_period_id = False
            b.fp_ending_cash = b.fp_available_capital = 0.0
            b.fp_net_cash_burn = b.fp_runway_months = 0.0
            b.fp_gross_margin_pct = 0.0
            b.fp_capital_received = b.fp_committed_unspent = 0.0
            b.financial_line_ids = FpLine.browse()
            b.use_of_funds_ids = Uof.browse()
            b.risks_open_red = b.risks_open_yellow = b.risks_worsening = 0
            b.top_risk_ids = Risk.browse()

            o = b.monthly_report_id
            k = b.report_key
            if not o or not k:
                continue
            b.currency_id = o.currency_id or env.company.currency_id

            if k == "exec":
                q = o._report_quarter()
                thai = o._thailand_readiness_data()
                eng = Lead.search([("sanare_stage", "in", [
                    "engaged", "evaluating", "contracting", "approved", "ordering", "repeat_ordering"])])
                ordr = Lead.search([("sanare_stage", "in", ["ordering", "repeat_ordering"])])
                qual = Lead.search([("probability", ">=", 50)])
                b.exec_overall_health = dict(o._fields["overall_health"].selection).get(o.overall_health) or ""
                b.exec_thailand_readiness_pct = thai["overall_readiness"] * 100.0
                b.exec_active_quarter = o._quarter_label()
                b.exec_report_status = dict(o._fields["report_status"].selection).get(o.report_status) or ""
                b.exec_rocks_on_track = Rock.search_count([("quarter", "=", q), ("status", "=", "on_track")])
                b.exec_rocks_at_risk = Rock.search_count([("quarter", "=", q), ("status", "=", "at_risk")])
                b.exec_ending_cash = o.ending_cash or 0.0
                b.exec_runway_months = o.runway_months or 0.0
                b.exec_hospitals_engaged = len(eng)
                b.exec_hospitals_ordering = len(ordr)
                b.exec_qualified_pipeline_cm2 = sum(
                    lead.est_annual_cm2 * (lead.probability / 100.0) for lead in qual)

            elif k == "eos":
                q = o._report_quarter()
                b.eos_rocks_on_track = Rock.search_count([("quarter", "=", q), ("status", "=", "on_track")])
                b.eos_rocks_at_risk = Rock.search_count([("quarter", "=", q), ("status", "=", "at_risk")])
                b.eos_rocks_off_track = Rock.search_count([("quarter", "=", q), ("status", "=", "off_track")])
                b.eos_rocks_complete = Rock.search_count([("quarter", "=", q), ("status", "=", "complete")])
                b.rock_ids = Rock.search([("quarter", "=", q)], order="rock_id")

            elif k == "commercial":
                qual = Lead.search([("probability", ">=", 50)])
                b.commercial_qualified_pipeline_cm2 = sum(
                    lead.est_annual_cm2 * (lead.probability / 100.0) for lead in qual)
                b.commercial_ordering_hospitals = Lead.search_count(
                    [("sanare_stage", "in", ["ordering", "repeat_ordering"])])
                stage_fields = {
                    "identified": "commercial_stage_identified",
                    "engaged": "commercial_stage_engaged",
                    "evaluating": "commercial_stage_evaluating",
                    "contracting": "commercial_stage_contracting",
                    "approved": "commercial_stage_approved",
                    "ordering": "commercial_stage_ordering",
                    "repeat_ordering": "commercial_stage_repeat_ordering",
                }
                for stage, fname in stage_fields.items():
                    setattr(b, fname, Lead.search_count([("sanare_stage", "=", stage)]))
                b.commercial_stage_contracted = Lead.search_count([("contracted", "=", True)])
                b.pipeline_lead_ids = Lead.search(
                    [("sanare_stage", "!=", "identified"), ("sanare_stage", "!=", False)],
                    order="est_annual_cm2 desc", limit=16)

            elif k == "clinical":
                rows = Phys.search([], order="name")
                b.clinical_kol_count = Phys.search_count([("relationship_stage", "=", "kol")])
                b.clinical_active_count = Phys.search_count([("relationship_stage", "=", "active")])
                b.clinical_trained_certified = Phys.search_count(
                    [("training_status", "in", ["trained", "certified"])])
                b.clinical_cases_ytd = int(sum(rows.mapped("cases_ytd")))
                b.clinical_cm2_ytd = sum(rows.mapped("cm2_ytd"))
                b.physician_ids = rows

            elif k == "reg_supply":
                reg = Rock.search([("rock_id", "in", ["R6", "R06"])], limit=1)
                if reg:
                    b.reg_status = dict(reg._fields["status"].selection).get(reg.status) or ""
                    b.reg_tasks_complete = len(reg.task_ids.filtered(lambda t: t.status == "complete"))
                    b.reg_tasks_open = len(
                        reg.task_ids.filtered(lambda t: t.status not in ("complete", "deferred")))
                    b.reg_percent_complete = reg.percent_complete or 0.0
                    b.regulatory_task_ids = reg.task_ids.sorted(key=lambda t: (t.due_date or date.max, t.sequence))
                b.sku_ids = Sku.search([], order="name")

            elif k in ("financial", "use_of_funds"):
                fp = o._financial_period()
                b.financial_period_id = fp
                b.fp_ending_cash = fp.ending_cash or 0.0
                b.fp_available_capital = fp.available_capital or 0.0
                b.fp_net_cash_burn = fp.net_cash_burn or 0.0
                b.fp_runway_months = fp.runway_months or 0.0
                b.fp_gross_margin_pct = fp.gross_margin_pct or 0.0
                b.fp_capital_received = fp.capital_received or 0.0
                b.fp_committed_unspent = fp.committed_unspent or 0.0
                if k == "financial":
                    b.financial_line_ids = fp.line_ids
                else:
                    b.use_of_funds_ids = Uof.search([], order="sequence, id")

            elif k == "risks":
                b.risks_open_red = Risk.search_count([("rating", "=", "red"), ("status", "!=", "resolved")])
                b.risks_open_yellow = Risk.search_count(
                    [("rating", "=", "yellow"), ("status", "!=", "resolved")])
                b.risks_worsening = Risk.search_count(
                    [("trend", "=", "worsening"), ("status", "!=", "resolved")])
                b.top_risk_ids = Risk.search(
                    [("status", "!=", "resolved")], order="risk_score desc, risk_id", limit=10)

    # ------------------------------------------------------------------
    def _open_rocks(self, status):
        self.ensure_one()
        o = self.monthly_report_id
        q = o._report_quarter() if o else False
        return {
            "type": "ir.actions.act_window",
            "name": "Rocks — %s" % dict(self.env["eos.rock"]._fields["status"].selection).get(status, status),
            "res_model": "eos.rock",
            "view_mode": "list,form",
            "domain": [("quarter", "=", q), ("status", "=", status)],
        }

    def action_view_rocks_on_track(self):
        return self._open_rocks("on_track")

    def action_view_rocks_at_risk(self):
        return self._open_rocks("at_risk")

    def _open_risks(self, rating):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Risks — %s" % dict(self.env["eos.risk"]._fields["rating"].selection).get(rating, rating),
            "res_model": "eos.risk",
            "view_mode": "list,form",
            "domain": [("rating", "=", rating), ("status", "!=", "resolved")],
        }

    def action_view_risks_red(self):
        return self._open_risks("red")

    def action_view_risks_yellow(self):
        return self._open_risks("yellow")

    # ------------------------------------------------------------------
    @api.model
    def action_open(self, report_key):
        """Menu entry point: open (or create) this month's board for report_key."""
        MR = self.env["eos.monthly.report"]
        mr = MR.search([], order="reporting_month desc", limit=1)
        if not mr:
            mr = MR.create({"reporting_month": fields.Date.context_today(self)})
        rec = self.search(
            [("report_key", "=", report_key), ("monthly_report_id", "=", mr.id)], limit=1)
        if not rec:
            rec = self.create({"report_key": report_key, "monthly_report_id": mr.id})
        return {
            "type": "ir.actions.act_window",
            "res_model": "eos.dashboard.board",
            "res_id": rec.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
            "name": dict(REPORT_KEYS).get(report_key, "Dashboard"),
        }

    def action_print(self):
        self.ensure_one()
        action = self.env.ref("eos_dashboard." + _PRINT_ACTION[self.report_key])
        return action.report_action(self.monthly_report_id)

    def action_view_history(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name + " — History",
            "res_model": "eos.dashboard.board",
            "view_mode": "graph,list,form",
            "domain": [("report_key", "=", self.report_key)],
        }
