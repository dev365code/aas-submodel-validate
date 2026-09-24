"""Every generated 02035-5 Product Condition rule fires, and the golden
fixture fires nothing at all.

Same contract as the other generated suites: a required row is proved
live by removing it, a bounded optional by injecting past its maximum,
and an unbounded (0..*) row by putting an element of the wrong kind under
its identifier -- the other half of what the row says.
"""
from __future__ import annotations

import copy
import json

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.rules import dbp5_tables
from builders import PC, dbp5_env, inject, strip_row, stub_of
from verdicts import by_id

#: What to put under a row's identifier so its kind check fires. A
#: Property is the odd one out: something has to differ from it.
_WRONG_KIND = {"Property": "MultiLanguageProperty"}


def _run(tmp_path, env: dict):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return runner.run(path)


def _ids(tmp_path, env: dict):
    return by_id(_run(tmp_path, env))


def _named(children, id_short):
    return next(child for child in children if child.get("idShort") == id_short)


def test_the_golden_environment_fires_nothing(tmp_path):
    assert set(_ids(tmp_path, dbp5_env())) == set()


def test_the_golden_environment_is_metamodel_clean_too(tmp_path):
    assert [f for f in _run(tmp_path, dbp5_env()).findings if f.rule.kind == "meta"] == []


def _mismatched(row) -> dict:
    wrong = stub_of(row)
    kind = _WRONG_KIND.get(row["kind"], "Property")
    wrong["modelType"] = kind
    wrong.pop("typeValueListElement", None)
    wrong.pop("valueTypeListElement", None)
    if kind == "Property":
        wrong["valueType"] = "xs:string"
        wrong["value"] = "x"
    else:
        wrong.pop("valueType", None)
        wrong["value"] = [{"language": "en", "text": "x"}]
    return wrong


@pytest.mark.parametrize("row", dbp5_tables.ROWS, ids=[r["id"] for r in dbp5_tables.ROWS])
def test_every_generated_rule_fires(tmp_path, row):
    env = copy.deepcopy(dbp5_env())
    low, high = row["card"]
    parent = dbp5_tables.BY_ID.get(row["parent"])
    if low >= 1:
        strip_row(env, row, tables=dbp5_tables)
    elif high is not None:
        inject(env, parent, [stub_of(row), stub_of(row)], tables=dbp5_tables)
    else:
        inject(env, parent, [_mismatched(row)], tables=dbp5_tables)
    assert row["id"] in _ids(tmp_path, env)


def test_the_golden_fixture_carries_every_row(tmp_path):
    from aas_submodel_validate.loader import load
    from aas_submodel_validate.rules import engine, profiles

    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(dbp5_env()).encode("utf-8"))
    ctx = runner.Context(load(path), profiles.Selection(None))
    instances = engine.analyze(ctx, dbp5_tables)["instances"]
    missing = [row["id"] for row in dbp5_tables.ROWS if not instances.get(row["id"])]
    assert not missing, "the golden fixture no longer carries: %s" % missing


def test_a_submodel_written_to_an_earlier_edition_is_named_by_its_version(tmp_path):
    """1.0.2 moved every identifier's SAMM version (its Annex B), and 1.0
    and 1.0.1 both name the submodel `...:1.0.0#ProductCondition`. A file
    written to either matches no row at all; SMT-D1 says which template it
    means and that only the version differs, rather than listing the
    identifier it could not place."""
    env = copy.deepcopy(dbp5_env())
    text = json.dumps(env).replace("product_condition:1.0.2#", "product_condition:1.0.0#")
    report = _run(tmp_path, json.loads(text))
    [finding] = [f for f in report.findings if f.id == "SMT-D1"]
    assert "only in its SAMM version" in finding.violation.detail, finding.violation.detail
    assert "02035-5" in finding.violation.detail
    assert finding.fixability == 2, finding.fixability


def test_another_element_of_the_namespace_is_not_one_version_off(tmp_path):
    """Read as "everything before the last `#`", a SAMM identifier's stem
    was its namespace and version, and a submodel naming any other element
    of that namespace was told it differed "only in the ECLASS version
    suffix"."""
    env = copy.deepcopy(dbp5_env())
    env["submodels"][0]["semanticId"]["keys"][0]["value"] = PC + "ProductConditionX"
    report = _run(tmp_path, env)
    [finding] = [f for f in report.findings if f.id == "SMT-D1"]
    assert "version" not in finding.violation.detail, finding.violation.detail


def test_an_element_one_samm_version_off_is_named_by_the_lint(tmp_path):
    """A 1.0.2 submodel holding one element copied from a 1.0.1 file: the
    element matches no row, and the pack's near-miss lint names it."""
    env = copy.deepcopy(dbp5_env())
    soc = _named(env["submodels"][0]["submodelElements"], "StateOfCharge")
    soc["semanticId"]["keys"][0]["value"] = PC.replace("1.0.2", "1.0.1") + "stateOfCharge"
    ids = _ids(tmp_path, env)
    assert "DBP5L1" in ids
