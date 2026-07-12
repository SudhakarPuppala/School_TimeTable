"""Self-checks run after solving. Returns (errors, warnings)."""
from __future__ import annotations
from collections import defaultdict

from .model import Model, DAYS, N_DAYS, STUDY_PERIOD


def verify(m: Model, solution: dict, windows=None):
    cfg = m.cfg
    windows = windows if windows is not None else cfg.teacher_windows
    errors, warnings = [], []
    generic = set(cfg.generic_teacher.values())

    # 1. no teacher double-booked (parallel activities exempt)
    occ = defaultdict(list)
    for (c, d, p), (s, t) in solution.items():
        if s in cfg.parallel_subjects or t in generic:
            continue
        occ[(t, d, p)].append((c, s))
    for (t, d, p), lst in occ.items():
        if len(lst) > 1:
            errors.append(f"DOUBLE-BOOK: {t} at {DAYS[d]} P{p} -> {lst}")

    # 2. weekly counts match the plan
    got = defaultdict(int)
    for (c, d, p), (s, t) in solution.items():
        got[(c, s)] += 1
    for (c, s), n in m.plan.items():
        if n and c in m.classes and got[(c, s)] != n:
            errors.append(f"COUNT: {c} {s} planned {n} got {got[(c, s)]}")

    # 3. one subject per taught slot
    slot = defaultdict(int)
    for (c, d, p), _ in solution.items():
        slot[(c, d, p)] += 1
    for k, v in slot.items():
        if v > 1:
            errors.append(f"SLOT CLASH: {k} has {v} subjects")

    # 4. every subject's placements land only in real (existing) slots
    for (c, d, p), (s, t) in solution.items():
        if p == STUDY_PERIOD and DAYS[d] in cfg.no_p8_days:
            errors.append(f"NO-P8-DAY: {c} {s} at {DAYS[d]} P8 (no P8 that day)")

    # 5. window rules (against the effective windows actually used)
    for (c, d, p), (s, t) in solution.items():
        if t in windows and p not in windows[t]:
            errors.append(f"WINDOW: {t} teaching {c} at P{p} (allowed {sorted(windows[t])})")
        if s in cfg.subject_windows and p not in cfg.subject_windows[s]:
            errors.append(f"SUBJECT-WINDOW: {s} for {c} at P{p} (allowed {sorted(cfg.subject_windows[s])})")

    # 6. Karate placement
    for (c, d, p), (s, t) in solution.items():
        if s == "Karate" and (DAYS[d] != cfg.karate_day or p != cfg.karate_period):
            errors.append(f"KARATE misplaced: {c} at {DAYS[d]} P{p}")
    for c in cfg.karate_classes:
        if m.plan.get((c, "Karate"), 0) and (c, DAYS.index(cfg.karate_day), cfg.karate_period) not in solution:
            errors.append(f"KARATE missing for {c} at {cfg.karate_day} P{cfg.karate_period}")

    # 7. study-hour supervisor not teaching elsewhere at P8
    supervisors = {m.study_supervisor[c] for c in m.study_hour_classes if c in m.study_supervisor}
    for (c, d, p), (s, t) in solution.items():
        if p == STUDY_PERIOD and t in supervisors and t != m.study_supervisor.get(c):
            errors.append(f"SUPERVISOR CLASH: {t} teaching {c} at P8 but supervises a study hour")

    # ---- soft: leisure (study hour not counted) ----
    teach = defaultdict(lambda: defaultdict(set))
    for (c, d, p), (s, t) in solution.items():
        if s in cfg.parallel_subjects or t in generic:
            continue
        teach[t][d].add(p)
    for t, days in teach.items():
        for d, ps in days.items():
            run = best = 0
            for p in range(1, 9):
                run = run + 1 if p in ps else 0
                best = max(best, run)
            if best >= 4:
                warnings.append(f"LEISURE: {t} has {best} consecutive periods on {DAYS[d]}")

    return errors, warnings
