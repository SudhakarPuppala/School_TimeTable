"""Data model + data-driven loader.

The rules engine was replaced by the *Teacher Leisure Plan* sheet: every
teacher-availability rule now lives in the workbook, not in code.

Each school's information workbook has 4 sheets (identical layout for both):
  1. Weekly Period Plan       subject rows x class cols -> periods/week (+ Total row)
  2. Teacher Allotment        subject rows x class cols -> teacher name
  3. Period 1 teacher allotment  per class: Period-1 teacher + Study-Hour supervisor
  4. Teacher Leisure Plan     per teacher: Leisure Fitment (MUST/BEST) + "Leisure"
                              marks for Period 1..7 / Study Hour (+ Lunch Break)

Semantics:
  - MUST + "Leisure"  -> hard: the teacher can NOT be scheduled in that period.
  - BEST + "Leisure"  -> soft: avoid that period if possible.
  - BEST (in general) -> the solver spreads periods to leave leisure gaps.
  - Lunch Break       -> everyone is free between P4 and P5 (informational).

The loader never raises on messy data: it collects `Issue`s (also consumed by
timetable.conflicts) so the dashboard can highlight the offending cells in red.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import difflib
import re

import openpyxl

# ---- common constants (same for every school) ----
DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT"]
N_DAYS = len(DAYS)
PERIODS = [1, 2, 3, 4, 5, 6, 7, 8]
STUDY_PERIOD = 8
ALL_PERIODS = set(PERIODS)

SHEET_PLAN = "Weekly Period Plan"
SHEET_ALLOT = "Teacher Allotment"
SHEET_P1 = "Period 1 teacher allotment"
SHEET_LEISURE = "Teacher Leisure Plan"
SHEET_ACTIVITY = "Activity Plan"

# Generic "whole class at once" instructors: exempt from double-booking because
# an external instructor (or several) handles all classes.  These labels are a
# data convention, not a scheduling rule.
GENERIC_CANON = {
    "PE": "P.E", "PET": "P.E", "PEINSTRUCTOR": "P.E", "PETINSTRUCTOR": "P.E",
    "MARTIALARTS": "MARTIAL ARTS", "KARATE": "MARTIAL ARTS",
    "KARATEINSTRUCTOR": "MARTIAL ARTS",
}
GENERIC_TEACHERS = {"P.E", "MARTIAL ARTS"}

# subject (compact key) -> display abbreviation used on the output sheets
SUBJ_ABBR = {
    "TELUGU": "TEL", "HINDI": "HIN", "ENGLISH": "ENG",
    "ENGGRAM": "GRAM", "ENGGRAMMAR": "GRAM",
    "MATHS": "MATH", "MATHEMATICS": "MATH", "EVS": "EVS",
    "PHYSICS": "PHY", "PHYCHE": "PHY", "CHEMISTRY": "CHEM", "CHEMISTY": "CHEM",
    "BIOLOGY": "BIO", "SOCIAL": "SOC", "COMPUTER": "COMP",
    "PET": "P.E.T", "GK": "G.K", "ORAL": "ORAL", "KARATE": "KAR",
}


# =====================================================================
#  small text helpers
# =====================================================================
def _norm(s):
    """Uppercase, collapse spaces, treat ',' as '.' (fixes 'K,ESWAR')."""
    return re.sub(r"\s+", " ", str(s).replace(",", ".").strip()).upper()


def _compact(s):
    """Letters+digits only, uppercased: 'Naga mani' -> 'NAGAMANI'."""
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


def _core(s):
    """Name without single-letter initials: 'K.ESWAR' -> 'ESWAR'."""
    toks = re.split(r"[.\s]+", _norm(s))
    keep = [t for t in toks if len(t) > 1]
    return "".join(keep) or "".join(toks)


def _first_tok(s):
    toks = re.split(r"[.\s]+", _norm(s))
    keep = [t for t in toks if len(t) > 1]
    return keep[0] if keep else (toks[0] if toks else "")


@dataclass
class Issue:
    """A data problem found while loading / checking.

    severity: 'error' (blocks generation), 'warning', or 'info'.
    sheet/row_key/col_key locate the offending cell for red highlighting
    (row_key = subject / teacher / class label, col_key = column label).
    """
    severity: str
    message: str
    sheet: str = ""
    row_key: str = ""
    col_key: str = ""


# =====================================================================
#  name resolver (teacher names differ across sheets)
# =====================================================================
class NameResolver:
    """Resolve raw teacher names to canonical ones (Leisure-Plan spelling).

    Tiers: exact norm -> compact -> core (no initials) -> unique first token
    -> unique fuzzy core match.  Non-exact resolutions are reported as info.
    """

    def __init__(self, canonical):
        self.canonical = list(dict.fromkeys(canonical))
        self.by_norm = {_norm(c): c for c in self.canonical}
        self.by_compact = {}
        self.by_core = {}
        self.by_first = {}
        for c in self.canonical:
            self.by_compact.setdefault(_compact(c), []).append(c)
            self.by_core.setdefault(_core(c), []).append(c)
            self.by_first.setdefault(_first_tok(c), []).append(c)
        self.cache = {}

    def add(self, name):
        if _norm(name) in self.by_norm:
            return
        self.canonical.append(name)
        self.by_norm[_norm(name)] = name
        self.by_compact.setdefault(_compact(name), []).append(name)
        self.by_core.setdefault(_core(name), []).append(name)
        self.by_first.setdefault(_first_tok(name), []).append(name)
        self.cache.clear()

    def resolve(self, raw):
        """-> (canonical_or_None, tier).  tier: 'exact'|'match'|None."""
        key = _norm(raw)
        if key in self.cache:
            return self.cache[key]
        out = (None, None)
        if key in self.by_norm:
            out = (self.by_norm[key], "exact")
        else:
            for table, q in ((self.by_compact, _compact(raw)),
                             (self.by_core, _core(raw)),
                             (self.by_first, _first_tok(raw))):
                hits = table.get(q, [])
                if len(hits) == 1:
                    out = (hits[0], "match")
                    break
            else:
                close = difflib.get_close_matches(_core(raw), list(self.by_core), n=2, cutoff=0.84)
                if len(close) == 1 and len(self.by_core[close[0]]) == 1:
                    out = (self.by_core[close[0]][0], "match")
        self.cache[key] = out
        return out


# =====================================================================
#  School configuration (structural facts only — no scheduling rules)
# =====================================================================
@dataclass
class SchoolConfig:
    name: str
    sheet_class_name: str
    sheet_teacher_name: str
    teacher_title: str
    no_p8_days: set = field(default_factory=set)   # days with no Period 8 (e.g. {"SAT"})


NRHS = SchoolConfig(
    name="NRHS",
    sheet_class_name="Class Time table", sheet_teacher_name="Teacher Time Table",
    teacher_title="SCHOOL TEACHER TIMETABLE",
    no_p8_days={"SAT"},
)

NRCS = SchoolConfig(
    name="NRCS",
    sheet_class_name="Class Time Table", sheet_teacher_name="Teacher Time Table",
    teacher_title="NRCS TEACHER TIMETABLE",
)

SCHOOLS = {"NRHS": NRHS, "NRCS": NRCS}

INPUTS = {
    "NRHS": "NRHS/Requirements/NRHS_Information.xlsx",
    "NRCS": "NRCS/Requirements/NRCS_information.xlsx",
}


# =====================================================================
#  Model
# =====================================================================
@dataclass
class Model:
    cfg: SchoolConfig
    classes: list                    # canonical order = Weekly Period Plan order
    subjects: list
    plan: dict                       # (class, subject) -> periods/week
    teacher_of: dict                 # (class, subject) -> teacher
    p1_teacher: dict                 # class -> Period-1 teacher
    study_supervisor: dict           # class -> Study-Hour supervisor
    teachers: list                   # real teachers (no generic instructors)
    study_hour_classes: list         # classes WITH a supervised study hour
    fitment: dict = field(default_factory=dict)       # teacher -> MUST | BEST
    blocked: dict = field(default_factory=dict)       # teacher -> {hard-blocked periods}
    soft_blocked: dict = field(default_factory=dict)  # teacher -> {soft-avoid periods}
    leisure_teachers: list = field(default_factory=list)   # sheet order
    # (subject, class) -> list of (days|None, periods|None) windows, one per
    # Activity-Plan row the class is ticked in. A class may span several rows;
    # its allowed slots are the UNION of all its windows.
    activity_windows: dict = field(default_factory=dict)
    # combined-session groups: list of (subject, label, frozenset(classes),
    # days|None, periods|None) — one per Activity-Plan row with ticks.
    activity_groups: list = field(default_factory=list)
    issues: list = field(default_factory=list)        # load-time Issues
    subjects_of: dict = field(default_factory=dict)

    # ---- helpers ----
    def abbr(self, subj):
        return SUBJ_ABBR.get(_compact(subj), str(subj)[:4].upper())

    def class_display(self, cls):
        return cls

    def is_parallel(self, cls, subj):
        return self.teacher_of.get((cls, subj)) in GENERIC_TEACHERS

    def teacher_allowed(self, teacher):
        """Periods the teacher may be scheduled in (hard leisure removed)."""
        return ALL_PERIODS - self.blocked.get(teacher, set())

    def teachable_periods(self, cls):
        return [1, 2, 3, 4, 5, 6, 7] if cls in self.study_hour_classes else [1, 2, 3, 4, 5, 6, 7, 8]

    def has_p8(self, day_name):
        return day_name not in self.cfg.no_p8_days

    def has_study_hour(self, cls, day_name):
        return cls in self.study_hour_classes and self.has_p8(day_name)

    def study_days(self):
        return sum(1 for d in DAYS if self.has_p8(d))

    def availability(self, teacher):
        """Total weekly slots the teacher could possibly teach/supervise."""
        allowed = self.teacher_allowed(teacher)
        n = 0
        for d in DAYS:
            for p in allowed:
                if p == STUDY_PERIOD and not self.has_p8(d):
                    continue
                n += 1
        return n

    def teaching_load(self, teacher):
        """(class, subject, n) triples this teacher is allotted."""
        return [(c, s, n) for (c, s), n in self.plan.items()
                if n > 0 and self.teacher_of.get((c, s)) == teacher]

    # ---- Activity Plan (days × periods, union over rows) ----
    def has_activity_window(self, subj, cls):
        return (subj, cls) in self.activity_windows

    def activity_allows(self, subj, cls, d, p):
        """Is (day d, period p) permitted for this activity/class?  True when
        the class has no Activity-Plan window (unrestricted), else it must fall
        inside at least one of the class's windows."""
        wins = self.activity_windows.get((subj, cls))
        if wins is None:
            return True
        for days, periods in wins:
            if (days is None or d in days) and (periods is None or p in periods):
                return True
        return False

    def activity_slots(self, subj, cls):
        """Set of concrete (day-index, period) slots allowed for this
        activity/class (union across the class's rows), honouring the class's
        teachable periods and no-P8 days.  None = unrestricted."""
        wins = self.activity_windows.get((subj, cls))
        if wins is None:
            return None
        teachable = set(self.teachable_periods(cls))
        out = set()
        for days, periods in wins:
            day_idx = range(N_DAYS) if days is None else days
            per = teachable if periods is None else (periods & teachable)
            for d in day_idx:
                for p in per:
                    if p == STUDY_PERIOD and not self.has_p8(DAYS[d]):
                        continue
                    out.add((d, p))
        return out


