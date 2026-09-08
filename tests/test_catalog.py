import json

import pytest

from csfcheck.catalog import ChecksumError, data_path, default_catalog, load_export


def test_full_csf_core_loads_from_export():
    cat = default_catalog()
    assert set(cat.functions) == {"GV", "ID", "PR", "DE", "RS", "RC"}
    assert len(cat.categories) == 22
    assert len(cat.subcategories) == 106
    assert sum(len(s.examples) for s in cat.subcategories.values()) == 363
    assert all(s.examples for s in cat.subcategories.values())


def test_withdrawn_csf_1_1_subcategories_are_dropped():
    cat = default_catalog()
    # ID.BE-01 was folded into GV.OC-05 and PR.AC-01 into PR.AA in CSF 2.0
    assert "ID.BE-01" not in cat.subcategories
    assert "PR.AC-01" not in cat.subcategories
    assert "ID.BE" not in cat.categories
    assert cat.subcategories["GV.OC-05"].category_id == "GV.OC"


def test_expand_references():
    cat = default_catalog()
    assert cat.expand("PR.AA-03") == ["PR.AA-03"]
    assert cat.expand("RS.MI") == ["RS.MI-01", "RS.MI-02"]
    assert len(cat.expand("GV")) == 31
    with pytest.raises(KeyError):
        cat.expand("XX.YY")


def test_modified_export_fails_checksum(tmp_path):
    raw = json.loads(data_path("csf-2.0-core.json").read_text())
    raw["response"]["elements"]["elements"][0]["text"] = "tampered"
    bad = tmp_path / "csf.json"
    bad.write_text(json.dumps(raw))
    with pytest.raises(ChecksumError):
        load_export(bad)
