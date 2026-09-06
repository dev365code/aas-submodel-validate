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


# -- the item type a list declares, against the one the template declares -----


def _list_rows():
    return [row for row in td_tables.ROWS if row.get("list_type")]


def _find(node, sid):
    if isinstance(node, dict):
        for key in (node.get("semanticId") or {}).get("keys") or []:
            if key.get("value") == sid:
                return node
        for value in node.values():
            found = _find(value, sid)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find(value, sid)
            if found is not None:
                return found
    return None


def test_the_generator_records_an_item_type_worth_reading():
    """Twenty-one rows across the three packs carry the item type their
    template declares, and for a long time nothing read one."""
    assert len(_list_rows()) == 4
    assert all(row["list_type"] == "SubmodelElementCollection" for row in _list_rows())


@pytest.mark.parametrize("label", ["ProductImages", "ProductClassifications",
                                   "SpecificDescriptions"])
def test_a_list_declaring_an_item_type_the_template_does_not(tmp_path, label):
    """The narrow case nothing covered.

    `AASd-108` makes the items agree with the list's own declaration and
    `AASd-109` asks for a value type where one is needed; both are the
    metamodel's and both are relayed. Neither compares the declaration to
    the *template*, which is not a question the metamodel can ask.

    Everywhere else the item row's own cardinality catches the file
    first: an item row of `1..*` cannot be satisfied by an empty list.
    These three are `0..*`, so a list that declares the wrong item type
    and carries no items is metamodel-clean, satisfies every row, and
    said nothing at all.
    """
    row = td_tables.BY_LABEL[label]
    environment = copy.deepcopy(td_env())
    node = _find(environment, row["sid"])
    assert node is not None, label
    node["typeValueListElement"] = "File"
    node.pop("value", None)          # not set, which the metamodel permits

    ids = _ids(tmp_path, environment)
    assert "X3" not in ids, ("the fixture stopped parsing", label, ids)
    assert row["id"] in ids, (label, ids)


@pytest.mark.parametrize("label", ["ProductImages", "ProductClassifications",
                                   "SpecificDescriptions"])
def test_a_list_declaring_what_the_template_declares_is_not_reported(tmp_path, label):
    """The direction that costs more. Same shape, right declaration."""
    row = td_tables.BY_LABEL[label]
    environment = copy.deepcopy(td_env())
    node = _find(environment, row["sid"])
    node["typeValueListElement"] = row["list_type"]
    node.pop("value", None)
    ids = _ids(tmp_path, environment)
    # The control. A negative assertion is satisfied by a document that
    # was never judged, and the sibling test below passed exactly that
    # way until it was measured -- so this one says out loud that the
    # run reached the rules.
    assert "X3" not in ids, ("the fixture stopped parsing", label, ids)
    assert row["id"] not in ids, (label, ids)


def test_a_list_cannot_decline_to_declare_an_item_type(tmp_path):
    """`typeValueListElement` is required of a `SubmodelElementList` by
    the schema, so "the file declares nothing" is not a state a document
    can reach: the payload does not parse and `X3` says so.

    This replaces a test that asserted the rule stays quiet for such a
    file. It did stay quiet -- because nothing was judged at all. A
    negative assertion with no control is satisfied by a run that never
    happened, which is the third time that shape has been found here.

    The guard in the walk stays: it costs a comparison, and a model
    built by hand rather than parsed can carry `None`.
    """
    row = td_tables.BY_LABEL["ProductImages"]
    environment = copy.deepcopy(td_env())
    node = _find(environment, row["sid"])
    node.pop("typeValueListElement", None)
    node.pop("value", None)
    ids = _ids(tmp_path, environment)
    assert set(ids) == {"X3"}, ids
    assert "typeValueListElement" in str(ids["X3"].violation.detail)
