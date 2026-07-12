"""Data model + per-school configuration.

Two schools (NRHS, NRCS) have different rules AND different workbook layouts, so
each has a `SchoolConfig` and a dedicated loader. Both loaders return a uniform
`Model`, which the generic solver / verifier / writer / pdf consume via `m.cfg`.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import re
import openpyxl

# ---- common constants (same for every school) ----
DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT"]
N_DAYS = len(DAYS)
PERIODS = [1, 2, 3, 4, 5, 6, 7, 8]
STUDY_PERIOD = 8


def _norm(s):
    return re.sub(r"\s+", " ", str(s).strip()).lower()


# =====================================================================
#  School configuration
# =====================================================================
@dataclass
class SchoolConfig:
    name: str
    class_order: list
    class_display: dict
    no_study_hour: set
    subj_abbr: dict
    parallel_subjects: set
    generic_teacher: dict            # subject -> generic instructor name
    class_teacher_subjects: set      # subjects taught by the class teacher if unassigned
    teacher_windows: dict            # teacher -> allowed periods
    default_window: set
    subject_windows: dict            # subject -> allowed periods
    karate_day: str
    karate_period: int
    karate_classes: set
    pinned_period: dict              # (class, subject) -> preferred period
    subject_inherit: dict            # subject -> fallback subject for teacher if unassigned
    teacher_aliases: dict            # raw name -> canonical
    morning_only: set                # teachers restricted to the morning (for relax pass)
    sheet_class_name: str
    sheet_teacher_name: str
    teacher_title: str
    no_p8_days: set = field(default_factory=set)   # days with no Period 8 (e.g. {"SAT"})

    def canon_teacher(self, name):
        n = re.sub(r"\s+", " ", str(name).strip())
        return self.teacher_aliases.get(n.upper(), n)


@dataclass
class Model:
    cfg: SchoolConfig
    classes: list
    subjects: list
    plan: dict                       # (class, subject) -> periods/week
    teacher_of: dict                 # (class, subject) -> teacher
    p1_teacher: dict                 # class -> Period-1 teacher
    study_supervisor: dict           # class -> Study-Hour supervisor
    teachers: list
    study_hour_classes: list
    subjects_of: dict = field(default_factory=dict)

    def teacher_window(self, teacher):
        return self.cfg.teacher_windows.get(teacher, self.cfg.default_window)

    def teachable_periods(self, cls):
        return [1, 2, 3, 4, 5, 6, 7, 8] if cls in self.cfg.no_study_hour else [1, 2, 3, 4, 5, 6, 7]

    def has_p8(self, day_name):
        return day_name not in self.cfg.no_p8_days

    def has_study_hour(self, cls, day_name):
        return cls in self.study_hour_classes and self.has_p8(day_name)


# =====================================================================
#  NRHS configuration
# =====================================================================
NRHS = SchoolConfig(
    name="NRHS",
    class_order=["LKG", "UKG(A)", "UKG(B)", "Class 1(A)", "CLASS 1(B)", "Class 2",
                 "Class 3", "Class 4", "Class 5", "Class 6", "Class 7",
                 "Class 8", "Class 9", "Class 10"],
    class_display={"LKG": "LKG", "UKG(A)": "UKG (A)", "UKG(B)": "UKG (B)",
                   "Class 1(A)": "Class 1(A)", "CLASS 1(B)": "Class 1(B)", "Class 2": "Class 2",
                   "Class 3": "Class 3", "Class 4": "Class 4", "Class 5": "Class 5",
                   "Class 6": "Class 6", "Class 7": "Class 7", "Class 8": "Class 8",
                   "Class 9": "Class 9", "Class 10": "Class 10"},
    no_study_hour={"Class 8", "Class 9", "Class 10"},
    subj_abbr={"Telugu": "TEL", "Hindi": "HIN", "English": "ENG", "Maths": "MATH", "EVS": "EVS",
               "Physics": "PHY", "Chemistry": "CHEM", "Biology": "BIO", "Social": "SOC",
               "Computer": "COMP", "P.E.T": "P.E.T", "G.K": "G.K", "ORAL": "ORAL", "Karate": "KAR"},
    parallel_subjects={"P.E.T", "Karate"},
    generic_teacher={"P.E.T": "P.E.T Instructor", "Karate": "Karate Instructor"},
    class_teacher_subjects={"ORAL", "G.K"},
    teacher_windows={"RIYA": {5, 6, 7, 8}, "SUNITHA": {5, 6, 7, 8},
                     "D.GOWTHAM": {6, 7, 8}, "CHALAPATHI": {1, 2, 3}},
    default_window={1, 2, 3, 4, 5, 6, 7},
    subject_windows={"P.E.T": {6, 7}},
    karate_day="THU", karate_period=7,
    karate_classes={"Class 1(A)", "CLASS 1(B)", "Class 2", "Class 3", "Class 4",
                    "Class 5", "Class 6", "Class 7", "Class 8"},
    pinned_period={("Class 2", "Maths"): 7, ("Class 1(A)", "P.E.T"): 7},
    subject_inherit={},
    teacher_aliases={"S.GAYATRI": "S.GAYATHRI", "SUMANI": "D.SUMANI"},
    morning_only=set(),
    sheet_class_name="Class Time table", sheet_teacher_name="Teacher Time Table",
    teacher_title="SCHOOL TEACHER TIMETABLE",
    no_p8_days={"SAT"},
)

# =====================================================================
#  NRCS configuration
# =====================================================================
NRCS = SchoolConfig(
    name="NRCS",
    class_order=["L.K.G", "U.K.G", "Class 1", "Class 2", "Class 3", "Class 4",
                 "Class 5", "Class 6", "Class 7", "Class 8", "Class 9", "Class 10"],
    class_display={c: c for c in ["L.K.G", "U.K.G", "Class 1", "Class 2", "Class 3",
                                  "Class 4", "Class 5", "Class 6", "Class 7", "Class 8",
                                  "Class 9", "Class 10"]},
    no_study_hour={"Class 10"},
    subj_abbr={"Telugu": "TEL", "Hindi": "HIN", "English": "ENG", "Eng Gram": "GRAM",
               "Maths": "MATH", "EVS": "EVS", "Physics": "PHY", "Chemisty": "CHEM",
               "Biology": "BIO", "Social": "SOC", "Oral": "ORAL", "G.K": "G.K",
               "Computer": "COMP", "P.E.T": "P.E.T", "Karate": "KAR"},
    parallel_subjects={"P.E.T", "Karate"},
    generic_teacher={"P.E.T": "P.E", "Karate": "Martial Arts"},
    class_teacher_subjects={"Oral"},
    teacher_windows={"Sonu": {5, 6, 7, 8}, "Gowtham": {2, 3, 4},
                     "Sunitha": {1, 2, 3, 4}, "Riya": {1, 2, 3, 4}, "Bheema": {1, 2, 3, 4},
                     "Chalapathi": {5, 6, 7}},   # avoid overlap w/ NRHS Chalapathi (P1-3)
    default_window={1, 2, 3, 4, 5, 6, 7},
    subject_windows={"P.E.T": {5, 6, 7}},
    karate_day="THU", karate_period=6,
    karate_classes={"Class 1", "Class 2", "Class 3", "Class 4", "Class 5",
                    "Class 6", "Class 7", "Class 8", "Class 9", "Class 10"},
    pinned_period={("L.K.G", "Oral"): 1},
    subject_inherit={"Chemisty": "Physics", "Eng Gram": "English"},
    teacher_aliases={},
    morning_only={"Gowtham", "Sunitha", "Riya", "Bheema"},
    sheet_class_name="Class Time Table", sheet_teacher_name="Teacher Time Table",
    teacher_title="NRCS TEACHER TIMETABLE",
)

SCHOOLS = {"NRHS": NRHS, "NRCS": NRCS}


# =====================================================================
#  helpers shared by loaders
# =====================================================================
def _finalise(cfg, classes, subjects, plan, teacher_of, p1_teacher, study_supervisor):
    # subject-inherit fallback (e.g. NRCS Chemisty -> Physics teacher)
    for cl in classes:
        for subj in subjects:
            if plan.get((cl, subj), 0) == 0 or (cl, subj) in teacher_of:
                continue
            src = cfg.subject_inherit.get(subj)
            if src and (cl, src) in teacher_of:
                teacher_of[(cl, subj)] = teacher_of[(cl, src)]
    # rule-based teachers for still-unassigned subjects
    for cl in classes:
        for subj in subjects:
            if plan.get((cl, subj), 0) == 0 or (cl, subj) in teacher_of:
                continue
            if subj in cfg.generic_teacher:
                teacher_of[(cl, subj)] = cfg.generic_teacher[subj]
            elif subj in cfg.class_teacher_subjects:
                teacher_of[(cl, subj)] = p1_teacher.get(cl, f"{cl} teacher")
    for cl in p1_teacher:
        study_supervisor.setdefault(cl, p1_teacher[cl])

    teachers = sorted({t for t in teacher_of.values()
                       if t not in cfg.generic_teacher.values()})
    study_hour_classes = [c for c in classes if c not in cfg.no_study_hour]
    subjects_of = {c: [s for s in subjects if plan.get((c, s), 0) > 0] for c in classes}
    return Model(cfg=cfg, classes=classes, subjects=subjects, plan=plan,
                 teacher_of=teacher_of, p1_teacher=p1_teacher,
                 study_supervisor=study_supervisor, teachers=teachers,
                 study_hour_classes=study_hour_classes, subjects_of=subjects_of)


def _read_plan(ws, cfg):
    rows = list(ws.iter_rows(values_only=True))
    hdr = rows[1]
    plan_classes = [str(c).strip() for c in hdr[1:] if c is not None]
    plan, subjects = {}, []
    for r in rows[2:]:
        subj = r[0]
        if not subj or "total" in str(subj).strip().lower():
            continue
        subj = str(subj).strip()
        subjects.append(subj)
        for j, cl in enumerate(hdr[1:], start=1):
            if cl is None:
                continue
            v = r[j]
            plan[(str(cl).strip(), subj)] = int(v) if v not in (None, "") else 0
    classes = [c for c in cfg.class_order if c in plan_classes]
    return classes, subjects, plan


# =====================================================================
#  NRHS loader  (allotment = class rows x subject cols; P1 = label rows)
# =====================================================================
_NRHS_ALLOT_SUBJ = {"TELUGU": "Telugu", "HINDI": "Hindi", "ENGLISH": "English", "MATHS": "Maths",
                    "EVS": "EVS", "PHYSICS": "Physics", "CHEMISTRY": "Chemistry",
                    "BIOLOGY": "Biology", "SOCIAL": "Social", "COMPUTER": "Computer", "G.K": "G.K"}
_NRHS_ALLOT_CLASS = {"L.K.G": "LKG", "U.K.G(A)": "UKG(A)", "U.K.G(B)": "UKG(B)",
                     "Class 1(A)": "Class 1(A)", "Class 1(B)": "CLASS 1(B)"}
_NRHS_P1_NAME = {"shekina": "SHEKINA", "bijili": "BIJILI", "maha lakshmi": "MAHA LAKSHMI",
                 "chandrakala": "CHANDRAKALA", "surya devi": "SURYA DEVI", "satyaveni": "P.SATYAVENI",
                 "navya": "N.NAVYA", "sai keerthi": "SAI KEERTHI", "gayatri": "S.GAYATHRI",
                 "kamala devi": "R.KAMALA", "chandini": "CHANDINI", "eswari": "K.ESWAR",
                 "lalitha": "M.LALITHA", "sumani": "D.SUMANI"}
_NRHS_P1_CLASS = {"L.K.G": "LKG", "U.K.G 1": "UKG(A)", "U.K.G 2": "UKG(B)", "1(A)": "Class 1(A)",
                  "1(B)": "CLASS 1(B)", "2": "Class 2", "3": "Class 3", "4": "Class 4",
                  "5": "Class 5", "6": "Class 6", "7": "Class 7", "8": "Class 8",
                  "9": "Class 9", "10": "Class 10"}


def _p1key(key):
    if key in (None, ""):
        return None
    if isinstance(key, float) and key.is_integer():
        key = int(key)
    return str(key).strip()


def load_nrhs(path, cfg):
    wb = openpyxl.load_workbook(path, data_only=True)
    classes, subjects, plan = _read_plan(wb["Weekly Period Plan"], cfg)

    ta = list(wb["Teacher Allotment"].iter_rows(values_only=True))
    subj_cols = ta[0][1:]
    teacher_of = {}
    for r in ta[1:]:
        lbl = r[0]
        if not lbl:
            continue
        cl = _NRHS_ALLOT_CLASS.get(lbl, lbl)
        for k, sc in enumerate(subj_cols, start=1):
            if not sc:
                continue
            subj = _NRHS_ALLOT_SUBJ.get(sc, sc)
            t = r[k]
            if t not in (None, ""):
                teacher_of[(cl, subj)] = cfg.canon_teacher(t)

    p1rows = list(wb["Period 1 teacher allotment"].iter_rows(values_only=True))
    hdr = p1rows[0][1:]
    p1_teacher, study_supervisor = {}, {}
    for row in p1rows[1:]:
        label = str(row[0]).strip().lower() if row[0] else ""
        target = p1_teacher if label.startswith("period 1") else (
            study_supervisor if label.startswith("study") else None)
        if target is None:
            continue
        for key, name in zip(hdr, row[1:]):
            cl = _NRHS_P1_CLASS.get(_p1key(key))
            if cl is None or name in (None, ""):
                continue
            target[cl] = cfg.canon_teacher(_NRHS_P1_NAME.get(_norm(name), str(name).strip()))
    return _finalise(cfg, classes, subjects, plan, teacher_of, p1_teacher, study_supervisor)


# =====================================================================
#  NRCS loader  (allotment = subject rows x class cols; P1 = Day/Period rows)
# =====================================================================
_NRCS_ALLOT_SUBJ = {"Telugu": "Telugu", "Hindi": "Hindi", "English": "English",
                    "Eng Gram": "Eng Gram", "Maths": "Maths", "EVS": "EVS",
                    "Phy/Che": "Physics", "Chemisty": "Chemisty", "Biology": "Biology",
                    "Social": "Social", "G.K": "G.K", "Computer": "Computer",
                    "P.E.T": "P.E.T", "Karate": "Karate", "Oral": "Oral"}


def load_nrcs(path, cfg):
    wb = openpyxl.load_workbook(path, data_only=True)
    classes, subjects, plan = _read_plan(wb["Weekly Period Plan"], cfg)

    ta = list(wb["Teacher Allotment"].iter_rows(values_only=True))
    class_cols = [str(c).strip() if c else None for c in ta[0][1:]]
    teacher_of = {}
    for r in ta[1:]:
        subj_lbl = r[0]
        if not subj_lbl:
            continue
        subj = _NRCS_ALLOT_SUBJ.get(str(subj_lbl).strip(), str(subj_lbl).strip())
        for k, cl in enumerate(class_cols, start=1):
            if not cl:
                continue
            t = r[k]
            if t not in (None, ""):
                teacher_of[(cl, subj)] = cfg.canon_teacher(t)

    # Period-1 sheet: Day | Period | <class cols>; rows '1' and 'Study Hour'
    p1rows = list(wb["Period 1 teacher allotment"].iter_rows(values_only=True))
    class_hdr = [str(c).strip() if c else None for c in p1rows[0][2:]]
    p1_teacher, study_supervisor = {}, {}
    for row in p1rows[1:]:
        period = row[1]
        plabel = str(period).strip().lower() if period is not None else ""
        target = (p1_teacher if plabel in ("1", "1.0") else
                  (study_supervisor if plabel.startswith("study") else None))
        if target is None:
            continue
        for cl, name in zip(class_hdr, row[2:]):
            if cl is None or name in (None, ""):
                continue
            target[cl] = cfg.canon_teacher(name)
    return _finalise(cfg, classes, subjects, plan, teacher_of, p1_teacher, study_supervisor)


# =====================================================================
#  public entry point
# =====================================================================
def load_model(path, school="NRHS"):
    cfg = SCHOOLS[school]
    return (load_nrcs if school == "NRCS" else load_nrhs)(path, cfg)
