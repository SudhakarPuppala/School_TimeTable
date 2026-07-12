"""Streamlit dashboard for the school timetable generator.

Run:  streamlit run dashboard.py

Edit the three source sheets in the browser, re-solve with OR-Tools, review the
Class & Teacher timetables, inspect validation + teacher load, and download the
styled workbook.
"""
from __future__ import annotations
import io
import os
import tempfile
from collections import defaultdict

import pandas as pd
import openpyxl
import streamlit as st

from timetable.model import (load_model, DAYS, SUBJ_ABBR, CLASS_DISPLAY,
                             GENERIC_TEACHER)
from timetable.solver import solve
from timetable.verify import verify
from timetable.writer import write_workbook

DEFAULT_INPUT = "NRHS/Requirements/NRHS_Information.xlsx"
PLABEL = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "Study Hour"]
SUBJ_COLOR = {
    "TEL": ("#E6F1FB", "#0C447C"), "HIN": ("#EEEDFE", "#3C3489"),
    "ENG": ("#E1F5EE", "#085041"), "MATH": ("#FAEEDA", "#633806"),
    "EVS": ("#EAF3DE", "#27500A"), "PHY": ("#FAECE7", "#712B13"),
    "CHEM": ("#FBEAF0", "#72243E"), "BIO": ("#C0DD97", "#173404"),
    "SOC": ("#F1EFE8", "#2C2C2A"), "COMP": ("#B5D4F4", "#042C53"),
    "P.E.T": ("#FCEBEB", "#791F1F"), "G.K": ("#FAC775", "#412402"),
    "ORAL": ("#F4C0D1", "#4B1528"), "KAR": ("#F5C4B3", "#4A1B0C"),
    "STUDY": ("#D3D1C7", "#2C2C2A"),
}

st.set_page_config(page_title="School Timetable Generator", layout="wide")


# ------------------------------------------------------------------ data I/O
def read_sheets(path):
    """Read the three source sheets into editable DataFrames."""
    plan = pd.read_excel(path, sheet_name="Weekly Period Plan", header=1)
    plan = plan[~plan.iloc[:, 0].astype(str).str.lower().str.contains("total", na=False)]
    allot = pd.read_excel(path, sheet_name="Teacher Allotment", header=0)
    p1raw = pd.read_excel(path, sheet_name="Period 1 teacher allotment", header=0)
    classes = list(p1raw.columns[1:])
    teachers = list(p1raw.iloc[0, 1:])
    p1 = pd.DataFrame({"Class": classes, "Period 1 Teacher": teachers})
    return plan.reset_index(drop=True), allot.reset_index(drop=True), p1


