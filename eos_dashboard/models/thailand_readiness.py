# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.fields import Command

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


class EosThailandReadiness(models.TransientModel):
    _name = "eos.thailand.readiness"
    _description = "Report 03 - Thailand Launch Readiness (live view)"

    as_of_date = fields.Date(
        string="As of", required=True, default=fields.Date.context_today,
        help="Date used for the overdue-task test in the Health column "
             "(the spreadsheet's TODAY()).")
    month_label = fields.Char(string="Period", compute="_compute_readiness")
    overall_readiness = fields.Float(
        string="Overall Weighted Readiness", compute="_compute_readiness",
        help="SUMPRODUCT(weight x readiness) / SUM(weight) over the 9 Thailand "
             "workstreams, on a 0-100 scale.")
    red_count = fields.Integer(string="Red Workstreams", compute="_compute_readiness")
    yellow_count = fields.Integer(string="Yellow Workstreams", compute="_compute_readiness")
    line_ids = fields.One2many(
        "eos.thailand.readiness.line", "readiness_id",
        string="Workstreams", compute="_compute_readiness")
    commentary_changed = fields.Text(
        string="What changed materially?", compute="_compute_readiness")
    commentary_actions = fields.Text(
        string="Critical corrective actions", compute="_compute_readiness")

    @api.depends("as_of_date")
    def _compute_readiness(self):
        tasks = task_rows_from_db(self.env)
        report = self.env["eos.monthly.report"].search(
            [], order="reporting_month desc", limit=1)
        for wiz in self:
            as_of = wiz.as_of_date or fields.Date.context_today(wiz)
            data = compute_thailand_readiness(tasks, today=as_of)
            wiz.month_label = as_of.strftime("%B %Y")
            wiz.overall_readiness = data["overall_readiness"] * 100.0
            wiz.red_count = data["red_count"]
            wiz.yellow_count = data["yellow_count"]
            wiz.line_ids = [Command.clear()] + [
                Command.create({
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
                for idx, r in enumerate(data["rows"])
            ]
            wiz.commentary_changed = report.executive_summary or ""
            wiz.commentary_actions = report.corrective_actions or ""


class EosThailandReadinessLine(models.TransientModel):
    _name = "eos.thailand.readiness.line"
    _description = "Report 03 - Thailand Launch Readiness workstream line"
    _order = "sequence, id"

    readiness_id = fields.Many2one(
        "eos.thailand.readiness", string="Readiness Board", ondelete="cascade")
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
    weight = fields.Float(string="Weight")
    readiness = fields.Float(string="Readiness")
    status = fields.Selection([
        ("green", "Green"),
        ("yellow", "Yellow"),
        ("red", "Red"),
    ], string="Health")
    key_gate = fields.Text(string="Evidence / Current State")
    owner = fields.Char(string="Owner")
    source_key = fields.Char(string="Source Key")


class ReportEosDashboardReport03Thailand(models.AbstractModel):
    _name = "report.eos_dashboard.report_03_thailand"
    _description = "Report 03 - Thailand QWeb data provider"

    @api.model
    def _get_report_values(self, docids, data=None):
        reports = self.env["eos.monthly.report"].browse(docids)
        tasks = task_rows_from_db(self.env)
        payload = {}
        for rep in reports:
            as_of = rep.reporting_month or fields.Date.context_today(self)
            data_ = compute_thailand_readiness(tasks, today=as_of)
            # Pre-format every number here: '%' formatting inside a QWeb t-esc
            # expression collides with Odoo's lazy-translation '%'-substitution.
            payload[rep.id] = {
                "period_label": as_of.strftime("%B %Y"),
                "overall_pct": "%.1f%%" % (data_["overall_readiness"] * 100.0),
                "red_count": data_["red_count"],
                "yellow_count": data_["yellow_count"],
                "rows": [
                    {
                        "label": r["label"],
                        "weight_pct": "%.0f%%" % (r["weight"] * 100.0),
                        "readiness_pct": "%.1f%%" % (r["readiness"] * 100.0),
                        "status": r["status"],
                        "status_color": {
                            "Red": "#d9534f", "Yellow": "#f0ad4e", "Green": "#5cb85c",
                        }.get(r["status"], "#cccccc"),
                        "key_gate": r["key_gate"],
                        "owner": r["owner"],
                    }
                    for r in data_["rows"]
                ],
            }
        return {
            "doc_ids": docids,
            "doc_model": "eos.monthly.report",
            "docs": reports,
            "payload": payload,
        }
