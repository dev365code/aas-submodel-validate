"""Every generated 02035-7 Circularity rule fires, and the golden fixture
fires nothing at all.

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
from aas_submodel_validate.rules import dbp7_tables
from builders import dbp7_env, inject, strip_row, stub_of
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


def test_the_golden_environment_fires_nothing(tmp_path):
    assert set(_ids(tmp_path, dbp7_env())) == set()


def test_the_golden_environment_is_metamodel_clean_too(tmp_path):
    assert [f for f in _run(tmp_path, dbp7_env()).findings if f.rule.kind == "meta"] == []


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


@pytest.mark.parametrize("row", dbp7_tables.ROWS, ids=[r["id"] for r in dbp7_tables.ROWS])
def test_every_generated_rule_fires(tmp_path, row):
    env = copy.deepcopy(dbp7_env())
    low, high = row["card"]
    parent = dbp7_tables.BY_ID.get(row["parent"])
    if low >= 1:
        strip_row(env, row, tables=dbp7_tables)
    elif high is not None:
        inject(env, parent, [stub_of(row), stub_of(row)], tables=dbp7_tables)
    else:
        inject(env, parent, [_mismatched(row)], tables=dbp7_tables)
    assert row["id"] in _ids(tmp_path, env)


def test_the_golden_fixture_carries_every_row(tmp_path):
    from aas_submodel_validate.loader import load
    from aas_submodel_validate.rules import engine, profiles

    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(dbp7_env()).encode("utf-8"))
    ctx = runner.Context(load(path), profiles.Selection(None))
    instances = engine.analyze(ctx, dbp7_tables)["instances"]
    missing = [row["id"] for row in dbp7_tables.ROWS if not instances.get(row["id"])]
    assert not missing, "the golden fixture no longer carries: %s" % missing


def test_a_submodel_named_as_the_template_is_told_matching_goes_by_identifier(tmp_path):
    """Named `Circularity`, as the template names it, and carrying another
    identifier, a submodel is told what the other packs' namesakes are: the
    name is not what matches, and the fix is a one-field change."""
    env = copy.deepcopy(dbp7_env())
    env["submodels"][0]["semanticId"]["keys"][0]["value"] = "urn:vendor:thing:1"
    report = _run(tmp_path, env)
    [finding] = [f for f in report.findings if f.id == "SMT-D1"]
    assert "is *named* Circularity" in finding.violation.detail, finding.violation.detail
    assert finding.fixability == 2, finding.fixability


# -- where the template disagrees with its neighbours or its specification (#61)

def _elements(env):
    pending = list(env["submodels"][0]["submodelElements"])
    while pending:
        element = pending.pop(0)
        yield element
        value = element.get("value")
        if isinstance(value, list):
            pending.extend(child for child in value
                           if isinstance(child, dict) and "modelType" in child)


def _named(env, id_short):
    return next(element for element in _elements(env) if element.get("idShort") == id_short)


def _own(element):
    return element["semanticId"]["keys"][0]["value"]


def _findings(report):
    return sorted(f.id for f in report.findings if f.rule.kind != "meta")


@pytest.mark.parametrize("prefix", ["", "urn:irdi:"],
                         ids=["as-02002-writes-them", "as-this-template-writes-them"])
def test_a_supplier_identified_the_contact_template_s_way_answers_its_rows(tmp_path, prefix):
    """The supplier's name, address fields and e-mail are the contact
    information namespace's, with the ECLASS identifier beside each
    written `urn:irdi:0173-1#...`; 02002's template writes the same
    identifiers bare, as its own. They are one IRDI spelt two ways
    (docs/divergences.md #62), so a supplier built the 02002 way answers
    every row, as one written with the prefix does. Until 0.11.0 the first
    was reported missing its name, three address fields, e-mail and web
    address."""
    from builders import dbp7_supplier_env
    env = dbp7_supplier_env(lambda irdi: prefix + irdi)
    assert _findings(_run(tmp_path, env)) == []


def test_separate_collection_known_by_the_specification_s_identifier_alone_is_missing(
        tmp_path):
    """The specification's table gives `SeparateCollection`'s ECLASS
    identifier as `urn:idi:0173-1#02-ABL854#001`; the template writes
    `urn:irdi:`. Beside the element's own identifier it costs nothing;
    alone, the list matches no row and is reported missing, and the run
    names it as a place it did not examine."""
    env = copy.deepcopy(dbp7_env())
    collection = _named(env, "SeparateCollection")
    collection["supplementalSemanticIds"] = [
        {"type": "ExternalReference",
         "keys": [{"type": "GlobalReference", "value": "urn:idi:0173-1#02-ABL854#001"}]}]
    assert _findings(_run(tmp_path, env)) == []
    collection["semanticId"] = collection.pop("supplementalSemanticIds")[0]
    report = _run(tmp_path, env)
    assert _findings(report) == ["DBP7-E33"]
    places = [place["label"] for place in report.as_dict()["summary"]["scopeNotExamined"]]
    assert places == ["SeparateCollection"], places


@pytest.mark.parametrize("identifier", [
    "0173-1#02-AAO099#004",
    "urn:samm:io.admin-shell.idta.handover_documentation:2.0.0#documentIdentifier",
], ids=["eclass", "samm-lower-case"])
def test_document_items_spelt_as_02035_2_spells_them_leave_every_list_empty(tmp_path,
                                                                            identifier):
    """The five document lists' items carry
    `...handover_documentation:2.0.0#DocumentIdentifier`; 02035-2 spells
    that element `0173-1#02-AAO099#004`, with the SAMM identifier beside
    it written `#documentIdentifier`. Items carrying either match no row,
    and the five mandatory lists are reported empty. Items carrying no
    identifier are placed by position and kind, and pass."""
    from builders import DBP7_DOCUMENT
    env = copy.deepcopy(dbp7_env())
    items = [element for element in _elements(env) if _own(element) == DBP7_DOCUMENT]
    assert len(items) == 5
    for item in items:
        item["semanticId"]["keys"][0]["value"] = identifier
    assert _findings(_run(tmp_path, env)) == [
        "DBP7-E02", "DBP7-E27", "DBP7-E32", "DBP7-E34", "DBP7-E36"]
    for item in items:
        del item["semanticId"]
    assert _findings(_run(tmp_path, env)) == []


def test_a_recycled_material_outside_the_listed_four_draws_nothing(tmp_path):
    """The specification and the template's concept description list
    `Cobalt`, `Nickel`, `Lithium` and `Lead` for `RecycledMaterial`; no
    value is checked for what it says, and neither is a share above 100."""
    env = copy.deepcopy(dbp7_env())
    _named(env, "RecycledMaterial")["value"] = "Copper"
    _named(env, "PreConsumerShare")["value"] = "150"
    _named(env, "RenewableContent")["value"] = "250"
    assert _findings(_run(tmp_path, env)) == []


def test_list_items_copied_with_the_template_s_idshorts_are_warned_about(tmp_path):
    """All nine lists' items carry an idShort in the template, which the
    metamodel forbids on a list's direct child (AASd-120). A file that
    copies them is judged as the golden one, and draws one relayed
    warning per item: exit 0, and 1 under `-W`."""
    from aas_submodel_validate.cli import main
    env = copy.deepcopy(dbp7_env())
    named = 0
    for element in _elements(env):
        if element["modelType"] == "SubmodelElementList":
            for child in element["value"]:
                child["idShort"] = _own(child).rsplit("#", 1)[1]
                named += 1
    assert named == 9
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    report = runner.run(path)
    assert _findings(report) == []
    assert [f.violation.message.split(":")[0] for f in report.findings] == [
        "Constraint AASd-120"] * 9
    assert main(["-q", str(path)]) == 0
    assert main(["-q", "-W", str(path)]) == 1
