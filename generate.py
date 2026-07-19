#!/usr/bin/env python3
"""Generate a school timetable workbook from a raw information workbook.

Usage:
    python generate.py --school NRHS
    python generate.py --school NRCS --input <custom.xlsx> --output <out.xlsx>

The conflict check always runs first; generation is refused while the data
still has errors (fix them in the workbook or the dashboard).
"""
import argparse
import os
import sys

from timetable.model import load_model, INPUTS
from timetable.conflicts import check_conflicts, has_errors
from timetable.solver import solve
from timetable.verify import verify
from timetable.writer import write_workbook
from timetable.pdf import write_pdf


def main():
    ap = argparse.ArgumentParser(description="School timetable generator")
    ap.add_argument("--school", default="NRHS", choices=["NRHS", "NRCS"])
    ap.add_argument("--input", help="raw information .xlsx (default: school's standard path)")
    ap.add_argument("--output", help="output .xlsx (default: <school>/Output/<school>_Timetable_Final.xlsx)")
    ap.add_argument("--pdf", help="also write a PDF to this path")
    ap.add_argument("--seconds", type=int, default=120, help="solver time budget")
    ap.add_argument("--log", action="store_true", help="log solver progress")
    args = ap.parse_args()

    inp = args.input or INPUTS[args.school]
    out = args.output or f"{args.school}/Output/{args.school}_Timetable_Final.xlsx"

    print(f"Loading {inp} (school={args.school}) ...")
    m = load_model(inp, args.school)
    print(f"  classes={len(m.classes)}  subjects={len(m.subjects)}  teachers={len(m.teachers)}")

    print("Checking conflicts ...")
    conflicts = check_conflicts(m)
    for c in conflicts:
        if c.severity != "info":
            print(f"  {c.severity.upper():7s}: {c.message}")
    n_err = sum(1 for c in conflicts if c.severity == "error")
    if n_err:
        print(f"\n{n_err} conflict(s) must be resolved before generating. "
              f"Fix the workbook (or use the dashboard) and re-run.")
        sys.exit(1)
    print("  no blocking conflicts.")

    print("Solving (CP-SAT) ...")
    solution, status, obj, notes = solve(m, max_seconds=args.seconds, log=args.log,
                                         precheck=False)
    print(f"  status={status}  objective={obj:.0f}  placed={len(solution)} slots")
    for note in notes:
        print("  NOTE   :", note)

    print("Verifying ...")
    errors, warnings = verify(m, solution)
    for e in errors:
        print("  ERROR  :", e)
    for w in warnings:
        print("  WARN   :", w)
    if errors:
        print(f"\n{len(errors)} hard error(s) found — not writing output.")
        sys.exit(1)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_workbook(out, m, solution)
    print(f"\nWrote {out}")
    if args.pdf:
        write_pdf(args.pdf, m, solution)
        print(f"Wrote {args.pdf}")
    print(f"({len(warnings)} soft warning(s) — see above.)")


if __name__ == "__main__":
    main()
