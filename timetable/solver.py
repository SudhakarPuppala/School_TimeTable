"""CP-SAT timetable solver — availability comes from the Teacher Leisure Plan.

Decision var  x[(class, subject, day, period)] = 1 if that class studies that
subject in that slot.

Hard constraints:
  - exact weekly count per (class, subject)
  - at most one subject per class slot
  - no teacher double-booking (generic P.E / MARTIAL ARTS instructors exempt)
  - MUST leisure periods are unavailable
  - Study-Hour supervisors never teach in Period 8
  - Period 8 exists only for no-Study-Hour classes (and not on no-P8 days)

Soft objective (minimise):
  - BEST-marked leisure periods used                       (weight 150)
  - a teacher busy a whole morning (P1-4) or whole
    afternoon (P5-8) block with no gap — the Lunch Break
    splits the day, so runs are counted per block          (weight 60)
  - same subject twice in one day                          (weight 5)
  - Period-8 teaching (pack P1-P7 first)                   (weight 3)
  - class's Period-1 teacher NOT taking Period 1           (reward 15)

Returns (solution, status, objective, notes).
"""
from __future__ import annotations
from collections import defaultdict

from ortools.sat.python import cp_model

from .model import Model, DAYS, N_DAYS, STUDY_PERIOD, GENERIC_TEACHERS
from .conflicts import check_conflicts

MORNING = (1, 2, 3, 4)
AFTERNOON = (5, 6, 7, 8)


