import copy

import pytest
import yaml

from csfcheck.catalog import data_path, default_catalog
from csfcheck.questions import QuestionBankError, _parse, default_bank


@pytest.fixture
def raw():
    return yaml.safe_load(data_path("questions.yaml").read_text())


def test_bank_loads_and_maps_every_subcategory():
    bank = default_bank()
    mapped = {s for q in bank.questions for s in q.maps}
    excluded = {s for rule in bank.exclusions for s in rule.subcategories}
    assert mapped | excluded == set(default_catalog().subcategories)
    assert len(bank.questions) == len(bank.by_id)


def test_profile_with_nothing_set_skips_conditional_questions():
    bank = default_bank()
    nothing = {f: False for f in bank.flags}
    skipped = {q.id for q in bank.questions} - {q.id for q in bank.applicable(nothing)}
    assert {"pr-physical", "payments-provider", "server-maintenance", "pr-secure-dev"} <= skipped


def test_uncovered_subcategory_is_rejected(raw):
    raw = copy.deepcopy(raw)
    raw["questions"] = [q for q in raw["questions"] if q["id"] != "rc-public-comms"]
    with pytest.raises(QuestionBankError, match="RC.CO-04 is neither asked nor excluded"):
        _parse(raw, default_catalog())


def test_conditional_question_without_matching_exclusion_is_rejected(raw):
    raw = copy.deepcopy(raw)
    for q in raw["questions"]:
        if q["id"] == "rc-public-comms":
            q["when"] = "holds_donor_data"
    with pytest.raises(QuestionBankError, match="RC.CO-04 is neither asked nor excluded"):
        _parse(raw, default_catalog())


def test_asked_and_excluded_at_once_is_rejected(raw):
    raw = copy.deepcopy(raw)
    raw["exclusions"].append({"subcategories": ["PR.AA-03"], "when": "remote_staff", "reason": "x"})
    with pytest.raises(QuestionBankError, match="PR.AA-03 is both asked and excluded"):
        _parse(raw, default_catalog())


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("maps", ["PR.AC-01"], "not a CSF 2.0 subcategory"),
        ("when", "has_cats", "unknown profile flag"),
        ("answers", "likert", "unknown answer set"),
        ("requires", {"question": "rc-close", "min_score": 1}, "must come earlier"),
    ],
)
def test_bad_question_fields_are_rejected(raw, field, value, message):
    raw = copy.deepcopy(raw)
    raw["questions"][0][field] = value
    with pytest.raises(QuestionBankError, match=message):
        _parse(raw, default_catalog())
