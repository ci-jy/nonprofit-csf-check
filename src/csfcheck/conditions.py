"""Tiny boolean language for profile conditions in questions.yaml.

Grammar::

    expr   := term ("or" term)*
    term   := factor ("and" factor)*
    factor := "not" factor | "(" expr ")" | FLAG

Conditions are parsed once into a tree of tuples and evaluated against a
mapping of profile flags. Unknown flags are a parse-time error, so a typo in
the question bank fails at startup instead of silently skipping a question.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

TOKEN = re.compile(r"\s*(\(|\)|[A-Za-z_][A-Za-z0-9_]*)")
KEYWORDS = {"and", "or", "not"}


class ConditionError(ValueError):
    pass


def _tokens(text: str) -> list[str]:
    pos, out = 0, []
    text = text.strip()
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m:
            raise ConditionError(f"cannot parse condition {text!r} at {text[pos:]!r}")
        out.append(m.group(1))
        pos = m.end()
    return out


class Condition:
    def __init__(self, text: str, flags: Iterable[str]):
        self.text = text
        self._flags = set(flags)
        self._toks = _tokens(text)
        self._i = 0
        self.tree = self._expr()
        if self._i != len(self._toks):
            raise ConditionError(f"unexpected {self._toks[self._i]!r} in {text!r}")

    def _peek(self) -> str | None:
        return self._toks[self._i] if self._i < len(self._toks) else None

    def _take(self) -> str:
        tok = self._peek()
        if tok is None:
            raise ConditionError(f"condition {self.text!r} ends too early")
        self._i += 1
        return tok

    def _expr(self):
        node = self._term()
        while self._peek() == "or":
            self._take()
            node = ("or", node, self._term())
        return node

    def _term(self):
        node = self._factor()
        while self._peek() == "and":
            self._take()
            node = ("and", node, self._factor())
        return node

    def _factor(self):
        tok = self._take()
        if tok == "not":
            return ("not", self._factor())
        if tok == "(":
            node = self._expr()
            if self._take() != ")":
                raise ConditionError(f"missing ')' in {self.text!r}")
            return node
        if tok in KEYWORDS or tok == ")":
            raise ConditionError(f"unexpected {tok!r} in {self.text!r}")
        if tok not in self._flags:
            raise ConditionError(f"unknown profile flag {tok!r} in {self.text!r}")
        return ("flag", tok)

    def evaluate(self, profile: Mapping[str, bool]) -> bool:
        return _eval(self.tree, profile)

    def __repr__(self) -> str:
        return f"Condition({self.text!r})"


def _eval(node, profile: Mapping[str, bool]) -> bool:
    op = node[0]
    if op == "flag":
        return bool(profile.get(node[1], False))
    if op == "not":
        return not _eval(node[1], profile)
    if op == "and":
        return _eval(node[1], profile) and _eval(node[2], profile)
    return _eval(node[1], profile) or _eval(node[2], profile)