# =====================================================================
#  sheet sniffing
# =====================================================================
def _grid(ws):
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _read_plan(rows, issues):
    """-> (classes, subjects, plan). Header = first row with >=3 filled cells
    after col A. Skips the Total row (totals are recomputed)."""
    hdr_i = None
    for i, r in enumerate(rows):
        if sum(1 for v in r[1:] if v not in (None, "")) >= 3:
            hdr_i = i
            break
    if hdr_i is None:
        issues.append(Issue("error", "Weekly Period Plan: no header row found", SHEET_PLAN))
        return [], [], {}
    col_class = {j: str(v).strip() for j, v in enumerate(rows[hdr_i])
                 if j >= 1 and v not in (None, "")}
    classes = list(col_class.values())
    plan, subjects = {}, []
    for r in rows[hdr_i + 1:]:
        subj = r[0]
        if subj in (None, ""):
            continue
        subj = str(subj).strip()
        if _compact(subj).startswith("TOTAL"):
            continue
        subjects.append(subj)
        for j, cl in col_class.items():
            v = r[j] if j < len(r) else None
            try:
                plan[(cl, subj)] = int(v) if v not in (None, "") else 0
            except (TypeError, ValueError):
                issues.append(Issue("error", f"'{v}' is not a number ({subj} / {cl})",
                                    SHEET_PLAN, subj, cl))
                plan[(cl, subj)] = 0
    return classes, subjects, plan


