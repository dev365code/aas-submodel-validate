"""Every generated 02035-1 Digital Nameplate rule fires, and the golden
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
from aas_submodel_validate.rules import dbp1_tables
from builders import dbp1_env, inject, strip_row, stub_of
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
    assert set(_ids(tmp_path, dbp1_env())) == set()


def test_the_golden_environment_is_metamodel_clean_too(tmp_path):
    assert [f for f in _run(tmp_path, dbp1_env()).findings if f.rule.kind == "meta"] == []


def _mismatched(row) -> dict:
    wrong = stub_of(row)
    kind = _WRONG_KIND.get(row["kind"], "Property")
    wrong["modelType"] = kind
    wrong.pop("typeValueListElement", None)
    wrong.pop("valueTypeListElement", None)
    wrong.pop("contentType", None)
    if kind == "Property":
        wrong["valueType"] = "xs:string"
        wrong["value"] = "x"
    else:
        wrong.pop("valueType", None)
        wrong["value"] = [{"language": "en", "text": "x"}]
    return wrong


@pytest.mark.parametrize("row", dbp1_tables.ROWS, ids=[r["id"] for r in dbp1_tables.ROWS])
def test_every_generated_rule_fires(tmp_path, row):
    env = copy.deepcopy(dbp1_env())
    low, high = row["card"]
    parent = dbp1_tables.BY_ID.get(row["parent"])
    if low >= 1:
        strip_row(env, row, tables=dbp1_tables)
    elif high is not None:
        inject(env, parent, [stub_of(row), stub_of(row)], tables=dbp1_tables)
    else:
        inject(env, parent, [_mismatched(row)], tables=dbp1_tables)
    assert row["id"] in _ids(tmp_path, env)


def test_the_golden_fixture_carries_every_row(tmp_path):
    from aas_submodel_validate.loader import load
    from aas_submodel_validate.rules import engine, profiles

    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(dbp1_env()).encode("utf-8"))
    ctx = runner.Context(load(path), profiles.Selection(None))
    instances = engine.analyze(ctx, dbp1_tables)["instances"]
    missing = [row["id"] for row in dbp1_tables.ROWS if not instances.get(row["id"])]
    assert not missing, "the golden fixture no longer carries: %s" % missing


def test_a_submodel_named_as_the_template_is_told_matching_goes_by_identifier(tmp_path):
    """Named `BatteryNameplate` and carrying another identifier, a
    submodel is told what the other packs' namesakes are: the name is not
    what matches, and the fix is a one-field change."""
    env = copy.deepcopy(dbp1_env())
    env["submodels"][0]["semanticId"]["keys"][0]["value"] = "urn:vendor:thing:1"
    report = _run(tmp_path, env)
    [finding] = [f for f in report.findings if f.id == "SMT-D1"]
    assert "is *named* BatteryNameplate" in finding.violation.detail, finding.violation.detail
    assert finding.fixability == 2, finding.fixability


# -- where the template disagrees with itself or its specification (#59) -----

def _element(env, id_short):
    return next(element for element in env["submodels"][0]["submodelElements"]
                if element.get("idShort") == id_short)


def _reference(value):
    return {"type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": value}]}


def test_a_markings_list_ending_in_a_version_suffix_matches_no_row(tmp_path):
    """The row's own identifier is `0112/2///61360_7#AAS006`, with no
    version suffix. A list whose identifier ends `#001` and that carries
    nothing else the row matches is no row's: the mandatory `Markings` is
    reported missing, no near miss is named -- there is no suffix to
    compare -- and the run says where it did not look."""
    env = copy.deepcopy(dbp1_env())
    _element(env, "Markings")["semanticId"]["keys"][0]["value"] = "0112/2///61360_7#AAS006#001"
    report = _run(tmp_path, env)
    assert [f.id for f in report.findings] == ["DBP1-E11"], [f.id for f in report.findings]
    places = [place["label"] for place in report.as_dict()["summary"]["scopeNotExamined"]]
    assert places == ["Markings"], places


@pytest.mark.parametrize("beside", [
    "0173-1#02-ABI563#003/0173-1#01-AHF849#003",
    "urn:samm:io.admin-shell.idta.digital_nameplate:3.0.0#markings",
], ids=["eclass", "samm"])
def test_a_suffixed_markings_list_is_matched_by_another_identifier_the_row_holds(tmp_path, beside):
    """What leaves the list unmatched is carrying nothing else the row
    matches, not the suffix: the ECLASS and SAMM identifiers the template
    puts beside its own each match it."""
    env = copy.deepcopy(dbp1_env())
    markings = _element(env, "Markings")
    markings["semanticId"]["keys"][0]["value"] = "0112/2///61360_7#AAS006#001"
    markings["supplementalSemanticIds"] = [_reference(beside)]
    assert set(_ids(tmp_path, env)) == set()


def test_an_address_is_asked_for_and_not_looked_inside(tmp_path):
    """The specification's §3.2 says Street, Zipcode, CityTown and
    NationalCode shall be specified inside `AddressInformation`; its table
    and the template write the collection with nothing in it, and the rows
    are the template's. So the address is asked to be there, an empty one
    passes, and so does one whose street is not text: the metamodel says
    so, and no template finding does."""
    env = copy.deepcopy(dbp1_env())
    address = _element(env, "AddressInformation")
    address.pop("value", None)
    assert set(_ids(tmp_path, env)) == set()
    address["value"] = [{"idShort": "Street", "modelType": "Property",
                         "semanticId": _reference("0173-1#02-AAO128#002"),
                         "valueType": "xs:int", "value": "Musterstrasse 1"}]
    assert set(_ids(tmp_path, env)) == {"META"}


@pytest.mark.parametrize("spelling", [
    "0173-1#02-AAO099#004",
    "urn:samm:io.admin-shell.idta.handover_documentation:2.0.0#documentIdentifier",
], ids=["eclass", "samm-lowercase"])
def test_document_identifiers_spelled_as_the_handover_part_spells_them_are_missing(
        tmp_path, spelling):
    """The template gives both lists' items the Handover Documentation
    identifier `...handover_documentation:2.0.0#DocumentIdentifier`, which
    the specification never prints; 02035-2's template spells the same
    element `0173-1#02-AAO099#004`, with `...#documentIdentifier` beside
    it. Items spelled either of 02035-2's ways match nothing, both
    mandatory lists are reported empty, and no near miss is named. Items
    with no identifier at all are placed by position and kind, and pass."""
    env = copy.deepcopy(dbp1_env())
    lists = ("EUDeclarationOfConformity", "ResultsOfTestReportsProvingCompliance")
    for name in lists:
        for item in _element(env, name)["value"]:
            item["semanticId"]["keys"][0]["value"] = spelling
    assert sorted(_ids(tmp_path, env)) == ["DBP1-E20", "DBP1-E22"]
    for name in lists:
        for item in _element(env, name)["value"]:
            item.pop("semanticId")
    assert set(_ids(tmp_path, env)) == set()


def test_another_element_wearing_the_drop_in_marker_is_a_second_address(tmp_path):
    """`AddressInformation`'s row matches the drop-in marker among its
    supplementals, as 02006's does (`DN-E04`), so any other element that
    carries the marker is counted as a second address."""
    env = copy.deepcopy(dbp1_env())
    other = copy.deepcopy(_element(env, "SerialNumber"))
    other["idShort"] = "Other"
    other["semanticId"]["keys"][0]["value"] = "urn:example:other"
    other["supplementalSemanticIds"] = [
        _reference("https://admin-shell.io/smt-dropin/smt-dropin-use/1/0")]
    env["submodels"][0]["submodelElements"].append(other)
    messages = [f.violation.message for f in _run(tmp_path, env).findings
                if f.id == "DBP1-E03"]
    assert "the template expects exactly one 'AddressInformation' here; found 2" in messages, \
        messages


@pytest.mark.parametrize("value", ["Original", "banana"])
def test_the_life_cycle_stage_is_not_checked_for_what_it_says(tmp_path, value):
    """The template's concept description lists `original`, `repurposed`,
    `re-used`, `remanufactured` and `waste`; its own example value, like
    the specification's table's, is `Original`, outside that list. No
    value is checked for what it says (docs/scope.md), so neither the
    example nor anything else draws a finding."""
    env = copy.deepcopy(dbp1_env())
    _element(env, "LifeCycleStage")["value"] = value
    assert set(_ids(tmp_path, env)) == set()


def test_the_golden_address_holds_what_the_specification_requires():
    """The rows do not ask for §3.2's four address fields (the test
    above), so the golden fixture carries them for the file it stands
    for: a valid Battery Nameplate, which by its specification has them.
    Their identifiers are 02002's, whose drop-in the collection is."""
    address = _element(dbp1_env(), "AddressInformation")
    held = {child["idShort"]: child["modelType"] for child in address.get("value", [])}
    assert held == dict.fromkeys(("Street", "Zipcode", "CityTown", "NationalCode"),
                                 "MultiLanguageProperty"), held


def test_the_golden_life_cycle_stage_is_on_the_template_s_own_list():
    """Not the template's example, `Original`, which is outside the list
    the template's concept description gives."""
    stage = _element(dbp1_env(), "LifeCycleStage")["value"]
    assert stage in ("original", "repurposed", "re-used", "remanufactured", "waste"), stage
