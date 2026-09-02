/** @odoo-module **/

import { Component, useState, onWillStart, useRef, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const DAY_MS = 86400000;
const ROW_H = 30;
const BAR_H = 14;
const ZOOM = {
    day: { pxPerDay: 46, minor: "day", major: "week" },
    week: { pxPerDay: 20, minor: "day", major: "month" },
    month: { pxPerDay: 6, minor: "week", major: "month" },
    quarter: { pxPerDay: 2.6, minor: "month", major: "quarter" },
};

const TASK_FIELDS = [
    "id", "name", "wbs", "sequence", "rock_id", "parent_task_id",
    "outline_level", "is_summary", "is_milestone", "is_critical",
    "task_mode", "planned_start", "planned_finish", "duration_hours",
    "duration_display", "percent_complete", "percent_work_complete",
    "total_slack_hours", "free_slack_hours", "late_finish",
    "baseline_start", "baseline_finish", "deadline",
    "predecessor_display", "resource_names", "status", "priority",
    "schedule_warning",
];

function parseDT(s) {
    if (!s) return null;
    // Odoo server datetime "YYYY-MM-DD HH:MM:SS" (UTC, naive)
    return new Date(s.replace(" ", "T") + "Z");
}
function startOfDay(d) {
    const n = new Date(d);
    n.setUTCHours(0, 0, 0, 0);
    return n;
}
function addDays(d, n) {
    const r = new Date(d);
    r.setUTCDate(r.getUTCDate() + n);
    return r;
}
function fmtDate(d) {
    return d
        ? d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" })
        : "—";
}
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export class EosGantt extends Component {
    static template = "eos.Gantt";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.rightPane = useRef("rightPane");
        this.leftList = useRef("leftList");

        this.state = useState({
            loading: true,
            rocks: [],
            rockId: this.props.action?.params?.rock_id || false,
            tasks: [],
            deps: [],
            collapsed: {},
            zoom: "week",
            opt: { baseline: true, critical: true, slack: false, links: true, nonworking: true },
            leftWidth: 460,
            tooltip: null,
        });

        onWillStart(async () => {
            this.state.rocks = await this.orm.searchRead(
                "eos.rock", [], ["id", "name", "rock_id"], { order: "quarter, sequence, name" }
            );
            if (!this.state.rockId && this.state.rocks.length) {
                this.state.rockId = this.state.rocks[0].id;
            }
            await this.loadTasks();
        });
        onMounted(() => this.scrollToToday());
    }

    async loadTasks() {
        this.state.loading = true;
        const rockId = this.state.rockId;
        if (!rockId) {
            this.state.tasks = [];
            this.state.deps = [];
            this.state.loading = false;
            return;
        }
        const [tasks, deps] = await Promise.all([
            this.orm.searchRead("eos.task", [["rock_id", "=", rockId]], TASK_FIELDS, {
                order: "sequence, id",
            }),
            this.orm.searchRead(
                "eos.task.dependency",
                [["rock_id", "=", rockId]],
                ["task_id", "predecessor_task_id", "dependency_type", "lag_hours"]
            ),
        ]);
        this.state.tasks = tasks;
        this.state.deps = deps;
        this.state.loading = false;
    }

    async onRockChange(ev) {
        this.state.rockId = parseInt(ev.target.value, 10) || false;
        await this.loadTasks();
        this.scrollToToday();
    }

    setZoom(z) {
        this.state.zoom = z;
        this.scrollToToday();
    }
    toggleOpt(k) {
        this.state.opt[k] = !this.state.opt[k];
    }

    // ----- tree / visible rows -----------------------------------------
    get orderedTasks() {
        const byId = {};
        for (const t of this.state.tasks) byId[t.id] = t;
        const children = {};
        for (const t of this.state.tasks) {
            const p = t.parent_task_id ? t.parent_task_id[0] : 0;
            (children[p] = children[p] || []).push(t);
        }
        for (const k in children) {
            children[k].sort((a, b) => (a.sequence - b.sequence) || (a.id - b.id));
        }
        const out = [];
        const walk = (pid, depth) => {
            for (const t of children[pid] || []) {
                t._depth = depth;
                t._hasKids = !!(children[t.id] && children[t.id].length);
                out.push(t);
                if (t._hasKids && !this.state.collapsed[t.id]) walk(t.id, depth + 1);
            }
        };
        walk(0, 0);
        return out;
    }
    toggleCollapse(id) {
        this.state.collapsed[id] = !this.state.collapsed[id];
    }
    expandAll() {
        this.state.collapsed = {};
    }
    collapseAll() {
        const c = {};
        for (const t of this.state.tasks) if (t.is_summary) c[t.id] = true;
        this.state.collapsed = c;
    }

    // ----- timeline scale --------------------------------------------
    get scale() {
        const rows = this.orderedTasks;
        let min = null;
        let max = null;
        const consider = (d) => {
            if (!d) return;
            if (!min || d < min) min = d;
            if (!max || d > max) max = d;
        };
        for (const t of rows) {
            consider(parseDT(t.planned_start));
            consider(parseDT(t.planned_finish));
            if (this.state.opt.baseline) {
                consider(parseDT(t.baseline_start));
                consider(parseDT(t.baseline_finish));
            }
            consider(parseDT(t.deadline));
        }
        const today = new Date();
        consider(addDays(today, -5));
        consider(addDays(today, 14));
        if (!min || !max) {
            min = addDays(today, -14);
            max = addDays(today, 30);
        }
        min = startOfDay(addDays(min, -3));
        max = startOfDay(addDays(max, 4));
        const pxPerDay = ZOOM[this.state.zoom].pxPerDay;
        const days = Math.max(1, Math.round((max - min) / DAY_MS));
        return { min, max, pxPerDay, width: days * pxPerDay, days };
    }
    x(d) {
        if (!d) return 0;
        return ((d - this.scale.min) / DAY_MS) * this.scale.pxPerDay;
    }

    get layout() {
        const s = this.scale;
        const rows = this.orderedTasks;
        const byId = {};
        rows.forEach((t, i) => (byId[t.id] = { t, i }));
        const R = [];
        for (let i = 0; i < rows.length; i++) {
            const t = rows[i];
            const y = i * ROW_H;
            const ps = parseDT(t.planned_start);
            const pf = parseDT(t.planned_finish);
            const isMs = t.is_milestone || (t.duration_hours || 0) === 0;
            const row = {
                id: t.id,
                y,
                mid: y + ROW_H / 2,
                kind: t.is_summary ? "summary" : isMs ? "milestone" : "bar",
                critical: this.state.opt.critical && t.is_critical,
                x1: this.x(ps),
                x2: this.x(pf),
                resource: t.resource_names || "",
            };
            row.w = Math.max(row.x2 - row.x1, isMs ? 0 : 2);
            const pct = t.percent_work_complete || t.percent_complete || 0;
            row.progressW = Math.max(0, (row.w * Math.min(pct, 100)) / 100);
            if (this.state.opt.baseline && t.baseline_start && t.baseline_finish) {
                const bx = this.x(parseDT(t.baseline_start));
                row.baseline = { x: bx, w: Math.max(2, this.x(parseDT(t.baseline_finish)) - bx) };
            }
            if (this.state.opt.slack && (t.total_slack_hours || 0) > 0 && t.late_finish) {
                const lx = this.x(parseDT(t.late_finish));
                if (lx > row.x2) row.slack = { x: row.x2, w: lx - row.x2 };
            }
            if (t.deadline) row.deadlineX = this.x(parseDT(t.deadline));
            R.push(row);
        }

        // arrows
        const A = [];
        if (this.state.opt.links) {
            for (const d of this.state.deps) {
                const from = byId[d.predecessor_task_id[0]];
                const to = byId[d.task_id[0]];
                if (!from || !to) continue;
                const rf = R[from.i];
                const rt = R[to.i];
                let sx;
                let sy = rf.mid;
                let tx;
                let ty = rt.mid;
                const type = d.dependency_type || "FS";
                sx = type[0] === "S" ? rf.x1 : rf.x1 + rf.w;
                tx = type[1] === "S" ? rt.x1 : rt.x1 + rt.w;
                const dir = type[1] === "S" ? -1 : 1;
                const midx = type[1] === "S" ? Math.min(sx, tx) - 12 : Math.max(sx, tx) + 12;
                const enterX = tx + dir * -8;
                A.push({
                    d: `M ${sx} ${sy} L ${midx} ${sy} L ${midx} ${ty} L ${enterX} ${ty}`,
                    critical: this.state.opt.critical && rf.critical && rt.critical,
                });
            }
        }

        // time header + weekends + grid
        const majors = [];
        const minors = [];
        const weekends = [];
        const grid = [];
        const zmode = ZOOM[this.state.zoom];
        let cur = new Date(s.min);
        while (cur < s.max) {
            const nx = addDays(cur, 1);
            const gx = this.x(cur);
            if (this.state.opt.nonworking && (cur.getUTCDay() === 0 || cur.getUTCDay() === 6)) {
                weekends.push({ x: gx, w: s.pxPerDay });
            }
            if (zmode.minor === "day") {
                grid.push(gx);
                if (this.state.zoom === "day") {
                    minors.push({ x: gx, w: s.pxPerDay, label: String(cur.getUTCDate()) });
                }
            }
            cur = nx;
        }
        // minor: week
        if (zmode.minor === "week") {
            let w = new Date(s.min);
            while (w.getUTCDay() !== 1) w = addDays(w, 1);
            for (; w < s.max; w = addDays(w, 7)) {
                minors.push({
                    x: this.x(w),
                    w: 7 * s.pxPerDay,
                    label: `${w.getUTCDate()} ${MONTHS[w.getUTCMonth()]}`,
                });
                grid.push(this.x(w));
            }
        }
        // minor: month
        if (zmode.minor === "month") {
            let m = new Date(Date.UTC(s.min.getUTCFullYear(), s.min.getUTCMonth(), 1));
            for (; m < s.max; m = new Date(Date.UTC(m.getUTCFullYear(), m.getUTCMonth() + 1, 1))) {
                minors.push({ x: this.x(m), w: 28 * s.pxPerDay, label: MONTHS[m.getUTCMonth()] });
                grid.push(this.x(m));
            }
        }
        // major
        if (zmode.major === "week") {
            let w = new Date(s.min);
            while (w.getUTCDay() !== 1) w = addDays(w, 1);
            for (; w < s.max; w = addDays(w, 7)) {
                majors.push({
                    x: this.x(w),
                    w: 7 * s.pxPerDay,
                    label: `Week of ${w.getUTCDate()} ${MONTHS[w.getUTCMonth()]}`,
                });
            }
        } else if (zmode.major === "month") {
            let m = new Date(Date.UTC(s.min.getUTCFullYear(), s.min.getUTCMonth(), 1));
            for (; m < s.max; m = new Date(Date.UTC(m.getUTCFullYear(), m.getUTCMonth() + 1, 1))) {
                majors.push({
                    x: this.x(m),
                    w: 28 * s.pxPerDay,
                    label: `${MONTHS[m.getUTCMonth()]} ${m.getUTCFullYear()}`,
                });
            }
        } else {
            let q = new Date(Date.UTC(s.min.getUTCFullYear(), Math.floor(s.min.getUTCMonth() / 3) * 3, 1));
            for (; q < s.max; q = new Date(Date.UTC(q.getUTCFullYear(), q.getUTCMonth() + 3, 1))) {
                majors.push({
                    x: this.x(q),
                    w: 90 * s.pxPerDay,
                    label: `Q${Math.floor(q.getUTCMonth() / 3) + 1} ${q.getUTCFullYear()}`,
                });
            }
        }

        return {
            rows: R,
            arrows: A,
            majors,
            minors,
            weekends,
            grid,
            todayX: this.x(new Date()),
            width: s.width,
            height: Math.max(rows.length * ROW_H, 120),
        };
    }

    // ----- interactions --------------------------------------------
    onRowScroll(ev) {
        if (this.rightPane.el) this.rightPane.el.scrollTop = ev.target.scrollTop;
    }
    onPaneScroll(ev) {
        if (this.leftList.el) this.leftList.el.scrollTop = ev.target.scrollTop;
    }
    scrollToToday() {
        setTimeout(() => {
            const el = this.rightPane.el;
            if (!el) return;
            el.scrollLeft = Math.max(0, this.x(new Date()) - el.clientWidth / 3);
        });
    }
    openTask(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "eos.task",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }
    showTip(ev, t) {
        this.state.tooltip = {
            x: ev.clientX + 14,
            y: ev.clientY + 12,
            name: t.name,
            wbs: t.wbs,
            start: fmtDate(parseDT(t.planned_start)),
            finish: fmtDate(parseDT(t.planned_finish)),
            dur: t.duration_display,
            pct: Math.round(t.percent_work_complete || t.percent_complete || 0),
            slack: t.total_slack_hours,
            crit: t.is_critical,
            res: t.resource_names,
            pred: t.predecessor_display,
            warn: t.schedule_warning,
        };
    }
    hideTip() {
        this.state.tooltip = null;
    }

    startSplit(ev) {
        ev.preventDefault();
        const startX = ev.clientX;
        const startW = this.state.leftWidth;
        const move = (e) => {
            this.state.leftWidth = Math.min(900, Math.max(240, startW + e.clientX - startX));
        };
        const up = () => {
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerup", up);
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
    }

    async reschedule(level) {
        if (!this.state.rockId) return;
        this.state.loading = true;
        await this.orm.call(
            "eos.rock",
            level ? "action_reschedule_and_level" : "action_reschedule",
            [[this.state.rockId]]
        );
        await this.loadTasks();
        this.scrollToToday();
    }
    async setBaseline() {
        if (!this.state.rockId) return;
        await this.orm.call("eos.rock", "action_set_all_baselines", [[this.state.rockId]]);
        await this.loadTasks();
    }

    get rowHeight() {
        return ROW_H;
    }
    get barH() {
        return BAR_H;
    }
}

registry.category("actions").add("eos_project_gantt", EosGantt);
