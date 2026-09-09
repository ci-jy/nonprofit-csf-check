"""Hypothesis property tests over profiles and answer sets."""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from csfcheck.engine import ASKED, Engine

ENGINE = Engine.default()
BANK = ENGINE.bank
FLAGS = list(BANK.flags)

profiles = st.fixed_dictionaries({f: st.booleans() for f in FLAGS})
choices = st.lists(st.integers(min_value=0, max_value=3), min_size=len(BANK.questions), max_size=len(BANK.questions))
SETTINGS = settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def walk(profile, picks, seen_batches=None):
    """Answer questions as the API hands them out, picking options by index."""
    answers = {}
    index = {q.id: i for i, q in enumerate(BANK.questions)}
    while True:
        batch = ENGINE.next_questions(profile, answers, limit=7)
        if not batch:
            return answers
        if seen_batches is not None:
            seen_batches.append((dict(answers), batch))
        for q in batch:
            answers[q.id] = q.options[picks[index[q.id]] % len(q.options)].value


@SETTINGS
@given(profiles)
def test_every_subcategory_reachable_or_excluded_by_a_rule(profile):
    excluded = BANK.excluded(profile)
    applicable = BANK.applicable(profile)
    applicable_ids = {q.id for q in applicable}
    reachable = set()
    for q in applicable:
        # a follow-up is reachable when its parent is asked, since answering
        # the parent well enough opens it
        if q.requires is None or q.requires[0] in applicable_ids:
            reachable.update(q.maps)
    for sub in ENGINE.catalog.subcategories:
        assert (sub in reachable) != (sub in excluded), sub
        if sub in excluded:
            assert any(sub in r.subcategories and r.when.evaluate(profile) for r in BANK.exclusions)


@SETTINGS
@given(profiles, choices)
def test_skipped_question_is_never_asked(profile, picks):
    batches = []
    answers = walk(profile, picks, batches)
    for before, batch in batches:
        status = ENGINE.question_status(profile, before)
        for q in batch:
            assert q.applies_to(profile)
            assert status[q.id] == ASKED
            assert q.id not in before
    final = ENGINE.question_status(profile, answers)
    assert set(answers) == {q for q, s in final.items() if s == ASKED}
    assert ENGINE.assess(profile, answers).complete


@SETTINGS
@given(profiles, choices, st.data())
def test_improving_an_answer_never_raises_risk(profile, picks, data):
    answers = walk(profile, picks)
    candidates = [q for q in BANK.questions if q.id in answers and ENGINE.score_of(q, answers) < 3]
    if not candidates:
        return
    q = data.draw(st.sampled_from(candidates))
    current = ENGINE.score_of(q, answers)
    better = data.draw(st.sampled_from([o for o in q.options if o.score > current]))
    improved = {**answers, q.id: better.value}

    before = ENGINE.assess(profile, answers)
    after = ENGINE.assess(profile, improved)
    old = {r.id: r for r in before.subcategories}
    for r in after.subcategories:
        assert r.risk <= old[r.id].risk + 1e-9, r.id
        assert r.gap <= old[r.id].gap + 1e-9
    assert after.totals["total_risk"] <= before.totals["total_risk"] + 1e-9

    # Raising a parent answer can open follow-ups; until they are answered
    # they count as 0, just as they did while skipped.
    opened = [x for x in ENGINE.next_questions(profile, improved, limit=100)]
    assert all(ENGINE.score_of(x, improved) is None for x in opened)