def write_sheets(plan, allot, p1, path):
    """Write edited DataFrames back into the loader's expected layout."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    ws = wb.create_sheet("Teacher Allotment")
    ws.append(list(allot.columns))
    for _, r in allot.iterrows():
        ws.append(["" if pd.isna(v) else v for v in r.tolist()])

    ws = wb.create_sheet("Weekly Period Plan")
    ws.append(["Weekly Period Plan"])                 # title row (loader skips row 0)
    ws.append(list(plan.columns))
    for _, r in plan.iterrows():
        row = [r.iloc[0]] + [int(v) if pd.notna(v) and str(v) != "" else 0
                             for v in r.iloc[1:].tolist()]
        ws.append(row)

    ws = wb.create_sheet("Period 1 teacher allotment")
    ws.append(["Class"] + p1["Class"].tolist())
    ws.append(["Period 1 Teacher"] + p1["Period 1 Teacher"].tolist())

    wb.save(path)
    return path


# ------------------------------------------------------------------ solve
def run_solver(input_path, seconds):
    m = load_model(input_path)
    solution, status, obj = solve(m, max_seconds=seconds)
    errors, warnings = verify(m, solution)
    return m, solution, status, obj, errors, warnings


def class_grid(m, solution, cls):
    g = [["—"] * 6 for _ in range(8)]
    for d in range(6):
        for p in range(1, 9):
            if (cls, d, p) in solution:
                s, t = solution[(cls, d, p)]
                g[p - 1][d] = f"{SUBJ_ABBR.get(s, s)}||{t}"
            elif p == 8 and cls in m.study_hour_classes:
                g[p - 1][d] = f"STUDY||{m.class_teacher.get(cls, '')}"
    return g


def teacher_grid(m, solution, teacher):
    g = [["—"] * 6 for _ in range(8)]
    for (c, d, p), (s, t) in solution.items():
        if t == teacher:
            g[p - 1][d] = f"{SUBJ_ABBR.get(s, s)}||{CLASS_DISPLAY.get(c, c)}"
    for c in m.study_hour_classes:
        if m.class_teacher.get(c) == teacher:
            for d in range(6):
                g[7][d] = f"STUDY||{CLASS_DISPLAY.get(c, c)}"
    return g


def grid_html(g, sub_label=True):
    rows = ["<table style='width:100%;border-collapse:separate;border-spacing:3px;table-layout:fixed'>"]
    rows.append("<tr><th style='width:60px'></th>" +
                "".join(f"<th style='font-size:12px;color:#666;padding:4px'>{d}</th>" for d in DAYS) + "</tr>")
    for p in range(8):
        cells = [f"<td style='font-size:12px;color:#666;text-align:right;padding-right:6px'>{PLABEL[p]}</td>"]
        for d in range(6):
            raw = g[p][d]
            if raw == "—":
                cells.append("<td style='background:#f4f4f2;border-radius:6px;height:44px'></td>")
                continue
            key, other = raw.split("||")
            bg, fg = SUBJ_COLOR.get(key, ("#F1EFE8", "#2C2C2A"))
            top = key if sub_label else other
            bot = other.replace(" Instructor", "") if sub_label else key
            cells.append(
                f"<td style='background:{bg};color:{fg};border-radius:6px;height:44px;"
                f"text-align:center;vertical-align:middle;padding:3px'>"
                f"<div style='font-size:12px;font-weight:600;line-height:1.1'>{top}</div>"
                f"<div style='font-size:10px;opacity:.85;line-height:1.15'>{bot}</div></td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    rows.append("</table>")
    return "".join(rows)


# ------------------------------------------------------------------ UI
st.title("🗓️  School Timetable Generator")
st.caption("Edit the source data, re-solve, review, and download — powered by OR-Tools CP-SAT.")

with st.sidebar:
    st.header("Setup")
    input_path = st.text_input("Information workbook", DEFAULT_INPUT)
    seconds = st.slider("Solver time budget (s)", 15, 240, 90, 15)
    st.divider()
    generate = st.button("⚙️  Generate timetable", type="primary", width="stretch")

if "sheets" not in st.session_state and os.path.exists(input_path):
    st.session_state.sheets = read_sheets(input_path)

tab_data, tab_class, tab_teacher, tab_report = st.tabs(
    ["✏️ Edit data", "📚 Class timetable", "👩‍🏫 Teacher timetable", "✅ Validation & bottlenecks"])

with tab_data:
    if "sheets" in st.session_state:
        plan, allot, p1 = st.session_state.sheets
        st.subheader("Weekly period plan")
        plan_e = st.data_editor(plan, width="stretch", num_rows="dynamic", key="plan_e")
        st.subheader("Teacher allotment")
        allot_e = st.data_editor(allot, width="stretch", num_rows="dynamic", key="allot_e")
        st.subheader("Period 1 teacher (also supervises Study Hour)")
        p1_e = st.data_editor(p1, width="stretch", key="p1_e")
        st.session_state.edited = (plan_e, allot_e, p1_e)
        st.info("Edit any cell, then click **Generate timetable** in the sidebar.")
    else:
        st.warning(f"Workbook not found: {input_path}")

if generate and "edited" in st.session_state:
    with st.spinner("Solving…"):
        tmp = os.path.join(tempfile.gettempdir(), "tt_edit.xlsx")
        write_sheets(*st.session_state.edited, tmp)
        try:
            res = run_solver(tmp, seconds)
            out = os.path.join(tempfile.gettempdir(), "NRHS_Timetable.xlsx")
            write_workbook(out, res[0], res[1])
            st.session_state.result = res
            st.session_state.out = out
            st.success(f"Solved: {res[2]} · objective {res[3]:.0f} · {len(res[4])} errors, {len(res[5])} warnings")
        except Exception as e:
            st.error(f"Solve failed: {e}")

res = st.session_state.get("result")

with tab_class:
    if res:
        m, solution = res[0], res[1]
        cls = st.selectbox("Class", [CLASS_DISPLAY.get(c, c) for c in m.classes])
        key = next(c for c in m.classes if CLASS_DISPLAY.get(c, c) == cls)
        st.markdown(grid_html(class_grid(m, solution, key)), unsafe_allow_html=True)
    else:
        st.info("Click **Generate timetable** to view results.")

with tab_teacher:
    if res:
        m, solution = res[0], res[1]
        teachers = m.teachers + [g for g in GENERIC_TEACHER.values()
                                 if any(t == g for _, t in solution.values())]
        who = st.selectbox("Teacher", sorted(teachers))
        st.markdown(grid_html(teacher_grid(m, solution, who), sub_label=True),
                    unsafe_allow_html=True)
    else:
        st.info("Click **Generate timetable** to view results.")

with tab_report:
    if res:
        m, solution, status, obj, errors, warnings = res
        c1, c2, c3 = st.columns(3)
        c1.metric("Status", status)
        c2.metric("Hard errors", len(errors))
        c3.metric("Leisure warnings", len(warnings))
        if errors:
            st.error("Hard-rule errors:\n\n" + "\n".join(f"- {e}" for e in errors))
        else:
            st.success("No hard-rule violations — all constraints satisfied.")

        load = defaultdict(int)
        for (c, d, p), (s, t) in solution.items():
            load[t] += 1
        for c in m.study_hour_classes:
            t = m.class_teacher.get(c)
            if t:
                load[t] += 6
        ldf = (pd.DataFrame({"Teacher": list(load), "Load / 48": list(load.values())})
               .sort_values("Load / 48", ascending=False).reset_index(drop=True))
        st.subheader("Teacher weekly load")
        st.bar_chart(ldf.set_index("Teacher"))

        if warnings:
            with st.expander(f"Leisure warnings ({len(warnings)})"):
                for w in warnings:
                    st.write("• " + w)

        with open(st.session_state.out, "rb") as f:
            st.download_button("⬇️  Download timetable (.xlsx)", f.read(),
                               file_name="NRHS_Timetable_Final.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               width="stretch")
    else:
        st.info("Click **Generate timetable** to view the report.")
