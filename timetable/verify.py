"""Self-checks run after solving. Returns (errors, warnings)."""
from __future__ import annotations
from collections import defaultdict

from .model import (Model, DAYS, N_DAYS, STUDY_PERIOD, PARALLEL_SUBJECTS,
                    GENERIC_TEACHER, SUBJECT_WINDOWS, TEACHER_WINDOWS,
                    KARATE_DAY, KARATE_PERIOD, KARATE_CLASSES)


def verify(m: Model, solution: dict):
    errors, warnings = [], []

    # 1. no teacher double-booked (parallel activities exempt)
    occ = defaultdict(list)
    for (c, d, p), (s, t) in solution.items():
        if s in PARALLEL_SUBJECTS or t in GENERIC_TEACHER.values():
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

    # 3. exactly one subject per taught slot
    slot = defaultdict(int)
    for (c, d, p), _ in solution.items():
        slot[(c, d, p)] += 1
    for k, v in slot.items():
        if v > 1:
            errors.append(f"SLOT CLASH: {k} has {v} subjects")

    # 4. study-hour classes: P1-P7 fully packed
    for c in m.study_hour_classes:
        for d in range(N_DAYS):
            for p in range(1, 8):
                if (c, d, p) not in solution:
                    warnings.append(f"EMPTY SLOT: {c} {DAYS[d]} P{p} (study-hour class)")

    # 5. window rules
    for (c, d, p), (s, t) in solution.items():
        if t in TEACHER_WINDOWS and p not in TEACHER_WINDOWS[t]:
            errors.append(f"WINDOW: {t} teaching {c} at P{p} (allowed {sorted(TEACHER_WINDOWS[t])})")
        if s in SUBJECT_WINDOWS and p not in SUBJECT_WINDOWS[s]:
            errors.append(f"SUBJECT-WINDOW: {s} for {c} at P{p} (allowed {sorted(SUBJECT_WINDOWS[s])})")

    # 6. Karate = Thursday P7 for classes 1-8
    for (c, d, p), (s, t) in solution.items():
        if s == "Karate" and (DAYS[d] != KARATE_DAY or p != KARATE_PERIOD):
            errors.append(f"KARATE misplaced: {c} at {DAYS[d]} P{p}")
    for c in KARATE_CLASSES:
        if m.plan.get((c, "Karate"), 0) and (c, DAYS.index(KARATE_DAY), KARATE_PERIOD) not in solution:
            errors.append(f"KARATE missing for {c} at Thu P7")

    # 7. Gowtham has leisure at P5 (Rule 9)
    for (c, d, p), (s, t) in solution.items():
        if t == "D.GOWTHAM" and p == 5:
            errors.append(f"GOWTHAM in P5 for {c} {DAYS[d]} (should be leisure)")

    # 8. study-hour supervisor not teaching at P8 elsewhere
    supervisors = {m.study_supervisor[c] for c in m.study_hour_classes if c in m.study_supervisor}
    for (c, d, p), (s, t) in solution.items():
        if p == STUDY_PERIOD and t in supervisors and t == m.study_supervisor.get(c):
            continue
        if p == STUDY_PERIOD and t in supervisors:
            errors.append(f"SUPERVISOR CLASH: {t} teaching {c} at P8 but supervises a study hour")

    # ---- soft: leisure after 2-3 periods (study hour NOT counted -- Rule 7) ----
    teach = defaultdict(lambda: defaultdict(set))   # t -> d -> set(taught periods)
    for (c, d, p), (s, t) in solution.items():
        if s in PARALLEL_SUBJECTS or t in GENERIC_TEACHER.values():
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
