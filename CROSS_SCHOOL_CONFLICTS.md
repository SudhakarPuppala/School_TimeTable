# Cross-School Conflict Check (NRHS ∩ NRCS)

Run: `python cross_check.py`

Some teachers appear at **both** schools. A shared teacher must not be scheduled at the
same day+period in both timetables. Teachers are matched **by name** (leading initials
like `D.` are stripped) — **please confirm whether same-named teachers are the same
person**; if they are different people, ignore the clash.

## Result

**Current result: ✅ No cross-school clashes.**

| Teacher (NRHS = NRCS) | NRHS periods | NRCS periods | Clash |
|-----------------------|--------------|--------------|-------|
| CHALAPATHI = Chalapathi | 1–3 | **5–7** | ✅ none (disjoint windows) |
| D.GOWTHAM = Gowtham | 6–8 | 2–4 | ✅ none |
| RIYA = Riya | 5–8 | 1–4 | ✅ none |
| SUNITHA = Sunitha | 5–8 | 1–4 | ✅ none |
| ~~M.LALITHA / Lalitha~~ | — | — | not shared (different people) |

All four shared teachers have **disjoint** windows across the two schools, so none is ever
double-booked:
- **Chalapathi** (same person, confirmed): NRHS **P1–P3**, NRCS **P5–P7**.
- **Gowtham / Riya / Sunitha**: afternoon at NRHS, morning at NRCS.

`M.LALITHA` (NRHS) and `Lalitha` (NRCS) are different people (`CONFIRMED_DISTINCT`).

## Interpretation

- **Riya, Sunitha, Gowtham, Chalapathi — no clash.** Their morning/afternoon windows at
  the two schools are complementary (afternoon at NRHS, morning at NRCS), so they never
  overlap. They are the same staff splitting the day between the two schools, and the
  rules are set up correctly for that.

- **Lalitha — confirmed DIFFERENT people.** NRHS `M.LALITHA` and NRCS `Lalitha` share a
  name by coincidence, so `LALITHA` is listed in `CONFIRMED_DISTINCT` in `cross_check.py`
  and excluded from the check. No action needed.

If any teacher identities change, update `CONFIRMED_DISTINCT` in `cross_check.py` and
re-run `python cross_check.py`.
