"""CP-SAT timetable solver.

Decision var  x[(class, subject, day, period)] = 1  if that class studies that
subject in that slot.  Hard rules are constraints; soft rules are penalties in
the objective.  Returns solution dict: (class, day, period) -> (subject, teacher).
"""
from __future__ import annotations
from collections import defaultdict
from ortools.sat.python import cp_model

from .model import (Model, DAYS, N_DAYS, STUDY_PERIOD, SUBJECT_WINDOWS,
                    PARALLEL_SUBJECTS, GENERIC_TEACHER, KARATE_DAY, KARATE_PERIOD,
                    KARATE_CLASSES, PINNED_PERIOD)


def _allowed_periods(m: Model, cls, subj, pin_windows):
    """Periods where (cls, subj) may be placed, honouring all window rules."""
    teacher = m.teacher_of[(cls, subj)]
    periods = set(m.teachable_periods(cls))
    if subj not in PARALLEL_SUBJECTS:          # generic instructors ignore windows
        periods &= m.teacher_window(teacher)
    if subj in SUBJECT_WINDOWS:                # e.g. P.E.T only P6/P7
        periods &= SUBJECT_WINDOWS[subj]
    if (cls, subj) in pin_windows:             # Rules 12/13 period pins
        periods &= pin_windows[(cls, subj)]
    return periods


def _compute_pins(m: Model):
    """Effective (auto-relaxed) period windows for pinned subjects + notes."""
    pin_windows, pin_pref, notes = {}, {}, []
    for (c, s), pp in PINNED_PERIOD.items():
        if c not in m.classes or m.plan.get((c, s), 0) == 0:
            continue
        n = m.plan[(c, s)]
        karate = 1 if (c in KARATE_CLASSES and pp == KARATE_PERIOD
                       and m.plan.get((c, "Karate"), 0)) else 0
        avail = N_DAYS - karate
        pin_pref[(c, s)] = pp
        if n <= avail:
            pin_windows[(c, s)] = {pp}
        else:
            pin_windows[(c, s)] = {pp, pp - 1}
            notes.append(
                f"{c} {s}: {n}/week requested in P{pp}, but only {avail} P{pp} slots "
                f"are usable (Thursday P{pp} is Karate). {avail} placed in P{pp}, "
                f"{n - avail} in P{pp - 1}.")
    return pin_windows, pin_pref, notes


