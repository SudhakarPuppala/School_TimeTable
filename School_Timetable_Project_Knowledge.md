# School Timetable Generation — Project Knowledge Base

> **⚠ July 19 2026 — Leisure-Plan redesign.** The hardcoded rules described in
> §3 below were **retired**. Teacher availability now comes entirely from the
> new **Teacher Leisure Plan** sheet in each information workbook
> (`Leisure Fitment`: **MUST** = hard block on the marked periods, **BEST** =
> soft/leisure-gap preference; `Lunch Break` splits the day between P4 and P5).
> Both schools use the same 4-sheet layout and one shared loader
> (`timetable/model.py`), a pre-solve conflict checker
> (`timetable/conflicts.py`) blocks generation and highlights offending cells
> red in the dashboard, and the AI_Instructions.docx files were removed.
> §§2–5 are kept for history only.

## Overview

This document captures the complete methodology, data structures, rules, code patterns,
and lessons learned from building conflict-free school timetables for two schools
(NRCS and NRHS) across multiple sessions with Claude.

---

## 1. Schools & Files

| School | Input File | Output File | Notes |
|--------|-----------|-------------|-------|
| NRCS | `NRCS_information_New.xlsx` | `NRCS_School_Timetable_Final.xlsx` | 12 classes, 22 teachers |
| NRHS | `NRHS_Teacher_Timetable_Final.xlsx` | `NRHS_Teacher_Timetable_Updated.xlsx` | 13 classes, 21 teachers |

---

## 2. Data Structure (NRCS)

### Input sheets in `NRCS_information_New.xlsx`

**Weekly Period Plan** (rows 3–17, cols B–M)
- Rows = subjects; Columns = classes (L.K.G → Class 10)
- Cell value = number of periods per week for that subject/class combo

**Teacher Allotment** (same layout)
- Cell value = teacher name assigned to that subject/class

**Period 1 teacher allotment**
- Row 2, cols C–N = class teacher for each class (also supervises Study Hour / Period 8)

### Classes (NRCS — 12 total)
`L.K.G, U.K.G, Class 1, Class 2, Class 3, Class 4, Class 5, Class 6, Class 7, Class 8, Class 9, Class 10`

### Classes (NRHS — 13 total)
`LKG, UKG 1, UKG 2, Class 1, Class 2, Class 3, Class 4, Class 5, Class 6, Class 7, Class 8, Class 9, Class 10`

### Days & Periods
- 6 days: MON TUE WED THU FRI SAT
- 8 periods per day: P1–P7 are teachable; P8 = Study Hour (class teacher supervises)

---

## 3. Scheduling Rules (NRCS — 12 Rules)

| # | Rule | Hard/Soft | Implementation |
|---|------|-----------|----------------|
| 1 | Beautiful subject-wise timetable | Soft | Objective function |
| 2 | No teacher double-booking | Hard | CP-SAT constraint: sum of teacher slots ≤ 1 |
| 3 | 8 periods/day; P8 = Study Hour | Hard | P8 handled separately outside solver |
| 4 | Gowtham, Chalapathi, Sonu: afternoon only (P5–7) | Hard | Force x=0 for period index 0–3 |
| 5 | Sunitha, Riya, Bheema: morning only (P1–4) | Hard | Force x=0 for period index 4–6 |
| 6 | Art class only Mon/Tue/Wed | Hard | Force x=0 on Thu/Fri/Sat |
| 7 | Class teacher must take P8 Study Hour (except Class 9 & 10) | Hard | Assigned by design; also soft reward for P1 |
| 8 | Ravi teaches Eng Grammar to Classes 8–10 | Hard | Encoded in allotment data |
| 9 | Karate on Thursday Period 6 for all classes | Hard | Force x[(c,'Karate',THU,5)] = 1; zero elsewhere |
| 10 | P.E.T only in Period 6 & 7 | Hard | Force x=0 for period index 0–4 |
| 11 | Avoid Period 1 for Riya (if possible) | Soft | Minimize sum of Riya P1 vars (weight 100) |
| 12 | Leisure after 2–3 periods | Soft | Penalise 4+ consecutive taught periods (weight 50) |

---

## 4. Solver Approach

**Library:** OR-Tools CP-SAT (`ortools.sat.python.cp_model`)
**Install:** `pip install ortools --break-system-packages`

### Decision variables
```python
x[(class, subject, day, period)]  # BoolVar, period index 0–6 (P1–P7)
```

