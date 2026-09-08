"""The CSF 2.0 core as published in NIST's CPRT JSON export.

The export is vendored under ``data/`` together with its SHA-256, so the
assessment always runs against the exact file it was written for. The export
also carries the withdrawn CSF 1.1 subcategories (each with a
``withdraw_reason`` element); those are dropped here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from pathlib import Path

CORE_FILE = "csf-2.0-core.json"
CHECKSUM_FILE = "csf-2.0-core.json.sha256"


class ChecksumError(RuntimeError):
    pass


@dataclass(frozen=True)
class Example:
    id: str
    label: str
    text: str


@dataclass(frozen=True)
class Subcategory:
    id: str
    category_id: str
    text: str
    examples: tuple[Example, ...] = ()

    @property
    def function_id(self) -> str:
        return self.id.split(".")[0]


@dataclass(frozen=True)
class Category:
    id: str
    function_id: str
    title: str
    text: str


@dataclass(frozen=True)
class Function:
    id: str
    title: str
    text: str


@dataclass
class Catalog:
    document: str
    version: str
    sha256: str
    functions: dict[str, Function] = field(default_factory=dict)
    categories: dict[str, Category] = field(default_factory=dict)
    subcategories: dict[str, Subcategory] = field(default_factory=dict)

    def category_of(self, sub_id: str) -> Category:
        return self.categories[self.subcategories[sub_id].category_id]

    def expand(self, ref: str) -> list[str]:
        """Turn a reference such as ``PR.AA-03``, ``RS.MI`` or ``DE`` into subcategory ids."""
        if ref in self.subcategories:
            return [ref]
        prefix = ref + ("-" if ref in self.categories else ".")
        found = [s for s in self.subcategories if s.startswith(prefix)]
        if not found:
            raise KeyError(f"unknown CSF reference {ref!r}")
        return found


def data_path(name: str) -> Path:
    return Path(str(resources.files("csfcheck") / "data" / name))


def expected_checksum() -> str:
    return data_path(CHECKSUM_FILE).read_text().split()[0]


def file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_export(raw: dict, sha256: str) -> Catalog:
    elements = raw["response"]["elements"]
    doc = elements["documents"][0]
    items = elements["elements"]
    withdrawn = {
        e["element_identifier"].removeprefix("WR-")
        for e in items
        if e["element_type"] == "withdraw_reason"
    }
    live = [e for e in items if e["element_identifier"] not in withdrawn]

    cat = Catalog(document=doc["name"], version=" ".join(doc["version"].split()), sha256=sha256)
    examples: dict[str, list[Example]] = {}
    for e in live:
        kind, ident = e["element_type"], e["element_identifier"]
        if kind == "function":
            cat.functions[ident] = Function(ident, e["title"], e["text"])
        elif kind == "category":
            cat.categories[ident] = Category(ident, ident.split(".")[0], e["title"], e["text"])
        elif kind == "implementation_example":
            sub_id = ident.rsplit(".", 1)[0]
            examples.setdefault(sub_id, []).append(Example(ident, e["title"], e["text"]))

    for e in live:
        if e["element_type"] != "subcategory":
            continue
        ident = e["element_identifier"]
        exs = tuple(sorted(examples.get(ident, []), key=lambda x: x.id))
        cat.subcategories[ident] = Subcategory(ident, ident.split("-")[0], e["text"], exs)

    cat.subcategories = dict(sorted(cat.subcategories.items()))
    return cat


def load_export(path: Path | None = None, verify: bool = True) -> Catalog:
    path = path or data_path(CORE_FILE)
    digest = file_checksum(path)
    if verify and digest != expected_checksum():
        raise ChecksumError(
            f"{path} has SHA-256 {digest}, expected {expected_checksum()}; "
            "the vendored CSF export has been modified"
        )
    return parse_export(json.loads(path.read_text(encoding="utf-8")), digest)


@lru_cache(maxsize=1)
def default_catalog() -> Catalog:
    return load_export()
