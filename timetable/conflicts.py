"""Pre-solve conflict checker.

Runs BEFORE the CP-SAT solver and reports every data problem that would make
the timetable impossible (errors) or surprising (warnings/info).  Each
`Issue` carries (sheet, row_key, col_key) so the dashboard can paint the
offending cells red.

Checks:
  1.  load-time issues (unknown names, bad numbers, duplicates, ...)
  2.  planned subject with no teacher
  3.  class weekly total vs available slots
  4.  teacher demand vs leisure-plan availability
  5.  per-class window arithmetic (restricted teachers vs late/early slots)
  6.  Study-Hour supervisor whose leisure blocks the Study Hour
  7.  data-gap warnings (no supervisor / no Period-1 teacher / unused rows)
"""
from __future__ import annotations
from collections import defaultdict, deque

from .model import (Model, Issue, DAYS, STUDY_PERIOD, GENERIC_TEACHERS,
                    SHEET_PLAN, SHEET_ALLOT, SHEET_P1, SHEET_LEISURE, SHEET_ACTIVITY)


def _class_pack_deficit(m: Model, c, supervisors):
    """Can class c place all its subject-periods into distinct slots, honouring
    each subject's teacher-leisure ∩ activity window?  Returns None if feasible,
    else (deficient_subjects, their_available_slots, need, demand) — the exact
    over-constrained set from the max-flow min-cut.

    Ignores cross-class teacher contention (that's checks 4/6); this is the
    per-class necessary condition that pins down Activity-Plan / leisure squeezes.
    """
    teachable = set(m.teachable_periods(c))
    subs, demand, options = [], {}, {}
    for s in m.subjects_of.get(c, []):
        n = m.plan.get((c, s), 0)
        if n <= 0:
            continue
        t = m.teacher_of.get((c, s))
        allow_p = set(teachable)
        if t and t not in GENERIC_TEACHERS:
            allow_p &= m.teacher_allowed(t)
            if t in supervisors:
                allow_p.discard(STUDY_PERIOD)
        opt = set()
        for d in range(len(DAYS)):
            if not allow_p:
                break
            for p in allow_p:
                if p == STUDY_PERIOD and DAYS[d] in m.cfg.no_p8_days:
                    continue
                if m.has_activity_window(s, c) and not m.activity_allows(s, c, d, p):
                    continue
                opt.add((d, p))
        subs.append(s)
        demand[s] = n
        options[s] = opt
    total = sum(demand.values())
    if total == 0:
        return None
    slot_list = sorted(set().union(*options.values())) if options else []
    slot_id = {sl: i for i, sl in enumerate(slot_list)}
    N, M = len(subs), len(slot_list)
    src, snk = 0, 1 + N + M
    cap = defaultdict(int)
    adj = defaultdict(set)

    def add(u, v, w):
        cap[(u, v)] += w
        adj[u].add(v)
        adj[v].add(u)

    for i, s in enumerate(subs):
        add(src, 1 + i, demand[s])
        for sl in options[s]:
            add(1 + i, 1 + N + slot_id[sl], 1)
    for j in range(M):
        add(1 + N + j, snk, 1)

    flow = 0
    while True:
        parent = {src: None}
        q = deque([src])
        while q:
            u = q.popleft()
            if u == snk:
                break
            for v in adj[u]:
                if v not in parent and cap[(u, v)] > 0:
                    parent[v] = u
                    q.append(v)
        if snk not in parent:
            break
        v, path = snk, []
        while parent[v] is not None:
            path.append((parent[v], v))
            v = parent[v]
        bott = min(cap[e] for e in path)
        for u, w in path:
            cap[(u, w)] -= bott
            cap[(w, u)] += bott
        flow += bott
    if flow == total:
        return None

    seen = {src}
    q = deque([src])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in seen and cap[(u, v)] > 0:
                seen.add(v)
                q.append(v)
    def_subs = [subs[i] for i in range(N) if (1 + i) in seen]
    if not def_subs:
        def_subs = subs
    avail = set().union(*(options[s] for s in def_subs)) if def_subs else set()
    need = sum(demand[s] for s in def_subs)
    if need <= len(avail):                      # message wouldn't make sense; widen set
        def_subs, avail, need = subs, set().union(*options.values()), total
    return def_subs, sorted(avail), need, demand


