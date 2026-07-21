"""Self-checks run after solving. Returns (errors, warnings)."""
from __future__ import annotations
from collections import defaultdict

from .model import Model, DAYS, STUDY_PERIOD, GENERIC_TEACHERS


def verify(m: Model, solution: dict):
    errors, warnings = [], []

    # 1. no teacher double-booked (generic instructors exempt)
    occ = defaultdict(list)
    for (c, d, p), (s, t) in solution.items():
        if t in GENERIC_TEACHERS:
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

    # 4. placements only in existing slots
    for (c, d, p), (s, t) in solution.items():
        if p == STUDY_PERIOD and DAYS[d] in m.cfg.no_p8_days:
            errors.append(f"NO-P8-DAY: {c} {s} at {DAYS[d]} P8 (no P8 that day)")
        if p == STUDY_PERIOD and c in m.study_hour_classes:
            errors.append(f"P8-TEACHING: {c} {s} at P8 but the class has a Study Hour")

    # 5. MUST leisure honoured
    for (c, d, p), (s, t) in solution.items():
        if t in GENERIC_TEACHERS:
            continue
        if p in m.blocked.get(t, set()):
            errors.append(f"LEISURE(MUST): {t} teaching {c} at {DAYS[d]} P{p} "
                          f"but that period is Leisure in the plan")

    # 5b. Activity-Plan windows honoured (days × periods, union over rows)
    for (c, d, p), (s, t) in solution.items():
        if m.has_activity_window(s, c) and not m.activity_allows(s, c, d, p):
            errors.append(f"ACTIVITY-WINDOW: {s} for {c} at {DAYS[d]} P{p} "
                          f"is outside its Activity-Plan window(s)")

    # 6. study-hour supervisor not teaching at P8
    supervisors = {m.study_supervisor[c] for c in m.study_hour_classes
                   if m.study_supervisor.get(c)}
    for (c, d, p), (s, t) in solution.items():
        if p == STUDY_PERIOD and t in supervisors:
            errors.append(f"SUPERVISOR CLASH: {t} teaching {c} at P8 but supervises a study hour")

    # ---- soft: BEST leisure + whole-block runs (lunch splits the day) ----
    busy = defaultdict(set)
    for (c, d, p), (s, t) in solution.items():
        if t in GENERIC_TEACHERS:
            continue
        busy[(t, d)].add(p)
        if p in m.soft_blocked.get(t, set()):
            warnings.append(f"LEISURE(BEST): {t} teaches {c} at {DAYS[d]} P{p} "
                            f"(marked Leisure, fitment BEST)")
    for c in m.study_hour_classes:
        t = m.study_supervisor.get(c)
        if t:
            for d in range(6):
                if m.has_p8(DAYS[d]):
                    busy[(t, d)].add(STUDY_PERIOD)
    for (t, d), ps in sorted(busy.items()):
        for block, label in (((1, 2, 3, 4), "morning P1-P4"),
                             ((5, 6, 7, 8), "afternoon P5-P8")):
            if all(p in ps for p in block):
                warnings.append(f"LEISURE: {t} has no free period in the {label} "
                                f"block on {DAYS[d]}")
    return errors, warnings
