"""Reusable school-timetable generator (NRHS / NRCS).

Pipeline: load raw workbook -> build CP-SAT model -> solve -> write styled Excel
(Class Time Table + Teacher Time Table) -> verify.
"""
