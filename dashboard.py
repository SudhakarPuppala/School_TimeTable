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

from timetable.model import load_model, DAYS
from timetable.solver import solve
from timetable.verify import verify
from timetable.writer import write_workbook
from timetable.pdf import write_pdf

SCHOOLS = {
    "NRHS": "NRHS/Requirements/NRHS_Information.xlsx",
    "NRCS": "NRCS/Requirements/NRCS_information_New.xlsx",
}
PLABEL = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "Study Hour"]
SUBJ_COLOR = {
    "TEL": ("#E6F1FB", "#0C447C"), "HIN": ("#EEEDFE", "#3C3489"),
    "ENG": ("#E1F5EE", "#085041"), "GRAM": ("#D6EFE6", "#0F6E56"), "MATH": ("#FAEEDA", "#633806"),
    "EVS": ("#EAF3DE", "#27500A"), "PHY": ("#FAECE7", "#712B13"),
    "CHEM": ("#FBEAF0", "#72243E"), "BIO": ("#C0DD97", "#173404"),
    "SOC": ("#F1EFE8", "#2C2C2A"), "COMP": ("#B5D4F4", "#042C53"),
    "P.E.T": ("#FCEBEB", "#791F1F"), "G.K": ("#FAC775", "#412402"),
    "ORAL": ("#F4C0D1", "#4B1528"), "KAR": ("#F5C4B3", "#4A1B0C"),
    "STUDY": ("#D3D1C7", "#2C2C2A"),
}

st.set_page_config(page_title="School Timetable Generator", layout="wide")


# ------------------------------------------------------------------ data I/O
def read_sheets(path, school):
    """Read the three source sheets into editable DataFrames (school-aware)."""
    plan = pd.read_excel(path, sheet_name="Weekly Period Plan", header=1)
    plan = plan[~plan.iloc[:, 0].astype(str).str.lower().str.contains("total", na=False)]
    if school == "NRCS":
        # allotment = subject rows x class cols; P1 = Day/Period rows
        allot = pd.read_excel(path, sheet_name="Teacher Allotment", header=0)
        p1raw = pd.read_excel(path, sheet_name="Period 1 teacher allotment", header=0)
        p1 = p1raw  # keep native Day | Period | <classes> layout
    else:
        allot = pd.read_excel(path, sheet_name="Teacher Allotment", header=0)
        p1raw = pd.read_excel(path, sheet_name="Period 1 teacher allotment", header=0)
        classes = list(p1raw.columns[1:])
        p1row = list(p1raw.iloc[0, 1:])
        shrow = list(p1raw.iloc[1, 1:]) if len(p1raw) > 1 else [""] * len(classes)
        p1 = pd.DataFrame({"Class": classes, "Period 1 Teacher": p1row, "Study Hour": shrow})
    return plan.reset_index(drop=True), allot.reset_index(drop=True), p1.reset_index(drop=True)


def _cell(v):
    return "" if pd.isna(v) else v


