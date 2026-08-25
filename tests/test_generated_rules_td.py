"""Every generated 02003 rule fires, and the golden fixture fires none.

Same contract as the 02004 suite, with one branch 02004 never needed. Its
rows were all bounded — a required element could be removed, an optional
one injected past its maximum. 02003 has five rows the template bounds at
neither end (0..*), and no count violates that. They are proved live by
putting an element of the wrong kind under their identifier, which is the
other half of what the row says.

Without that branch those five rules would be registered, never fire,
and be indistinguishable from dead ones — which `make exercised` would
have reported as a coverage failure rather than as the design hole it is.
"""
from __future__ import annotations

import copy
import json

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.rules import td_tables
from builders import inject, strip_row, stub_of, td_env

#: What to put under a row's identifier so its kind check fires. A
#: Property is the odd one out: something has to differ from it.
_WRONG_KIND = {"Property": "MultiLanguageProperty"}


def _ids(tmp_path, env: dict):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return {finding.id: finding for finding in runner.run(path).findings}


def test_the_golden_environment_is_clean(tmp_path):
    assert set(_ids(tmp_path, td_env())) == set()


def test_the_golden_environment_is_metamodel_clean_too(tmp_path):
    """02003's own official sample carries sixty metamodel findings. A
    fixture that copied that would make every later assertion about the
    meta channel read as noise."""
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(td_env()).encode("utf-8"))
    assert [f for f in runner.run(path).findings if f.rule.kind == "meta"] == []


def _mismatched(row) -> dict:
    wrong = stub_of(row)
    kind = _WRONG_KIND.get(row["kind"], "Property")
    wrong["modelType"] = kind
    wrong.pop("typeValueListElement", None)
    wrong.pop("contentType", None)
    if kind == "Property":
        wrong["valueType"] = "xs:string"
        wrong["value"] = "x"
    else:
        wrong.pop("valueType", None)
        wrong["value"] = [{"language": "en", "text": "x"}]
    return wrong


@pytest.mark.parametrize("row", td_tables.ROWS, ids=[r["id"] for r in td_tables.ROWS])
def test_every_generated_rule_fires(tmp_path, row):
    env = copy.deepcopy(td_env())
    low, high = row["card"]
    parent = td_tables.BY_ID.get(row["parent"])
    if low >= 1:
        strip_row(env, row, tables=td_tables)
    elif high is not None:
        inject(env, parent, [stub_of(row), stub_of(row)], tables=td_tables)
    else:
        inject(env, parent, [_mismatched(row)], tables=td_tables)
    assert row["id"] in _ids(tmp_path, env)


def test_a_value_type_mismatch_is_reported(tmp_path):
    env = copy.deepcopy(td_env())
    row = td_tables.BY_LABEL["ValidDate"]
    strip_row(env, row, tables=td_tables)
    wrong = stub_of(row)
    wrong["valueType"] = "xs:string"
    wrong["value"] = "2025-03-15"
    inject(env, td_tables.BY_ID[row["parent"]], [wrong], tables=td_tables)
    assert "xs:date" in _ids(tmp_path, env)[row["id"]].violation.message


def test_the_two_templates_do_not_judge_each_other(tmp_path):
    """One environment, both submodels, one defect each. Neither pack may
    claim the other's elements, and neither presence rule may fire."""
    from builders import hd_env
    env = copy.deepcopy(td_env())
    env["submodels"].extend(copy.deepcopy(hd_env())["submodels"])
    strip_row(env, td_tables.BY_LABEL["ManufacturerName"], tables=td_tables)
    ids = set(_ids(tmp_path, env))
    assert "TD-E02" in ids
    assert "SMT-D1" not in ids
