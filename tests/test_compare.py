"""Comparing a retake with the earlier assessment."""

from hypothesis import given
from hypothesis import strategies as st

from csfcheck.compare import (
    COMPLETED,
    IMPROVED,
    NEW,
    NO_LONGER_APPLICABLE,
    NOW_APPLICABLE,
    PROGRESSED,
    REGRESSED,
    STILL_OPEN,
    compare,
    summary_points,
)
from csfcheck.samples import load_answers

from .conftest import ROOT
from .test_properties import BANK, ENGINE, SETTINGS, choices, profiles, walk

FOOD_BANK = ROOT / "samples" / "food_bank.json"
RETAKE = ROOT / "samples" / "retakes" / "food_bank.json"


def scored(engine, path):
    org = load_answers(path)
    return org, engine.assess(org.profile, org.answers)


def test_comparing_an_assessment_with_itself_changes_nothing(engine):
    org, result = scored(engine, FOOD_BANK)
    c = compare(engine, result, result, org.answers, org.answers)
    assert {s.change for s in c.subcategories} == {"unchanged"}
    assert {a.status for a in c.actions} == {STILL_OPEN}
    assert c.answers == [] and c.profile_changes == {}
    assert c.totals["actions_completed"] == 0 and c.totals["risk_before"] == c.totals["risk_after"]


def test_food_bank_retake(engine):
    """The figures the README quotes for the food bank's second assessment."""
    old, before = scored(engine, FOOD_BANK)
    new, after = scored(engine, RETAKE)
    assert after.complete
    c = compare(engine, before, after, old.answers, new.answers)
    t = c.totals
    assert (t["improved"], t["regressed"]) == (18, 3)
    assert (t["actions_before"], t["actions_completed"], t["actions_progressed"], t["actions_new"]) == (85, 4, 14, 1)
    assert (t["at_target_before"], t["at_target_after"]) == (19, 22)
    assert t["actions_after"] == 82
    assert (round(100 * t["attainment_before"]), round(100 * t["attainment_after"])) == (27, 34)
    assert c.profile_changes == {"remote_staff": (False, True)}
    respond = next(f for f in c.functions if f.id == "RS")
    assert (round(100 * respond.before), round(100 * respond.after)) == (10, 32)

    # The IT owner left, so GV.RR-02 went backwards and came back into the plan.
    assert {s.id for s in c.by_change(REGRESSED)} == {"GV.RR-02", "PR.AA-05", "PR.DS-01"}
    assert [a.subcategory for a in c.actions_with(NEW)] == ["GV.RR-02"]
    assert {a.subcategory for a in c.actions_with(COMPLETED)} == {"RC.RP-04", "RS.MA-02", "RS.MA-04", "GV.RM-06"}
    # Every closed gap is an action the old plan had and the new plan doesn't.
    assert all(a.rank_after is None and a.gap_after == 0 for a in c.actions_with(COMPLETED))
    changed = {a.question_id: (a.before, a.after) for a in c.answers}
    assert changed["gv-owner"] == ("Yes", "No, or not sure")
    assert changed["remote-devices"][0] is None  # not asked before the profile changed
    assert any("remote staff (now yes)" in p for p in summary_points(c))


def test_a_profile_change_moves_subcategories_in_and_out_of_scope(engine):
    small = BANK.normalise_profile({})
    big = BANK.normalise_profile({f: True for f in BANK.flags})
    picks = [1] * len(BANK.questions)
    before = engine.assess(small, walk(small, picks))
    after = engine.assess(big, walk(big, picks))
    c = compare(engine, before, after)
    opened = set(BANK.excluded(small)) - set(BANK.excluded(big))
    assert opened, "turning every flag on brings some subcategories into scope"
    assert {s.id for s in c.by_change(NOW_APPLICABLE)} == opened
    assert all(s.before is None and s.after is not None for s in c.by_change(NOW_APPLICABLE))
    back = compare(engine, after, before)
    assert {s.id for s in back.by_change(NO_LONGER_APPLICABLE)} == opened
    assert {a.subcategory for a in back.actions_with(NO_LONGER_APPLICABLE)} <= opened


@SETTINGS
@given(profiles, choices, st.data())
def test_raising_answers_never_shows_a_regression(profile, picks, data):
    answers = walk(profile, picks)
    raisable = [q for q in BANK.questions if q.id in answers and ENGINE.score_of(q, answers) < 3]
    chosen = data.draw(st.lists(st.sampled_from(raisable), unique_by=lambda q: q.id)) if raisable else []
    improved = dict(answers)
    for q in chosen:
        better = [o for o in q.options if o.score > ENGINE.score_of(q, answers)]
        improved[q.id] = data.draw(st.sampled_from(better)).value

    before, after = ENGINE.assess(profile, answers), ENGINE.assess(profile, improved)
    c = compare(ENGINE, before, after, answers, improved)
    t = c.totals
    assert t["regressed"] == 0 and t["actions_new"] == 0
    assert t["actions_completed"] + t["actions_progressed"] + t["actions_still_open"] == len(before.actions)
    assert t["actions_after"] == len(before.actions) - t["actions_completed"]
    assert t["risk_after"] <= t["risk_before"] + 1e-9
    assert {a.question_id for a in c.answers if a.before is not None} == {q.id for q in chosen}
    # An action only moves when its subcategory did.
    moved = {a.subcategory for a in c.actions if a.status in (COMPLETED, PROGRESSED)}
    assert moved <= {s.id for s in c.by_change(IMPROVED)}
