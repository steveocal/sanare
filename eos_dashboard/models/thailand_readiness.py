# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .readiness_engine import TaskRow, compute_thailand_readiness

# eos.task.status -> 'Task Tracker' column K canonical string
_STATUS = {
    "not_started": "Not Started",
    "on_track": "On Track",
    "at_risk": "At Risk",
    "off_track": "Off Track",
    "complete": "Complete",
    "deferred": "Deferred",
}
# eos.task.priority -> 'Task Tracker' column H
_PRIORITY = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}
# eos.task.critical_path -> 'Task Tracker' column N
_CRIT_PATH = {"critical": "Critical", "parallel": "Parallel", "post_launch": "Post-Launch"}


def task_rows_from_db(env):
    """Read every ``eos.task`` and adapt it to a :class:`TaskRow` the engine understands."""
    rows = []
    for t in env["eos.task"].search([]):
        rows.append(TaskRow(
            rock=t.rock_id.rock_id or "",
            status=_STATUS.get(t.status, ""),
            due=t.due_date or None,
            priority=_PRIORITY.get(t.priority, ""),
            critical_path=_CRIT_PATH.get(t.critical_path, ""),
        ))
    return rows


class EosThailandReadiness(models.Model):
    _name = "eos.thailand.readiness"
    _description = "Report 03 - Thailand Launch Readiness"
    _order = "as_of_date desc, id desc"

    name = fields.Char(required=True, default="Thailand Launch Readiness")
    as_of_date = fields.Date(
        string="As of", required=True, default=fields.Date.context_today,
        help="Date used for the overdue-task test in the Health column "
             "(the spreadsheet's TODAY()). Change it and the board recomputes.")
    month_label = fields.Char(string="Period", compute="_compute_month_label")

    overall_readiness = fields.Float(
        string="Overall Weighted Readiness", readonly=True,
        help="SUMPRODUCT(weight x readiness) / SUM(weight) over the 9 Thailand "
             "workstreams, on a 0-100 scale.")
    red_count = fields.Integer(string="Red Workstreams", readonly=True)
    yellow_count = fields.Integer(string="Yellow Workstreams", readonly=True)
    computed_on = fields.Datetime(string="Last Recomputed", readonly=True)

    line_ids = fields.One2many(
        "eos.thailand.readiness.line", "readiness_id", string="Workstreams")

    monthly_report_id = fields.Many2one(
        "eos.monthly.report", string="Monthly Report",
        help="Optional. 'Pull Commentary' copies this report's Executive Summary "
             "and Corrective Actions into the commentary fields below; leave "
             "blank to use the most recent monthly report.")
    commentary_changed = fields.Text(string="What changed materially?")
    commentary_actions = fields.Text(string="Critical corrective actions")

    # ------------------------------------------------------------------ compute
    @api.depends("as_of_date")
    def _compute_month_label(self):
        for rec in self:
            d = rec.as_of_date or fields.Date.context_today(rec)
            rec.month_label = d.strftime("%B %Y")

    # ------------------------------------------------------------------ engine
    def _recompute_lines(self):
        tasks = task_rows_from_db(self.env)
        Line = self.env["eos.thailand.readiness.line"]
        for rec in self:
            as_of = rec.as_of_date or fields.Date.context_today(rec)
            data = compute_thailand_readiness(tasks, today=as_of)
            rec.line_ids.unlink()
            for idx, r in enumerate(data["rows"]):
                Line.create({
                    "readiness_id": rec.id,
                    "sequence": idx * 10,
                    "workstream": r["key"],
                    "name": r["label"],
                    "weight": r["weight"] * 100.0,
                    "readiness": r["readiness"] * 100.0,
                    "status": r["status_odoo"],
                    "key_gate": r["key_gate"],
                    "owner": r["owner"],
                    "source_key": r["source_key"],
                })
            rec.overall_readiness = data["overall_readiness"] * 100.0
            rec.red_count = data["red_count"]
            rec.yellow_count = data["yellow_count"]
            rec.computed_on = fields.Datetime.now()

    def _pull_commentary(self):
        for rec in self:
            report = rec.monthly_report_id or self.env["eos.monthly.report"].search(
                [], order="reporting_month desc", limit=1)
            if not report:
                continue
            if report.executive_summary:
                rec.commentary_changed = report.executive_summary
            if report.corrective_actions:
                rec.commentary_actions = report.corrective_actions

    # ------------------------------------------------------------------ CRUD
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._recompute_lines()
        for rec in records:
            if not rec.commentary_changed and not rec.commentary_actions:
                rec._pull_commentary()
        return records

    def write(self, vals):
        res = super().write(vals)
        if "as_of_date" in vals:
            self._recompute_lines()
        return res

    # ------------------------------------------------------------------ buttons
    def action_recompute(self):
        self._recompute_lines()
        return True

    def action_pull_commentary(self):
        self._pull_commentary()
        return True

    def action_view_chart(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Readiness by Workstream",
            "res_model": "eos.thailand.readiness.line",
            "view_mode": "graph,list",
            "domain": [("readiness_id", "=", self.id)],
            "target": "current",
        }

    @api.model
    def action_open_board(self):
        """Menu entry point: open the latest board (refreshed) or make the first one."""
        rec = self.search([], order="as_of_date desc, id desc", limit=1)
        if rec:
            rec._recompute_lines()
        else:
            rec = self.create({})
        return {
            "type": "ir.actions.act_window",
            "name": "Report 03 — Thailand Readiness",
            "res_model": "eos.thailand.readiness",
            "res_id": rec.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }


class EosThailandReadinessLine(models.Model):
    _name = "eos.thailand.readiness.line"
    _description = "Report 03 - Thailand Launch Readiness workstream line"
    _order = "sequence, id"

    readiness_id = fields.Many2one(
        "eos.thailand.readiness", string="Readiness Board",
        required=True, ondelete="cascade", index=True)
    sequence = fields.Integer()
    workstream = fields.Selection([
        ("corporate", "Corporate"),
        ("finance", "Finance"),
        ("manufacturer", "Manufacturer"),
        ("regulatory", "Regulatory"),
        ("supply_chain", "Supply Chain"),
        ("clinical", "Clinical"),
        ("hospitals", "Hospitals"),
        ("commercial", "Commercial"),
        ("compliance", "Compliance"),
    ], string="Workstream Key")
    name = fields.Char(string="Workstream")
    weight = fields.Float(string="Weight", aggregator="sum")
    readiness = fields.Float(string="Readiness", aggregator="avg")
    status = fields.Selection([
        ("green", "Green"),
        ("yellow", "Yellow"),
        ("red", "Red"),
    ], string="Health")
    key_gate = fields.Text(string="Evidence / Current State")
    owner = fields.Char(string="Owner")
    source_key = fields.Char(string="Source Key")
