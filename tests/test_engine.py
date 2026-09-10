import pytest

from csfcheck.engine import ASKED, SKIPPED_FOLLOW_UP, SKIPPED_PROFILE, AnswerError
from csfcheck.model import default_targets


def all_answers(engine, profile, value_for=lambda q: q.options[-1].value):
    """Answer every reachable question, walking the flow like a user would."""
    answers = {}
    while True:
        batch = engine.next_questions(profile, answers, limit=100)
        if not batch:
            return answers
        for q in batch:
            answers[q.id] = value_for(q)


def test_quick_start_targets():
    t = default_targets()
    assert t.tiers["PR.AA-03"] == 3  # MFA is named directly
    assert t.tiers["GV.OC-04"] == 3  # printed as "GV.0C-04" in the guide
    assert t.tiers["RS.MI-01"] == 2  # guide cites the whole RS.MI category
    assert t.tiers["GV.RM-07"] == 1  # not mentioned


def test_follow_up_only_after_parent_answer(engine):
    profile = {}
    status = engine.question_status(profile, {"pr-backup": "no"})
    assert status["pr-backup-test"] == SKIPPED_FOLLOW_UP
    status = engine.question_status(profile, {"pr-backup": "informal"})
    assert status["pr-backup-test"] == ASKED
    assert engine.question_status(profile, {})["payments-provider"] == SKIPPED_PROFILE


def test_next_questions_waits_for_parent(engine):
    answers = {}
    batch = engine.next_questions({}, answers, limit=100)
    ids = [q.id for q in batch]
    assert "gv-policy" in ids and "gv-policy-review" not in ids
    assert ids[-1] == "gv-policy"  # stops at the open follow-up


def test_everything_in_place_meets_every_target(engine):
    profile = {f: True for f in engine.bank.flags}
    result = engine.assess(profile, all_answers(engine, profile))
    assert result.complete
    assessed = [r for r in result.subcategories if r.status == "assessed"]
    assert len(assessed) == 106
    assert all(r.gap == 0 for r in assessed)
    assert result.actions == []


def test_nothing_in_place_ranks_actions(engine):
    profile = {"has_office": True, "holds_client_data": True}
    answers = all_answers(engine, profile, lambda q: q.options[0].value)
    result = engine.assess(profile, answers)
    assert result.complete
    excluded = {r.id for r in result.subcategories if r.status == "excluded"}
    assert excluded == {"PR.PS-06", "ID.RA-08", "PR.AA-04", "PR.PS-04", "GV.RR-04"}
    ranks = [a.priority for a in result.actions]
    assert ranks == sorted(ranks, reverse=True)
    assert [a.rank for a in result.actions] == list(range(1, len(result.actions) + 1))
    top = result.actions[0]
    assert top.cost_band == "free"
    # action text comes straight from the CSF implementation examples
    sub = engine.catalog.subcategories[top.subcategory]
    assert top.what_to_do == sub.examples[0].text
    assert top.example_ids[0] == sub.examples[0].id


def test_scoring_arithmetic(engine):
    profile = {}
    answers = all_answers(engine, profile)
    answers["pr-mfa"] = "informal"  # 1 of 3; pr-passwords stays at 3
    r = {x.id: x for x in engine.assess(profile, answers).subcategories}["PR.AA-03"]
    assert r.current == 2.0 and r.target == 3 and r.gap == 1.0
    lik, imp = engine.model.inherent("PR.AA-03", profile)
    assert (lik, imp) == (4, 4)
    assert r.likelihood == pytest.approx(1 + 3 * 1 / 3)
    assert r.risk == pytest.approx(r.likelihood * imp)


def test_unanswered_counts_as_not_in_place(engine):
    result = engine.assess({}, {})
    assert not result.complete
    r = {x.id: x for x in result.subcategories}["PR.AA-03"]
    assert r.current == 0 and set(r.unanswered) == {"pr-mfa", "pr-passwords"}


def test_answers_to_skipped_or_unknown_questions_are_rejected(engine):
    with pytest.raises(AnswerError, match="skipped"):
        engine.check_answers({}, {"payments-provider": "yes"})
    with pytest.raises(AnswerError, match="skipped"):
        engine.check_answers({}, {"pr-backup": "no", "pr-backup-test": "yes"})
    with pytest.raises(AnswerError, match="unknown question"):
        engine.check_answers({}, {"nope": "yes"})
    with pytest.raises(AnswerError, match="not an answer"):
        engine.check_answers({}, {"gv-owner": "mostly"})  # yes/no question


def test_risk_model_covers_every_category(engine):
    assert set(engine.model.categories) == set(engine.catalog.categories)
    full = {f: True for f in engine.bank.flags}
    for sub in engine.catalog.subcategories:
        lik, imp = engine.model.inherent(sub, full)
        assert 1 <= lik <= 5 and 1 <= imp <= 5
