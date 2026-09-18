"""Every generated 02002 Contact Information rule fires, and the golden
fixture fires nothing at all.

Same contract as the 02004/02003/02006/02023 suites: a required row is
proved live by removing it, a bounded optional by injecting past its
maximum, and an unbounded (0..*) row by putting an element of the wrong
kind under its identifier -- the other half of what the row says.

Nothing fires on the golden file, and that is the whole verdict here:
02002's submodel identifier is claimed by no second template, so there is
no shared-identifier caveat riding along as there is for 02023.

Repetition in this template does not use a `SubmodelElementList` at all:
`ContactInformation` is `1..*` and `IPCommunication__00__` is `0..*` as
collections repeated in one scope. That is the path the four older packs
never exercised, so the counts below are also the test that the walk
counts siblings rather than list items.
"""
from __future__ import annotations

import copy
import json

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.rules import contact_tables
from builders import contact_env, inject, strip_row, stub_of
from verdicts import by_id

#: What to put under a row's identifier so its kind check fires. A
#: Property is the odd one out: something has to differ from it.
_WRONG_KIND = {"Property": "MultiLanguageProperty"}


def _ids(tmp_path, env: dict):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return by_id(runner.run(path))


def test_the_golden_environment_fires_nothing(tmp_path):
    """The golden file satisfies 02002's table and claims an identifier no
    other vendored template claims, so the verdict is empty. An empty
    verdict is the right answer here, unlike 02023, where an empty one
    would mean a shared identifier had gone unnamed."""
    assert set(_ids(tmp_path, contact_env())) == set()


def test_the_golden_environment_is_metamodel_clean_too(tmp_path):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(contact_env()).encode("utf-8"))
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


@pytest.mark.parametrize("row", contact_tables.ROWS,
                         ids=[r["id"] for r in contact_tables.ROWS])
def test_every_generated_rule_fires(tmp_path, row):
    env = copy.deepcopy(contact_env())
    low, high = row["card"]
    parent = contact_tables.BY_ID.get(row["parent"])
    if low >= 1:
        strip_row(env, row, tables=contact_tables)
    elif high is not None:
        inject(env, parent, [stub_of(row), stub_of(row)], tables=contact_tables)
    else:
        inject(env, parent, [_mismatched(row)], tables=contact_tables)
    assert row["id"] in _ids(tmp_path, env)


def test_a_second_contact_information_is_counted_not_ignored(tmp_path):
    """The repetition this template expresses without a list. A second
    conformant `ContactInformation` must be counted -- `1..*` allows it --
    and a defect inside the second must be reported against the second,
    not silently absorbed by the first having satisfied the row."""
    env = copy.deepcopy(contact_env())
    first = env["submodels"][0]["submodelElements"][0]
    second = copy.deepcopy(first)
    second["idShort"] = "ContactInformation02"
    # break the mandatory TelephoneNumber inside the *second* one only
    for child in second["value"]:
        if child.get("idShort") == "Phone":
            child["value"] = [c for c in child["value"]
                              if c.get("idShort") != "TelephoneNumber"]
    env["submodels"][0]["submodelElements"].append(second)
    found = _ids(tmp_path, env)
    assert "CI-E10" in found        # the second one's missing TelephoneNumber
    assert "CI-E01" not in found    # two of them still satisfy 1..*
