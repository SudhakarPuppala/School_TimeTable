"""CP-SAT timetable solver (school-agnostic; reads rules from m.cfg).

Decision var  x[(class, subject, day, period)] = 1 if that class studies that
subject in that slot. Returns (solution, status, objective, notes).
"""
from __future__ import annotations
from collections import defaultdict
from ortools.sat.python import cp_model

from .model import Model, DAYS, N_DAYS, STUDY_PERIOD


def _allowed_periods(m: Model, cls, subj, windows, pin_windows):
    cfg = m.cfg
    teacher = m.teacher_of[(cls, subj)]
    periods = set(m.teachable_periods(cls))
    if subj not in cfg.parallel_subjects:
        periods &= windows.get(teacher, cfg.default_window)
    if subj in cfg.subject_windows:
        periods &= cfg.subject_windows[subj]
    if (cls, subj) in pin_windows:
        periods &= pin_windows[(cls, subj)]
    return periods


def _compute_pins(m: Model):
    cfg = m.cfg
    pin_windows, pin_pref, notes = {}, {}, []
    for (c, s), pp in cfg.pinned_period.items():
        if c not in m.classes or m.plan.get((c, s), 0) == 0:
            continue
        n = m.plan[(c, s)]
        karate = 1 if (c in cfg.karate_classes and pp == cfg.karate_period
                       and m.plan.get((c, "Karate"), 0)) else 0
        avail = N_DAYS - karate
        pin_pref[(c, s)] = pp
        if n <= avail:
            pin_windows[(c, s)] = {pp}
        else:
            pin_windows[(c, s)] = {pp, pp - 1}
            notes.append(
                f"{c} {s}: {n}/week requested in P{pp}, but only {avail} P{pp} slots "
                f"usable. {avail} placed in P{pp}, {n - avail} in P{pp - 1}.")
    return pin_windows, pin_pref, notes


def _build_and_solve(m: Model, windows, max_seconds, log):
    cfg = m.cfg
    model = cp_model.CpModel()
    x, by_slot, by_cs, by_teacher_slot = {}, defaultdict(list), defaultdict(list), defaultdict(list)
    supervisors = {m.study_supervisor[c] for c in m.study_hour_classes if c in m.study_supervisor}
    pin_windows, pin_pref, pin_notes = _compute_pins(m)

    for c in m.classes:
        for s in m.subjects_of[c]:
            teacher = m.teacher_of[(c, s)]
            if s == "Karate":
                d, p = DAYS.index(cfg.karate_day), cfg.karate_period
                v = model.NewBoolVar(f"x_{c}_{s}_{d}_{p}")
                model.Add(v == 1)
                x[(c, s, d, p)] = v
                by_slot[(c, d, p)].append(v)
                by_cs[(c, s)].append(v)
                continue
            for d in range(N_DAYS):
                for p in _allowed_periods(m, c, s, windows, pin_windows):
                    if p == STUDY_PERIOD and not m.has_p8(DAYS[d]):
                        continue                      # no Period 8 on this day
                    if p == STUDY_PERIOD and teacher in supervisors:
                        continue
                    v = model.NewBoolVar(f"x_{c}_{s}_{d}_{p}")
                    x[(c, s, d, p)] = v
                    by_slot[(c, d, p)].append(v)
                    by_cs[(c, s)].append(v)
                    if s not in cfg.parallel_subjects:
                        by_teacher_slot[(teacher, d, p)].append(v)

    for (c, s), n in m.plan.items():
        if n == 0 or c not in m.classes:
            continue
        model.Add(sum(by_cs[(c, s)]) == n)

    for c in m.classes:
        for d in range(N_DAYS):
            for p in m.teachable_periods(c):
                vs = by_slot[(c, d, p)]
                if vs:
                    model.Add(sum(vs) <= 1)          # at most one subject per slot

    for (t, d, p), vs in by_teacher_slot.items():
        if len(vs) > 1:
            model.Add(sum(vs) <= 1)

    # ---- soft objective ----
    penalties = []
    busy = {}
    real = [t for t in m.teachers if t not in cfg.generic_teacher.values()]
    for t in real:
        for d in range(N_DAYS):
            for p in range(1, 9):
                vs = by_teacher_slot.get((t, d, p), [])
                b = model.NewBoolVar(f"busy_{t}_{d}_{p}")
                model.Add(b == sum(vs)) if vs else model.Add(b == 0)
                busy[(t, d, p)] = b

    for t in real:
        for d in range(N_DAYS):
            for start in range(1, 6):
                pen = model.NewBoolVar(f"run4_{t}_{d}_{start}")
                model.Add(sum(busy[(t, d, p)] for p in range(start, start + 4)) - 3 <= pen)
                penalties.append((60, pen))

    for c in m.study_hour_classes:
        ct = m.p1_teacher.get(c)
        if not ct:
            continue
        for s in m.subjects_of[c]:
            for d in range(N_DAYS):
                if (c, s, d, 1) in x and m.teacher_of[(c, s)] == ct:
                    penalties.append((-15, x[(c, s, d, 1)]))

    for (c, s), pp in pin_pref.items():
        for d in range(N_DAYS):
            if (c, s, d, pp) in x:
                penalties.append((-40, x[(c, s, d, pp)]))

    # keep morning-only teachers out of P5 unless strictly forced (relax pass)
    for (c, s, d, p), v in x.items():
        if p == 5 and m.teacher_of[(c, s)] in cfg.morning_only:
            penalties.append((200, v))

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
        return None, solver.StatusName(status), None, pin_notes

    solution = {}
    for (c, s, d, p), v in x.items():
        if solver.Value(v) == 1:
            solution[(c, d, p)] = (s, m.teacher_of[(c, s)])
    return solution, solver.StatusName(status), solver.ObjectiveValue(), pin_notes


def solve(m: Model, max_seconds: int = 120, log: bool = False):
    cfg = m.cfg
    # validate: every subject with periods must have a teacher
    missing = [(c, s, m.plan[(c, s)]) for c in m.classes for s in m.subjects_of[c]
               if (c, s) not in m.teacher_of]
    if missing:
        lines = "; ".join(f"{c} · {s} ({n} period{'s' if n != 1 else ''}/week)"
                          for c, s, n in missing)
        raise ValueError("No teacher assigned for: " + lines +
                         ". Fix in 'Teacher Allotment' or set the periods to 0.")

    windows = dict(cfg.teacher_windows)
    sol, status, obj, notes = _build_and_solve(m, windows, max_seconds, log)

    # relaxation pass: if infeasible, let morning-only teachers also use P5
    if sol is None and cfg.morning_only:
        for t in cfg.morning_only:
            windows[t] = set(windows.get(t, cfg.default_window)) | {5}
        sol, status, obj, notes = _build_and_solve(m, windows, max_seconds, log)
        if sol is not None:
            overflow = sorted({(c, t) for (c, d, p), (s, t) in sol.items()
                               if p == 5 and t in cfg.morning_only})
            where = ", ".join(f"{t}→{c}" for c, t in overflow)
            notes = notes + [
                f"RELAXED (morning window): the strict morning window (P1-P4) is 1+ slots "
                f"short for some classes, so {len(overflow)} morning-only period(s) were moved "
                f"to P5: {where}. To keep everyone strictly P1-P4, reduce a morning-only "
                f"subject's weekly count by 1 for the affected class, or reassign it."]

    if sol is None:
        raise RuntimeError(f"No solution found (status={status}).")
    return sol, status, obj, notes, windows