### Core constraints
```python
# At most 1 subject per class-slot
model.Add(sum(x[(c,s,d,p)] for s in subjects) <= 1)

# Exact weekly count per subject/class
model.Add(sum(x[(c,s,d,p)] for d in range(6) for p in range(7)) == n)

# Teacher no double-book (exclude parallel activities like P.E / Karate)
model.Add(sum(vars_for_teacher_at_slot) <= 1)
```

### Objective (minimise)
```python
model.Minimize(
    100 * sum(riya_p1_vars)
  +  50 * sum(consecutive_violation_vars)
  +   5 * sum(same_subject_twice_in_day_vars)
  -  20 * sum(class_teacher_in_p1_reward_vars)
)
```

### Solver config
```python
solver.parameters.max_time_in_seconds = 120
solver.parameters.num_search_workers = 8
```

### Parallel / combined activities
Karate and P.E.T are whole-school simultaneous activities — exempt from
single-teacher no-double-booking. Treat them with a generic instructor label
(`Martial Arts`, `P.E`) so the constraint doesn't fire.

---

## 5. Known Bottlenecks (NRCS)

1. **LKG & UKG P.E.T** — no teacher in allotment data; auto-assigned generic `P.E`.
2. **Rule 12 (break after 2–3 periods)** — structurally impossible for:
   - Maha (41/48 slots incl. Study Hour) → 5 days with forced 4-run
   - Sai Lakshmi (40/48) → 4 days forced
   - Riya (20/24 morning-only) → 2 days forced
   - Bheema (19/24 morning-only) → 1 day forced
   - **Fix:** redistribute some classes to lighter teachers
3. **Riya P1 minimum = 2** — she has 20 morning periods but only 18 P2–P4 slots
4. **Sonu at 100% afternoon capacity** (18/18 P5–P7)
5. **Classes 1–9 are 100% full** (42/42 slots) — no free periods possible

---

## 6. Output Format — Excel

Both schools use the same two-sheet format.

### Sheet 1: Class Time Table

| Column | Content |
|--------|---------|
| A | Day (MONDAY…SATURDAY), merged across 8 rows, rotated 90°, blue fill |
| B | Period (1–7 + "Study Hour"), light blue fill |
| C–N/O | One column per class; cell = `"Teacher\n(SUBJ_ABBR)"` |

- Header row: navy fill `#2A4D69`, white bold font
- Day column: blue fill `#4B86B4`
- Period column: light fill `#E7EFF6`
- Study Hour row: class teacher + "(Study Hour)"
- Free periods: italic grey "Free Period"
- Freeze panes: C2
- Row height: 30px data rows; wrap_text=True

### Sheet 2: Teacher Time Table

Per teacher block (repeated for all teachers):
```
Row N:   TEACHER: NAME          [navy #000080, merged A:I, white bold]
Row N+1: DAY | P1 | P2 | ... P7 | STUDY HOUR   [blue header]
Row N+2: MON | cells...                          [light blue DAY col]
...
Row N+7: SAT | cells...
Row N+8: (blank gap)
```
- Cell content: `"Class (SUBJ)"` e.g. `"Class 5 (MATH)"`
- Study Hour column: class name(s) the teacher supervises
- Column widths: A=10, B–H=15–17, I=13–14

### Subject abbreviations (NRCS)
```python
SUBJ_ABBR = {
  'Telugu':'TEL', 'Hindi':'HIN', 'English':'ENG', 'Eng Gram':'GRAM',
  'Maths':'MATH', 'EVS':'EVS', 'Phy/Che':'PHY', 'Chemisty':'CHEM',
  'Biology':'BIO', 'Social':'SOC', 'G.K':'G.K', 'Art':'ART',
  'Computer':'COMP', 'P.E.T':'P.E.T', 'Karate':'KARATE'
}
```

---

## 7. Parser for Class Time Table → Teacher Time Table

Used when user manually edits the Class Time Table and needs the
Teacher Time Table regenerated to match.