class ClassResolver:
    """Map class labels from other sheets onto the Weekly-Plan class names.
    'U.K.G 1' -> 'UKG(A)' etc."""

    def __init__(self, classes):
        self.classes = classes
        self.by_key = {_compact(c): c for c in classes}

    def resolve(self, raw):
        k = _compact(raw)
        if k in self.by_key:
            return self.by_key[k]
        swap = k.translate(str.maketrans("12", "AB"))       # 'UKG1' -> 'UKGA'
        if swap in self.by_key:
            return self.by_key[swap]
        hit = difflib.get_close_matches(k, list(self.by_key), n=2, cutoff=0.8)
        if len(hit) == 1:
            return self.by_key[hit[0]]
        return None


def _class_columns(row, cres, start=1):
    """-> {col_index: canonical class} for one header row."""
    out = {}
    for j, v in enumerate(row):
        if j < start or v in (None, ""):
            continue
        c = cres.resolve(v)
        if c:
            out[j] = c
    return out


def _read_allotment(rows, cres, subjects, issues):
    """-> {(class, subject_raw): teacher_raw} plus per-cell issue locations."""
    hdr_i, cols = None, {}
    for i, r in enumerate(rows):
        cand = _class_columns(r, cres)
        if len(cand) >= 3:
            hdr_i, cols = i, cand
            break
    if hdr_i is None:
        issues.append(Issue("error", "Teacher Allotment: no class header row found", SHEET_ALLOT))
        return {}
    # subject resolver: compact match, then prefix, then fuzzy
    subj_keys = {_compact(s): s for s in subjects}
    special = {"PHYCHE": "PHYSICS"}

    def subj_resolve(raw):
        k = _compact(raw)
        k = special.get(k, k)
        if k in subj_keys:
            return subj_keys[k]
        pref = [s for key, s in subj_keys.items() if key.startswith(k) or k.startswith(key)]
        if len(pref) == 1:
            return pref[0]
        hit = difflib.get_close_matches(k, list(subj_keys), n=2, cutoff=0.8)
        if len(hit) == 1:
            return subj_keys[hit[0]]
        return None

    out = {}
    for r in rows[hdr_i + 1:]:
        lbl = r[0]
        if lbl in (None, ""):
            continue
        subj = subj_resolve(lbl)
        if subj is None:
            issues.append(Issue("warning",
                                f"Teacher Allotment row '{lbl}' does not match any "
                                f"Weekly-Plan subject — row ignored",
                                SHEET_ALLOT, str(lbl).strip()))
            continue
        for j, cl in cols.items():
            v = r[j] if j < len(r) else None
            if v not in (None, ""):
                out[(cl, subj)] = str(v).strip()
    return out