def write_sheets(plan, allot, p1, path, school):
    """Write edited DataFrames back into the school's expected layout."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    ws = wb.create_sheet("Weekly Period Plan")
    ws.append(["Weekly Period Plan"])                 # title row (loader skips row 0)
    ws.append(list(plan.columns))
    for _, r in plan.iterrows():
        ws.append([r.iloc[0]] + [int(v) if pd.notna(v) and str(v) != "" else 0
                                 for v in r.iloc[1:].tolist()])

    ws = wb.create_sheet("Teacher Allotment")
    ws.append(list(allot.columns))
    for _, r in allot.iterrows():
        ws.append([_cell(v) for v in r.tolist()])

    ws = wb.create_sheet("Period 1 teacher allotment")
    if school == "NRCS":
        ws.append(list(p1.columns))                   # Day | Period | <classes>
        for _, r in p1.iterrows():
            ws.append([_cell(v) for v in r.tolist()])
    else:
        ws.append(["Class"] + p1["Class"].tolist())
        ws.append(["Period 1 Teacher"] + [_cell(v) for v in p1["Period 1 Teacher"].tolist()])
        if "Study Hour" in p1.columns:
            ws.append(["Study Hour"] + [_cell(v) for v in p1["Study Hour"].tolist()])

    wb.save(path)
    return path


# ------------------------------------------------------------------ solve
def run_solver(input_path, seconds, school="NRHS"):
    m = load_model(input_path, school)
    solution, status, obj, notes, windows = solve(m, max_seconds=seconds)
    errors, warnings = verify(m, solution, windows)
    return m, solution, status, obj, errors, warnings + notes


def class_grid(m, solution, cls):
    cfg = m.cfg
    g = [["—"] * 6 for _ in range(8)]
    for d in range(6):
        for p in range(1, 9):
            if (cls, d, p) in solution:
                s, t = solution[(cls, d, p)]
                g[p - 1][d] = f"{cfg.subj_abbr.get(s, s)}||{t}"
            elif p == 8 and cls in m.study_hour_classes and m.has_p8(DAYS[d]):
                g[p - 1][d] = f"STUDY||{m.study_supervisor.get(cls, '')}"
    return g


def teacher_grid(m, solution, teacher):
    cfg = m.cfg
    g = [["—"] * 6 for _ in range(8)]
    for (c, d, p), (s, t) in solution.items():
        if t == teacher:
            g[p - 1][d] = f"{cfg.subj_abbr.get(s, s)}||{cfg.class_display.get(c, c)}"
    for c in m.study_hour_classes:
        if m.study_supervisor.get(c) == teacher:
            for d in range(6):
                if m.has_p8(DAYS[d]):
                    g[7][d] = f"STUDY||{cfg.class_display.get(c, c)}"
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
    school = st.selectbox("School", list(SCHOOLS.keys()))
    input_path = st.text_input("Information workbook", SCHOOLS[school])
    seconds = st.slider("Solver time budget (s)", 15, 240, 90, 15)
    st.divider()
    generate = st.button("⚙️  Generate timetable", type="primary", width="stretch")
    save_src = st.button("💾  Save edits to source workbook", width="stretch")
    st.caption("Generate = solve on your edits (in memory). Save = write edits back "
               "to the workbook so they persist.")

# reload source sheets when the school changes (or on first load)
if st.session_state.get("school") != school:
    st.session_state.school = school
    st.session_state.pop("sheets", None)
    st.session_state.pop("result", None)
if "sheets" not in st.session_state and os.path.exists(input_path):
    st.session_state.sheets = read_sheets(input_path, school)

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

# Save handler runs AFTER the editors so it always uses the freshest edits.
if save_src and "edited" in st.session_state:
    write_sheets(*st.session_state.edited, input_path, school)
    st.session_state.pop("sheets", None)          # re-read from the saved file
    st.sidebar.success(f"Saved edits to {input_path}")

if generate and "edited" in st.session_state:
    with st.spinner("Solving…"):
        tmp = os.path.join(tempfile.gettempdir(), f"tt_edit_{school}.xlsx")
        write_sheets(*st.session_state.edited, tmp, school)
        try:
            res = run_solver(tmp, seconds, school)
            out = os.path.join(tempfile.gettempdir(), f"{school}_Timetable.xlsx")
            write_workbook(out, res[0], res[1])
            pdf_out = os.path.join(tempfile.gettempdir(), f"{school}_Timetable.pdf")
            write_pdf(pdf_out, res[0], res[1])
            st.session_state.result = res
            st.session_state.out = out
            st.session_state.pdf = pdf_out
            st.success(f"Solved: {res[2]} · objective {res[3]:.0f} · {len(res[4])} errors, {len(res[5])} warnings")
        except Exception as e:
            st.error(f"Solve failed: {e}")

res = st.session_state.get("result")

def _section(title, body_html):
    st.markdown(
        f"<div style='background:#2A4D69;color:#fff;font-weight:600;font-size:16px;"
        f"padding:8px 14px;border-radius:8px;margin:18px 0 8px'>{title}</div>",
        unsafe_allow_html=True)
    st.markdown(body_html, unsafe_allow_html=True)

with tab_class:
    if res:
        m, solution = res[0], res[1]
        st.caption(f"{m.cfg.name} — all {len(m.classes)} class timetables")
        for c in m.classes:
            _section(f"📚  {m.cfg.class_display.get(c, c)}",
                     grid_html(class_grid(m, solution, c)))
    else:
        st.info("Click **Generate timetable** to view results.")

with tab_teacher:
    if res:
        m, solution = res[0], res[1]
        teachers = sorted(m.teachers) + sorted(
            g for g in m.cfg.generic_teacher.values() if any(t == g for _, t in solution.values()))
        st.caption(f"{m.cfg.name} — all {len(teachers)} teacher timetables")
        for who in teachers:
            _section(f"👩‍🏫  {who}",
                     grid_html(teacher_grid(m, solution, who), sub_label=True))
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
            t = m.study_supervisor.get(c)
            if t:
                load[t] += 6
        ldf = (pd.DataFrame({"Teacher": list(load), "Load / 48": list(load.values())})
               .sort_values("Load / 48", ascending=False).reset_index(drop=True))
        st.subheader("Teacher weekly load")
        st.bar_chart(ldf.set_index("Teacher"))

        if warnings:
            with st.expander(f"Notes & leisure warnings ({len(warnings)})"):
                for w in warnings:
                    st.write("• " + w)

        dl1, dl2 = st.columns(2)
        with open(st.session_state.out, "rb") as f:
            dl1.download_button("⬇️  Download Excel (.xlsx)", f.read(),
                                file_name=f"{m.cfg.name}_Timetable_Final.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                width="stretch")
        if st.session_state.get("pdf"):
            with open(st.session_state.pdf, "rb") as f:
                dl2.download_button("⬇️  Download PDF (all classes + teachers)", f.read(),
                                    file_name=f"{m.cfg.name}_Timetable.pdf",
                                    mime="application/pdf", width="stretch")
    else:
        st.info("Click **Generate timetable** to view the report.")
