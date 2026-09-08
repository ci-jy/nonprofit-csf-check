import pytest

from csfcheck.conditions import Condition, ConditionError

FLAGS = ["a", "b", "c"]


@pytest.mark.parametrize(
    "text,profile,expected",
    [
        ("a", {"a": True}, True),
        ("not a", {"a": True}, False),
        ("a or b", {"b": True}, True),
        ("a and b", {"a": True}, False),
        ("not a and not b", {}, True),
        ("a or b and c", {"a": True}, True),  # and binds tighter than or
        ("(a or b) and c", {"a": True}, False),
        ("not (a or b)", {"c": True}, True),
    ],
)
def test_evaluate(text, profile, expected):
    assert Condition(text, FLAGS).evaluate(profile) is expected


@pytest.mark.parametrize("text", ["a and", "a b", "(a or b", "has_pets", "or a", "a & b"])
def test_rejects_bad_conditions(text):
    with pytest.raises(ConditionError):
        Condition(text, FLAGS)
