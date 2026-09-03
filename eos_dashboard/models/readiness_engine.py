# -*- coding: utf-8 -*-
"""Pure-Python re-implementation of the *Report 03 Thailand* / *Launch Readiness*
formulae from ``Sanare_Management_Reporting_Engine_v2``.

There are deliberately **no Odoo imports** in this file: it is imported both by
the Odoo model (``models/thailand_readiness.py``) and by the standalone parity
checker (``scripts/verify_vs_spreadsheet.py``) which runs without Odoo.

Spreadsheet chain reproduced
----------------------------
``'Report 03 Thailand'`` is only a view onto ``'Launch Readiness'`` rows 4-12
(``Market = "Thailand"``) plus two commentary cells pulled from
``'Monthly Control'``.

``'Launch Readiness'`` computes, per workstream row:

``Readiness %`` (column D)::

    =IFERROR( SUMIFS('Task Tracker'!L, 'Task Tracker'!D=<rock>, 'Task Tracker'!K<>"Deferred")
              / COUNTIFS('Task Tracker'!D=<rock>, 'Task Tracker'!K<>"Deferred"), 0)

where ``'Task Tracker'!L`` (``% Complete (Auto)``) is::

    =IF(K="Complete",1, IF(K="Not Started",0, IF(K="Deferred","",
        IF(OR(K="On Track",K="At Risk",K="Off Track"),0.5, 0))))

``Status`` (column E)::

    =IF( COUNTIFS(rock, K="Off Track")
       + COUNTIFS(rock, J<TODAY, J<>"", K<>"Complete", K<>"Deferred", H="Critical")
       + COUNTIFS(rock, J<TODAY, J<>"", K<>"Complete", K<>"Deferred", N="Critical") > 0,
         "Red",
       IF( COUNTIFS(rock, K="At Risk") > 0, "Yellow", "Green"))

``H`` is *Priority*, ``N`` is *Critical Path*, ``J`` is *Due Date*.

Summary block (row 24, ``Market = "Thailand"``)::

    Overall Weighted Readiness (B24) = SUMPRODUCT((A="Thailand")*C*D) / SUMIF(A,"Thailand",C)
    Red Workstreams            (C24) = COUNTIFS(A="Thailand", E="Red")
    Yellow Workstreams         (D24) = COUNTIFS(A="Thailand", E="Yellow")

The Commercial workstream aggregates two rocks (R10 + R11); its formula sums the
two ``SUMIFS`` and the two ``COUNTIFS`` before dividing, which is what
:func:`workstream_readiness` does when handed a multi-rock tuple.
"""

from __future__ import annotations

import datetime

# --- canonical 'Task Tracker' status strings (column K) -----------------------
COMPLETE = "Complete"
NOT_STARTED = "Not Started"
DEFERRED = "Deferred"
ON_TRACK = "On Track"
AT_RISK = "At Risk"
OFF_TRACK = "Off Track"

_HALF = frozenset({ON_TRACK, AT_RISK, OFF_TRACK})

# --- 'Launch Readiness' Thailand block ---------------------------------------
# (key, label, weight, rock_ids, key_gate/evidence, owner)
# rock_ids and weights come from C4:C12 / I4:I12; text from F4:F12 / G4:G12.
THAILAND_WORKSTREAMS = (
    ("corporate", "Corporate", 0.10, ("R1",),
     "Legal entity, governance, tax/banking and statutory setup completed and operating.",
     "Greg Walker"),
    ("finance", "Finance", 0.08, ("R2",),
     "Banking, accounting, budget, monthly reporting and cash forecasting operational.",
     "Greg Walker / Finance"),
    ("manufacturer", "Manufacturer", 0.14, ("R5",),
     "Manufacturer approved; commercial/supply agreement executed; quality and "
     "regulatory documentation complete.",
     "Greg Walker"),
    ("regulatory", "Regulatory", 0.18, ("R6",),
     "Classification/pathway locked; dossier, submission and approval conditions "
     "on track with no unresolved launch blocker.",
     "Regulatory Lead"),
    ("supply_chain", "Supply Chain", 0.12, ("R7",),
     "Importer, freight/customs, storage, traceability, receiving, lot/expiry/recall "
     "and replenishment operational.",
     "Greg Walker / Operations"),
    ("clinical", "Clinical", 0.10, ("R8",),
     "Medical Director, KOLs, training, case support and clinical "
     "documentation/outcomes process operational.",
     "Harold"),
    ("hospitals", "Hospitals", 0.10, ("R9",),
     "Target hospitals approved/contracted/vendor-ready with ordering and "
     "first-case pathway.",
     "Sales Lead"),
    ("commercial", "Commercial", 0.10, ("R10", "R11"),
     "Pricing/cm², margins, CRM, sales coverage, pipeline, contracts and "
     "selling tools live.",
     "Greg Walker / Sales Lead"),
    ("compliance", "Compliance", 0.08, ("R12",),
     "Insurance, HCP/anti-bribery, PDPA/data, contracts, "
     "complaints/adverse-event/recall controls operational.",
     "Greg Walker / Legal"),
)

