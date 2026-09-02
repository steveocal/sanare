"""Microsoft Project-compatible scheduling layer for eos.task.

Adds WBS/outline hierarchy, MSP scheduling fields (start/finish/duration,
constraints, deadline), typed predecessor links (FS/SS/FF/SF + lag), resource
assignments with units and work/actual-work, baseline capture, and a
calendar-aware critical-path scheduler with basic resource-levelling.
"""
from datetime import datetime, timedelta

from pytz import utc

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

MAX_DEPTH = 20
LEVELLING_MAX_ITERATIONS = 300

CONSTRAINT_TYPES = [
    ('asap', 'As Soon As Possible'),
    ('alap', 'As Late As Possible'),
    ('snet', 'Start No Earlier Than'),
    ('snlt', 'Start No Later Than'),
    ('fnet', 'Finish No Earlier Than'),
    ('fnlt', 'Finish No Later Than'),
    ('mso', 'Must Start On'),
    ('mfo', 'Must Finish On'),
]
DEP_TYPES = [
    ('FS', 'Finish-to-Start'),
    ('SS', 'Start-to-Start'),
    ('FF', 'Finish-to-Finish'),
    ('SF', 'Start-to-Finish'),
]


# --------------------------------------------------------------------------
# Working-time helpers (thin wrapper over resource.calendar, with a Mon-Fri
# 8h fallback so scheduling never hard-fails on an odd calendar/version).
# --------------------------------------------------------------------------
class WorkingTime:
    def __init__(self, calendar):
        self.calendar = calendar

    @staticmethod
    def _loc(dt):
        return utc.localize(dt) if dt and not dt.tzinfo else dt

    @staticmethod
    def _naive(dt):
        return dt.astimezone(utc).replace(tzinfo=None) if dt and dt.tzinfo else dt

    def add_hours(self, start, hours):
        """Datetime reached after adding `hours` working hours from `start`.

        `hours` may be negative to plan backwards.
        """
        if not start:
            return start
        if not hours:
            return start
        if self.calendar:
            try:
                res = self.calendar.plan_hours(
                    hours, self._loc(start), compute_leaves=True)
                if res:
                    return self._naive(res)
            except Exception:  # noqa: BLE001 - fall back below on any API drift
                pass
        return self._fallback_add(start, hours)

    def hours_between(self, start, end):
        if not start or not end:
            return 0.0
        if end < start:
            return -self.hours_between(end, start)
        if self.calendar:
            try:
                return float(self.calendar.get_work_hours_count(
                    self._loc(start), self._loc(end), compute_leaves=True))
            except Exception:  # noqa: BLE001
                try:
                    return float(self.calendar._get_work_hours_count(
                        self._loc(start), self._loc(end)))
                except Exception:  # noqa: BLE001
                    pass
        return self._fallback_between(start, end)

    # -- naive Mon-Fri 09:00-17:00 fallback -------------------------------
    _DAY_START, _DAY_END, _DAY_HOURS = 9, 17, 8

    def _fallback_add(self, start, hours):
        step = timedelta(minutes=30)
        remaining = abs(hours)
        cur = start
        forward = hours > 0
        guard = 0
        while remaining > 1e-6 and guard < 200000:
            guard += 1
            nxt = cur + step if forward else cur - step
            probe = min(cur, nxt)
            if probe.weekday() < 5 and self._DAY_START <= probe.hour < self._DAY_END:
                remaining -= 0.5
            cur = nxt
        return cur

    def _fallback_between(self, start, end):
        step = timedelta(minutes=30)
        cur, total = start, 0.0
        guard = 0
        while cur < end and guard < 500000:
            guard += 1
            if cur.weekday() < 5 and self._DAY_START <= cur.hour < self._DAY_END:
                total += 0.5
            cur += step
        return total


