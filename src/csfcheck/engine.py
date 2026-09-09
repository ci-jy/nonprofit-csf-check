"""Question flow, current-vs-target scoring and the ranked action plan.

Everything here is a pure function of (profile, answers), so the API, the
CLI and the property tests all share one implementation.

Scoring, per applicable subcategory:

* current = mean score (0-3) of the applicable questions mapped to it. An
  unanswered question, or a follow-up skipped because its parent scored too
  low, counts as 0.
* target  = Quick-Start tier (see ``model.load_targets``).
* gap     = max(0, target - current).
* likelihood = 1 + (inherent likelihood - 1) * gap / target, so a closed gap
  leaves the minimum likelihood of 1 and a full gap the inherent one.
* risk = likelihood x impact. Risk reduced by an action is the drop to the
  closed-gap risk (1 x impact); actions are ranked by that drop per unit of
  cost-band weight.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from .catalog import Catalog, default_catalog
from .model import RiskModel, Targets, default_risk_model, default_targets
from .questions import Question, QuestionBank, default_bank

ASKED, SKIPPED_PROFILE, SKIPPED_FOLLOW_UP = "asked", "skipped (profile)", "skipped (follow-up)"


class AnswerError(ValueError):
    pass


@dataclass(frozen=True)
class SubcategoryResult:
    id: str
    function: str
    category: str
    outcome: str
    status: str  # "assessed" or "excluded"
    reason: str = ""
    questions: tuple[str, ...] = ()
    current: float = 0.0
    target: int = 0
    gap: float = 0.0
    likelihood: float = 0.0
    impact: int = 0
    risk: float = 0.0
    rating: str = ""
    target_reason: str = ""
    unanswered: tuple[str, ...] = ()


@dataclass(frozen=True)
class Action:
    rank: int
    subcategory: str
    function: str
    outcome: str
    what_to_do: str
    also_consider: tuple[str, ...]
    example_ids: tuple[str, ...]
    quick_start: tuple[str, ...]
    questions: tuple[str, ...]
    current: float
    target: int
    risk: float
    rating: str
    risk_reduction: float
    cost_band: str
    cost_label: str
    priority: float
    horizon: str


@dataclass
class Result:
    profile: dict[str, bool]
    question_status: dict[str, str]
    subcategories: list[SubcategoryResult]
    actions: list[Action]
    complete: bool
    totals: dict[str, float] = field(default_factory=dict)


@dataclass
class Engine:
    catalog: Catalog
    bank: QuestionBank
    targets: Targets
    model: RiskModel

    @classmethod
    def default(cls) -> "Engine":
        return cls(default_catalog(), default_bank(), default_targets(), default_risk_model())

    # ------------------------------------------------------------ question flow
    def score_of(self, q: Question, answers: Mapping[str, str]) -> int | None:
        value = answers.get(q.id)
        return None if value is None else q.option(value).score

    def question_status(self, profile: Mapping[str, bool], answers: Mapping[str, str]) -> dict[str, str]:
        status: dict[str, str] = {}
        for q in self.bank.questions:
            if not q.applies_to(profile):
                status[q.id] = SKIPPED_PROFILE
                continue
            if q.requires:
                parent_id, min_score = q.requires
                parent = self.bank.by_id[parent_id]
                parent_score = self.score_of(parent, answers)
                if status[parent_id] != ASKED or parent_score is None or parent_score < min_score:
                    status[q.id] = SKIPPED_FOLLOW_UP
                    continue
            status[q.id] = ASKED
        return status

    def next_questions(
        self, profile: Mapping[str, bool], answers: Mapping[str, str], limit: int = 5
    ) -> list[Question]:
        """The next unanswered questions to ask, in bank order.

        A follow-up waits until its parent has been answered, so the list may be
        shorter than ``limit`` while answers are pending.
        """
        status = self.question_status(profile, answers)
        out = []
        for q in self.bank.questions:
            if status[q.id] == ASKED and q.id not in answers:
                out.append(q)
            elif status[q.id] == SKIPPED_FOLLOW_UP and q.requires[0] not in answers:
                break  # parent still open; later questions wait for it
            if len(out) >= limit:
                break
        return out

    def check_answers(
        self, profile: Mapping[str, bool], answers: Mapping[str, str], only: Iterable[str] | None = None
    ) -> None:
        """Reject answers to unknown or skipped questions and invalid options.

        ``only`` limits the check to some of the answers (the ones just
        submitted); older answers that a change has made unreachable are the
        caller's to drop.
        """
        status = self.question_status(profile, answers)
        for qid in answers if only is None else only:
            value = answers[qid]
            q = self.bank.by_id.get(qid)
            if q is None:
                raise AnswerError(f"unknown question {qid!r}")
            if status[qid] != ASKED:
                raise AnswerError(f"question {qid!r} is {status[qid]} for this organisation")
            try:
                q.option(value)
            except KeyError as exc:
                raise AnswerError(str(exc.args[0])) from None

    # ------------------------------------------------------------------ scoring
    def assess(self, profile: Mapping[str, bool], answers: Mapping[str, str]) -> Result:
        profile = self.bank.normalise_profile(profile)
        status = self.question_status(profile, answers)
        excluded = self.bank.excluded(profile)
        mapped: dict[str, list[Question]] = {}
        for q in self.bank.questions:
            if status[q.id] != SKIPPED_PROFILE:
                for sub in q.maps:
                    mapped.setdefault(sub, []).append(q)

        results: list[SubcategoryResult] = []
        for sub_id, sub in self.catalog.subcategories.items():
            cat = self.catalog.categories[sub.category_id]
            common = dict(id=sub_id, function=sub.function_id, category=cat.title, outcome=sub.text)
            if sub_id in excluded:
                results.append(SubcategoryResult(status="excluded", reason=excluded[sub_id], **common))
                continue
            qs = mapped[sub_id]
            scores, unanswered = [], []
            for q in qs:
                s = self.score_of(q, answers) if status[q.id] == ASKED else 0
                if s is None:
                    unanswered.append(q.id)
                    s = 0
                scores.append(s)
            current = round(sum(scores) / len(scores), 2)
            target = self.targets.tiers[sub_id]
            gap = round(max(0.0, target - current), 2)
            lik0, impact = self.model.inherent(sub_id, profile)
            likelihood = round(1 + (lik0 - 1) * gap / target, 2)
            risk = round(likelihood * impact, 2)
            results.append(
                SubcategoryResult(
                    status="assessed",
                    questions=tuple(q.id for q in qs),
                    current=current,
                    target=target,
                    gap=gap,
                    likelihood=likelihood,
                    impact=impact,
                    risk=risk,
                    rating=self.model.rating(risk),
                    target_reason=self.targets.reasons[sub_id],
                    unanswered=tuple(unanswered),
                    **common,
                )
            )

        actions = self._actions(results)
        asked = [q for q, s in status.items() if s == ASKED]
        assessed = [r for r in results if r.status == "assessed"]
        totals = {
            "questions_in_bank": len(self.bank.questions),
            "questions_asked": len(asked),
            "skipped_profile": sum(s == SKIPPED_PROFILE for s in status.values()),
            "skipped_follow_up": sum(s == SKIPPED_FOLLOW_UP for s in status.values()),
            "skipped_pct": round(100 * (1 - len(asked) / len(self.bank.questions)), 1),
            "subcategories_assessed": len(assessed),
            "subcategories_excluded": len(results) - len(assessed),
            "subcategories_at_target": sum(r.gap == 0 for r in assessed),
            "total_risk": round(sum(r.risk for r in assessed), 2),
        }
        complete = all(q in answers for q in asked)
        return Result(profile, status, results, actions, complete, totals)

    def _actions(self, results: list[SubcategoryResult]) -> list[Action]:
        draft = []
        for r in results:
            if r.status != "assessed" or r.gap <= 0:
                continue
            sub = self.catalog.subcategories[r.id]
            band = self.model.cost(r.id)
            reduction = round(r.risk - r.impact, 2)
            examples = sub.examples
            draft.append(
                dict(
                    subcategory=r.id,
                    function=r.function,
                    outcome=r.outcome,
                    what_to_do=examples[0].text if examples else r.outcome,
                    also_consider=tuple(e.text for e in examples[1:3]),
                    example_ids=tuple(e.id for e in examples[:3]),
                    quick_start=tuple(a.text for a in self.targets.actions_for.get(r.id, ())),
                    questions=r.questions,
                    current=r.current,
                    target=r.target,
                    risk=r.risk,
                    rating=r.rating,
                    risk_reduction=reduction,
                    cost_band=band.key,
                    cost_label=band.label,
                    priority=round(reduction / band.weight, 3),
                )
            )
        # Highest risk reduced per cost unit first; ties go to the bigger risk,
        # then to CSF order so the plan is stable.
        draft.sort(key=lambda a: (-a["priority"], -a["risk"], a["subcategory"]))
        actions = []
        for i, a in enumerate(draft, start=1):
            horizon = "Now" if i <= 5 else "Next" if i <= 15 else "Later"
            actions.append(Action(rank=i, horizon=horizon, **a))
        return actions
