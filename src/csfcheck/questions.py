"""Loading and checking the question bank (``data/questions.yaml``)."""

from __future__ import annotations

import itertools
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from .catalog import Catalog, data_path, default_catalog
from .conditions import Condition, ConditionError


class QuestionBankError(ValueError):
    """The question bank is inconsistent with itself or with the CSF core."""


@dataclass(frozen=True)
class Option:
    value: str
    label: str
    score: int


@dataclass(frozen=True)
class Question:
    id: str
    section: str
    text: str
    maps: tuple[str, ...]
    options: tuple[Option, ...]
    when: Condition | None = None
    requires: tuple[str, int] | None = None
    help: str = ""

    def option(self, value: str) -> Option:
        for opt in self.options:
            if opt.value == value:
                return opt
        allowed = ", ".join(o.value for o in self.options)
        raise KeyError(f"{value!r} is not an answer to {self.id} (expected one of: {allowed})")

    def applies_to(self, profile: Mapping[str, bool]) -> bool:
        return self.when is None or self.when.evaluate(profile)


@dataclass(frozen=True)
class Exclusion:
    subcategories: tuple[str, ...]
    when: Condition
    reason: str


@dataclass
class QuestionBank:
    flags: dict[str, str]
    questions: list[Question]
    exclusions: list[Exclusion]
    by_id: dict[str, Question] = field(init=False)

    def __post_init__(self):
        self.by_id = {q.id: q for q in self.questions}

    def normalise_profile(self, profile: Mapping[str, bool]) -> dict[str, bool]:
        unknown = set(profile) - set(self.flags)
        if unknown:
            raise KeyError(f"unknown profile flags: {', '.join(sorted(unknown))}")
        return {f: bool(profile.get(f, False)) for f in self.flags}

    def applicable(self, profile: Mapping[str, bool]) -> list[Question]:
        """Questions whose profile condition holds (before any answer branching)."""
        return [q for q in self.questions if q.applies_to(profile)]

    def excluded(self, profile: Mapping[str, bool]) -> dict[str, str]:
        """Subcategories that do not apply to this profile, with the stated reason."""
        out: dict[str, str] = {}
        for rule in self.exclusions:
            if rule.when.evaluate(profile):
                for sub in rule.subcategories:
                    out.setdefault(sub, rule.reason)
        return out

    def every_profile(self):
        names = list(self.flags)
        for values in itertools.product([False, True], repeat=len(names)):
            yield dict(zip(names, values))

    def check_coverage(self, catalog: Catalog) -> None:
        """Every subcategory is asked about or excluded, never both, for every profile."""
        problems: list[str] = []
        for profile in self.every_profile():
            asked = {s for q in self.applicable(profile) for s in q.maps}
            excluded = set(self.excluded(profile))
            on = sorted(f for f, v in profile.items() if v) or ["(none)"]
            for sub in catalog.subcategories:
                if sub not in asked and sub not in excluded:
                    problems.append(f"{sub} is neither asked nor excluded for profile {on}")
                elif sub in asked and sub in excluded:
                    problems.append(f"{sub} is both asked and excluded for profile {on}")
            if len(problems) > 20:
                break
        if problems:
            raise QuestionBankError("question bank coverage:\n  " + "\n  ".join(problems[:20]))


def _parse(raw: dict, catalog: Catalog) -> QuestionBank:
    flags = dict(raw["profile_flags"])
    sets = {
        name: tuple(Option(str(o["value"]), o["label"], int(o["score"])) for o in opts)
        for name, opts in raw["answer_sets"].items()
    }
    errors: list[str] = []

    def cond(text, where):
        try:
            return Condition(text, flags)
        except ConditionError as exc:
            errors.append(f"{where}: {exc}")
            return None

    questions: list[Question] = []
    seen: set[str] = set()
    for item in raw["questions"]:
        qid = item["id"]
        if qid in seen:
            errors.append(f"duplicate question id {qid}")
        maps = tuple(item["maps"])
        for sub in maps:
            if sub not in catalog.subcategories:
                errors.append(f"{qid} maps to {sub}, which is not a CSF 2.0 subcategory")
        options = sets.get(item.get("answers", "maturity"))
        if options is None:
            errors.append(f"{qid} uses unknown answer set {item.get('answers')!r}")
            options = ()
        if any(not 0 <= o.score <= 3 for o in options):
            errors.append(f"{qid} has an answer score outside 0-3")
        requires = None
        if "requires" in item:
            parent = item["requires"]["question"]
            if parent not in seen:
                errors.append(f"{qid} requires {parent}, which must come earlier in the bank")
            requires = (parent, int(item["requires"]["min_score"]))
        when = cond(item["when"], qid) if "when" in item else None
        help_text = str(item.get("help", "")).strip()
        if not help_text:
            errors.append(f"{qid} has no plain-language help text")
        questions.append(Question(qid, item["section"], item["text"], maps, options, when, requires, help_text))
        seen.add(qid)

    exclusions = []
    for i, item in enumerate(raw.get("exclusions", [])):
        subs = tuple(item["subcategories"])
        for sub in subs:
            if sub not in catalog.subcategories:
                errors.append(f"exclusion {i} names unknown subcategory {sub}")
        c = cond(item["when"], f"exclusion {i}")
        if c is not None:
            exclusions.append(Exclusion(subs, c, item["reason"]))

    # A follow-up inherits its parent's profile condition: it can only be
    # reached when the parent is asked.
    by_id = {q.id: q for q in questions}
    for q in questions:
        if q.requires:
            parent = by_id.get(q.requires[0])
            if parent and parent.when and (q.when is None or q.when.text != parent.when.text):
                errors.append(f"{q.id} must carry the same 'when' as its parent {parent.id}")

    if errors:
        raise QuestionBankError("invalid question bank:\n  " + "\n  ".join(errors))
    bank = QuestionBank(flags, questions, exclusions)
    bank.check_coverage(catalog)
    return bank


def load_bank(path: Path | None = None, catalog: Catalog | None = None) -> QuestionBank:
    path = path or data_path("questions.yaml")
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return _parse(raw, catalog or default_catalog())


@lru_cache(maxsize=1)
def default_bank() -> QuestionBank:
    return load_bank()
