"""Every generated rule fires, and the golden fixture fires none.

The mutation per row is chosen by what the row demands: a required
element is removed; an optional one is injected twice (over its maximum);
a required child of an optional list gets its list injected empty. If
any row's id never appears, that rule is dead -- and a dead rule is
indistinguishable from a wrong one from the outside.
"""
from __future__ import annotations

import copy
import json

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.rules import hd_tables
from builders import hd_env, inject, strip_row, stub_of


def _ids(tmp_path, env: dict):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return {finding.id for finding in runner.run(path).findings}


def _matched_in_golden(row) -> bool:
    from builders import _element_matches, _scopes
    return any(_element_matches(element, row["match"])
               for _container, element in _scopes(hd_env()))


def test_the_golden_environment_is_clean(tmp_path):
    assert _ids(tmp_path, hd_env()) == set()


@pytest.mark.parametrize("row", hd_tables.ROWS, ids=[r["id"] for r in hd_tables.ROWS])
def test_every_generated_rule_fires(tmp_path, row):
    env = copy.deepcopy(hd_env())
    low, _high = row["card"]
    if low >= 1:
        if _matched_in_golden(row):
            strip_row(env, row)
        else:
            # required child of an optional list: an empty list violates it
            parent = hd_tables.BY_ID[row["parent"]]
            grandparent = hd_tables.BY_ID.get(parent["parent"])
            inject(env, grandparent, [stub_of(parent)])
    else:
        parent = hd_tables.BY_ID.get(row["parent"])
        inject(env, parent, [stub_of(row), stub_of(row)])
    assert row["id"] in _ids(tmp_path, env)


def test_a_kind_mismatch_names_both_kinds(tmp_path):
    env = copy.deepcopy(hd_env())
    row = hd_tables.BY_LABEL["Version"]
    strip_row(env, row)
    wrong = {"idShort": "Version", "modelType": "MultiLanguageProperty",
             "semanticId": {"type": "ExternalReference",
                            "keys": [{"type": "GlobalReference", "value": row["sid"]}]},
             "value": [{"language": "en", "text": "V1.2"}]}
    inject(env, hd_tables.BY_ID[row["parent"]], [wrong])
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    findings = {f.id: f for f in runner.run(path).findings}
    assert "must be a Property" in findings[row["id"]].violation.message


def test_a_value_type_mismatch_is_reported(tmp_path):
    env = copy.deepcopy(hd_env())
    row = hd_tables.BY_LABEL["StatusSetDate"]
    strip_row(env, row)
    wrong = stub_of(row)
    wrong["valueType"] = "xs:string"
    wrong["value"] = "2020-02-06"
    inject(env, hd_tables.BY_ID[row["parent"]], [wrong])
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    findings = {f.id: f for f in runner.run(path).findings}
    assert "xs:date" in findings[row["id"]].violation.message