def solve(m: Model, max_seconds: int = 120, log: bool = False):
    model = cp_model.CpModel()
    x = {}                                     # (c,s,d,p) -> BoolVar
    by_slot = defaultdict(list)                # (c,d,p) -> [vars]
    by_cs = defaultdict(list)                  # (c,s)   -> [vars]
    by_teacher_slot = defaultdict(list)        # (teacher,d,p) -> [vars]

    supervisors = {m.study_supervisor[c] for c in m.study_hour_classes if c in m.study_supervisor}

    # ---- validate: every subject with periods must have a teacher ----
    missing = [(c, s, m.plan[(c, s)]) for c in m.classes for s in m.subjects_of[c]
               if (c, s) not in m.teacher_of]
    if missing:
        lines = "; ".join(f"{c} · {s} ({n} period{'s' if n != 1 else ''}/week)"
                          for c, s, n in missing)
        raise ValueError(
            "No teacher assigned for: " + lines +
            ". Fix in 'Teacher Allotment' (add a teacher) or set the periods to 0 "
            "in 'Weekly Period Plan'.")

    pin_windows, pin_pref, pin_notes = _compute_pins(m)

    for c in m.classes:
        for s in m.subjects_of[c]:
            teacher = m.teacher_of[(c, s)]
            # ---- Karate: fixed at Thursday P7 for classes 1-8 ----
            if s == "Karate":
                d, p = DAYS.index(KARATE_DAY), KARATE_PERIOD
                v = model.NewBoolVar(f"x_{c}_{s}_{d}_{p}")
                model.Add(v == 1)              # pin it
                x[(c, s, d, p)] = v
                by_slot[(c, d, p)].append(v)
                by_cs[(c, s)].append(v)
                continue
            for d in range(N_DAYS):
                for p in _allowed_periods(m, c, s, pin_windows):
                    # study-hour supervisors are busy at P8 -> can't teach there
                    if p == STUDY_PERIOD and teacher in supervisors:
                        continue
                    v = model.NewBoolVar(f"x_{c}_{s}_{d}_{p}")
                    x[(c, s, d, p)] = v
                    by_slot[(c, d, p)].append(v)
                    by_cs[(c, s)].append(v)
                    if s not in PARALLEL_SUBJECTS:
                        by_teacher_slot[(teacher, d, p)].append(v)

    # ---- (H) exact weekly count per (class, subject) ----
    for (c, s), n in m.plan.items():
        if n == 0 or c not in m.classes:
            continue
        vs = by_cs[(c, s)]
        model.Add(sum(vs) == n)

    # ---- (H) one subject per class-slot; study-hour classes are fully packed ----
    for c in m.classes:
        for d in range(N_DAYS):
            for p in m.teachable_periods(c):
                vs = by_slot[(c, d, p)]
                if not vs:
                    continue
                if c in m.study_hour_classes and p <= 7:
                    model.Add(sum(vs) == 1)    # P1-P7 exactly full
                else:
                    model.Add(sum(vs) <= 1)    # classes 8/9/10 may keep free slots

    # ---- (H) a teacher can be in at most one class per slot ----
    for (t, d, p), vs in by_teacher_slot.items():
        if len(vs) > 1:
            model.Add(sum(vs) <= 1)

    # =====================  SOFT OBJECTIVE  =====================
    penalties = []

    # busy[t,d,p] : teacher actively TEACHING (study-hour supervision is NOT
    # counted -- Rule 7 "Study Hour is not counted").
    busy = {}
    real_teachers = [t for t in m.teachers if t not in GENERIC_TEACHER.values()]
    for t in real_teachers:
        for d in range(N_DAYS):
            for p in range(1, 9):
                vs = by_teacher_slot.get((t, d, p), [])
                b = model.NewBoolVar(f"busy_{t}_{d}_{p}")
                model.Add(b == sum(vs)) if vs else model.Add(b == 0)
                busy[(t, d, p)] = b

    # (S1) leisure: penalise 4 consecutive taught periods (Rule 7)
    for t in real_teachers:
        for d in range(N_DAYS):
            for start in range(1, 6):          # windows 1-4 .. 5-8
                window = [busy[(t, d, p)] for p in range(start, start + 4)]
                pen = model.NewBoolVar(f"run4_{t}_{d}_{start}")
                model.Add(sum(window) - 3 <= pen)
                penalties.append((60, pen))

    # (S2) class teacher should take Period 1 (Rule 4) -> reward (negative penalty)
    for c in m.study_hour_classes:
        ct = m.p1_teacher.get(c)
        if not ct:
            continue
        p1vars = [x[(c, s, d, 1)] for s in m.subjects_of[c]
                  for d in range(N_DAYS)
                  if (c, s, d, 1) in x and m.teacher_of[(c, s)] == ct]
        for v in p1vars:
            penalties.append((-15, v))         # reward class teacher in P1

    # (S2b) pinned subjects (Rules 12/13) -> strongly reward the preferred period
    for (c, s), pp in pin_pref.items():
        for d in range(N_DAYS):
            if (c, s, d, pp) in x:
                penalties.append((-40, x[(c, s, d, pp)]))

    # (S3) avoid same subject twice in one day
    for c in m.classes:
        for s in m.subjects_of[c]:
            if m.plan[(c, s)] <= N_DAYS:
                for d in range(N_DAYS):
                    dayvars = [x[(c, s, d, p)] for p in range(1, 9) if (c, s, d, p) in x]
                    if len(dayvars) > 1:
                        twice = model.NewBoolVar(f"twice_{c}_{s}_{d}")
                        model.Add(sum(dayvars) - 1 <= twice)
                        penalties.append((5, twice))

    model.Minimize(sum(w * v for w, v in penalties))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_seconds
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = log
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"No solution found (status={solver.StatusName(status)})")

    solution = {}
    for (c, s, d, p), v in x.items():
        if solver.Value(v) == 1:
            solution[(c, d, p)] = (s, m.teacher_of[(c, s)])

    return solution, solver.StatusName(status), solver.ObjectiveValue(), pin_notes