# workstream key -> "Red"/"Yellow"/"Green" written lower-case for Odoo selections
STATUS_TO_ODOO = {"Red": "red", "Yellow": "yellow", "Green": "green"}


def _as_date(value):
    """Coerce a due-date-ish value (datetime, date, ISO string, blank) to date|None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        return datetime.date.fromisoformat(value[:10])
    raise TypeError("unsupported due-date value: %r" % (value,))


class TaskRow:
    """One ``'Task Tracker'`` row reduced to the columns the formulae read."""

    __slots__ = ("rock", "status", "due", "priority", "critical_path")

    def __init__(self, rock, status, due=None, priority=None, critical_path=None):
        self.rock = (rock or "").strip()
        self.status = (status or "").strip()
        self.due = _as_date(due)
        self.priority = (priority or "").strip()
        self.critical_path = (critical_path or "").strip()

    def __repr__(self):  # pragma: no cover - debug helper
        return "TaskRow(%r, %r, due=%r, pri=%r, cp=%r)" % (
            self.rock, self.status, self.due, self.priority, self.critical_path)


def task_percent(status):
    """``'Task Tracker'!L`` - ``% Complete (Auto)``.

    Returns ``None`` for *Deferred* (the spreadsheet leaves the cell blank, which
    makes both the ``SUMIFS`` and ``COUNTIFS`` skip the row via ``K<>"Deferred"``).
    """
    if status == COMPLETE:
        return 1.0
    if status == NOT_STARTED:
        return 0.0
    if status == DEFERRED:
        return None
    if status in _HALF:
        return 0.5
    return 0.0


def workstream_readiness(tasks, rock_ids):
    """``'Launch Readiness'!D`` - ``IFERROR(SUMIFS/COUNTIFS, 0)`` as a 0..1 fraction."""
    wanted = set(rock_ids)
    considered = [t for t in tasks if t.rock in wanted and t.status != DEFERRED]
    if not considered:
        return 0.0
    total = sum(task_percent(t.status) or 0.0 for t in considered)
    return total / len(considered)


def _is_overdue_open(task, today):
    """``J<TODAY, J<>"", K<>"Complete", K<>"Deferred"``."""
    return (
        task.due is not None
        and task.due < today
        and task.status not in (COMPLETE, DEFERRED)
    )


def workstream_status(tasks, rock_ids, today):
    """``'Launch Readiness'!E`` - ``"Red"`` / ``"Yellow"`` / ``"Green"``."""
    wanted = set(rock_ids)
    rows = [t for t in tasks if t.rock in wanted]
    red_hits = 0
    for t in rows:
        if t.status == OFF_TRACK:
            red_hits += 1
        if _is_overdue_open(t, today):
            # the spreadsheet adds two separate COUNTIFS; a row that is both
            # Critical priority and Critical path therefore counts twice. Only
            # the ">0" test matters, but mirror it faithfully anyway.
            if t.priority == "Critical":
                red_hits += 1
            if t.critical_path == "Critical":
                red_hits += 1
    if red_hits > 0:
        return "Red"
    if any(t.status == AT_RISK for t in rows):
        return "Yellow"
    return "Green"


def compute_thailand_readiness(tasks, today=None):
    """Return the full *Report 03 Thailand* payload from an iterable of :class:`TaskRow`.

    ``today`` defaults to :func:`datetime.date.today` and stands in for the
    spreadsheet's ``TODAY()`` in the Health column.
    """
    if today is None:
        today = datetime.date.today()
    today = _as_date(today)
    tasks = list(tasks)

    rows = []
    for key, label, weight, rock_ids, key_gate, owner in THAILAND_WORKSTREAMS:
        readiness = workstream_readiness(tasks, rock_ids)
        status = workstream_status(tasks, rock_ids, today)
        rows.append({
            "key": key,
            "label": label,
            "weight": weight,
            "rock_ids": list(rock_ids),
            "source_key": "ROCK:" + "|".join(rock_ids),
            "readiness": readiness,
            "status": status,
            "status_odoo": STATUS_TO_ODOO[status],
            "key_gate": key_gate,
            "owner": owner,
        })

    weight_total = sum(r["weight"] for r in rows)
    overall = (
        sum(r["weight"] * r["readiness"] for r in rows) / weight_total
        if weight_total else 0.0
    )
    return {
        "as_of": today,
        "rows": rows,
        "overall_readiness": overall,
        "red_count": sum(1 for r in rows if r["status"] == "Red"),
        "yellow_count": sum(1 for r in rows if r["status"] == "Yellow"),
    }
