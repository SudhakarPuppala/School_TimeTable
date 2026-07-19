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
from itertools import combinations

from .model import (Model, Issue, STUDY_PERIOD, GENERIC_TEACHERS,
                    SHEET_PLAN, SHEET_ALLOT, SHEET_P1, SHEET_LEISURE)


def class_capacity(m: Model, cls):
    """Total schedulable slots for the class in a week."""
    cap = 6 * 7
    if cls not in m.study_hour_classes:
        cap += m.study_days()            # Period 8 becomes teachable
    return cap


def class_content(m: Model, cls):
    return sum(m.plan.get((cls, s), 0) for s in m.subjects)


def _days_with_period(m: Model, cls, p):
    """How many days per week period p is schedulable for this class."""
    if p == STUDY_PERIOD:
        return m.study_days() if cls not in m.study_hour_classes else 0
    return 6


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

    # ---- 5. per-class window arithmetic ----
    for c in m.classes:
        # demand per teacher in this class (parallel subjects don't bind a teacher)
        dem = {}
        for s in m.subjects_of.get(c, []):
            t = m.teacher_of.get((c, s))
            if t and t not in GENERIC_TEACHERS:
                dem[t] = dem.get(t, 0) + m.plan[(c, s)]
        teachable = set(m.teachable_periods(c))
        windows = {}                       # teacher -> usable period set in this class
        for t in dem:
            w = m.teacher_allowed(t) & teachable
            if t in supervisors:
                w -= {STUDY_PERIOD}
            windows[t] = frozenset(w)
        restricted = sorted({w for t, w in windows.items() if w != frozenset(teachable)},
                            key=sorted)
        for r in range(1, min(len(restricted), 3) + 1):
            for combo in combinations(restricted, r):
                u = frozenset().union(*combo)
                cap = sum(_days_with_period(m, c, p) for p in u)
                inside = [t for t, w in windows.items() if w <= u]
                need = sum(dem[t] for t in inside)
                if need > cap:
                    plist = f"P{'/P'.join(str(p) for p in sorted(u))}"
                    who = ", ".join(f"{t} ({dem[t]})" for t in sorted(inside))
                    out.append(Issue("error",
                                     f"{c}: teachers restricted to {plist} need {need} "
                                     f"periods but the class only has {cap} such slots — "
                                     f"{who}. Free a leisure period or reassign a subject",
                                     SHEET_LEISURE, sorted(inside)[0], "Leisure Fitment"))

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
