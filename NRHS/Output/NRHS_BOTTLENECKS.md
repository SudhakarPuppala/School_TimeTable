# NRHS Timetable — Feasibility & Bottleneck Report

**Result:** solver **OPTIMAL**, **0 hard-rule violations**, independent audit
(`python audit.py --school NRHS ...`) passes all checks over **603** taught slots.

## 1. New in this revision

- **No Period 8 on Saturday** (whole school). Saturday now runs P1–P7 only.
  - **Classes 8/9/10** (no Study Hour): usable slots = `5 days × 8 + Sat × 7 = 47`,
    which exactly equals their new **47-period** load → **fully packed, 0 free slots**.
  - **Classes LKG–7:** P1–P7 stay full on all 6 days; **Study Hour runs Mon–Fri only**
    (no Saturday study hour). Teaching load unchanged.
- **Increased periods for the senior classes** (Physics, Chemistry, Biology, Maths,
  English, P.E.T for Classes 8/9/10) — all absorbed; totals now 47 for 8/9/10.

## 2. Teacher weekly occupancy (of 47 usable slots; Study-Hour supervision incl.)

| Teacher | Load | Teacher | Load |
|---------|------|---------|------|
| SHEKINA | 44 | S.GAYATHRI | 34 |
| BIJILI | 44 | SAI KEERTHI | 30 |
| MAHA LAKSHMI | 44 | M.LALITHA | 30 |
| CHANDRAKALA | 44 | D.SUMANI | 27 |
| **K.ESWAR** | **42** | VINAY | 21 |
| SURYA DEVI | 40 | SUNITHA | 18 |
| N.NAVYA | 39 | D.GOWTHAM | 16 |
| CHANDINI | 36 | RIYA | 15 |
| R.KAMALA | 35 | CHALAPATHI | 12 |
| P.SATYAVENI | 34 | SAIRAM | 10 |

**K.ESWAR jumped to 42/47** — the senior-class Physics/Chemistry increases land almost
entirely on him (he teaches Chem to 6–10 and Physics to 6–8, plus Class-5 EVS + Class-5
Study Hour + some G.K). If leisure for him matters, split some Chemistry/Physics load
with SAIRAM (10/47).

## 3. Rules 12 & 13 (unchanged) — pins with minor P6 overflow
- Class 2 Maths → P7: 5 in P7, 2 in P6 (Thursday P7 is Karate).
- Class 1(A) P.E.T → P7: 5 in P7, 1 in P6.

## 4. Rules applied
Study Hour = Period-1 sheet supervisor, Mon–Fri, Classes 1–7 only; Riya/Sunitha/Gowtham
afternoon (Gowtham no P5); Chalapathi P1–P3; Karate Thu P7 (Classes 1–8); P.E.T P6/P7;
leisure after 2–3 periods (Study Hour not counted). No hard violations.

## 5. Leisure note (soft)
The four KG/UKG-and-Class-1(A) homeroom teachers (44/47) and K.Eswar (42/47) have long
teaching stretches by load; unavoidable at that occupancy. See the dashboard Validation
tab for the per-day list.
