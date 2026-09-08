"""Excel findings and evidence workbook for an auditor or funder."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .engine import ASKED, Engine, Result

SHEETS = ("Summary", "Profile", "Gaps", "Action Plan", "Evidence Log")

PROFILE_HEADERS = (
    "Function", "Category", "Subcategory", "Outcome", "Status", "Current (0-3)",
    "Target (0-3)", "Gap", "Target basis", "Questions", "Not applicable because",
)
GAP_HEADERS = (
    "Subcategory", "Function", "Outcome", "Current", "Target", "Gap", "Likelihood (1-5)",
    "Impact (1-5)", "Risk (1-25)", "Rating", "Unanswered questions",
)
ACTION_HEADERS = (
    "Rank", "Horizon", "Subcategory", "What to do (CSF implementation example)", "Also consider",
    "Quick-Start Guide action", "Cost band", "Risk now", "Risk reduced", "Reduction per cost unit",
    "Example IDs", "Owner", "Status",
)
EVIDENCE_HEADERS = (
    "Question", "Section", "Question text", "Answer", "Score (0-3)", "Subcategories",
    "Evidence offered", "Auditor: evidence seen?", "Auditor notes",
)

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
RATING_FILLS = {
    "Low": PatternFill("solid", fgColor="C6EFCE"),
    "Medium": PatternFill("solid", fgColor="FFEB9C"),
    "High": PatternFill("solid", fgColor="F8CBAD"),
    "Critical": PatternFill("solid", fgColor="FF7C80"),
}
WRAP = Alignment(wrap_text=True, vertical="top")


def _sheet(wb: Workbook, title: str, headers, widths) -> object:
    ws = wb.create_sheet(title)
    ws.append(list(headers))
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
        cell = ws.cell(row=1, column=i)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = WRAP
    ws.freeze_panes = "A2"
    return ws


def _finish(ws, rating_col: int | None = None) -> None:
    if ws.max_row > 1:
        ws.auto_filter.ref = ws.dimensions
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = WRAP
        if rating_col:
            fill = RATING_FILLS.get(row[rating_col - 1].value)
            if fill:
                row[rating_col - 1].fill = fill


def build_workbook(
    engine: Engine,
    result: Result,
    answers: Mapping[str, str],
    evidence: Mapping[str, str] | None = None,
    organisation: str = "Organisation",
) -> Workbook:
    evidence = evidence or {}
    wb = Workbook()
    wb.remove(wb.active)
    cat = engine.catalog
    t = result.totals

    ws = wb.create_sheet("Summary")
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 70
    rows = [
        ("Organisation", organisation),
        ("Framework", f"{cat.document} {cat.version} (CPRT export, SHA-256 {cat.sha256[:16]}...)"),
        ("Targets", engine.targets.source),
        ("Assessment complete", "Yes" if result.complete else "No: some questions are unanswered"),
        ("Profile flags set", ", ".join(f for f, v in result.profile.items() if v) or "none"),
        ("Questions asked", f"{t['questions_asked']} of {t['questions_in_bank']}"),
        ("Skipped as irrelevant to this profile", t["skipped_profile"]),
        ("Follow-ups skipped after a 'no'", t["skipped_follow_up"]),
        ("Subcategories assessed", t["subcategories_assessed"]),
        ("Subcategories not applicable", t["subcategories_excluded"]),
        ("Subcategories at or above target", t["subcategories_at_target"]),
        ("Actions in plan", len(result.actions)),
        ("Note", "Self-assessment against NIST CSF 2.0 outcomes. It is not a certification "
                 "and no systems were scanned; the auditor columns on the Evidence Log are for "
                 "recording what was actually seen."),
    ]
    for label, value in rows:
        ws.append([label, value])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
        ws.cell(row=ws.max_row, column=2).alignment = WRAP

    ws = _sheet(wb, "Profile", PROFILE_HEADERS, (10, 26, 13, 60, 12, 10, 10, 8, 36, 30, 50))
    for r in result.subcategories:
        assessed = r.status == "assessed"
        ws.append([
            cat.functions[r.function].title, r.category, r.id, r.outcome,
            "Assessed" if assessed else "Not applicable",
            r.current if assessed else None, r.target if assessed else None,
            r.gap if assessed else None, r.target_reason, ", ".join(r.questions), r.reason,
        ])
    _finish(ws)

    ws = _sheet(wb, "Gaps", GAP_HEADERS, (13, 10, 60, 9, 8, 8, 12, 12, 11, 10, 28))
    gaps = sorted(
        (r for r in result.subcategories if r.status == "assessed" and r.gap > 0),
        key=lambda r: (-r.risk, r.id),
    )
    for r in gaps:
        ws.append([
            r.id, r.function, r.outcome, r.current, r.target, r.gap, r.likelihood,
            r.impact, r.risk, r.rating, ", ".join(r.unanswered),
        ])
    _finish(ws, rating_col=10)

    ws = _sheet(wb, "Action Plan", ACTION_HEADERS, (6, 9, 13, 60, 60, 45, 24, 9, 10, 12, 22, 16, 14))
    for a in result.actions:
        ws.append([
            a.rank, a.horizon, a.subcategory, a.what_to_do, "\n".join(a.also_consider),
            "\n".join(a.quick_start), a.cost_label, a.risk, a.risk_reduction, a.priority,
            ", ".join(a.example_ids), None, "Open",
        ])
    status_dv = DataValidation(type="list", formula1='"Open,In progress,Done,Accepted risk"')
    ws.add_data_validation(status_dv)
    if result.actions:
        status_dv.add(f"M2:M{ws.max_row}")
    _finish(ws)

    ws = _sheet(wb, "Evidence Log", EVIDENCE_HEADERS, (20, 10, 60, 34, 10, 22, 45, 14, 40))
    for q in engine.bank.questions:
        if result.question_status[q.id] != ASKED:
            continue
        value = answers.get(q.id)
        opt = q.option(value) if value is not None else None
        ws.append([
            q.id, q.section, q.text, opt.label if opt else "(unanswered)",
            opt.score if opt else None, ", ".join(q.maps), evidence.get(q.id, ""), None, None,
        ])
    seen_dv = DataValidation(type="list", formula1='"Yes,Partly,No"')
    ws.add_data_validation(seen_dv)
    if ws.max_row > 1:
        seen_dv.add(f"H2:H{ws.max_row}")
    _finish(ws)
    return wb


def export_workbook(path: Path, *args, **kwargs) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    build_workbook(*args, **kwargs).save(path)
    return path
