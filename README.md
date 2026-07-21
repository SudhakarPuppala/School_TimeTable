# School Timetable Generator (NRHS / NRCS)

Generates conflict-free, subject-wise **Class** and **Teacher** timetables from a
raw information workbook, using an OR-Tools **CP-SAT** constraint solver, and
writes a styled Excel workbook that matches the school's sample template.

**All scheduling rules live in the workbook** — there is no per-school rule code.
Teacher availability comes from the **Teacher Leisure Plan** sheet; change the
sheet, regenerate, done.

## Layout

```
timetable/
  model.py      # data-driven loader (4 sheets) + name/class/subject resolvers
  conflicts.py  # pre-solve conflict checker (used by CLI + dashboard)
  solver.py     # CP-SAT model (hard constraints + soft objective)
  verify.py     # post-solve self-checks (errors + warnings)
  writer.py     # styled 'Class Time table' + 'Teacher Time Table' sheets
  pdf.py        # print-ready PDF (all classes + teachers)
generate.py     # CLI entry point
audit.py        # independent re-parse + tally check of a generated workbook
dashboard.py    # Streamlit dashboard (edit, check conflicts, generate, download)
cross_check.py  # teachers shared between both schools: same-slot clash check
NRHS/Requirements/   NRHS/Output/
NRCS/Requirements/   NRCS/Output/
```

## Usage

```bash
pip install -r requirements.txt
python generate.py --school NRCS            # conflict check + solve + write
python audit.py --school NRCS --out NRCS/Output/NRCS_Timetable_Final.xlsx
python -m streamlit run dashboard.py        # interactive dashboard
```

## Input workbook (4 sheets, same layout for both schools)

| Sheet | Meaning |
|-------|---------|
| Weekly Period Plan | #periods/week for each (subject, class) + Total row |
| Teacher Allotment | teacher assigned to each (subject, class) |
| Period 1 teacher allotment | per class: Period-1 teacher + Study-Hour supervisor |
| **Teacher Leisure Plan** | per teacher: **Leisure Fitment** (MUST/BEST) + `Leisure` marks per period |
| **Activity Plan** *(optional)* | each row = one **combined session group**: Activity, **Allowed Days** (`MON,TUE` / `MON-THU`, blank = any), **Allowed Periods** (`6,7`, blank = any), and a tick per class in the group |

### Activity Plan semantics

- Ticked classes may only do that activity inside the row's **days × periods**
  window (hard), and the solver **combines** their sessions — grouped classes do
  the activity together whenever the weekly counts allow.
- A class may be ticked in **several rows**; its allowed slots are the **union**
  of those rows' windows. Example: tick a class in a `MON,WED,FRI × P7` row and
  a `SAT × P5` row and it can take that activity in P7 on Mon/Wed/Fri **or** P5
  on Sat.
- A class ticked in no row is scheduled independently with no restriction.
- P.E.T / Karate are parallel whole-class activities (generic `P.E` /
  `MARTIAL ARTS` instructors, no double-booking constraint).

### Teacher Leisure Plan semantics

- **MUST** + `Leisure` in a period → the teacher is **never** scheduled there (hard).
- **BEST** + `Leisure` in a period → avoided when possible (soft).
- **BEST** in general → the solver leaves leisure gaps inside continuous periods
  (a full morning P1–P4 or full afternoon P5–P8 without a break is penalised).
- **Lunch Break** → free for every teacher (between P4 and P5).
- A class **without** a Study-Hour supervisor treats Period 8 as teachable.

### Data-gap conventions (reported as notes, override by editing the workbook)

- **P.E.T** / **Karate** with no teacher → generic `P.E` / `MARTIAL ARTS`
  instructors, treated as parallel whole-class activities (no double-book check).
- **Eng Grammar** with no teacher → the class's English teacher.
- **Chemistry** with no teacher → the class's Physics teacher (`Phy/Che` row).
- **Oral** / **G.K** with no teacher → the class's Period-1 teacher.

## Conflict check (before every generation)

`generate.py` and the dashboard's **Check conflicts** button refuse to solve while
the data has errors, e.g.:

- a subject with periods/week but no teacher anywhere;
- a class total above its available slots;
- a teacher allotted more periods than their Leisure Plan allows;
- a class whose late/early-window teachers together need more slots than exist;
- a Study-Hour supervisor whose own Study Hour is marked Leisure (MUST).

The dashboard highlights the offending cells in **red** and shows live Total
rows (plan) and a per-teacher load-vs-availability table.

## Saving edits & GitHub check-in

**Save edits to source workbook** writes the four sheets back to the school's
information workbook and (with the sidebar toggle on) commits & pushes it to
GitHub automatically.

- **Running locally**: uses your normal git credentials — nothing to set up.
- **Running on Streamlit Community Cloud**: the container has no git
  credentials, so add a token to the app's **Secrets** (Manage app →
  Settings → Secrets):

  ```toml
  GITHUB_TOKEN = "github_pat_..."
  ```

  Create it at GitHub → Settings → Developer settings → Fine-grained personal
  access tokens: select **only** this repository and grant **Contents: Read
  and write**. The dashboard then commits as "Timetable Dashboard" and pushes
  over HTTPS with the token (a rejected push is retried after `pull --rebase`).
  Each cloud save triggers a redeploy, so the app restarts on the new data —
  edits made in the cloud persist.
