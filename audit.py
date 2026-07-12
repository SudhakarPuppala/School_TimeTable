#!/usr/bin/env python3
"""Independent audit: re-parse a generated timetable .xlsx (both sheets) and
verify every class/period/teacher against the source workbook. School-aware.

Usage:  python audit.py --school NRCS \
                        --src NRCS/Requirements/NRCS_information_New.xlsx \
                        --out NRCS/Output/NRCS_Timetable_Final.xlsx
"""
import argparse
from collections import defaultdict

import openpyxl
from timetable.model import load_model, DAYS


def parse_class_sheet(path, m):
    cfg = m.cfg
    abbr2subj = {v: k for k, v in cfg.subj_abbr.items()}
    disp2canon = {v: k for k, v in cfg.class_display.items()}
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[cfg.sheet_class_name]
    headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
    col_class = {c: disp2canon.get(headers[c - 1], headers[c - 1])
                 for c in range(3, ws.max_column + 1) if headers[c - 1]}
    out, supervisors, day = {}, {}, -1
    for r in range(2, ws.max_row + 1):
        if ws.cell(r, 1).value:
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
            out[(cls, day, period)] = (teacher, abbr2subj.get(abbr, abbr))
    return out, supervisors


def parse_teacher_sheet(path, m):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[m.cfg.sheet_teacher_name]
    grid, teacher = defaultdict(set), None
    for r in range(1, ws.max_row + 1):
        a = ws.cell(r, 1).value
        if a and str(a).startswith("TEACHER:"):
            teacher = str(a).split(":", 1)[1].strip()
            continue
        if a in DAYS and teacher:
            day = DAYS.index(a)
            for c in range(2, 10):
                raw = ws.cell(r, c).value
                if raw:
                    grid[(teacher, day, 8 if c == 9 else c - 1)].add(str(raw).strip())
    return grid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--school", default="NRHS", choices=["NRHS", "NRCS"])
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    m = load_model(args.src, args.school)
    cfg = m.cfg
    generic = set(cfg.generic_teacher.values())
    sol, supers = parse_class_sheet(args.out, m)
    tgrid = parse_teacher_sheet(args.out, m)
    fail = []

    got = defaultdict(int)
    for (c, d, p), (t, s) in sol.items():
        got[(c, s)] += 1
    for c in m.classes:
        for s in m.subjects:
            want = m.plan.get((c, s), 0)
            if got[(c, s)] != want:
                fail.append(f"[COUNT] {c} {s}: plan={want} timetable={got[(c, s)]}")

    for (c, d, p), (t, s) in sol.items():
        exp = m.teacher_of.get((c, s))
        if exp is None:
            fail.append(f"[NO-ALLOT] {c} {s} taught by {t}")
        elif s not in cfg.parallel_subjects and t != exp:
            fail.append(f"[WRONG-TEACHER] {c} {s} @ {DAYS[d]}P{p}: got {t}, allotment {exp}")

    occ = defaultdict(list)
    for (c, d, p), (t, s) in sol.items():
        if s in cfg.parallel_subjects or t in generic:
            continue
        occ[(t, d, p)].append(c)
    for (t, d, p), cs in occ.items():
        if len(cs) > 1:
            fail.append(f"[DOUBLE-BOOK] {t} @ {DAYS[d]}P{p}: {cs}")

    # study-hour classes: P1-P7 filled == their content (free periods allowed if content < 42)
    for c in m.study_hour_classes:
        content = sum(m.plan.get((c, s), 0) for s in m.subjects)
        filled = sum(1 for d in range(6) for p in range(1, 8) if (c, d, p) in sol)
        if filled != content:
            fail.append(f"[PACK] {c}: {filled} taught in P1-P7 but content is {content}")
    capacity = sum(1 for d in range(6) for p in range(1, 9)
                   if not (p == 8 and DAYS[d] in cfg.no_p8_days))
    for c in cfg.no_study_hour:
        if c in m.classes:
            filled = sum(1 for d in range(6) for p in range(1, 9) if (c, d, p) in sol)
            if filled > capacity:
                fail.append(f"[FREE] {c}: {filled} filled > {capacity} slots")

    # no teaching in a period that does not exist (e.g. Saturday P8)
    for (c, d, p), (t, s) in sol.items():
        if p == 8 and DAYS[d] in cfg.no_p8_days:
            fail.append(f"[NO-P8-DAY] {c} scheduled at {DAYS[d]} P8 (no P8 that day)")

    for c in m.study_hour_classes:
        if supers.get(c) != m.study_supervisor.get(c):
            fail.append(f"[SUPERVISOR] {c}: sheet={supers.get(c)} source={m.study_supervisor.get(c)}")

    for (c, d, p), (t, s) in sol.items():
        allowed = set(cfg.teacher_windows.get(t, cfg.default_window))
        if t in cfg.morning_only:
            allowed |= {5}                       # documented relaxation
        if t in cfg.teacher_windows and p not in allowed:
            fail.append(f"[WINDOW] {t} @ P{p} ({c}) allowed {sorted(allowed)}")
        if s in cfg.subject_windows and p not in cfg.subject_windows[s]:
            fail.append(f"[SUBJ-WINDOW] {s} @ P{p} ({c}) allowed {sorted(cfg.subject_windows[s])}")

    for (c, d, p), (t, s) in sol.items():
        if s == "Karate" and (DAYS[d] != cfg.karate_day or p != cfg.karate_period):
            fail.append(f"[KARATE] {c} @ {DAYS[d]}P{p}")

    for (c, s), pp in cfg.pinned_period.items():
        if m.plan.get((c, s), 0) == 0:
            continue
        slots = [p for (cc, d, p), (t, ss) in sol.items() if cc == c and ss == s]
        bad = [p for p in slots if p not in (pp, pp - 1)]
        if bad:
            fail.append(f"[PIN] {c} {s} at P{bad} (allowed P{pp}/P{pp-1})")
        print(f"  · pin {c} {s}: {slots.count(pp)}@P{pp}, {slots.count(pp-1)}@P{pp-1}")

    for (c, d, p), (t, s) in sol.items():
        if t in generic:
            continue
        exp = f"{cfg.class_display.get(c, c)} ({cfg.subj_abbr.get(s, s)})"
        if exp not in tgrid.get((t, d, p), set()):
            fail.append(f"[SHEET-MISMATCH] {t} @ {DAYS[d]}P{p}: Class says '{exp}', "
                        f"Teacher sheet {tgrid.get((t, d, p)) or 'nothing'}")

    print(f"INDEPENDENT AUDIT of {args.out}  (school={args.school})")
    print("=" * 60)
    for ck in ["weekly counts", "teacher==allotment", "no double-booking",
               "grid packed / free-slots", "study-hour supervisors", "window rules",
               "Karate placement", "pinned periods", "Class↔Teacher sheet agreement"]:
        print(f"  ✓ checked: {ck}")
    print("=" * 60)
    if fail:
        print(f"❌ {len(fail)} problem(s):")
        for f in fail:
            print("   ", f)
    else:
        print(f"✅ ALL CHECKS PASSED — {len(sol)} taught slots across "
              f"{len(m.classes)} classes and {len(m.teachers)} teachers.")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
