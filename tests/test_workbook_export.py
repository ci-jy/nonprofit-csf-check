import json
import subprocess
import sys

import pytest
from openpyxl import load_workbook

from csfcheck.workbook import ACTION_HEADERS, EVIDENCE_HEADERS, GAP_HEADERS, PROFILE_HEADERS, SHEETS

from .conftest import ROOT, SAMPLES


@pytest.mark.parametrize("path", SAMPLES, ids=[p.stem for p in SAMPLES])
def test_cli_export_writes_verified_sheets(tmp_path, engine, path):
    out = tmp_path / f"{path.stem}.xlsx"
    proc = subprocess.run(
        [sys.executable, "-m", "csfcheck", "export", str(path), "-o", str(out)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    sample = json.loads(path.read_text())
    result = engine.assess(sample["organisation"]["profile"], sample["answers"])

    wb = load_workbook(out)
    assert wb.sheetnames == list(SHEETS)
    headers = lambda ws: [c.value for c in ws[1]]  # noqa: E731
    assert headers(wb["Profile"]) == list(PROFILE_HEADERS)
    assert headers(wb["Gaps"]) == list(GAP_HEADERS)
    assert headers(wb["Action Plan"]) == list(ACTION_HEADERS)
    assert headers(wb["Evidence Log"]) == list(EVIDENCE_HEADERS)

    profile_rows = list(wb["Profile"].iter_rows(min_row=2, values_only=True))
    assert len(profile_rows) == 106
    statuses = {r[2]: r[4] for r in profile_rows}
    assert sum(s == "Not applicable" for s in statuses.values()) == result.totals["subcategories_excluded"]

    gaps = list(wb["Gaps"].iter_rows(min_row=2, values_only=True))
    assert len(gaps) == 106 - result.totals["subcategories_excluded"] - result.totals["subcategories_at_target"]
    risks = [g[8] for g in gaps]
    assert risks == sorted(risks, reverse=True)

    plan = list(wb["Action Plan"].iter_rows(min_row=2, values_only=True))
    assert [p[0] for p in plan] == list(range(1, len(result.actions) + 1))
    assert {p[2] for p in plan} == {g[0] for g in gaps}  # one action per gap

    log = list(wb["Evidence Log"].iter_rows(min_row=2, values_only=True))
    assert {r[0] for r in log} == set(sample["answers"])
    assert all(r[3] != "(unanswered)" for r in log)