def solve(m: Model, max_seconds: int = 120, log: bool = False, precheck: bool = True):
    if precheck:
        conflicts = [c for c in check_conflicts(m) if c.severity == "error"]
        if conflicts:
            msg = "\n".join(f"  - {c.message}" for c in conflicts)
            raise ValueError(
                f"{len(conflicts)} conflict(s) must be resolved before generating:\n{msg}")

    model = cp_model.CpModel()
    x = {}
    by_slot = defaultdict(list)          # (class, day, period)   -> vars
    by_cs = defaultdict(list)            # (class, subject)       -> vars
    by_teacher_slot = defaultdict(list)  # (teacher, day, period) -> vars
    supervisors = {m.study_supervisor[c] for c in m.study_hour_classes
                   if m.study_supervisor.get(c)}

    for c in m.classes:
        teachable = m.teachable_periods(c)
        for s in m.subjects_of[c]:
            teacher = m.teacher_of.get((c, s))
            if teacher is None:
                continue                                    # precheck reports this
            parallel = teacher in GENERIC_TEACHERS
            allowed = set(teachable)
            if (s, c) in m.activity_window:          # Activity Plan: allowed periods
                allowed &= m.activity_window[(s, c)]
            act_days = m.activity_days.get((s, c))   # Activity Plan: allowed days
            if not parallel:
                allowed &= m.teacher_allowed(teacher)
                if teacher in supervisors:
                    allowed.discard(STUDY_PERIOD)
            for d in range(N_DAYS):
                if act_days is not None and d not in act_days:
                    continue
                for p in allowed:
                    if p == STUDY_PERIOD and not m.has_p8(DAYS[d]):
                        continue
                    v = model.NewBoolVar(f"x_{c}_{s}_{d}_{p}")
                    x[(c, s, d, p)] = v
                    by_slot[(c, d, p)].append(v)
                    by_cs[(c, s)].append(v)
                    if not parallel:
                        by_teacher_slot[(teacher, d, p)].append(v)

    for (c, s), n in m.plan.items():
        if n == 0 or c not in m.classes:
            continue
        vs = by_cs[(c, s)]
        if len(vs) < n:
            raise ValueError(
                f"{c} · {s}: needs {n} periods/week but only {len(vs)} usable slots "
                f"exist for {m.teacher_of.get((c, s))} — check the Teacher Leisure Plan.")
        model.Add(sum(vs) == n)

    for vs in by_slot.values():
        if len(vs) > 1:
            model.Add(sum(vs) <= 1)                        # one subject per class slot

    for vs in by_teacher_slot.values():
        if len(vs) > 1:
            model.Add(sum(vs) <= 1)                        # no double-booking

    # ---- soft objective ----
    penalties = []

    # busy indicators per teacher/day/period (supervision occupies P8)
    busy = {}
    for t in m.teachers:
        sup_classes = [c for c in m.study_hour_classes if m.study_supervisor.get(c) == t]
        for d in range(N_DAYS):
            for p in range(1, 9):
                vs = by_teacher_slot.get((t, d, p), [])
                b = model.NewBoolVar(f"busy_{t}_{d}_{p}")
                if p == STUDY_PERIOD and sup_classes and m.has_p8(DAYS[d]):
                    model.Add(b == 1)                      # supervising study hour
                elif vs:
                    model.Add(b == sum(vs))
                else:
                    model.Add(b == 0)
                busy[(t, d, p)] = b

    # whole morning / whole afternoon without a gap (lunch splits the day)
    for t in m.teachers:
        for d in range(N_DAYS):
            for block in (MORNING, AFTERNOON):
                pen = model.NewBoolVar(f"block_{t}_{d}_{block[0]}")
                model.Add(sum(busy[(t, d, p)] for p in block) - (len(block) - 1) <= pen)
                penalties.append((60, pen))

    # BEST teachers' marked leisure periods — avoid if possible
    for (c, s, d, p), v in x.items():
        t = m.teacher_of[(c, s)]
        if p in m.soft_blocked.get(t, set()):
            penalties.append((150, v))

    # prefer the class's Period-1 teacher to open the day
    for c in m.classes:
        ct = m.p1_teacher.get(c)
        if not ct:
            continue
        for s in m.subjects_of[c]:
            if m.teacher_of.get((c, s)) == ct:
                for d in range(N_DAYS):
                    if (c, s, d, 1) in x:
                        penalties.append((-15, x[(c, s, d, 1)]))

    # pack P1-P7 before spilling into Period 8
    for (c, s, d, p), v in x.items():
        if p == STUDY_PERIOD:
            penalties.append((3, v))

    # Activity Plan groups: combine sessions — minimise the number of distinct
    # (day, period) sessions per (activity, group) so grouped classes do the
    # activity together whenever the weekly counts allow.
    groups = defaultdict(list)                       # (subject, label) -> classes
    for (s, c), label in m.activity_group.items():
        if c in m.classes and m.plan.get((c, s), 0) > 0:
            groups[(s, label)].append(c)
    for (s, label), cls_list in groups.items():
        if len(cls_list) < 2:
            continue
        for d in range(N_DAYS):
            for p in range(1, 9):
                vs = [x[(c, s, d, p)] for c in cls_list if (c, s, d, p) in x]
                if not vs:
                    continue
                sess = model.NewBoolVar(f"sess_{s}_{label}_{d}_{p}")
                for v in vs:
                    model.Add(sess >= v)
                penalties.append((12, sess))

    # same subject twice in a day
    for c in m.classes:
        for s in m.subjects_of[c]:
            if m.plan[(c, s)] <= N_DAYS:
                for d in range(N_DAYS):
                    dv = [x[(c, s, d, p)] for p in range(1, 9) if (c, s, d, p) in x]
                    if len(dv) > 1:
                        twice = model.NewBoolVar(f"twice_{c}_{s}_{d}")
                        model.Add(sum(dv) - 1 <= twice)
                        penalties.append((5, twice))

    model.Minimize(sum(w * v for w, v in penalties))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_seconds
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = log
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(
            f"No timetable satisfies the current data (solver status: "
            f"{solver.StatusName(status)}). Run the conflict check and loosen the "
            f"Teacher Leisure Plan or the Weekly Period Plan.")

    solution = {}
    for (c, s, d, p), v in x.items():
        if solver.Value(v) == 1:
            solution[(c, d, p)] = (s, m.teacher_of[(c, s)])

    notes = []
    soft_hits = sorted({(m.teacher_of[(c, s)], DAYS[d], p)
                        for (c, s, d, p), v in x.items()
                        if solver.Value(v) == 1
                        and p in m.soft_blocked.get(m.teacher_of[(c, s)], set())})
    for t, d, p in soft_hits:
        notes.append(f"BEST leisure not honoured: {t} teaches at {d} P{p} "
                     f"(marked Leisure, fitment BEST)")
    for (s, label), cls_list in sorted(groups.items()):
        if len(cls_list) < 2:
            continue
        sess = defaultdict(list)
        for c in cls_list:
            for d in range(N_DAYS):
                for p in range(1, 9):
                    if (c, s, d, p) in x and solver.Value(x[(c, s, d, p)]) == 1:
                        sess[(d, p)].append(c)
        detail = "; ".join(f"{DAYS[d]} P{p} ({len(cs)} classes)"
                           for (d, p), cs in sorted(sess.items()))
        notes.append(f"{s} '{label}' group: {len(sess)} combined session(s) for "
                     f"{len(cls_list)} classes — {detail}")
    return solution, solver.StatusName(status), solver.ObjectiveValue(), notes
