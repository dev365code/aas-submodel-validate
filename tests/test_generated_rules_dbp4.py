"""Every generated 02035-4 Technical Data rule fires, and the golden
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
from aas_submodel_validate.rules import dbp4_tables
from builders import dbp4_env, inject, strip_row, stub_of
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
    assert set(_ids(tmp_path, dbp4_env())) == set()


def test_the_golden_environment_is_metamodel_clean_too(tmp_path):
    assert [f for f in _run(tmp_path, dbp4_env()).findings if f.rule.kind == "meta"] == []


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


#: The one row whose own identifier another row also holds: stubs of it
#: carry the ECLASS IRDI the template gives it beside its own, because an
#: element carrying its own is counted by `DBP4-E27` too (#60, and the
#: test of that below).
_SPELLED_BY_ITS_OTHER_IDENTIFIER = {"DBP4-E30": "0173-1#02-ABL836#001"}


def _stub(row) -> dict:
    stub = stub_of(row)
    if row["id"] in _SPELLED_BY_ITS_OTHER_IDENTIFIER:
        stub["semanticId"]["keys"][0]["value"] = _SPELLED_BY_ITS_OTHER_IDENTIFIER[row["id"]]
    return stub


@pytest.mark.parametrize("row", dbp4_tables.ROWS, ids=[r["id"] for r in dbp4_tables.ROWS])
def test_every_generated_rule_fires(tmp_path, row):
    env = copy.deepcopy(dbp4_env())
    low, high = row["card"]
    parent = dbp4_tables.BY_ID.get(row["parent"])
    if low >= 1:
        strip_row(env, row, tables=dbp4_tables)
    elif high is not None:
        inject(env, parent, [_stub(row), _stub(row)], tables=dbp4_tables)
    else:
        inject(env, parent, [_mismatched(row)], tables=dbp4_tables)
    assert row["id"] in _ids(tmp_path, env)


def test_the_golden_fixture_carries_every_row(tmp_path):
    from aas_submodel_validate.loader import load
    from aas_submodel_validate.rules import engine, profiles

    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(dbp4_env()).encode("utf-8"))
    ctx = runner.Context(load(path), profiles.Selection(None))
    instances = engine.analyze(ctx, dbp4_tables)["instances"]
    missing = [row["id"] for row in dbp4_tables.ROWS if not instances.get(row["id"])]
    assert not missing, "the golden fixture no longer carries: %s" % missing


def test_a_submodel_named_as_the_template_is_told_matching_goes_by_identifier(tmp_path):
    """Named `BatteryTechnicalData` and carrying another identifier, a
    submodel is told what the other packs' namesakes are: the name is not
    what matches, and the fix is a one-field change."""
    env = copy.deepcopy(dbp4_env())
    env["submodels"][0]["semanticId"]["keys"][0]["value"] = "urn:vendor:thing:1"
    report = _run(tmp_path, env)
    [finding] = [f for f in report.findings if f.id == "SMT-D1"]
    assert "is *named* BatteryTechnicalData" in finding.violation.detail, \
        finding.violation.detail
    assert finding.fixability == 2, finding.fixability


# -- where the template disagrees with itself or its specification (#60) -----

def _element(children, id_short):
    return next(element for element in children if element.get("idShort") == id_short)


def _top(env, id_short):
    return _element(env["submodels"][0]["submodelElements"], id_short)


def _reference(value):
    return {"type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": value}]}


def _findings(report):
    return sorted((f.id, f.violation.message) for f in report.findings if f.rule.kind != "meta")


def test_a_module_resistance_increase_spelled_as_the_template_spells_it_is_two(tmp_path):
    """The template gives `InternalResistanceIncreaseOfBatteryModuleLevel`
    the identifier `...#initialInternalResistanceOfBatteryModule`, which is
    also what it gives `InitialInternalResistanceOnBatteryModuleLevel` as a
    supplemental. An element carrying it counts as both, so a file written
    as the template writes it is told it has two initial module
    resistances: the template's defect, handed to the file."""
    env = copy.deepcopy(dbp4_env())
    resistance = _element(_top(env, "TechnicalPropertyAreas")["value"], "Resistance")
    increase = _element(resistance["value"], "InternalResistanceIncreaseOfBatteryModuleLevel")
    increase["semanticId"] = _reference(
        "urn:samm:io.admin-shell.idta.batterypass.technical_data:1.0.0"
        "#initialInternalResistanceOfBatteryModule")
    assert _findings(_run(tmp_path, env)) == [(
        "DBP4-E27",
        "the template expects at most one 'InitialInternalResistanceOnBatteryModuleLevel' "
        "here; found 2")]


