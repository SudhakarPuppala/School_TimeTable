# NRHS Timetable — Feasibility & Bottleneck Report

**Result:** solver status **OPTIMAL**, **0 hard-rule violations**. All hard rules
(2, 3, 4-P8, 5, 6, 8, 9, 10, 11) are fully satisfied. The only soft rule that
cannot be fully met is **Rule 7 (leisure after 2–3 periods)** — because of teacher
overload in the source data. Details below.

## 1. Assumptions made (please confirm / adjust)

Four subjects have **no teacher** in the *Teacher Allotment* sheet. They were
handled as follows:

| Subject | Periods/wk | Handling |
|---------|-----------|----------|
| **ORAL** | 18 (LKG/UKG) | taught by each class's **class teacher** |
| **G.K** | 12 | taught by each class's **class teacher** |
| **P.E.T** | 27 | **generic "P.E.T Instructor"**, parallel activity, P6/P7 only |
| **Karate** | 9 | **generic "Karate Instructor"**, parallel, Thu P7 |

> **Why P.E.T must be parallel:** a single P.E.T teacher would need 27 slots but only
> 12 P6/P7 slots exist in a week. So P.E.T is modelled as a whole-school activity
> (multiple coaches / grounds). If you have named P.E.T staff, add them to the
> allotment and we can enforce real no-double-booking.

## 2. Teacher weekly load (occupied slots out of 48)

| Teacher | Load | Teacher | Load |
|---------|------|---------|------|
| SHEKINA | 45/48 | SURYA DEVI | 35/48 |
| BIJILI | 45/48 | SAI KEERTHI | 32/48 |
| MAHA LAKSHMI | 45/48 | M.LALITHA | 30/48 |
| **S.GAYATHRI** | **45/48** | D.SUMANI | 24/48 |
| CHANDRAKALA | 42/48 | K.ESWAR | 23/48 |
| N.NAVYA | 41/48 | VINAY | 21/48 |
| CHANDINI | 39/48 | SUNITHA | 18/48 |
| P.SATYAVENI | 37/48 | RIYA | 15/48 |
| R.KAMALA | 37/48 | D.GOWTHAM | 14/48 |
| | | CHALAPATHI | 11/48 |
| | | SAIRAM | 7/48 |

## 3. The one real bottleneck — Rule 7 (leisure)

Some teachers are so heavily loaded in the source data that they **cannot** get a
free period after every 2–3 periods:

- **SHEKINA, BIJILI, MAHA LAKSHMI (LKG/UKG homeroom teachers)** — 45/48.
  These are pre-primary homeroom teachers who stay with their class almost the whole
  day *by design*. Long unbroken stretches here are normal and usually acceptable.
- **S.GAYATHRI — 45/48 (genuine concern).** She is the Class-5 teacher **and** the
  EVS teacher for ~8 classes **and** teaches some Biology + G.K. With only 3 free
  slots all week she has full 7–8 period days.
- **CHANDRAKALA (42), N.NAVYA (41)** — also very tight.

### Suggested data-side fixes (pick any)
1. **Redistribute EVS**: move EVS for 2–3 of the lower classes from **S.GAYATHRI**
   to a lighter teacher (e.g. SAIRAM 7/48, CHALAPATHI 11/48, ANURADHA 12/48).
2. **Add a KG assistant** so SHEKINA / BIJILI / MAHA LAKSHMI are not solo all day.
3. **Provide named P.E.T staff** if P.E.T should be a real (non-parallel) subject.
4. Reduce any subject's weekly count for the most-loaded classes.

Give us the adjusted *Teacher Allotment* / *Weekly Period Plan* and re-run — the
leisure warnings will shrink automatically.

## 4. What is guaranteed correct

- No teacher is ever in two classes at once (parallel P.E.T / Karate excluded by design).
- Every subject hits its exact weekly period count for every class.
- Classes LKG–7 are fully packed P1–P7 with Study Hour (P8) supervised by the class teacher.
- Classes 8/9/10 have no Study Hour and exactly 6 free slots each.
- Karate = Thursday P7 (Classes 1–8); P.E.T only in P6/P7; Gowtham never in P5;
  Chalapathi only P1–P3; Riya/Sunitha/Gowtham only in the afternoon.