class EosTaskDependency(models.Model):
    _name = 'eos.task.dependency'
    _description = 'EOS Task Predecessor Link'
    _rec_name = 'predecessor_task_id'

    task_id = fields.Many2one(
        'eos.task', string='Task', required=True, ondelete='cascade', index=True)
    predecessor_task_id = fields.Many2one(
        'eos.task', string='Predecessor', required=True, ondelete='cascade', index=True)
    dependency_type = fields.Selection(
        DEP_TYPES, string='Type', required=True, default='FS')
    lag_hours = fields.Float(
        string='Lag (h)', help='Working-hours lag; negative for lead time.')
    lag_display = fields.Char(string='Lag', compute='_compute_lag_display')
    rock_id = fields.Many2one(related='task_id.rock_id', store=True, index=True)

    _no_self_link = models.Constraint(
        'CHECK(task_id != predecessor_task_id)',
        'A task cannot depend on itself.',
    )
    _uniq_link = models.Constraint(
        'unique(task_id, predecessor_task_id)',
        'That predecessor is already linked to this task.',
    )

    @api.depends('lag_hours')
    def _compute_lag_display(self):
        for link in self:
            if not link.lag_hours:
                link.lag_display = ''
            else:
                days = link.lag_hours / 8.0
                sign = '+' if link.lag_hours > 0 else '-'
                link.lag_display = '%s%gd' % (sign, abs(round(days, 2)))

    @api.constrains('task_id', 'predecessor_task_id')
    def _check_no_cycle(self):
        for link in self:
            seen = set()
            stack = [link.predecessor_task_id.id]
            while stack:
                cur = stack.pop()
                if cur == link.task_id.id:
                    raise ValidationError(
                        'Circular dependency: %s ↔ %s'
                        % (link.task_id.display_name,
                           link.predecessor_task_id.display_name))
                if cur in seen:
                    continue
                seen.add(cur)
                stack += self.search(
                    [('task_id', '=', cur)]).mapped('predecessor_task_id').ids


