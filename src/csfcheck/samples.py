"""Reading an organisation's answers from a JSON file (see ``samples/``)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OrganisationAnswers:
    name: str
    profile: dict[str, bool]
    answers: dict[str, str]
    evidence: dict[str, str] = field(default_factory=dict)
    description: str = ""


def load_answers(path: str | Path) -> OrganisationAnswers:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    org = raw["organisation"]
    return OrganisationAnswers(
        name=org["name"],
        description=org.get("description", ""),
        profile=dict(org.get("profile", {})),
        answers={k: str(v) for k, v in raw.get("answers", {}).items()},
        evidence=dict(raw.get("evidence", {})),
    )
