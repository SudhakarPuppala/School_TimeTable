"""Data model: load NRHS_Information.xlsx into a structured, solver-ready form.

Three input sheets are read:
  * "Teacher Allotment"          -> which teacher teaches each (subject, class)
  * "Weekly Period Plan"         -> #periods/week for each (subject, class)
  * "Period 1 teacher allotment" -> class teacher (P1 + Study-Hour supervisor)

Subjects with no teacher in the allotment are handled by rules (see RULES below):
  * ORAL, G.K -> taught by that class's own class teacher
  * P.E.T, Karate -> parallel activities with a generic instructor
"""
from __future__ import annotations
from dataclasses import dataclass, field
import re
import openpyxl

DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT"]
N_DAYS = len(DAYS)
PERIODS = [1, 2, 3, 4, 5, 6, 7, 8]        # P8 = Study Hour (or teachable for 8/9/10)
STUDY_PERIOD = 8

# ---- canonical class order (Class-TT column order C..P) ----
CLASS_ORDER = ["LKG", "UKG(A)", "UKG(B)", "Class 1(A)", "CLASS 1(B)", "Class 2",
               "Class 3", "Class 4", "Class 5", "Class 6", "Class 7",
               "Class 8", "Class 9", "Class 10"]

CLASS_DISPLAY = {
    "LKG": "LKG", "UKG(A)": "UKG (A)", "UKG(B)": "UKG (B)",
    "Class 1(A)": "Class 1(A)", "CLASS 1(B)": "Class 1(B)", "Class 2": "Class 2",
    "Class 3": "Class 3", "Class 4": "Class 4", "Class 5": "Class 5",
    "Class 6": "Class 6", "Class 7": "Class 7", "Class 8": "Class 8",
    "Class 9": "Class 9", "Class 10": "Class 10",
}

# classes that have NO Study Hour (P8 is a normal teachable slot) -- Rule 11
NO_STUDY_HOUR = {"Class 8", "Class 9", "Class 10"}

# ---- subject abbreviations shown in cells ----
SUBJ_ABBR = {
    "Telugu": "TEL", "Hindi": "HIN", "English": "ENG", "Maths": "MATH", "EVS": "EVS",
    "Physics": "PHY", "Chemistry": "CHEM", "Biology": "BIO", "Social": "SOC",
    "Computer": "COMP", "P.E.T": "P.E.T", "G.K": "G.K", "ORAL": "ORAL", "Karate": "KAR",
}

# ---- parallel activities: generic instructor, exempt from teacher double-booking ----
PARALLEL_SUBJECTS = {"P.E.T", "Karate"}
GENERIC_TEACHER = {"P.E.T": "P.E.T Instructor", "Karate": "Karate Instructor"}

# subjects that have no allotment column but are taught by the class teacher
CLASS_TEACHER_SUBJECTS = {"ORAL", "G.K"}

# ---- period-window rules (which periods a teacher may teach in) -------------
#   Rule 5  : Suneetha, Riya, Gowtham -> afternoon only (P5-P8)
#   Rule 9  : Gowtham -> leisure in P5  => Gowtham window is P6-P8
#   Rule 6  : Chalapathi (Bio) -> P1-P3 only
TEACHER_WINDOWS = {
    "RIYA": {5, 6, 7, 8},
    "SUNITHA": {5, 6, 7, 8},
    "D.GOWTHAM": {6, 7, 8},          # afternoon, no P5 (leisure)
    "CHALAPATHI": {1, 2, 3},
}
DEFAULT_WINDOW = {1, 2, 3, 4, 5, 6, 7}   # ordinary teachers: teachable P1-P7

# ---- subject-window rules --------------------------------------------------
SUBJECT_WINDOWS = {"P.E.T": {6, 7}}      # Rule 10: P.E.T only in P6 & P7

# ---- fixed placements ------------------------------------------------------
#   Rule 8 : Karate on Thursday P7 for Classes 1-8
KARATE_DAY = "THU"
KARATE_PERIOD = 7
KARATE_CLASSES = {"Class 1(A)", "CLASS 1(B)", "Class 2", "Class 3", "Class 4",
                  "Class 5", "Class 6", "Class 7", "Class 8"}

# ---- name normalisation: "Period 1 teacher allotment" -> allotment names ----
_P1_NAME_MAP = {
    "shekina": "SHEKINA", "bijili": "BIJILI", "maha lakshmi": "MAHA LAKSHMI",
    "chandrakala": "CHANDRAKALA", "surya devi": "SURYA DEVI", "satyaveni": "P.SATYAVENI",
    "navya": "N.NAVYA", "sai keerthi": "SAI KEERTHI", "gayatri": "S.GAYATHRI",
    "kamala devi": "R.KAMALA", "chandini": "CHANDINI", "eswari": "K.ESWAR",
    "lalitha": "M.LALITHA", "sumani": "D.SUMANI",
}
_P1_CLASS_MAP = {
    "L.K.G": "LKG", "U.K.G 1": "UKG(A)", "U.K.G 2": "UKG(B)", "1(A)": "Class 1(A)",
    "1(B)": "CLASS 1(B)", 2: "Class 2", 3: "Class 3", 4: "Class 4", 5: "Class 5",
    6: "Class 6", 7: "Class 7", 8: "Class 8", 9: "Class 9", 10: "Class 10",
}

