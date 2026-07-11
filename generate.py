#!/usr/bin/env python3
"""Generate a school timetable workbook from a raw information workbook.

Usage:
    python generate.py --input NRHS/Requirements/NRHS_Information.xlsx \
                       --output NRHS/Output/NRHS_Timetable_Final.xlsx
"""
import argparse
import os
import sys

from timetable.model import load_model
from timetable.solver import solve
from timetable.verify import verify
from timetable.writer import write_workbook


def main():
    ap = argparse.ArgumentParser(description="School timetable generator")
    ap.add_argument("--input", required=True, help="raw information .xlsx")
    ap.add_argument("--output", required=True, help="output .xlsx")
    ap.add_argument("--seconds", type=int, default=120, help="solver time budget")
    ap.add_argument("--log", action="store_true", help="log solver progress")
    args = ap.parse_args()

    print(f"Loading {args.input} ...")
    m = load_model(args.input)
    print(f"  classes={len(m.classes)}  subjects={len(m.subjects)}  teachers={len(m.teachers)}")

    print("Solving (CP-SAT) ...")
    solution, status, obj = solve(m, max_seconds=args.seconds, log=args.log)
    print(f"  status={status}  objective={obj:.0f}  placed={len(solution)} slots")

    print("Verifying ...")
    errors, warnings = verify(m, solution)
    for e in errors:
        print("  ERROR  :", e)
    for w in warnings:
        print("  WARN   :", w)
    if errors:
        print(f"\n{len(errors)} hard error(s) found — not writing output.")
        sys.exit(1)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    write_workbook(args.output, m, solution)
    print(f"\nWrote {args.output}")
    print(f"({len(warnings)} soft warning(s) — see above.)")


if __name__ == "__main__":
    main()
