"""IDTA 02035-2's pack: what it asks, and what it stops asking.

The pack exists because two published templates answer to one submodel
identifier and do not want the same things. So the tests that matter are
comparisons: the same file is clean under one and faulted under the
other, and every row of the second table can be made to fire.

Which of the two answers is the caller's: `--profile`. The file's own
declaration reports and does not choose, which is a decision with a
measurement behind it rather than a stage on the way to something --
docs/divergences.md #30.
"""
from __future__ import annotations

import copy
import json

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.registry import all_rules
from aas_submodel_validate.rules import dbp_tables, hd_tables
from builders import DROPPED_BY_02035_2, break_row, dbp_env, hd_env

#: The findings 02004 reports about a file 02035-2 calls conformant.
#: These six are the whole disagreement a real instance runs into.
THE_DISAGREEMENT = {"HD-E17", "HD-E20", "HD-E22", "HD-E23", "HD-E24", "HD-E25"}


def _ids(tmp_path, env, profile=None, name="env.json"):
    path = tmp_path / name
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return {f.id for f in runner.run(path, profile=profile).findings}


def test_the_golden_is_clean_under_02035_2_and_faulted_under_02004(tmp_path):
    """One file, two verdicts. This is the slice, in one assertion.

    Clean under 02035-2 means one finding, not none: choosing a template
    other than the one that answers by default is itself reported
    (SMT-D2), because a stored report has to say which requirements
    produced it.
    """
    assert _ids(tmp_path, dbp_env(), profile="02035-2") == {"SMT-D2"}
    assert _ids(tmp_path, dbp_env(), profile="02004") == THE_DISAGREEMENT | {"SMT-D2"}
    assert _ids(tmp_path, dbp_env()) == THE_DISAGREEMENT, "02004 answers by default"


def test_the_dropped_elements_are_ones_the_table_agrees_are_dropped():
    """The fixture names its six by hand. The table is asked from the
    other side whether it agrees -- either the row is gone or its
    cardinality no longer requires it. Two things written independently,
    checked against each other."""
    for label in DROPPED_BY_02035_2:
        row = dbp_tables.BY_LABEL.get(label)
        assert row is None or row["card"][0] == 0, label
        assert hd_tables.BY_LABEL[label]["card"][0] >= 1, label


def test_a_conformant_02004_file_is_conformant_to_02035_2_too(tmp_path):
    """02035-2 asks for a subset of the rows and relaxes two of them, so
    the golden environment passes under either template.

    That is a fact about this file, not an implication. The docstring
    here used to draw one -- "it makes nothing stricter, so the
    implication runs one way" -- and the test below is the
    counter-example (docs/divergences.md #32)."""
    assert _ids(tmp_path, hd_env(), profile="02035-2") == {"SMT-D2"}


def test_a_wider_match_set_is_a_tightening_where_a_row_is_bounded(tmp_path):
    """Every 02035-2 match set is a strict superset of 02004's, and a
    superset admits *more* elements to the same row. Where the row has an
    upper bound, admitting more is stricter, not looser.

    A `Documents` under 02004's ECLASS identifier with a sibling under
    the SAMM URN 02035-2 adds: one row filled under 02004, two under
    02035-2, against a bound of exactly one. Neither verdict is wrong --
    a battery passport carrying both spellings really has declared the
    list twice, and a 02004 file has one list and a stranger's element
    beside it, which this project does not refuse. What was wrong was
    believing this could not happen."""
    env = copy.deepcopy(hd_env())
    documents = env["submodels"][0]["submodelElements"][0]
    samm = sorted(set(dbp_tables.BY_LABEL["Documents"]["match"])
                  - set(hd_tables.BY_LABEL["Documents"]["match"]))
    assert len(samm) == 1, samm
    sibling = copy.deepcopy(documents)
    sibling["idShort"] = "DocumentsUnderTheOtherSpelling"
    sibling["semanticId"] = {"type": "ExternalReference",
                             "keys": [{"type": "GlobalReference", "value": samm[0]}]}
    env["submodels"][0]["submodelElements"].append(sibling)
    assert "DBP2-E01" not in _ids(tmp_path, env, profile="02004")
    assert "DBP2-E01" in _ids(tmp_path, env, profile="02035-2")


@pytest.mark.parametrize("row", dbp_tables.ROWS, ids=[r["id"] for r in dbp_tables.ROWS])
def test_every_generated_rule_fires(tmp_path, row):
    """A row whose rule never fires is dead or wrong, and the two cannot
    be told apart from outside."""
    env = break_row(dbp_env(), row, dbp_tables)
    assert row["id"] in _ids(tmp_path, env, profile="02035-2")


def test_the_pack_answers_eleven_of_02004s_hand_rules():
    registered = {rule.id for rule in all_rules()}
    hand = sorted(i for i in registered if i.startswith("DBP2") and not i.startswith("DBP2-E"))
    assert hand == ["DBP2-D10", "DBP2-D2", "DBP2-D3", "DBP2-D4", "DBP2-D5",
                    "DBP2-D7", "DBP2L1", "DBP2L2", "DBP2L3", "DBP2L4", "DBP2L5"]


def test_the_mandatory_vdi_classification_is_still_mandatory(tmp_path):
    """02035-2 keeps VDI 2770: its ClassificationSystem row is still
    required and its own ExampleValue is still `VDI2770:2020`. A profile
    that dropped the classification would make this tool's first
    paragraph false for battery passports."""
    env = dbp_env()
    for document in env["submodels"][0]["submodelElements"][0]["value"]:
        document["value"] = [c for c in document["value"]
                             if c.get("idShort") != "DocumentClassifications"]
    ids = _ids(tmp_path, env, profile="02035-2")
    assert "DBP2-D2" in ids
    assert dbp_tables.BY_LABEL["ClassificationSystem"]["example"] == "VDI2770:2020"


def test_the_status_rules_02035_2_dropped_are_not_registered_for_it():
    """D6, D8 and D9 navigate rows this template does not have. They are
    absent by declaration, not by crashing on a missing label."""
    registered = {rule.id for rule in all_rules()}
    for suffix in ("-D6", "-D8", "-D9"):
        assert "DBP2" + suffix not in registered
        assert "HD" + suffix in registered