# allotment header -> plan subject
_ALLOT_SUBJ = {
    "TELUGU": "Telugu", "HINDI": "Hindi", "ENGLISH": "English", "MATHS": "Maths",
    "EVS": "EVS", "PHYSICS": "Physics", "CHEMISTRY": "Chemistry", "BIOLOGY": "Biology",
    "SOCIAL": "Social", "COMPUTER": "Computer",
}
# allotment class label -> canonical
_ALLOT_CLASS = {
    "L.K.G": "LKG", "U.K.G(A)": "UKG(A)", "U.K.G(B)": "UKG(B)", "Class 1(A)": "Class 1(A)",
    "Class 1(B)": "CLASS 1(B)", "Class 2": "Class 2", "Class 3": "Class 3",
    "Class 4": "Class 4", "Class 5": "Class 5", "Class 6": "Class 6", "Class 7": "Class 7",
    "Class 8": "Class 8", "Class 9": "Class 9", "Class 10": "Class 10",
}


def _norm(s):
    return re.sub(r"\s+", " ", str(s).strip()).lower()


@dataclass
class Model:
    classes: list                         # canonical class keys, ordered
    subjects: list                        # subject names
    plan: dict                            # (class, subject) -> periods/week
    teacher_of: dict                      # (class, subject) -> teacher (incl. generic)
    class_teacher: dict                   # class -> class teacher (P1 / study-hour)
    teachers: list                        # all real (non-generic) teachers
    study_hour_classes: list              # classes with a study hour
    # convenience
    subjects_of: dict = field(default_factory=dict)   # class -> [subjects with n>0]

    def teacher_window(self, teacher):
        return TEACHER_WINDOWS.get(teacher, DEFAULT_WINDOW)

    def teachable_periods(self, cls):
        return [1, 2, 3, 4, 5, 6, 7, 8] if cls in NO_STUDY_HOUR else [1, 2, 3, 4, 5, 6, 7]


def load_model(path: str) -> Model:
    wb = openpyxl.load_workbook(path, data_only=True)

    # ---- Weekly Period Plan ----
    wp = list(wb["Weekly Period Plan"].iter_rows(values_only=True))
    hdr = wp[1]
    plan_classes = [c for c in hdr[1:] if c is not None]
    plan, subjects = {}, []
    for r in wp[2:]:
        subj = r[0]
        if not subj:
            continue
        subjects.append(subj)
        for j, cl in enumerate(hdr[1:], start=1):
            if cl is None:
                continue
            v = r[j]
            plan[(cl, subj)] = int(v) if v not in (None, "") else 0

    classes = [c for c in CLASS_ORDER if c in plan_classes]

    # ---- Teacher Allotment ----
    ta = list(wb["Teacher Allotment"].iter_rows(values_only=True))
    subj_cols = ta[0][1:]
    teacher_of = {}
    for r in ta[1:]:
        lbl = r[0]
        if not lbl:
            continue
        cl = _ALLOT_CLASS.get(lbl, lbl)
        for k, sc in enumerate(subj_cols, start=1):
            if not sc:
                continue
            subj = _ALLOT_SUBJ.get(sc, sc)
            t = r[k]
            if t not in (None, ""):
                teacher_of[(cl, subj)] = str(t).strip()

    # ---- Period 1 teacher allotment (class teacher) ----
    p1 = list(wb["Period 1 teacher allotment"].iter_rows(values_only=True))
    class_teacher = {}
    for key, name in zip(p1[0][1:], p1[1][1:]):
        cl = _P1_CLASS_MAP.get(key)
        if cl is None or name in (None, ""):
            continue
        class_teacher[cl] = _P1_NAME_MAP.get(_norm(name), str(name).strip())

    # ---- fill in rule-based teachers for subjects lacking allotment ----
    for cl in classes:
        for subj in subjects:
            if plan.get((cl, subj), 0) == 0:
                continue
            if (cl, subj) in teacher_of:
                continue
            if subj in GENERIC_TEACHER:
                teacher_of[(cl, subj)] = GENERIC_TEACHER[subj]
            elif subj in CLASS_TEACHER_SUBJECTS:
                teacher_of[(cl, subj)] = class_teacher.get(cl, f"{cl} teacher")

    teachers = sorted({t for t in teacher_of.values() if t not in GENERIC_TEACHER.values()})
    study_hour_classes = [c for c in classes if c not in NO_STUDY_HOUR]

    subjects_of = {c: [s for s in subjects if plan.get((c, s), 0) > 0] for c in classes}

    return Model(classes=classes, subjects=subjects, plan=plan, teacher_of=teacher_of,
                 class_teacher=class_teacher, teachers=teachers,
                 study_hour_classes=study_hour_classes, subjects_of=subjects_of)
