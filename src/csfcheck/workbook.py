"""Excel findings and evidence workbook for an auditor or funder."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .compare import COMPLETED, STILL_OPEN, Comparison
from .engine import ASKED, Engine, Result
from .rollup import by_function

SHEETS = ("Summary", "Profile", "Gaps", "Action Plan", "Evidence Log", "Progress")

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

PROGRESS_FUNCTION_HEADERS = ("Function", "Target reached before", "Target reached now", "Change",
                             "At target before", "At target now")
PROGRESS_SUBCATEGORY_HEADERS = ("Subcategory", "Outcome", "Change", "Current before", "Current now", "Target",
                                "Risk before", "Risk now")
PROGRESS_ACTION_HEADERS = ("Subcategory", "Action", "Status", "Rank before", "Rank now", "Gap before", "Gap now",
                           "Cost band")
PROGRESS_ANSWER_HEADERS = ("Question", "Question text", "Answer before", "Answer now", "Section")

CHANGE_FILLS = {
    "improved": PatternFill("solid", fgColor="C6EFCE"),
    "completed": PatternFill("solid", fgColor="C6EFCE"),
    "progressed": PatternFill("solid", fgColor="E2EFDA"),
    "regressed": PatternFill("solid", fgColor="F8CBAD"),
    "new": PatternFill("solid", fgColor="FFEB9C"),
}
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


@dataclass(frozen=True)
class Progress:
    """A comparison with an earlier version, and how to name the two versions."""

    comparison: Comparison
    before: str = "the earlier assessment"
    after: str = "this assessment"


def _header_row(ws, headers) -> None:
    ws.append(list(headers))
    for i in range(1, len(headers) + 1):
        cell = ws.cell(row=ws.max_row, column=i)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = WRAP


def _title_row(ws, text: str) -> None:
    ws.append([])
    ws.append([text])
    ws.cell(row=ws.max_row, column=1).font = Font(bold=True, size=12)


def _pct(x: float | None):
    return None if x is None else round(100 * x)


def _progress_sheet(wb: Workbook, engine: Engine, result: Result, organisation: str,
                    progress: Progress | None) -> None:
    ws = wb.create_sheet("Progress")
    # Every table puts its long text in column B, so B is the wide one.
    for col, width in zip("ABCDEFGH", (26, 62, 18, 18, 16, 12, 12, 12)):
        ws.column_dimensions[col].width = width
    if progress is None:
        ws.append(["Progress", f"This is the first assessment of {organisation}, so there is nothing to compare "
                               "with yet. Retake it after some of the actions are done and this sheet will list "
                               "what improved, what went backwards and which actions were completed."])
        ws.cell(row=1, column=1).font = Font(bold=True)
        ws.cell(row=1, column=2).alignment = WRAP
        _title_row(ws, "Baseline by function (share of target reached, %)")
        _header_row(ws, PROGRESS_FUNCTION_HEADERS)
        for f in by_function(engine.catalog, result):
            ws.append([f.title.capitalize(), None, _pct(f.attainment), None, None, f.at_target])
        return

    c, t = progress.comparison, progress.comparison.totals
    rows = [
        ("Compared", f"{progress.after} with {progress.before}"),
        ("Target profile reached", f"{_pct(t['attainment_before'])}% before, {_pct(t['attainment_after'])}% now"),
        ("Subcategories at target", f"{t['at_target_before']} before, {t['at_target_after']} now"),
        ("Subcategories improved", t["improved"]),
        ("Subcategories regressed", t["regressed"]),
        ("Now applicable / no longer applicable", f"{t['now_applicable']} / {t['no_longer_applicable']}"),
        ("Actions completed", f"{t['actions_completed']} of {t['actions_before']}"),
        ("Actions progressed (gap smaller)", t["actions_progressed"]),
        ("Actions still open", t["actions_still_open"]),
        ("New actions", t["actions_new"]),
        ("Total risk", f"{t['risk_before']:g} before, {t['risk_after']:g} now"),
        ("Answers changed", t["answers_changed"]),
        ("Profile changes", ", ".join(f"{k}: {'yes' if v[1] else 'no'} (was {'yes' if v[0] else 'no'})"
                                      for k, v in c.profile_changes.items()) or "none"),
    ]
    for label, value in rows:
        ws.append([label, value])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
        ws.cell(row=ws.max_row, column=2).alignment = Alignment(wrap_text=True, vertical="top", horizontal="left")

    _title_row(ws, "By function (share of target reached, %)")
    _header_row(ws, PROGRESS_FUNCTION_HEADERS)
    for f in c.functions:
        before, after = _pct(f.before), _pct(f.after)
        change = None if before is None or after is None else after - before
        ws.append([f.title.capitalize(), before, after, change, f.at_target_before, f.at_target_after])

    _title_row(ws, "Subcategories that changed")
    _header_row(ws, PROGRESS_SUBCATEGORY_HEADERS)
    for x in c.subcategories:
        if x.change == "unchanged":
            continue
        ws.append([x.id, x.outcome, x.change, x.before, x.after, x.target, x.risk_before, x.risk_after])
        _fill(ws, 3, x.change)

    _title_row(ws, f"Actions from the earlier plan, and new ones ({t['actions_still_open']} still open "
                   "with no change are left out)")
    _header_row(ws, PROGRESS_ACTION_HEADERS)
    order = {COMPLETED: 0, "progressed": 1, "no longer applicable": 2, "new": 3}
    for x in sorted((x for x in c.actions if x.status != STILL_OPEN),
                    key=lambda x: (order[x.status], x.rank_before or 0, x.rank_after or 0)):
        ws.append([x.subcategory, x.what_to_do, x.status, x.rank_before, x.rank_after, x.gap_before, x.gap_after,
                   x.cost_label])
        _fill(ws, 3, x.status)

    _title_row(ws, "Answers that changed")
    _header_row(ws, PROGRESS_ANSWER_HEADERS)
    for x in c.answers:
        ws.append([x.question_id, x.text, x.before or "(not asked)", x.after or "(not asked)", x.section])
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            if cell.alignment is None or not cell.alignment.wrap_text:
                cell.alignment = WRAP


def _fill(ws, col: int, key: str) -> None:
    fill = CHANGE_FILLS.get(key)
    if fill:
        ws.cell(row=ws.max_row, column=col).fill = fill


def build_workbook(
    engine: Engine,
    result: Result,
    answers: Mapping[str, str],
    evidence: Mapping[str, str] | None = None,
    organisation: str = "Organisation",
    progress: Progress | None = None,
) -> Workbook:
    """The auditor's workbook; ``progress`` adds the comparison with an earlier version."""
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

    _progress_sheet(wb, engine, result, organisation, progress)
    return wb


def export_workbook(path: Path, *args, **kwargs) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    build_workbook(*args, **kwargs).save(path)
    return path
