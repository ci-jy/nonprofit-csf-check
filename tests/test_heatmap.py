import xml.etree.ElementTree as ET

import pytest

from csfcheck.heatmap import NOT_APPLICABLE, attainment_colour, render_svg
from csfcheck.rollup import by_category, by_function
from csfcheck.samples import load_answers

from .conftest import SAMPLES

SVG = "{http://www.w3.org/2000/svg}"


def test_colour_ramp_ends():
    assert attainment_colour(None) == NOT_APPLICABLE
    assert attainment_colour(0) == "#f4a6a6"
    assert attainment_colour(0.5) == "#fde68a"
    assert attainment_colour(1) == "#a7e3b5"
    assert attainment_colour(1.7) == attainment_colour(1)


@pytest.mark.parametrize("path", SAMPLES, ids=[p.stem for p in SAMPLES])
def test_svg_has_one_cell_per_category(engine, path):
    org = load_answers(path)
    result = engine.assess(org.profile, org.answers)
    root = ET.fromstring(render_svg(engine.catalog, result))
    groups = [g for g in root.iter(f"{SVG}g") if g.get("class") == "cell"]
    assert [g.get("data-category") for g in groups] == list(engine.catalog.categories)
    grid = {c.id: c for cells in by_category(engine.catalog, result).values() for c in cells}
    for g in groups:
        cell = grid[g.get("data-category")]
        rect = g.find(f"{SVG}rect")
        assert rect.get("fill") == attainment_colour(cell.attainment)
        tick = [x for x in g.iter(f"{SVG}line") if x.get("class") == "target"]
        assert len(tick) == (cell.target is not None)


def test_full_marks_reach_every_target(engine):
    answers = {}
    profile = {f: True for f in engine.bank.flags}
    for q in engine.bank.questions:
        answers[q.id] = max(q.options, key=lambda o: o.score).value
    result = engine.assess(profile, answers)
    for f in by_function(engine.catalog, result):
        assert f.attainment == 1 and f.at_target == f.assessed
    assert "100%" in render_svg(engine.catalog, result)


def test_rollup_ignores_excluded_subcategories(engine):
    result = engine.assess({}, {})  # no flags: several subcategories excluded
    grid = {c.id: c for cells in by_category(engine.catalog, result).values() for c in cells}
    excluded = [r for r in result.subcategories if r.status == "excluded"]
    assert excluded
    for cat in {engine.catalog.subcategories[r.id].category_id for r in excluded}:
        assert grid[cat].excluded > 0
    assert sum(c.assessed for c in grid.values()) == result.totals["subcategories_assessed"]
    assert all(c.attainment == 0 for c in grid.values() if c.assessed)


def test_food_bank_function_figures_in_readme(engine):
    # The README's per-function table quotes these; keep it honest.
    org = load_answers(SAMPLES[[p.stem for p in SAMPLES].index("food_bank")])
    result = engine.assess(org.profile, org.answers)
    reached = {f.id: round(100 * f.attainment) for f in by_function(engine.catalog, result)}
    assert reached == {"GV": 33, "ID": 19, "PR": 46, "DE": 30, "RS": 10, "RC": 11}