def _period_label(p):
    return "Study Hour" if p == STUDY_PERIOD else f"P{p}"


def _describe_slots(m: Model, slotset):
    """Compactly render a set of (day-index, period) slots, e.g.
    'MON/WED/FRI × P6, SAT × P5'.  Groups days that share the same period-set."""
    by_period_set = {}
    for d in sorted({d for d, _ in slotset}):
        ps = tuple(sorted(p for dd, p in slotset if dd == d))
        by_period_set.setdefault(ps, []).append(d)
    parts = []
    for ps, days in sorted(by_period_set.items(), key=lambda kv: kv[1]):
        parts.append(f"{'/'.join(DAYS[d] for d in days)} × "
                     f"{'/'.join(_period_label(p) for p in ps)}")
    return ", ".join(parts)


def class_capacity(m: Model, cls):
    """Total schedulable slots for the class in a week."""
    cap = 6 * 7
    if cls not in m.study_hour_classes:
        cap += m.study_days()            # Period 8 becomes teachable
    return cap


def class_content(m: Model, cls):
    return sum(m.plan.get((cls, s), 0) for s in m.subjects)


def teacher_capacity(m: Model, t):
    """Teachable slots/week for a real teacher, honouring MUST leisure.
    Period 8 counts only where it is teachable (no-Study-Hour classes) and
    only if the teacher is not supervising a study hour then."""
    allowed = m.teacher_allowed(t)
    cap = 6 * len(allowed - {STUDY_PERIOD})
    supervises = t in {m.study_supervisor.get(c) for c in m.study_hour_classes}
    teaches_p8_class = any(c not in m.study_hour_classes for c, _, _ in m.teaching_load(t))
    if STUDY_PERIOD in allowed and teaches_p8_class and not supervises:
        cap += m.study_days()
    return cap


def teacher_demand(m: Model, t):
    return sum(n for _, _, n in m.teaching_load(t))