def _read_p1(rows, cres, issues):
    """-> (p1_raw, study_raw): class -> raw teacher name.  Accepts both layouts:
      A) label rows:  Class | ... / Period 1 Teacher | ... / Study Hour | ...
      B) Day/Period:  Day | Period | classes...  with rows '1' and 'Study Hour'
    """
    p1_raw, study_raw = {}, {}
    day_i = next((i for i, r in enumerate(rows)
                  if r and _compact(r[0]) == "DAY" and len(r) > 1 and _compact(r[1]) == "PERIOD"), None)
    if day_i is not None:                                    # layout B
        cols = _class_columns(rows[day_i], cres, start=2)
        for r in rows[day_i + 1:]:
            lbl = _compact(r[1]) if len(r) > 1 and r[1] is not None else ""
            target = p1_raw if lbl in ("1", "10") else (study_raw if lbl.startswith("STUDY") else None)
            if target is None:
                continue
            for j, cl in cols.items():
                v = r[j] if j < len(r) else None
                if v not in (None, ""):
                    target[cl] = str(v).strip()
        return p1_raw, study_raw

    hdr_i, cols = None, {}
    for i, r in enumerate(rows):                             # layout A
        cand = _class_columns(r, cres)
        if len(cand) >= 3:
            hdr_i, cols = i, cand
            break
    if hdr_i is None:
        issues.append(Issue("warning", "Period 1 sheet: no class header row found", SHEET_P1))
        return p1_raw, study_raw
    for r in rows[hdr_i + 1:]:
        lbl = _compact(r[0]) if r and r[0] is not None else ""
        target = (p1_raw if lbl.startswith("PERIOD1") else
                  (study_raw if lbl.startswith("STUDY") else None))
        if target is None:
            continue
        for j, cl in cols.items():
            v = r[j] if j < len(r) else None
            if v not in (None, ""):
                target[cl] = str(v).strip()
    return p1_raw, study_raw


