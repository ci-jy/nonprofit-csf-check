"""Quick-Start targets and the likelihood/impact model, both loaded from YAML."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache

import yaml

from .catalog import Catalog, data_path, default_catalog


@dataclass(frozen=True)
class QuickStartAction:
    function: str
    step: str
    text: str
    refs: tuple[str, ...]


@dataclass(frozen=True)
class Targets:
    """Target tier (0-3) per subcategory, from the Small Business Quick-Start Guide."""

    tiers: dict[str, int]
    reasons: dict[str, str]
    actions_for: dict[str, tuple[QuickStartAction, ...]]
    source: str


@dataclass(frozen=True)
class CostBand:
    key: str
    weight: int
    label: str


@dataclass(frozen=True)
class RiskModel:
    categories: dict[str, dict]
    cost_bands: dict[str, CostBand]
    cost_overrides: dict[str, str]
    modifiers: dict[str, dict[str, dict[str, int]]]
    ratings: tuple[tuple[float, str], ...]

    def inherent(self, sub_id: str, profile: Mapping[str, bool]) -> tuple[int, int]:
        """Inherent (likelihood, impact) for a subcategory, before any controls."""
        cat = sub_id.split("-")[0]
        base = self.categories[cat]
        lik, imp = base["likelihood"], base["impact"]
        for flag, mods in self.modifiers.items():
            if profile.get(flag):
                lik += mods.get("likelihood", {}).get(cat, 0)
                imp += mods.get("impact", {}).get(cat, 0)
        return min(lik, 5), min(imp, 5)

    def cost(self, sub_id: str) -> CostBand:
        key = self.cost_overrides.get(sub_id) or self.categories[sub_id.split("-")[0]]["cost"]
        return self.cost_bands[key]

    def rating(self, score: float) -> str:
        for limit, label in self.ratings:
            if score <= limit:
                return label
        return self.ratings[-1][1]


def load_targets(catalog: Catalog | None = None) -> Targets:
    catalog = catalog or default_catalog()
    raw = yaml.safe_load(data_path("quickstart.yaml").read_text(encoding="utf-8"))
    levels = raw["targets"]
    tiers = {s: levels["baseline"] for s in catalog.subcategories}
    reasons = {s: "Not named in the Quick-Start Guide: aim for at least an informal practice" for s in tiers}
    actions_for: dict[str, list[QuickStartAction]] = {}
    for item in raw["actions"]:
        action = QuickStartAction(item["function"], item["step"], item["text"], tuple(item["refs"]))
        for ref in action.refs:
            direct = ref in catalog.subcategories
            level = levels["cited"] if direct else levels["category"]
            for sub in catalog.expand(ref):
                actions_for.setdefault(sub, []).append(action)
                if level > tiers[sub]:
                    tiers[sub] = level
                    reasons[sub] = (
                        f"Quick-Start {action.step} action cites {ref}"
                        if direct
                        else f"Quick-Start {action.step} action cites the {ref} category"
                    )
    return Targets(
        tiers=tiers,
        reasons=reasons,
        actions_for={k: tuple(v) for k, v in actions_for.items()},
        source=raw["source"],
    )


def load_risk_model() -> RiskModel:
    raw = yaml.safe_load(data_path("risk_model.yaml").read_text(encoding="utf-8"))
    bands = {k: CostBand(k, v["weight"], v["label"]) for k, v in raw["cost_bands"].items()}
    ratings = tuple((float(r["max"]), r["label"]) for r in raw["ratings"])
    model = RiskModel(raw["categories"], bands, raw.get("cost_overrides", {}), raw.get("modifiers", {}), ratings)
    for sub, band in model.cost_overrides.items():
        if band not in bands:
            raise ValueError(f"cost override for {sub} uses unknown band {band!r}")
    return model


@lru_cache(maxsize=1)
def default_targets() -> Targets:
    return load_targets()


@lru_cache(maxsize=1)
def default_risk_model() -> RiskModel:
    return load_risk_model()