def check_conflicts(m: Model):
    """-> list[Issue], errors first."""
    out = list(m.issues)
    sup_of = {c: m.study_supervisor.get(c) for c in m.study_hour_classes}
    supervisors = set(sup_of.values())

    # ---- 2. planned subject with no teacher ----
    for c in m.classes:
        for s in m.subjects_of.get(c, []):
            if (c, s) not in m.teacher_of:
                out.append(Issue("error",
                                 f"{c} · {s}: {m.plan[(c, s)]} period(s)/week planned but no "
                                 f"teacher in Teacher Allotment", SHEET_ALLOT, s, c))

    # ---- 3. class totals vs capacity ----
    for c in m.classes:
        content, cap = class_content(m, c), class_capacity(m, c)
        if content > cap:
            out.append(Issue("error",
                             f"{c}: {content} periods/week planned but only {cap} slots exist "
                             f"({'no ' if c not in m.study_hour_classes else ''}Study Hour"
                             f"{'' if not m.cfg.no_p8_days else ', no P8 on ' + '/'.join(sorted(m.cfg.no_p8_days))})"
                             f" — reduce the Weekly Period Plan column by {content - cap}",
                             SHEET_PLAN, "Total", c))
        elif content < 6 * 7:
            out.append(Issue("info",
                             f"{c}: {content} periods/week planned, {6 * 7 - content} free "
                             f"period(s) will show as Recreation", SHEET_PLAN, "Total", c))

    # ---- 4. teacher demand vs availability ----
    for t in m.teachers:
        demand, cap = teacher_demand(m, t), teacher_capacity(m, t)
        if demand > cap:
            det = ", ".join(f"{c} {s}×{n}" for c, s, n in m.teaching_load(t))
            allowed = sorted(m.teacher_allowed(t))
            out.append(Issue("error",
                             f"{t}: allotted {demand} periods/week but the Leisure Plan leaves "
                             f"only {cap} slots (available periods {allowed}). Load: {det}. "
                             f"Free a leisure period or move a subject to another teacher",
                             SHEET_LEISURE, t, "Leisure Fitment"))
        # ---- 6. supervisor blocked at Study Hour ----
        if t in supervisors and STUDY_PERIOD in m.blocked.get(t, set()):
            cls = ", ".join(c for c, s in sup_of.items() if s == t)
            out.append(Issue("error",
                             f"{t} supervises the Study Hour of {cls} but the Leisure Plan "
                             f"marks their Study Hour as Leisure (MUST)",
                             SHEET_LEISURE, t, "Study Hour"))

    # ---- 5. per-class packing feasibility (exact, via max-flow / Hall) ----
    # Each class must place all its subject-periods into its own (day, period)
    # slots, one subject per slot, where each subject may only use slots inside
    # its teacher's leisure window AND its Activity-Plan window. This is a
    # bipartite b-matching; if it has no perfect matching the timetable is
    # impossible. The min-cut names the exact over-constrained subjects, so the
    # user gets a precise message instead of a bare solver INFEASIBLE.
    for c in m.classes:
        deficit = _class_pack_deficit(m, c, supervisors)
        if deficit is None:
            continue
        def_subs, def_slots, need, demand = deficit
        avail = len(def_slots)
        detail = ", ".join(f"{s} ({demand[s]})" for s in def_subs)
        where = _describe_slots(m, def_slots) if def_slots else "no usable slot"
        # blame the Activity Plan if any deficient subject is activity-limited,
        # else the Leisure Plan (a teacher window is the binding constraint)
        act_sub = next((s for s in def_subs if m.has_activity_window(s, c)), None)
        if act_sub:
            sheet, row, col = SHEET_ACTIVITY, act_sub, "Allowed Periods"
        else:
            binder = next((m.teacher_of.get((c, s)) for s in def_subs
                           if m.teacher_of.get((c, s)) not in GENERIC_TEACHERS), None)
            sheet, row, col = SHEET_LEISURE, (binder or def_subs[0]), "Leisure Fitment"
        out.append(Issue("error",
                         f"{c}: {detail} together need {need} period(s) but can only be "
                         f"placed in {avail} slot(s) — {where}. Widen the Activity-Plan "
                         f"days/periods or free a leisure period for these, or reduce the "
                         f"Weekly Period Plan count",
                         sheet, row, col))

    # ---- 7. data-gap warnings ----
    for c in m.classes:
        if not m.p1_teacher.get(c):
            out.append(Issue("warning", f"{c}: no Period-1 teacher named",
                             SHEET_P1, c, "Period 1 Teacher"))
        if c not in m.study_hour_classes and class_content(m, c) < class_capacity(m, c):
            out.append(Issue("warning",
                             f"{c}: no Study-Hour supervisor — Period 8 will be free/"
                             f"Recreation unless a supervisor is named",
                             SHEET_P1, c, "Study Hour"))
        pt = m.p1_teacher.get(c)
        if pt and pt not in GENERIC_TEACHERS:
            if not any(m.teacher_of.get((c, s)) == pt for s in m.subjects_of.get(c, [])):
                out.append(Issue("warning",
                                 f"{c}: Period-1 teacher {pt} has no subject allotted in "
                                 f"this class, so they cannot actually take Period 1",
                                 SHEET_P1, c, "Period 1 Teacher"))
    used = {t for t in m.teacher_of.values()} | supervisors | set(m.p1_teacher.values())
    for t in m.leisure_teachers:
        if t not in used:
            out.append(Issue("info", f"{t} is in the Teacher Leisure Plan but has no "
                             f"allotment anywhere", SHEET_LEISURE, t, "Teacher Name"))

    # de-duplicate identical messages, errors first
    seen, dedup = set(), []
    for i in sorted(out, key=lambda i: {"error": 0, "warning": 1, "info": 2}[i.severity]):
        if i.message not in seen:
            seen.add(i.message)
            dedup.append(i)
    return dedup


def has_errors(conflicts):
    return any(i.severity == "error" for i in conflicts)


def error_cells(conflicts):
    """-> {sheet: {(row_key, col_key)}} for RED cell highlighting."""
    cells = {}
    for i in conflicts:
        if i.severity == "error" and i.sheet:
            cells.setdefault(i.sheet, set()).add((i.row_key, i.col_key))
    return cells
