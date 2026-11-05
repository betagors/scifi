"""
scifi.latex — Multi-File LaTeX Project Resolver, Compilation, Tables, and Venue Compliance.
"""

from scifi.latex.compiler import check_engine, compile_latex, parse_log
from scifi.latex.project import LatexProject, TexSourceFile, find_main_tex, resolve_latex_project
from scifi.latex.tables import generate_latex_table
from scifi.latex.venue import check_venue_compliance

__all__ = [
    "LatexProject",
    "TexSourceFile",
    "check_engine",
    "check_venue_compliance",
    "compile_latex",
    "find_main_tex",
    "generate_latex_table",
    "parse_log",
    "resolve_latex_project",
]
