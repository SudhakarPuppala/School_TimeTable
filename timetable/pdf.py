"""Render the timetable to a print-ready PDF (all classes + all teachers),
each grid under its own header. Uses ReportLab (no system dependencies)."""
from __future__ import annotations

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                Spacer, PageBreak, KeepTogether)

from .model import DAYS

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
NAVY = colors.HexColor("#2A4D69")
PERIOD_BG = colors.HexColor("#E7EFF6")
EMPTY_BG = colors.HexColor("#F4F4F2")

_H = ParagraphStyle("hdr", fontName="Helvetica-Bold", fontSize=13,
                    textColor=colors.white, leading=16)
_SEC = ParagraphStyle("sec", fontName="Helvetica-Bold", fontSize=15,
                      textColor=NAVY, spaceAfter=6, spaceBefore=6)


def _class_grid(m, solution, c):
    cfg = m.cfg
    g = [["—"] * 6 for _ in range(8)]
    for d in range(6):
        for p in range(1, 9):
            if (c, d, p) in solution:
                s, t = solution[(c, d, p)]
                g[p - 1][d] = (cfg.subj_abbr.get(s, s), t.replace(" Instructor", ""))
            elif p == 8 and c in m.study_hour_classes and m.has_p8(DAYS[d]):
                g[p - 1][d] = ("STUDY", m.study_supervisor.get(c, ""))
    return g


def _teacher_grid(m, solution, teacher):
    cfg = m.cfg
    g = [["—"] * 6 for _ in range(8)]
    for (c, d, p), (s, t) in solution.items():
        if t == teacher:
            g[p - 1][d] = (cfg.subj_abbr.get(s, s), cfg.class_display.get(c, c))
    for c in m.study_hour_classes:
        if m.study_supervisor.get(c) == teacher:
            for d in range(6):
                if m.has_p8(DAYS[d]):
                    g[7][d] = ("STUDY", cfg.class_display.get(c, c))
    return g


def _cell_para(top, bot, fg):
    style = ParagraphStyle("c", fontName="Helvetica-Bold", fontSize=7,
                           alignment=1, leading=8, textColor=colors.HexColor(fg))
    return Paragraph(f"{top}<br/><font size=6 face='Helvetica'>{bot}</font>", style)


def _grid_block(title, grid):
    header = Table([[Paragraph(title, _H)]], colWidths=[259 * mm], rowHeights=[9 * mm])
    header.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY),
                                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))

    data = [[""] + DAYS]
    for p in range(8):
        row = [PLABEL[p]]
        for d in range(6):
            raw = grid[p][d]
            row.append("" if raw == "—" else _cell_para(raw[0], raw[1], SUBJ_COLOR.get(raw[0], ("#F1EFE8", "#2C2C2A"))[1]))
        data.append(row)

    tbl = Table(data, colWidths=[19 * mm] + [40 * mm] * 6, rowHeights=[8 * mm] + [13 * mm] * 8)
    ts = [("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("ALIGN", (0, 0), (-1, -1), "CENTER"),
          ("BACKGROUND", (0, 0), (-1, 0), NAVY),
          ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
          ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
          ("FONTSIZE", (0, 0), (-1, 0), 9),
          ("BACKGROUND", (0, 1), (0, -1), PERIOD_BG),
          ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
          ("FONTSIZE", (0, 1), (0, -1), 8)]
    for p in range(8):
        for d in range(6):
            raw = grid[p][d]
            bg = EMPTY_BG if raw == "—" else colors.HexColor(SUBJ_COLOR.get(raw[0], ("#F1EFE8", "#2C2C2A"))[0])
            ts.append(("BACKGROUND", (d + 1, p + 1), (d + 1, p + 1), bg))
    tbl.setStyle(TableStyle(ts))
    return KeepTogether([header, Spacer(1, 2 * mm), tbl, Spacer(1, 6 * mm)])


def write_pdf(path, m, solution, school=None):
    cfg = m.cfg
    school = school or cfg.name
    doc = SimpleDocTemplate(path, pagesize=landscape(A4),
                            leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=10 * mm, bottomMargin=10 * mm,
                            title=f"{school} Timetable")
    story = [Paragraph(f"{school} — Class Timetables", _SEC), Spacer(1, 3 * mm)]
    for c in m.classes:
        story.append(_grid_block(f"Class:  {cfg.class_display.get(c, c)}", _class_grid(m, solution, c)))

    story.append(PageBreak())
    story.append(Paragraph(f"{school} — Teacher Timetables", _SEC))
    story.append(Spacer(1, 3 * mm))
    teachers = sorted(m.teachers) + sorted(
        g for g in cfg.generic_teacher.values() if any(t == g for _, t in solution.values()))
    for who in teachers:
        story.append(_grid_block(f"Teacher:  {who}", _teacher_grid(m, solution, who)))

    doc.build(story)
    return path
