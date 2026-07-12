#!/usr/bin/env python3
"""Cross-school conflict check: a teacher who works at BOTH schools must not be
scheduled at the same day+period in both. Matches teachers by normalised name
(strips leading initials like 'D.'), so confirm identities in the report.

Usage:  python cross_check.py
"""
import re
from collections import defaultdict

from timetable.model import load_model, DAYS
from timetable.solver import solve

SCHOOLS = {
    "NRHS": "NRHS/Requirements/NRHS_Information.xlsx",
    "NRCS": "NRCS/Requirements/NRCS_information_New.xlsx",
}

# Normalised names confirmed to be DIFFERENT people at each school (same name by
# coincidence) — excluded from the shared-teacher clash check.
CONFIRMED_DISTINCT = {"LALITHA"}   # NRHS M.LALITHA != NRCS Lalitha


def norm(name):
    n = re.sub(r"^[A-Za-z]\.", "", str(name).strip())   # drop leading "X."
    return re.sub(r"\s+", " ", n).strip().upper()


def occupancy(m, solution):
    """normalised-teacher -> {(day, period)} occupied (teaching or study-hour)."""
    occ = defaultdict(set)
    display = {}
    generic = set(m.cfg.generic_teacher.values())
    for (c, d, p), (s, t) in solution.items():
        if t in generic:
            continue
        occ[norm(t)].add((d, p))
        display.setdefault(norm(t), t)
    for c in m.study_hour_classes:
        t = m.study_supervisor.get(c)
        if t:
            for d in range(6):
                occ[norm(t)].add((d, 8))
            display.setdefault(norm(t), t)
    return occ, display


def main():
    data = {}
    for school, path in SCHOOLS.items():
        m = load_model(path, school)
        sol = solve(m, 90)[0]
        occ, disp = occupancy(m, sol)
        data[school] = (occ, disp)

    occ_h, disp_h = data["NRHS"]
    occ_c, disp_c = data["NRCS"]
    shared = sorted((set(occ_h) & set(occ_c)) - CONFIRMED_DISTINCT)

    print("=" * 64)
    print("CROSS-SCHOOL CONFLICT CHECK  (NRHS ∩ NRCS, matched by name)")
    print("=" * 64)
    if not shared:
        print("No teachers appear in both schools (by name).")
        return 0

    total_conflicts = 0
    for key in shared:
        clash = sorted(occ_h[key] & occ_c[key])
        label = f"{disp_h[key]} (NRHS) = {disp_c[key]} (NRCS)"
        if clash:
            total_conflicts += len(clash)
            slots = ", ".join(f"{DAYS[d]} P{p}" for d, p in clash)
            print(f"  ⚠ {label}: {len(clash)} CLASH -> {slots}")
        else:
            print(f"  ✓ {label}: no clash "
                  f"(NRHS periods {sorted({p for _, p in occ_h[key]})}, "
                  f"NRCS periods {sorted({p for _, p in occ_c[key]})})")
    print("=" * 64)
    print(f"{'⚠ ' + str(total_conflicts) + ' cross-school clash(es) found.' if total_conflicts else '✅ No cross-school clashes.'}")
    print("Note: teachers are matched by name — confirm whether same-named "
          "teachers are truly the same person.")
    return 1 if total_conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
