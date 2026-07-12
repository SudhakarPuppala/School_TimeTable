#!/usr/bin/env python3
"""Independent audit: re-parse the generated timetable .xlsx (both sheets) and
verify EVERY class/period/teacher against the source workbook. Does not trust the
solver's internal solution — it reads the actual output cells.

Usage:  python audit.py --src NRHS/Requirements/NRHS_Information.xlsx \
                        --out NRHS/Output/NRHS_Timetable_Final.xlsx
"""
import argparse
from collections import defaultdict

import openpyxl
from timetable.model import (load_model, DAYS, SUBJ_ABBR, CLASS_DISPLAY,
                             PARALLEL_SUBJECTS, GENERIC_TEACHER, TEACHER_WINDOWS,
                             SUBJECT_WINDOWS, KARATE_DAY, KARATE_PERIOD, KARATE_CLASSES,
                             PINNED_PERIOD)

ABBR2SUBJ = {v: k for k, v in SUBJ_ABBR.items()}
DISP2CANON = {v: k for k, v in CLASS_DISPLAY.items()}


def parse_class_sheet(path):
    """Return {(canon_class, day_idx, period): (teacher, subject)} from Class sheet."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Class Time table"]
    headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
    col_class = {c: DISP2CANON.get(headers[c - 1], headers[c - 1])
                 for c in range(3, ws.max_column + 1) if headers[c - 1]}
    out, supervisors = {}, {}
    day = -1
    for r in range(2, ws.max_row + 1):
        a = ws.cell(r, 1).value
        if a:
            day += 1
        plabel = ws.cell(r, 2).value
        is_study = str(plabel).strip().lower().startswith("study")
        period = 8 if is_study else int(plabel)
        for c, cls in col_class.items():
            raw = ws.cell(r, c).value
            if not raw or str(raw).strip().lower() in ("recreation", "free period", "—", "-"):
                continue
            parts = str(raw).split("\n")
            teacher = parts[0].strip()
            abbr = parts[1].strip("() ").strip() if len(parts) > 1 else ""
            if abbr.upper() == "CLASS":
                supervisors[cls] = teacher
                continue
            subj = ABBR2SUBJ.get(abbr, abbr)
            out[(cls, day, period)] = (teacher, subj)
    return out, supervisors


def parse_teacher_sheet(path):
    """Return {(teacher, day_idx, period): set((class, subj))} from Teacher sheet."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Teacher Time Table"]
    grid = defaultdict(set)
    teacher = None
    for r in range(1, ws.max_row + 1):
        a = ws.cell(r, 1).value
        if a and str(a).startswith("TEACHER:"):
            teacher = str(a).split(":", 1)[1].strip()
            continue
        if a in DAYS and teacher:
            day = DAYS.index(a)
            for c in range(2, 10):
                raw = ws.cell(r, c).value
                if not raw:
                    continue
                period = 8 if c == 9 else c - 1
                grid[(teacher, day, period)].add(str(raw).strip())
    return grid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="NRHS/Requirements/NRHS_Information.xlsx")
    ap.add_argument("--out", default="NRHS/Output/NRHS_Timetable_Final.xlsx")
    args = ap.parse_args()

    m = load_model(args.src)
    sol, supers = parse_class_sheet(args.out)
    tgrid = parse_teacher_sheet(args.out)
    fail = []

    # 1 -- weekly counts per (class, subject) match the plan EXACTLY
    got = defaultdict(int)
    for (c, d, p), (t, s) in sol.items():
        got[(c, s)] += 1
    for c in m.classes:
        for s in m.subjects:
            want = m.plan.get((c, s), 0)
            if got[(c, s)] != want:
                fail.append(f"[COUNT] {c} {s}: plan={want} timetable={got[(c, s)]}")

    # 2 -- every teacher matches the allotment for that (class, subject)
    for (c, d, p), (t, s) in sol.items():
        exp = m.teacher_of.get((c, s))
        if exp is None:
            fail.append(f"[NO-ALLOT] {c} {s} taught by {t} but no allotment")
        elif s in PARALLEL_SUBJECTS:
            pass  # generic instructor label
        elif t != exp:
            fail.append(f"[WRONG-TEACHER] {c} {s} @ {DAYS[d]}P{p}: got {t}, allotment {exp}")

    # 3 -- no teacher double-booked (parallel activities exempt)
    occ = defaultdict(list)
    for (c, d, p), (t, s) in sol.items():
        if s in PARALLEL_SUBJECTS or t in GENERIC_TEACHER.values():
            continue
        occ[(t, d, p)].append(c)
    for (t, d, p), cs in occ.items():
        if len(cs) > 1:
            fail.append(f"[DOUBLE-BOOK] {t} @ {DAYS[d]}P{p}: {cs}")

    # 4 -- study-hour classes fully packed P1-P7; 8/9/10 have exactly 6 free
    for c in m.classes:
        filled = sum(1 for p in range(1, 8) if (c, d, p) in sol
                     for d in range(6)) if False else 0
        for d in range(6):
            for p in range(1, 8):
                if c in m.study_hour_classes and (c, d, p) not in sol:
                    fail.append(f"[EMPTY] {c} {DAYS[d]}P{p} (should be full)")
    for c in ("Class 8", "Class 9", "Class 10"):
        free = 48 - sum(1 for d in range(6) for p in range(1, 9) if (c, d, p) in sol)
        if free != 6:
            fail.append(f"[FREE] {c}: {free} free slots (expected 6)")

    # 5 -- study-hour supervisor matches the source sheet
    for c in m.study_hour_classes:
        if supers.get(c) != m.study_supervisor.get(c):
            fail.append(f"[SUPERVISOR] {c}: sheet={supers.get(c)} source={m.study_supervisor.get(c)}")

    # 6 -- window rules
    for (c, d, p), (t, s) in sol.items():
        if t in TEACHER_WINDOWS and p not in TEACHER_WINDOWS[t]:
            fail.append(f"[WINDOW] {t} @ P{p} ({c}) allowed {sorted(TEACHER_WINDOWS[t])}")
        if s in SUBJECT_WINDOWS and p not in SUBJECT_WINDOWS[s]:
            fail.append(f"[SUBJ-WINDOW] {s} @ P{p} ({c}) allowed {sorted(SUBJECT_WINDOWS[s])}")

    # 7 -- Karate = Thu P7 for classes 1-8
    for (c, d, p), (t, s) in sol.items():
        if s == "Karate" and (DAYS[d] != KARATE_DAY or p != KARATE_PERIOD):
            fail.append(f"[KARATE] {c} @ {DAYS[d]}P{p}")
    for c in KARATE_CLASSES:
        if m.plan.get((c, "Karate"), 0) and (c, DAYS.index(KARATE_DAY), KARATE_PERIOD) not in sol:
            fail.append(f"[KARATE-MISSING] {c} Thu P7")

    # 7b -- pinned subjects (Rules 12/13) stay within {pref, pref-1}, mostly at pref
    for (c, s), pp in PINNED_PERIOD.items():
        if m.plan.get((c, s), 0) == 0:
            continue
        slots = [p for (cc, d, p), (t, ss) in sol.items() if cc == c and ss == s]
        bad = [p for p in slots if p not in (pp, pp - 1)]
        if bad:
            fail.append(f"[PIN] {c} {s} placed at P{bad} (allowed P{pp}/P{pp-1})")
        print(f"  · pin {c} {s}: {slots.count(pp)}@P{pp}, {slots.count(pp-1)}@P{pp-1}")

    # 8 -- Class sheet and Teacher sheet AGREE with each other (exact class+subject)
    for (c, d, p), (t, s) in sol.items():
        if t in GENERIC_TEACHER.values():
            continue
        entry = tgrid.get((t, d, p), set())
        exp = f"{CLASS_DISPLAY.get(c, c)} ({SUBJ_ABBR.get(s, s)})"
        if exp not in entry:
            fail.append(f"[SHEET-MISMATCH] {t} @ {DAYS[d]}P{p}: Class sheet says '{exp}', "
                        f"Teacher sheet shows {entry or 'nothing'}")

    # ---- report ----
    checks = ["weekly counts", "teacher==allotment", "no double-booking",
              "grid fully packed / free-slots", "study-hour supervisors",
              "window rules", "Karate placement", "Class↔Teacher sheet agreement"]
    print("INDEPENDENT AUDIT of", args.out)
    print("=" * 60)
    for ck in checks:
        print(f"  ✓ checked: {ck}")
    print("=" * 60)
    if fail:
        print(f"❌ {len(fail)} problem(s):")
        for f in fail:
            print("   ", f)
    else:
        print(f"✅ ALL CHECKS PASSED — {len(sol)} taught slots verified across "
              f"{len(m.classes)} classes and {len(m.teachers)} teachers.")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
