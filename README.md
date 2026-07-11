# School Timetable Generator (NRHS / NRCS)

Generates conflict-free, subject-wise **Class** and **Teacher** timetables from a
raw information workbook, using an OR-Tools **CP-SAT** constraint solver, and
writes a styled Excel workbook that matches the school's sample template.

## Layout

```
timetable/
  model.py     # load NRHS_Information.xlsx -> structured Model; all rule constants
  solver.py    # CP-SAT model (hard constraints + soft objective)
  verify.py    # post-solve self-checks (errors + warnings)
  writer.py    # styled 'Class Time table' + 'Teacher Time Table' sheets
generate.py    # CLI entry point
NRHS/Requirements/   # input workbooks
NRHS/Output/         # generated timetables
```

## Usage

```bash
pip install -r requirements.txt
python generate.py \
  --input  NRHS/Requirements/NRHS_Information.xlsx \
  --output NRHS/Output/NRHS_Timetable_Final.xlsx
```

The same code runs for **NRCS** — point `--input` at the NRCS workbook (same
three-sheet structure: *Teacher Allotment*, *Weekly Period Plan*,
*Period 1 teacher allotment*).

## Input workbook (3 sheets)

| Sheet | Meaning |
|-------|---------|
| Teacher Allotment | teacher assigned to each (subject, class) |
| Weekly Period Plan | #periods/week for each (subject, class) |
| Period 1 teacher allotment | class teacher (takes P1 + supervises Study Hour / P8) |

## Rules implemented

| # | Rule | Type |
|---|------|------|
| 1 | Beautiful subject-wise timetable | output |
| 2 | No teacher double-booking | hard |
| 3 | 8 periods/day; P8 = Study Hour | hard |
| 4 | P1 teacher also takes P8 study hour (except 8/9/10); P1 = class teacher | hard P8 / soft P1 |
| 5 | Suneetha, Riya, Gowtham → afternoon only (P5–P8) | hard |
| 6 | Chalapathi (Bio) → P1–P3 only | hard |
| 7 | Leisure after 2–3 periods | soft |
| 8 | Karate on Thursday P7 for Classes 1–8 | hard |
| 9 | Gowtham leisure in P5 (so he teaches P6–P8) | hard |
| 10 | P.E.T only in P6 & P7 | hard |
| 11 | No Study Hour for Classes 8/9/10; may allot Gowtham/Riya/Sunitha there | hard |

Subjects with no teacher in the allotment are handled by rule:
**ORAL** and **G.K** → the class's own class teacher; **P.E.T** and **Karate** →
generic instructors treated as parallel whole-school activities (exempt from the
single-teacher no-double-book constraint).

See [`NRHS/Output/NRHS_BOTTLENECKS.md`](NRHS/Output/NRHS_BOTTLENECKS.md) for the
feasibility report and data-side recommendations.
