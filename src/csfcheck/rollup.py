"""Rolling subcategory results up to CSF categories and functions.

The heat map and the Word report both show the profile one category at a
time, so the averaging lives here once. Excluded subcategories take no part;
a category whose subcategories are all excluded has no score at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import Catalog
from .engine import Result, SubcategoryResult

RATING_ORDER = ("Low", "Medium", "High", "Critical")


@dataclass(frozen=True)
class Rollup:
    id: str
    title: str
    assessed: int
    excluded: int
    at_target: int
    current: float | None  # mean current over assessed subcategories
    target: float | None
    attainment: float | None  # share of the target reached, 0-1
    worst_rating: str = ""
    high_risk: int = 0  # gaps rated High or Critical

    @property
    def gap(self) -> float | None:
        return None if self.current is None else round(max(0.0, self.target - self.current), 2)


def _roll(ident: str, title: str, rows: list[SubcategoryResult]) -> Rollup:
    assessed = [r for r in rows if r.status == "assessed"]
    excluded = len(rows) - len(assessed)
    if not assessed:
        return Rollup(ident, title, 0, excluded, 0, None, None, None)
    reached = sum(min(r.current, r.target) for r in assessed)
    wanted = sum(r.target for r in assessed)
    rated = [r.rating for r in assessed if r.gap > 0]
    return Rollup(
        id=ident,
        title=title,
        assessed=len(assessed),
        excluded=excluded,
        at_target=sum(r.gap == 0 for r in assessed),
        current=round(sum(r.current for r in assessed) / len(assessed), 2),
        target=round(wanted / len(assessed), 2),
        attainment=round(reached / wanted, 3),
        worst_rating=max(rated, key=RATING_ORDER.index) if rated else "",
        high_risk=sum(r in ("High", "Critical") for r in rated),
    )


def by_category(catalog: Catalog, result: Result) -> dict[str, list[Rollup]]:
    """Category rollups grouped by function, both in CSF order."""
    rows: dict[str, list[SubcategoryResult]] = {}
    for r in result.subcategories:
        rows.setdefault(catalog.subcategories[r.id].category_id, []).append(r)
    out: dict[str, list[Rollup]] = {f: [] for f in catalog.functions}
    for cat in catalog.categories.values():
        out[cat.function_id].append(_roll(cat.id, cat.title, rows.get(cat.id, [])))
    return out


def by_function(catalog: Catalog, result: Result) -> list[Rollup]:
    rows: dict[str, list[SubcategoryResult]] = {f: [] for f in catalog.functions}
    for r in result.subcategories:
        rows[r.function].append(r)
    return [_roll(f.id, f.title, rows[f.id]) for f in catalog.functions.values()]
