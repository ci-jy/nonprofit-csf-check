"""Comparing two assessments of the same organisation.

A retake is scored on its own with ``Engine.assess``; this module lines the
two results up. Like the engine it is a pure function of its inputs, so the
API, the web pages, the workbook and the CLI all report the same changes.

Per subcategory the change is read from ``current`` (the target is the same
in both, since Quick-Start tiers do not depend on the profile):

* improved / regressed / unchanged when it was assessed both times,
* now applicable / no longer applicable when a profile change moved it in or
  out of scope.

Per action of the earlier plan:

* completed when the gap is now closed,
* progressed when the gap is smaller but still open,
* still open when the gap is the same or larger,
* no longer applicable when the subcategory is now excluded.

Actions in the new plan that were not in the old one are "new".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .catalog import Catalog
from .engine import ASKED, Engine, Result
from .rollup import by_function

IMPROVED, REGRESSED, UNCHANGED = "improved", "regressed", "unchanged"
NOW_APPLICABLE, NO_LONGER_APPLICABLE = "now applicable", "no longer applicable"
COMPLETED, PROGRESSED, STILL_OPEN, NEW = "completed", "progressed", "still open", "new"
EPS = 1e-9


@dataclass(frozen=True)
class SubcategoryChange:
    id: str
    function: str
    outcome: str
    change: str
    before: float | None  # current, None when not applicable
    after: float | None
    target: int
    risk_before: float | None
    risk_after: float | None

    @property
    def delta(self) -> float | None:
        if self.before is None or self.after is None:
            return None
        return round(self.after - self.before, 2)


@dataclass(frozen=True)
class ActionChange:
    subcategory: str
    what_to_do: str
    status: str
    rank_before: int | None
    rank_after: int | None
    gap_before: float | None
    gap_after: float | None
    cost_label: str


@dataclass(frozen=True)
class AnswerChange:
    question_id: str
    section: str
    text: str
    before: str | None  # option label, None when not asked or unanswered
    after: str | None
    score_before: int | None
    score_after: int | None


@dataclass(frozen=True)
class FunctionChange:
    id: str
    title: str
    before: float | None  # share of target reached, 0-1
    after: float | None
    at_target_before: int
    at_target_after: int


@dataclass
class Comparison:
    subcategories: list[SubcategoryChange]
    actions: list[ActionChange]
    answers: list[AnswerChange]
    functions: list[FunctionChange]
    profile_changes: dict[str, tuple[bool, bool]]
    totals: dict[str, float] = field(default_factory=dict)

    def by_change(self, change: str) -> list[SubcategoryChange]:
        return [s for s in self.subcategories if s.change == change]

    def actions_with(self, status: str) -> list[ActionChange]:
        return [a for a in self.actions if a.status == status]


def attainment(result: Result) -> float:
    """Share of the whole target profile reached, as on the heat map."""
    assessed = [r for r in result.subcategories if r.status == "assessed"]
    wanted = sum(r.target for r in assessed)
    return round(sum(min(r.current, r.target) for r in assessed) / wanted, 3) if wanted else 1.0


def _subcategory_change(old, new) -> str:
    if old.status != "assessed" and new.status != "assessed":
        return UNCHANGED
    if old.status != "assessed":
        return NOW_APPLICABLE
    if new.status != "assessed":
        return NO_LONGER_APPLICABLE
    if new.current > old.current + EPS:
        return IMPROVED
    if new.current < old.current - EPS:
        return REGRESSED
    return UNCHANGED


def _answer_label(engine: Engine, result: Result, answers: Mapping[str, str], qid: str):
    if result.question_status[qid] != ASKED or qid not in answers:
        return None, None
    opt = engine.bank.by_id[qid].option(answers[qid])
    return opt.label, opt.score


def compare(
    engine: Engine,
    before: Result,
    after: Result,
    answers_before: Mapping[str, str] | None = None,
    answers_after: Mapping[str, str] | None = None,
) -> Comparison:
    """What changed from ``before`` to ``after``.

    The answer-level list is only filled in when both answer sets are given.
    """
    cat: Catalog = engine.catalog
    old = {r.id: r for r in before.subcategories}
    subs = []
    for new in after.subcategories:
        o = old[new.id]
        assessed_before, assessed_after = o.status == "assessed", new.status == "assessed"
        subs.append(SubcategoryChange(
            id=new.id, function=new.function, outcome=new.outcome,
            change=_subcategory_change(o, new),
            before=o.current if assessed_before else None,
            after=new.current if assessed_after else None,
            target=new.target or o.target,
            risk_before=o.risk if assessed_before else None,
            risk_after=new.risk if assessed_after else None,
        ))

    new_by_sub = {a.subcategory: a for a in after.actions}
    now = {r.id: r for r in after.subcategories}
    actions = []
    for a in before.actions:
        r = now[a.subcategory]
        gap_before = old[a.subcategory].gap
        if r.status != "assessed":
            status, gap_after = NO_LONGER_APPLICABLE, None
        elif r.gap <= EPS:
            status, gap_after = COMPLETED, 0.0
        elif r.gap < gap_before - EPS:
            status, gap_after = PROGRESSED, r.gap
        else:
            status, gap_after = STILL_OPEN, r.gap
        later = new_by_sub.get(a.subcategory)
        actions.append(ActionChange(a.subcategory, a.what_to_do, status, a.rank,
                                    later.rank if later else None, gap_before, gap_after, a.cost_label))
    had = {a.subcategory for a in before.actions}
    for a in after.actions:
        if a.subcategory not in had:
            actions.append(ActionChange(a.subcategory, a.what_to_do, NEW, None, a.rank, None,
                                        now[a.subcategory].gap, a.cost_label))

    answer_changes = []
    if answers_before is not None and answers_after is not None:
        for q in engine.bank.questions:
            lb, sb = _answer_label(engine, before, answers_before, q.id)
            la, sa = _answer_label(engine, after, answers_after, q.id)
            if (lb, sb) != (la, sa):
                answer_changes.append(AnswerChange(q.id, q.section, q.text, lb, la, sb, sa))

    f_old = {f.id: f for f in by_function(cat, before)}
    functions = [
        FunctionChange(f.id, f.title, f_old[f.id].attainment, f.attainment, f_old[f.id].at_target, f.at_target)
        for f in by_function(cat, after)
    ]
    profile_changes = {
        flag: (bool(before.profile.get(flag)), bool(after.profile.get(flag)))
        for flag in engine.bank.flags
        if bool(before.profile.get(flag)) != bool(after.profile.get(flag))
    }

    comparison = Comparison(subs, actions, answer_changes, functions, profile_changes)
    count = lambda xs, key, value: sum(getattr(x, key) == value for x in xs)  # noqa: E731
    comparison.totals = {
        "improved": count(subs, "change", IMPROVED),
        "regressed": count(subs, "change", REGRESSED),
        "unchanged": sum(s.change == UNCHANGED and s.before is not None for s in subs),
        "now_applicable": count(subs, "change", NOW_APPLICABLE),
        "no_longer_applicable": count(subs, "change", NO_LONGER_APPLICABLE),
        "actions_before": len(before.actions),
        "actions_after": len(after.actions),
        "actions_completed": count(actions, "status", COMPLETED),
        "actions_progressed": count(actions, "status", PROGRESSED),
        "actions_still_open": count(actions, "status", STILL_OPEN),
        "actions_new": count(actions, "status", NEW),
        "answers_changed": len(answer_changes),
        "at_target_before": before.totals["subcategories_at_target"],
        "at_target_after": after.totals["subcategories_at_target"],
        "attainment_before": attainment(before),
        "attainment_after": attainment(after),
        "risk_before": before.totals["total_risk"],
        "risk_after": after.totals["total_risk"],
    }
    return comparison


def summary_points(comparison: Comparison, label_before: str = "the last assessment") -> list[str]:
    """The comparison in a few sentences, for the web page and the Word report."""
    t = comparison.totals
    pct = lambda x: f"{round(100 * x)}%"  # noqa: E731
    points = [
        f"Since {label_before} the organisation went from {pct(t['attainment_before'])} to "
        f"{pct(t['attainment_after'])} of its target profile, and from {t['at_target_before']} to "
        f"{t['at_target_after']} subcategories at target.",
        f"{t['improved']} subcategories improved and {t['regressed']} went backwards; "
        f"{t['answers_changed']} answers changed.",
        f"Of the {t['actions_before']} actions in the earlier plan, {t['actions_completed']} are done and "
        f"{t['actions_progressed']} have moved forward; the plan now has {t['actions_after']} actions"
        + (f", {t['actions_new']} of them new." if t["actions_new"] else "."),
        f"Total risk across the profile went from {t['risk_before']:g} to {t['risk_after']:g}.",
    ]
    if comparison.profile_changes:
        changed = ", ".join(
            f"{flag.replace('_', ' ')} ({'now yes' if after else 'now no'})"
            for flag, (_, after) in comparison.profile_changes.items()
        )
        points.append(f"The organisation's profile changed: {changed}.")
    return points