def test_a_warranty_is_optional_because_the_template_states_no_cardinality(tmp_path):
    """`WarrantyInformation` carries no cardinality qualifier, which reads
    0..* (#50): leave it out and nothing is said of it but that the run
    did not look there."""
    env = copy.deepcopy(dbp4_env())
    general = _top(env, "GeneralInformation")
    general["value"] = [e for e in general["value"] if e.get("idShort") != "WarrantyInformation"]
    report = _run(tmp_path, env)
    assert _findings(report) == []
    places = [place["label"] for place in report.as_dict()["summary"]["scopeNotExamined"]]
    assert places == ["WarrantyInformation"], places


def test_a_collection_known_only_by_the_identifier_six_share_is_taken_for_the_first(tmp_path):
    """Six collections carry `0173-1#02-ABL358#002/0173-1#01-AHX773#002`
    beside their own identifiers. `Temperature` known by it alone matches
    the first row that holds it, `CapacityEnergyVoltage`: the file is told
    it has two of those, that the second lacks voltages, and that it has
    no temperature at all."""
    env = copy.deepcopy(dbp4_env())
    temperature = _element(_top(env, "TechnicalPropertyAreas")["value"], "Temperature")
    temperature["semanticId"] = _reference("0173-1#02-ABL358#002/0173-1#01-AHX773#002")
    found = [finding for finding, _message in _findings(_run(tmp_path, env))]
    assert found == ["DBP4-E12", "DBP4-E13", "DBP4-E14", "DBP4-E15", "DBP4-E16",
                     "DBP4-E39"], found


def test_a_warranty_known_by_the_manufacturer_name_s_identifier_is_a_second_name(tmp_path):
    """`WarrantyInformation` carries `ManufacturerName`'s own identifier,
    `0173-1#02-AAO677#004`, as a supplemental; known by it alone, the
    warranty is counted as a second manufacturer name, of the wrong kind."""
    env = copy.deepcopy(dbp4_env())
    warranty = _element(_top(env, "GeneralInformation")["value"], "WarrantyInformation")
    warranty["semanticId"] = _reference("0173-1#02-AAO677#004")
    assert _findings(_run(tmp_path, env)) == [
        ("DBP4-E02", "'ManufacturerName' must be a Property"),
        ("DBP4-E02", "the template expects exactly one 'ManufacturerName' here; found 2")]


@pytest.mark.parametrize("element, version, lost", [
    ("BatteryCategory", "1.0.1", ["DBP4-E05"]),
    ("WarrantyInformation", "1.0.0", []),
], ids=["category-at-1.0.1", "warranty-at-1.0.0"])
def test_a_samm_identifier_of_the_other_release_is_a_near_miss(tmp_path, element, version,
                                                               lost):
    """The part's SAMM namespace is at 1.0.0 for most elements and at 1.0.1
    for the warranty the 1.0.1 release added, and the specification gives
    the submodel's own SAMM identifier at 1.0.1. An element written at the
    other release matches no row: `DBP4L1` names it, and a mandatory one is
    reported missing."""
    env = copy.deepcopy(dbp4_env())
    target = _element(_top(env, "GeneralInformation")["value"], element)
    name = target["semanticId"]["keys"][0]["value"].rsplit("#", 1)[1]
    target["semanticId"] = _reference(
        "urn:samm:io.admin-shell.idta.batterypass.technical_data:%s#%s" % (version, name))
    found = [finding for finding, _message in _findings(_run(tmp_path, env))]
    assert found == sorted(lost + ["DBP4L1"]), found
