"""Every generated 02006 Digital Nameplate rule fires, and the golden
fixture fires none.

Same contract as the 02004/02003 suites: a required row is proved live by
removing it, a bounded optional by injecting past its maximum, and an
unbounded (0..*) row by putting an element of the wrong kind under its
identifier -- the other half of what the row says.
"""
from __future__ import annotations

import copy
import json

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.rules import dn_tables
from builders import dn_env, inject, strip_row, stub_of
from verdicts import by_id

#: What to put under a row's identifier so its kind check fires. A
#: Property is the odd one out: something has to differ from it.
_WRONG_KIND = {"Property": "MultiLanguageProperty"}


def _ids(tmp_path, env: dict):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return by_id(runner.run(path))


def test_the_golden_environment_is_clean(tmp_path):
    assert set(_ids(tmp_path, dn_env())) == set()


def test_the_golden_environment_is_metamodel_clean_too(tmp_path):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(dn_env()).encode("utf-8"))
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


@pytest.mark.parametrize("row", dn_tables.ROWS, ids=[r["id"] for r in dn_tables.ROWS])
def test_every_generated_rule_fires(tmp_path, row):
    env = copy.deepcopy(dn_env())
    low, high = row["card"]
    parent = dn_tables.BY_ID.get(row["parent"])
    if low >= 1:
        strip_row(env, row, tables=dn_tables)
    elif high is not None:
        inject(env, parent, [stub_of(row), stub_of(row)], tables=dn_tables)
    else:
        inject(env, parent, [_mismatched(row)], tables=dn_tables)
    assert row["id"] in _ids(tmp_path, env)