class EosTaskAssignment(models.Model):
    _name = 'eos.task.assignment'
    _description = 'EOS Task Resource Assignment'
    _rec_name = 'user_id'

    task_id = fields.Many2one(
        'eos.task', string='Task', required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', string='Resource', required=True)
    units = fields.Float(
        string='Units %', default=100.0,
        help='Allocation percentage of the resource to this task (MSP Units).')
    work_hours = fields.Float(string='Work (h)')
    actual_work_hours = fields.Float(string='Actual Work (h)')
    rock_id = fields.Many2one(related='task_id.rock_id', store=True, index=True)


class EosTask(models.Model):
    _inherit = 'eos.task'

    # -- WBS / outline -------------------------------------------------------
    parent_task_id = fields.Many2one(
        'eos.task', string='Parent Task', ondelete='cascade', index=True,
        domain="[('rock_id', '=', rock_id), ('id', '!=', id)]")
    child_task_ids = fields.One2many(
        'eos.task', 'parent_task_id', string='Sub-tasks')
    outline_level = fields.Integer(
        string='Outline Level', compute='_compute_outline_level', store=True,
        recursive=True)
    wbs = fields.Char(string='WBS', compute='_compute_wbs')
    is_summary = fields.Boolean(
        string='Summary Task', compute='_compute_is_summary', store=True)

    # -- MSP scheduling core ----------------------------------------------
    task_mode = fields.Selection(
        [('auto', 'Auto Scheduled'), ('manual', 'Manually Scheduled')],
        string='Schedule Mode', default='auto', required=True)
    planned_start = fields.Datetime(string='Start')
    planned_finish = fields.Datetime(string='Finish')
    duration_hours = fields.Float(string='Duration (h)', default=8.0)
    duration_display = fields.Char(
        string='Duration', compute='_compute_duration_display')
    is_milestone = fields.Boolean(string='Milestone')
    calendar_id = fields.Many2one('resource.calendar', string='Task Calendar')
    effort_driven = fields.Boolean(string='Effort Driven')

    # -- constraints / deadline -----------------------------------------
    constraint_type = fields.Selection(
        CONSTRAINT_TYPES, string='Constraint Type', default='asap', required=True)
    constraint_date = fields.Datetime(string='Constraint Date')
    deadline = fields.Datetime(string='Deadline')

    # -- work -----------------------------------------------------------
    work_hours = fields.Float(string='Work (h)')
    actual_work_hours = fields.Float(string='Actual Work (h)')
    remaining_work_hours = fields.Float(
        string='Remaining Work (h)', compute='_compute_remaining_work', store=True)
    percent_work_complete = fields.Float(string='% Work Complete')

    # -- baseline -----------------------------------------------------
    baseline_start = fields.Datetime(string='Baseline Start', readonly=True)
    baseline_finish = fields.Datetime(string='Baseline Finish', readonly=True)
    baseline_duration_hours = fields.Float(
        string='Baseline Duration (h)', readonly=True)
    baseline_work_hours = fields.Float(string='Baseline Work (h)', readonly=True)
    baseline_date = fields.Datetime(string='Baseline Saved On', readonly=True)

    # -- CPM outputs -------------------------------------------------
    early_start = fields.Datetime(string='Early Start', readonly=True)
    early_finish = fields.Datetime(string='Early Finish', readonly=True)
    late_start = fields.Datetime(string='Late Start', readonly=True)
    late_finish = fields.Datetime(string='Late Finish', readonly=True)
    total_slack_hours = fields.Float(string='Total Slack (h)', readonly=True)
    free_slack_hours = fields.Float(string='Free Slack (h)', readonly=True)
    is_critical = fields.Boolean(string='Critical', readonly=True, index=True)
    schedule_warning = fields.Char(string='Schedule Warning', readonly=True)

    # -- links --------------------------------------------------------
    predecessor_ids = fields.One2many(
        'eos.task.dependency', 'task_id', string='Predecessors')
    successor_ids = fields.One2many(
        'eos.task.dependency', 'predecessor_task_id', string='Successors')
    predecessor_display = fields.Char(
        string='Predecessors', compute='_compute_predecessor_display')

    # -- resources ---------------------------------------------------
    assignment_ids = fields.One2many(
        'eos.task.assignment', 'task_id', string='Resources')
    resource_names = fields.Char(
        string='Resource Names', compute='_compute_resource_names')
    is_overallocated = fields.Boolean(string='Over-allocated', readonly=True)

    # ==================================================================
    # Computes
    # ==================================================================
    @api.depends('parent_task_id', 'parent_task_id.outline_level')
    def _compute_outline_level(self):
        for task in self:
            level, cur, guard = 0, task.parent_task_id, 0
            while cur and guard < MAX_DEPTH:
                level += 1
                cur = cur.parent_task_id
                guard += 1
            task.outline_level = level

    @api.depends('child_task_ids')
    def _compute_is_summary(self):
        for task in self:
            task.is_summary = bool(task.child_task_ids)

    @api.depends('parent_task_id', 'sequence', 'rock_id',
                 'rock_id.task_ids.sequence', 'rock_id.task_ids.parent_task_id')
    def _compute_wbs(self):
        for task in self:
            task.wbs = ''
        rock_ids = set(self.mapped('rock_id').ids)
        for rock_id in rock_ids:
            siblings = self.env['eos.task'].search(
                [('rock_id', '=', rock_id)], order='sequence, id')
            children = {}
            for t in siblings:
                children.setdefault(t.parent_task_id.id, []).append(t)
            numbers = {}

            def walk(parent_id, prefix):
                for idx, node in enumerate(children.get(parent_id, []), start=1):
                    num = '%s%d' % (prefix, idx)
                    numbers[node.id] = num
                    walk(node.id, num + '.')

            walk(False, '')
            for t in self:
                if t.rock_id.id == rock_id:
                    t.wbs = numbers.get(t.id, '')

    @api.depends('duration_hours', 'is_milestone')
    def _compute_duration_display(self):
        for task in self:
            if task.is_milestone or not task.duration_hours:
                task.duration_display = '0 d'
            else:
                task.duration_display = '%g d' % round(task.duration_hours / 8.0, 2)

    @api.depends('work_hours', 'actual_work_hours')
    def _compute_remaining_work(self):
        for task in self:
            task.remaining_work_hours = max(
                0.0, (task.work_hours or 0.0) - (task.actual_work_hours or 0.0))

    @api.depends('predecessor_ids.predecessor_task_id',
                 'predecessor_ids.dependency_type', 'predecessor_ids.lag_hours')
    def _compute_predecessor_display(self):
        for task in self:
            parts = []
            for link in task.predecessor_ids:
                ref = link.predecessor_task_id.task_id or str(
                    link.predecessor_task_id.id)
                token = ref
                if link.dependency_type != 'FS':
                    token += link.dependency_type
                if link.lag_hours:
                    token += link.lag_display
                parts.append(token)
            task.predecessor_display = ', '.join(parts)

    @api.depends('assignment_ids.user_id', 'assignment_ids.units')
    def _compute_resource_names(self):
        for task in self:
            task.resource_names = ', '.join(
                '%s%s' % (a.user_id.name,
                          '' if a.units == 100 else ' [%g%%]' % a.units)
                for a in task.assignment_ids)

    # ==================================================================
    # Actions
    # ==================================================================
    def action_open_task(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'eos.task',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_set_baseline(self):
        for task in self:
            task.write({
                'baseline_start': task.planned_start,
                'baseline_finish': task.planned_finish,
                'baseline_duration_hours': task.duration_hours,
                'baseline_work_hours': task.work_hours,
                'baseline_date': fields.Datetime.now(),
            })

    # ==================================================================
    # Scheduling engine (CPM, calendar-aware)
    # ==================================================================
    def _plan_calendar(self):
        return (self.calendar_id
                or self.rock_id.calendar_id
                or self.env.company.resource_calendar_id)

    @api.model
    def _schedule_rock(self, rock, level_resources=False):
        tasks = rock.task_ids
        leaves = tasks.filtered(lambda t: not t.child_task_ids)
        if not leaves:
            return

        links = self.env['eos.task.dependency'].search(
            [('task_id', 'in', leaves.ids), ('predecessor_task_id', 'in', leaves.ids)])
        preds = {}
        succs = {}
        for lk in links:
            preds.setdefault(lk.task_id.id, []).append(lk)
            succs.setdefault(lk.predecessor_task_id.id, []).append(lk)

        order = self._topological_order(leaves, preds)
        by_id = {t.id: t for t in leaves}
        default_wt = WorkingTime(rock.calendar_id
                                 or self.env.company.resource_calendar_id)
        project_start = self._project_start(rock)

        extra_delay = {}  # task_id -> hours pushed by resource levelling

        def forward_pass():
            es, ef = {}, {}
            for tid in order:
                t = by_id[tid]
                wt = WorkingTime(t._plan_calendar())
                dur = 0.0 if t.is_milestone else max(t.duration_hours or 0.0, 0.0)
                cands = [project_start]
                for lk in preds.get(tid, []):
                    p = lk.predecessor_task_id.id
                    if p not in ef:
                        continue
                    dt = lk.dependency_type
                    lag = lk.lag_hours or 0.0
                    if dt == 'FS':
                        cands.append(wt.add_hours(ef[p], lag))
                    elif dt == 'SS':
                        cands.append(wt.add_hours(es[p], lag))
                    elif dt == 'FF':
                        cands.append(wt.add_hours(wt.add_hours(ef[p], lag), -dur))
                    elif dt == 'SF':
                        cands.append(wt.add_hours(wt.add_hours(es[p], lag), -dur))
                start = max(c for c in cands if c)
                start = self._apply_start_constraint(t, start, wt)
                if extra_delay.get(tid):
                    start = wt.add_hours(start, extra_delay[tid])
                es[tid] = start
                ef[tid] = wt.add_hours(start, dur) if dur else start
            return es, ef

        es, ef = forward_pass()

        if level_resources:
            self._level_resources(order, by_id, preds, es, ef, extra_delay,
                                  forward_pass_ref=forward_pass)
            es, ef = forward_pass()

        project_finish = max(ef.values()) if ef else project_start

        # Backward pass
        ls, lf = {}, {}
        for tid in reversed(order):
            t = by_id[tid]
            wt = WorkingTime(t._plan_calendar())
            dur = 0.0 if t.is_milestone else max(t.duration_hours or 0.0, 0.0)
            cands = []
            for lk in succs.get(tid, []):
                s = lk.task_id.id
                if s not in ls:
                    continue
                dt = lk.dependency_type
                lag = lk.lag_hours or 0.0
                if dt == 'FS':
                    cands.append(wt.add_hours(ls[s], -lag))
                elif dt == 'SS':
                    cands.append(wt.add_hours(wt.add_hours(ls[s], -lag), dur))
                elif dt == 'FF':
                    cands.append(wt.add_hours(lf[s], -lag))
                elif dt == 'SF':
                    cands.append(wt.add_hours(wt.add_hours(lf[s], -lag), dur))
            if t.deadline:
                cands.append(t.deadline)
            finish = min(cands) if cands else project_finish
            lf[tid] = finish
            ls[tid] = wt.add_hours(finish, -dur) if dur else finish

        # Write results
        for tid in order:
            t = by_id[tid]
            wt = WorkingTime(t._plan_calendar())
            slack = wt.hours_between(es[tid], ls[tid])
            warn = False
            if t.deadline and ef[tid] and ef[tid] > t.deadline:
                warn = 'Finish %s is past the deadline' % fields.Datetime.to_string(
                    ef[tid])
            vals = {
                'early_start': es[tid], 'early_finish': ef[tid],
                'late_start': ls[tid], 'late_finish': lf[tid],
                'total_slack_hours': round(slack, 2),
                'is_critical': slack <= 0.01,
                'schedule_warning': warn,
            }
            if t.task_mode == 'auto':
                vals['planned_start'] = es[tid]
                vals['planned_finish'] = ef[tid]
            t.write(vals)

        self._rollup_summaries(rock)
        self._flag_overallocation(rock)

    def _topological_order(self, tasks, preds):
        indeg = {t.id: 0 for t in tasks}
        adj = {t.id: [] for t in tasks}
        for tid, links in preds.items():
            for lk in links:
                p = lk.predecessor_task_id.id
                if p in adj and tid in indeg:
                    adj[p].append(tid)
                    indeg[tid] += 1
        queue = sorted([tid for tid, d in indeg.items() if d == 0])
        out = []
        while queue:
            cur = queue.pop(0)
            out.append(cur)
            for nxt in adj[cur]:
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    queue.append(nxt)
                    queue.sort()
        if len(out) != len(indeg):
            raise UserError(
                'Cannot schedule: the task dependencies contain a cycle.')
        return out

    def _project_start(self, rock):
        starts = []
        for t in rock.task_ids:
            if t.constraint_type in ('snet', 'mso') and t.constraint_date:
                starts.append(t.constraint_date)
        if rock.plan_start_date:
            base = datetime.combine(rock.plan_start_date, datetime.min.time()).replace(
                hour=9)
            starts.append(base)
        if not starts:
            now = fields.Datetime.now()
            starts.append(now.replace(hour=9, minute=0, second=0, microsecond=0))
        return min(starts)

    def _apply_start_constraint(self, task, start, wt):
        ct, cd = task.constraint_type, task.constraint_date
        if not cd:
            return start
        if ct in ('snet', 'mso') and start < cd:
            return cd
        if ct == 'mso':
            return cd
        if ct == 'snlt' and start > cd:
            return cd
        if ct in ('fnet',) and cd:
            dur = 0.0 if task.is_milestone else max(task.duration_hours or 0.0, 0.0)
            min_start = wt.add_hours(cd, -dur)
            if start < min_start:
                return min_start
        return start

    def _rollup_summaries(self, rock):
        summaries = rock.task_ids.filtered(lambda t: t.child_task_ids)
        # deepest first
        for summary in summaries.sorted(lambda s: -s.outline_level):
            kids = summary.child_task_ids
            starts = [k.planned_start for k in kids if k.planned_start]
            finishes = [k.planned_finish for k in kids if k.planned_finish]
            work = sum(k.work_hours or 0.0 for k in kids)
            done = sum((k.work_hours or 0.0) * (k.percent_work_complete or 0.0) / 100.0
                       for k in kids)
            summary.write({
                'planned_start': min(starts) if starts else summary.planned_start,
                'planned_finish': max(finishes) if finishes else summary.planned_finish,
                'early_start': min(starts) if starts else False,
                'early_finish': max(finishes) if finishes else False,
                'work_hours': work,
                'percent_work_complete': (done / work * 100.0) if work else 0.0,
                'is_critical': any(k.is_critical for k in kids),
                'duration_hours': (
                    WorkingTime(summary._plan_calendar()).hours_between(
                        min(starts), max(finishes))
                    if starts and finishes else summary.duration_hours),
            })

    def _resource_load_by_day(self, order, by_id, es, ef):
        """Return {date: {user_id: hours}} across auto tasks in the window."""
        load = {}
        for tid in order:
            t = by_id[tid]
            if t.is_milestone or not es.get(tid) or not ef.get(tid):
                continue
            assigns = t.assignment_ids
            if not assigns:
                continue
            span_days = max(1, (ef[tid].date() - es[tid].date()).days + 1)
            for a in assigns:
                per_day = (t.duration_hours or 0.0) / span_days * (a.units or 100.0) / 100.0
                d = es[tid].date()
                for _ in range(span_days):
                    if d.weekday() < 5:
                        load.setdefault(d, {}).setdefault(a.user_id.id, 0.0)
                        load[d][a.user_id.id] += per_day
                    d += timedelta(days=1)
        return load

    def _level_resources(self, order, by_id, preds, es, ef, extra_delay,
                         forward_pass_ref):
        """Greedy, priority-ordered levelling (MSP 'Level' style, no splitting).

        Non-critical, auto-scheduled tasks are delayed a day at a time to clear
        the worst per-resource over-allocation. Approximate, not optimal.
        """
        prio_rank = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3, False: 2}
        for _ in range(LEVELLING_MAX_ITERATIONS):
            load = self._resource_load_by_day(order, by_id, es, ef)
            worst = None
            for day, per_user in load.items():
                for uid, hrs in per_user.items():
                    if hrs > 8.01 and (worst is None or hrs > worst[2]):
                        worst = (day, uid, hrs)
            if not worst:
                break
            day, uid, _hrs = worst
            movable = []
            for tid in order:
                t = by_id[tid]
                if t.task_mode != 'auto' or t.is_milestone or t.is_critical:
                    continue
                if uid not in t.assignment_ids.mapped('user_id').ids:
                    continue
                if not es.get(tid) or es[tid].date() > day or ef[tid].date() < day:
                    continue
                movable.append(t)
            if not movable:
                break
            movable.sort(key=lambda t: (prio_rank.get(t.priority, 2), t.id))
            victim = movable[-1]
            extra_delay[victim.id] = extra_delay.get(victim.id, 0.0) + 8.0
            es, ef = forward_pass_ref()

    def _flag_overallocation(self, rock):
        leaves = rock.task_ids.filtered(lambda t: not t.child_task_ids)
        order = [t.id for t in leaves]
        by_id = {t.id: t for t in leaves}
        es = {t.id: t.planned_start for t in leaves}
        ef = {t.id: t.planned_finish for t in leaves}
        load = self._resource_load_by_day(order, by_id, es, ef)
        over_users = set()
        for per_user in load.values():
            for uid, hrs in per_user.items():
                if hrs > 8.01:
                    over_users.add(uid)
        for t in leaves:
            t.is_overallocated = bool(
                set(t.assignment_ids.mapped('user_id').ids) & over_users)


class EosRockPlan(models.Model):
    _inherit = 'eos.rock'

    calendar_id = fields.Many2one(
        'resource.calendar', string='Project Calendar',
        help='Working-time calendar used to schedule this Rock\'s tasks.')
    plan_start_date = fields.Date(
        string='Plan Start',
        help='Project start date for auto-scheduled tasks with no constraint.')
    plan_finish_date = fields.Date(
        string='Plan Finish', compute='_compute_plan_finish', store=True)
    critical_task_count = fields.Integer(
        string='Critical Tasks', compute='_compute_plan_finish', store=True)

    @api.depends('task_ids.planned_finish', 'task_ids.is_critical')
    def _compute_plan_finish(self):
        for rock in self:
            finishes = rock.task_ids.mapped('planned_finish')
            finishes = [f for f in finishes if f]
            rock.plan_finish_date = max(finishes).date() if finishes else False
            rock.critical_task_count = len(
                rock.task_ids.filtered('is_critical'))

    def action_reschedule(self):
        for rock in self:
            self.env['eos.task']._schedule_rock(rock, level_resources=False)
        return self._plan_reload_action()

    def action_reschedule_and_level(self):
        for rock in self:
            self.env['eos.task']._schedule_rock(rock, level_resources=True)
        return self._plan_reload_action()

    def action_set_all_baselines(self):
        for rock in self:
            rock.task_ids.action_set_baseline()
        return self._plan_reload_action()

    def action_open_gantt(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'eos_project_gantt',
            'name': 'Project Plan — %s' % (self.rock_id or self.name),
            'params': {'rock_id': self.id},
        }

    def _plan_reload_action(self):
        return {'type': 'ir.actions.client', 'tag': 'reload'}