```python
import re
from collections import defaultdict

SKIP = {'Recreation', 'recreation', 'RECREATION'}

def parse_cell(raw):
    """Extract (teacher, subject_abbr) from a Class Time Table cell."""
    raw = raw.replace("'", "").strip().lstrip()
    if not raw or raw.strip() in SKIP:
        return None, None
    # Case 1: newline separator  "Teacher\n(SUBJ)"
    if '\\n' in raw or '\n' in raw:
        parts = raw.split('\\n') if '\\n' in raw else raw.split('\n')
        teacher = parts[0].strip()
        subj_raw = parts[1].strip() if len(parts) > 1 else ''
    # Case 2: inline  "Teacher(SUBJ)" — no newline
    else:
        m = re.match(r'^([A-Za-z][^(]*)(\(.*\))?$', raw)
        teacher  = m.group(1).strip() if m else raw.strip()
        subj_raw = (m.group(2) or '').strip() if m else ''
    m2 = re.match(r'\(([^)]+)\)', subj_raw)
    subj = m2.group(1).strip() if m2 else subj_raw.replace('(','').replace(')','').strip()
    return teacher, subj

# Accumulate schedule
tgrid    = defaultdict(lambda: [[[] for _ in range(7)] for _ in range(6)])
study_hr = defaultdict(lambda: [[] for _ in range(6)])

# In the parsing loop:
#   if period == 'Study Hour' -> study_hr[teacher][day].append(class_name)
#   else -> tgrid[teacher][day][period_0based].append(f"{class} ({subj})")
```

---

## 8. Key Lessons Learned

### Parsing quirks
- Cells may use literal `\n` (backslash-n as text) **or** real newlines — handle both
- Some cells have inline format `Teacher(Subj)` with no separator — use regex split on `(`
- Junk/accidental keystrokes in cells (e.g. `9kb ,b,,;h...`) — filter with `re.compile(r'^[^a-zA-Z]')`
- Name variants (e.g. `Bhavani(Evs)` vs `Bhavani\n(Evs)`) — normalise in `parse_cell`
- Leading/trailing spaces in cell values are common — always `.strip().lstrip()`

### Styling quirks
- Never run openpyxl files through LibreOffice `--recalc` — it strips indexed colors
- Use hex color strings (e.g. `'002A4D69'`) not named colors in openpyxl PatternFill
- Day column merged cells: apply fill to **every row in merge**, not just the anchor cell
- `text_rotation=90` goes in the `Alignment` object

### Solver insights
- CP-SAT finds OPTIMAL for this problem size (12 classes × 6 days × 7 periods) in < 30s
- Parallel activities (Karate, P.E.T) must be **excluded from teacher no-double-book**
  because all classes share the same slot simultaneously
- Morning/afternoon window constraints are the tightest bottleneck
- Soft constraints: use penalty weights (100 > 50 > 20 > 5) to rank priority

### Workflow preference
User prefers to:
1. Receive the auto-generated Class Time Table
2. Make manual edits to Class Time Table in Excel
3. Re-upload and have Claude regenerate **only the Teacher Time Table** to match

---

## 9. Verification Checklist

Run after every Teacher Time Table rebuild:

```python
# 1. Zero hard errors in source → no duplicate teacher at same slot
occ = defaultdict(list)
for (c, day, period), (subj, teacher) in sol.items():
    if teacher not in PARALLEL_TEACHERS:
        occ[(teacher, day, period)].append((c, subj))
assert all(len(v) == 1 for v in occ.values()), "DOUBLE-BOOKING DETECTED"

# 2. Weekly counts match plan
for c in classes:
    for subj, teacher, n in class_subjects[c]:
        got = sum(1 for (cc,d,p),(s,_) in sol.items() if cc==c and s==subj)
        assert got == n, f"COUNT MISMATCH: {c} {subj}"

# 3. Window rules
for (c,d,p),(s,t) in sol.items():
    assert not (t in MORNING_ONLY and p >= 4)
    assert not (t in AFTERNOON_ONLY and p < 4)

# 4. Art only Mon/Tue/Wed
for (c,d,p),(s,_) in sol.items():
    if s == 'Art': assert DAYS[d] in ('MON','TUE','WED')

# 5. Karate = Thursday P6 only
# 6. P.E.T = Period 6 or 7 only
```

---

## 10. File Naming Convention

| File | Purpose |
|------|---------|
| `NRCS_information_New.xlsx` | NRCS raw input (period plan + allotment) |
| `NRCS_School_Timetable_Final.xlsx` | NRCS final output (both sheets) |
| `NRCS_School_Timetable_New.xlsx` | NRCS after user manual edits |
| `NRCS_School_Timetable_Updated.xlsx` | NRCS after Teacher TT rebuild |
| `NRHS_Teacher_Timetable_Final.xlsx` | NRHS input (Class TT already edited by user) |
| `NRHS_Teacher_Timetable_Updated.xlsx` | NRHS after Teacher TT rebuild |
| `sample_timetable.xlsx` | Format reference (NRCS) |

---

*Generated from session history — NRCS & NRHS timetable projects, July 2026*
