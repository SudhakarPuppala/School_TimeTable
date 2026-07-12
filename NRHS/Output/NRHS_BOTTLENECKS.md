# NRHS Timetable — Feasibility & Bottleneck Report

**Result:** solver status **OPTIMAL**, **0 hard-rule violations**. All hard rules
(2, 3, 4, 5, 6, 8, 9, 10, 11) are fully satisfied. The only soft rule not fully met
is **Rule 7 (no continuous classes / leisure in between — Study Hour not counted)**,
and only for structurally-overloaded teachers. Details below.

## 1. Data corrections applied (please confirm)

Two teacher names in the **G.K** column looked like data-entry variants and were
auto-normalised to a single teacher (otherwise they would count as phantom extra
teachers):

| As typed | Normalised to | Where |
|----------|--------------|-------|
| `S.GAYATRI` | **S.GAYATHRI** | Class 2 G.K |
| `SUMANI` | **D.SUMANI** | Class 3 G.K |

Also note: **Class 3 G.K → D.SUMANI** (a senior-class English teacher) and
**Classes 4–8 G.K → K.ESWAR** (science teacher). These are unusual cross-level
assignments — confirm they are intended.

## 2. Class Teacher vs Study-Hour supervisor (new two-row Period-1 sheet)

They are now read separately. They differ for **Class 5**:

| Class | Period-1 teacher | Study-Hour (P8) |
|-------|------------------|-----------------|
| Class 5 | S.GAYATHRI | **K.ESWAR** |

All other classes 1–7 use the same teacher for both. Classes 8/9/10 have no study hour.

## 3. Teacher weekly occupancy (of 48; Study-Hour supervision included)

| Teacher | Load | Teacher | Load |
|---------|------|---------|------|
| SHEKINA | 45 | SURYA DEVI | 35 |
| BIJILI | 45 | K.ESWAR | 33 |
| MAHA LAKSHMI | 45 | SAI KEERTHI | 31 |
| CHANDRAKALA | 42 | M.LALITHA | 30 |
| N.NAVYA | 40 | D.SUMANI | 25 |
| S.GAYATHRI | 40 | VINAY | 21 |
| R.KAMALA | 36 | SUNITHA | 18 |
| CHANDINI | 36 | RIYA | 15 |
| P.SATYAVENI | 35 | D.GOWTHAM | 14 |
| | | ANURADHA | 12 · CHALAPATHI 11 · SAIRAM 7 |

## 4. Remaining soft note — Rule 7 (leisure)

Longest unbroken teaching stretch (Study Hour excluded), teachers with 4+:

- **SHEKINA, BIJILI, MAHA LAKSHMI — 7** (LKG/UKG homeroom teachers, with their class
  all day by design; acceptable).
- **S.GAYATHRI — 7 (genuine overload).** She teaches EVS to Classes 2–5, Maths to
  Class 3, Biology to Classes 6–7, plus G.K — ~40/48. Some days are fully packed.
- **CHANDRAKALA — 6.**

### To smooth further (optional data change)
Move some of **S.GAYATHRI**'s load to a lighter teacher: e.g. shift **Class 3 Maths**
(7/wk) or one EVS class to SAIRAM (7/48), CHALAPATHI (11/48), or ANURADHA (12/48).

## 5. Guaranteed correct
- No teacher double-booked (parallel P.E.T / Karate excluded by design).
- Every (class, subject) hits its exact weekly count; every class totals 42.
- Classes 1–7 fully packed P1–P7 + Study Hour by the listed supervisor.
- Classes 8/9/10: no Study Hour, 6 free slots each.
- Karate = Thursday P7 (Classes 1–8); P.E.T only P6/P7; Gowtham never in P5;
  Chalapathi only P1–P3; Riya/Sunitha/Gowtham only in the afternoon; K.Eswar
  supervises Class-5 Study Hour and is never double-booked at P8.