LEISURE_COLS = ["Teacher Name", "Leisure Fitment", "Period 1", "Period 2", "Period 3",
                "Period 4", "Lunch Break", "Period 5", "Period 6", "Period 7", "Study Hour"]


def parse_period_list(raw):
    """'6,7' / 'P6, P7' / '6-7' / 'Study Hour' -> {6, 7} / {8}.  Blank -> None."""
    if raw in (None, ""):
        return None
    s = str(raw)
    out = set()
    if re.search(r"study", s, re.I) or re.search(r"\bSH\b", s, re.I):
        out.add(STUDY_PERIOD)
    for a, b in re.findall(r"(\d+)\s*-\s*(\d+)", s):
        out.update(range(int(a), int(b) + 1))
    s2 = re.sub(r"\d+\s*-\s*\d+", "", s)
    out.update(int(n) for n in re.findall(r"\d+", s2))
    return {p for p in out if 1 <= p <= 8} or None


_DAY_IDX = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5}


def parse_day_list(raw):
    """'MON,TUE' / 'Monday Wednesday' / 'MON-THU' -> {0, 1} / {0, 2} / {0..3}.
    Blank (or no recognisable day) -> None = any day."""
    if raw in (None, ""):
        return None
    s = str(raw).upper()
    out = set()
    for a, b in re.findall(r"([A-Z]+)\s*-\s*([A-Z]+)", s):
        ia, ib = _DAY_IDX.get(a[:3]), _DAY_IDX.get(b[:3])
        if ia is not None and ib is not None and ia <= ib:
            out.update(range(ia, ib + 1))
    for t in re.findall(r"[A-Z]+", s):
        i = _DAY_IDX.get(t[:3])
        if i is not None:
            out.add(i)
    return out or None


TICK_TOKENS = {"YES", "Y", "TRUE", "X", "OK", "1", "COMBINE", "COMBINED", "✓", "✔"}


def _is_tick(v):
    if v is True:
        return True
    if v in (None, "", False):
        return False
    return _compact(v) in TICK_TOKENS or str(v).strip() in ("✓", "✔")


def _read_activity(rows, cres, subjects, issues):
    """Activity Plan sheet — each row is one COMBINED-SESSION group:
        Activity | Allowed Days | Allowed Periods | one column per class (tick)

    Ticked classes get that row's Allowed Days × Allowed Periods as a hard
    window and are scheduled together whenever the weekly counts allow.
    Blank days = any day; blank periods = any period.  A class ticked in no
    row for its activity has no restriction and is not combined.  A class may
    be ticked in SEVERAL rows — its allowed slots are the UNION of those rows'
    windows (e.g. P7 on Mon/Wed/Fri and P5 on Sat).

    -> (activity_windows {(subject, class): [(days|None, periods|None), ...]},
        activity_groups  [(subject, label, frozenset(classes), days, periods)])
    """
    windows, groups = {}, []
    if not rows:
        return windows, groups
    hdr_i, ap_col, day_col, cols = None, None, None, {}
    for i, r in enumerate(rows):
        if not r or r[0] in (None, "") or not _compact(r[0]).startswith("ACTIVITY"):
            continue
        for j, v in enumerate(r):
            if j == 0 or v in (None, ""):
                continue
            k = _compact(v)
            if "DAY" in k and "PERIOD" not in k:
                day_col = j
            elif "PERIOD" in k or k == "ALLOWED":
                ap_col = j
            else:
                c = cres.resolve(v)
                if c:
                    cols[j] = c
        if len(cols) >= 3 or ap_col is not None:
            hdr_i = i
            break
        cols = {}
    if hdr_i is None:
        return windows, groups

    subj_keys = {_compact(s): s for s in subjects}

    def subj_resolve(raw):
        k = _compact(raw)
        if k in subj_keys:
            return subj_keys[k]
        pref = [s for key, s in subj_keys.items() if key.startswith(k) or k.startswith(key)]
        return pref[0] if len(pref) == 1 else None

    row_no = {}                                  # subject -> running group number
    for r in rows[hdr_i + 1:]:
        if not r or r[0] in (None, ""):
            continue
        subj = subj_resolve(r[0])
        if subj is None:
            issues.append(Issue("warning",
                                f"Activity Plan row '{r[0]}' does not match any Weekly-Plan "
                                f"subject — row ignored", SHEET_ACTIVITY, str(r[0]).strip()))
            continue
        row_no[subj] = row_no.get(subj, 0) + 1
        ps = parse_period_list(r[ap_col]) if ap_col is not None and ap_col < len(r) else None
        ds = parse_day_list(r[day_col]) if day_col is not None and day_col < len(r) else None
        if day_col is not None and day_col < len(r) and r[day_col] not in (None, "") and ds is None:
            issues.append(Issue("warning",
                                f"Activity Plan '{subj}': could not read Allowed Days "
                                f"'{r[day_col]}' — use day names like MON,TUE or MON-THU",
                                SHEET_ACTIVITY, subj, "Allowed Days"))
        row_classes = []
        for j, cl in enumerate_cols(cols, r):
            v = r[j]
            if v in (None, "", False):
                continue
            row_classes.append(cl)
            # accumulate this row's window onto the class (union across rows)
            windows.setdefault((subj, cl), []).append((ds, ps))
        if row_classes:
            groups.append((subj, f"Group {row_no[subj]}",
                           frozenset(row_classes), ds, ps))
    return windows, groups


