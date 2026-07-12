# NRHS Timetable — Feasibility & Bottleneck Report

**Result:** solver status **OPTIMAL**, **0 hard-rule violations**, and the independent
audit (`python audit.py`) passes all 8 cross-checks over 588 slots. Rules 1–13 are
implemented. Two items required attention — see §1 (a genuine capacity conflict) and
§4 (leisure).

## 1. Rules 12 & 13 — capacity conflict (auto-resolved, please confirm)

- **Rule 12** — Chandrakala's **Class 2 Maths in Period 7 only**. Class 2 Maths is
  **7/week**, but there are only 6 P7 slots and **Thursday P7 is Karate**, so only
  **5** are usable. Result: **5 in P7, 2 in P6**.
- **Rule 13** — **Class 1(A) P.E.T in Period 7**. Class 1(A) P.E.T is **6/week**;
  same Thursday-Karate clash → **5 in P7, 1 in P6** (P6 is still valid per Rule 10).

These two rules interlock nicely: putting Class 1(A) P.E.T in P7 frees Chandrakala
(Class 1(A)'s teacher) to take Class 2 Maths in P7. It only *slightly* overflows.

**To make them 100% P7**, pick one:
- reduce **Class 2 Maths to ≤5/week** and **Class 1(A) P.E.T to ≤5/week**, or
- exempt these classes from Thursday-P7 Karate, or
- accept the 2 + 1 periods sitting in P6 (current output).

## 2. Data change noticed
**ANURADHA is now unassigned** — her Class 1(A)/1(B) EVS moved to the class teachers
(Chandrakala / Surya Devi), so she teaches nothing and drops off the roster (20 teachers).
Confirm this is intended.

## 3. Teacher weekly occupancy (of 48; Study-Hour supervision included)

| Teacher | Load | Teacher | Load |
|---------|------|---------|------|
| SHEKINA | 45 | P.SATYAVENI | 35 |
| BIJILI | 45 | S.GAYATHRI | 34 |
| MAHA LAKSHMI | 45 | SAI KEERTHI | 31 |
| CHANDRAKALA | 45 | M.LALITHA | 30 |
| SURYA DEVI | 41 | D.SUMANI | 25 |
| N.NAVYA | 40 | VINAY | 21 |
| K.ESWAR | 38 | SUNITHA | 18 |
| R.KAMALA | 36 | D.GOWTHAM | 16 |
| CHANDINI | 36 | RIYA | 15 · CHALAPATHI 11 · SAIRAM 6 |

## 4. Remaining soft note — Rule 7 (leisure, Study Hour not counted)

Longest unbroken teaching stretch, teachers with 4+:
- **SHEKINA, BIJILI, MAHA LAKSHMI, CHANDRAKALA — 7.** The first three are LKG/UKG
  homeroom teachers (with their class all day by design). **CHANDRAKALA** is now also
  at 45/48 because she teaches all of Class 1(A) *plus* Class 2 Maths — a genuine load
  to watch; shift some Class 1(A) subjects to another teacher to relieve her.
- SURYA DEVI 5; SAI KEERTHI, R.KAMALA 4.

## 5. Guaranteed correct (independently audited)
- No teacher double-booked; every (class, subject) hits its exact weekly count; every class = 42.
- Classes 1–7 fully packed P1–P7 + Study Hour by the listed supervisor; 8/9/10 have 6 free slots.
- Karate = Thu P7 (Classes 1–8); P.E.T only P6/P7; Gowtham never P5; Chalapathi P1–P3;
  Riya/Sunitha/Gowtham afternoon only; Class-5 Study Hour = K.Eswar (never double-booked).
- Rules 12/13 pins verified within P7/P6 (Class 2 Maths 5@P7+2@P6; Class 1(A) P.E.T 5@P7+1@P6).
