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