def enumerate_cols(cols, r):
    return [(j, cl) for j, cl in cols.items() if j < len(r)]


def _read_leisure(rows, issues):
    """-> (order, fitment, blocked, soft_blocked)."""
    hdr_i = next((i for i, r in enumerate(rows)
                  if r and r[0] and _compact(r[0]).startswith("TEACHERNAME")), None)
    if hdr_i is None:
        issues.append(Issue("error", "Teacher Leisure Plan: header row "
                            "('Teacher Name | Leisure Fitment | ...') not found", SHEET_LEISURE))
        return [], {}, {}, {}
    fit_col, period_col = None, {}
    for j, v in enumerate(rows[hdr_i]):
        if v in (None, ""):
            continue
        k = _compact(v)
        if "FITM" in k:
            fit_col = j
        elif k.startswith("PERIOD"):
            mnum = re.search(r"(\d+)", k)
            if mnum:
                period_col[j] = int(mnum.group(1))
        elif k.startswith("STUDY"):
            period_col[j] = STUDY_PERIOD

    order, fitment, blocked, soft = [], {}, {}, {}
    for r in rows[hdr_i + 1:]:
        name = r[0]
        if name in (None, ""):
            continue
        t = _norm(name)
        if t in fitment:
            issues.append(Issue("error", f"Duplicate teacher '{t}' in Teacher Leisure Plan",
                                SHEET_LEISURE, t, "Teacher Name"))
            continue
        fit = _compact(r[fit_col]) if fit_col is not None and fit_col < len(r) and r[fit_col] else "BEST"
        if fit not in ("MUST", "BEST"):
            issues.append(Issue("warning", f"{t}: unknown Leisure Fitment '{r[fit_col]}' — "
                                f"treated as BEST", SHEET_LEISURE, t, "Leisure Fitment"))
            fit = "BEST"
        order.append(t)
        fitment[t] = fit
        marks = set()
        for j, p in period_col.items():
            v = r[j] if j < len(r) else None
            if v in (None, ""):
                continue
            if "LEISURE" in _compact(v):
                marks.add(p)
            else:
                issues.append(Issue("warning",
                                    f"{t}: unexpected value '{v}' in period column — "
                                    f"only 'Leisure' (or empty) is understood",
                                    SHEET_LEISURE, t,
                                    "Study Hour" if p == STUDY_PERIOD else f"Period {p}"))
        (blocked if fit == "MUST" else soft)[t] = marks
    return order, fitment, blocked, soft


# =====================================================================
#  loader
# =====================================================================
def load_model(path, school="NRHS"):
    cfg = SCHOOLS[school]
    wb = openpyxl.load_workbook(path, data_only=True)
    issues = []

    def sheet_rows(name, required=True):
        for ws in wb.worksheets:
            if _compact(ws.title) == _compact(name):
                return _grid(ws)
        if required:
            issues.append(Issue("error", f"Sheet '{name}' not found in workbook", name))
        return []

    classes, subjects, plan = _read_plan(sheet_rows(SHEET_PLAN), issues)
    cres = ClassResolver(classes)
    allot_raw = _read_allotment(sheet_rows(SHEET_ALLOT), cres, subjects, issues)
    p1_raw, study_raw = _read_p1(sheet_rows(SHEET_P1), cres, issues)
    order, fitment, blocked, soft = _read_leisure(sheet_rows(SHEET_LEISURE), issues)
    activity_windows, activity_groups = _read_activity(
        sheet_rows(SHEET_ACTIVITY, required=False), cres, subjects, issues)

    # ---- resolve teacher names against the Leisure-Plan spelling ----
    resolver = NameResolver(order)

    def canon(raw, sheet, row_key, col_key):
        g = GENERIC_CANON.get(_compact(raw))
        if g:
            return g
        got, tier = resolver.resolve(raw)
        if got is None:
            t = _norm(raw)
            issues.append(Issue("warning",
                                f"Teacher '{raw}' is not in the Teacher Leisure Plan — "
                                f"treated as BEST with no leisure periods",
                                sheet, row_key, col_key))
            resolver.add(t)
            fitment.setdefault(t, "BEST")
            soft.setdefault(t, set())
            return t
        if tier != "exact":
            issues.append(Issue("info", f"Name '{raw}' matched to '{got}' ({sheet})",
                                sheet, row_key, col_key))
        return got

    teacher_of = {}
    for (cl, subj), raw in allot_raw.items():
        teacher_of[(cl, subj)] = canon(raw, SHEET_ALLOT, subj, cl)
    p1_teacher = {cl: canon(raw, SHEET_P1, cl, "Period 1 Teacher")
                  for cl, raw in p1_raw.items()}
    study_supervisor = {cl: canon(raw, SHEET_P1, cl, "Study Hour")
                        for cl, raw in study_raw.items()}

    # ---- fill data gaps by convention (reported, overridable in the sheet) ----
    fills = {"PET": ("P.E", "generic P.E instructor (parallel activity)"),
             "KARATE": ("MARTIAL ARTS", "generic Martial-Arts instructor (parallel activity)")}
    inherit = {"ENGGRAM": "ENGLISH", "ENGGRAMMAR": "ENGLISH",
               "CHEMISTRY": "PHYSICS", "CHEMISTY": "PHYSICS"}
    class_teacher_subjects = {"ORAL", "GK"}
    subj_by_key = {_compact(s): s for s in subjects}
    for cl in classes:
        for subj in subjects:
            if plan.get((cl, subj), 0) == 0 or (cl, subj) in teacher_of:
                continue
            key = _compact(subj)
            if key in fills:
                teacher_of[(cl, subj)] = fills[key][0]
                note = fills[key][1]
            elif key in inherit and (cl, subj_by_key.get(inherit[key], "")) in teacher_of:
                teacher_of[(cl, subj)] = teacher_of[(cl, subj_by_key[inherit[key]])]
                note = f"inherited from {subj_by_key[inherit[key]]} teacher"
            elif key in class_teacher_subjects and cl in p1_teacher:
                teacher_of[(cl, subj)] = p1_teacher[cl]
                note = "assigned to the class (Period-1) teacher"
            else:
                continue        # left unassigned -> conflicts.py reports an error
            issues.append(Issue("info",
                                f"{cl} · {subj}: no Teacher-Allotment entry — {note} "
                                f"({teacher_of[(cl, subj)]})", SHEET_ALLOT, subj, cl))

    teachers = sorted({t for t in teacher_of.values() if t not in GENERIC_TEACHERS})
    for t in teachers:                       # teachers seen only in the allotment
        fitment.setdefault(t, "BEST")
        soft.setdefault(t, set())
    study_hour_classes = [c for c in classes if study_supervisor.get(c)]
    subjects_of = {c: [s for s in subjects if plan.get((c, s), 0) > 0] for c in classes}

    return Model(cfg=cfg, classes=classes, subjects=subjects, plan=plan,
                 teacher_of=teacher_of, p1_teacher=p1_teacher,
                 study_supervisor=study_supervisor, teachers=teachers,
                 study_hour_classes=study_hour_classes,
                 fitment=fitment, blocked=blocked, soft_blocked=soft,
                 leisure_teachers=order, activity_windows=activity_windows,
                 activity_groups=activity_groups,
                 issues=issues, subjects_of=subjects_of)
