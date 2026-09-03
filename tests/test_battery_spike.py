"""The battery-passport spike: what the template permits and the law does not.

Four things, and the fourth is why the other three are worth having.

`--profile` chooses between two templates that wear one identifier. This
project already carries one such pair (IDTA 02004 and 02035-2, both
answering `0173-1#01-AHF578#003`), and `SMT-D2` owns it: the choice rides
on the `Selection` the walk reads, so a verdict cannot move without the
sentence that explains it. A second collision is published -- IDTA 02023
and IDTA 02035-3 share one CarbonFootprint identifier -- and this project
has a table for neither side of it. Today such a submodel is reported as
nothing this tool knows, which is false: it knows exactly what it is,
twice over. `BAT-R2` says that, and `--profile` silences it.

`BAT-R8` is the product. Nine template elements are `ZeroToOne` -- the
template is content for them to be absent -- while the Battery Pass long
list and the Commission's data-point guidance mark the same attributes
mandatory under Regulation (EU) 2023/1542. A file can be conformant to
the template and non-conformant to the regulation at the same time, and
the finding says so in those words.

And a coverage note nobody may quote from a document: it is computed
from the generated table when the pack runs, and it says "floor",
because the templates carry no citation of the law and the join that
produced the table matched by name.
"""
from __future__ import annotations

import json

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.rules import battery_tables

CARBON_FOOTPRINT = "https://admin-shell.io/idta/CarbonFootprint/CarbonFootprint/1/0"
PRODUCT_CONDITION = ("urn:samm:io.admin-shell.idta.batterypass."
                     "product_condition:1.0.2#ProductCondition")
_PC = "urn:samm:io.admin-shell.idta.batterypass.product_condition:1.0.2#%s"

#: The five 02035-5 elements the table names, written out rather than
#: read from it: a fixture built from the table under test passes
#: whatever the table says, and the pin is the point.
PRODUCT_CONDITION_LAW_ELEMENTS = (
    ("EnergyThroughput", _PC % "energyThroughput"),
    ("CapacityThroughput", _PC % "capacityThroughput"),
    ("RemainingCapacity", _PC % "remainingCapacity"),
    ("RemainingPowerCapability", _PC % "remainingPowerCapability"),
    ("RemainingRoundTripEnergyEfficiency",
     _PC % "remainingRoundTripEnergyEfficiency"),
)
REMAINING_CAPACITY = _PC % "remainingCapacity"


def _external(value: str) -> dict:
    return {"type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": value}]}


def _collection(id_short: str, semantic_id: str, value=()) -> dict:
    return {"idShort": id_short, "modelType": "SubmodelElementCollection",
            "semanticId": _external(semantic_id), "value": list(value)}


def _submodel(id_short: str, semantic_id: str, elements=()) -> dict:
    return {"modelType": "Submodel", "id": "urn:example:%s" % id_short.lower(),
            "idShort": id_short, "semanticId": _external(semantic_id),
            "submodelElements": list(elements)}


def _env(*submodels) -> dict:
    return {"assetAdministrationShells": [], "submodels": list(submodels),
            "conceptDescriptions": []}


def _product_condition(*, absent=(), pad: bool = False) -> dict:
    """An 02035-5 ProductCondition carrying every element the law
    requires, minus the ones named.

    Template-conformant in every case: all five are `ZeroToOne` there, so
    an AAS tool answers "valid" whichever of them is missing. That is the
    demonstration -- the difference between the two answers is the
    product.

    `pad` puts two elements the table says nothing about in front, so a
    walk that stopped at the first element would miss what follows."""
    elements = []
    if pad:
        elements += [_collection("StateOfCharge", _PC % "stateOfCharge"),
                     _collection("StateOfHealth", _PC % "stateOfHealth")]
    elements += [_collection(id_short, semantic_id)
                 for id_short, semantic_id in PRODUCT_CONDITION_LAW_ELEMENTS
                 if id_short not in absent]
    return _submodel("ProductCondition", PRODUCT_CONDITION, elements)


def _run(tmp_path, env, **kwargs):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return runner.run(path, **kwargs)


def _ids(report):
    return {finding.id for finding in report.findings}


def _one(report, rule_id):
    (finding,) = [f for f in report.findings if f.id == rule_id]
    return finding


# -- BAT-R2: an identifier two published templates claim ----------------------

def test_a_shared_identifier_with_no_table_is_named_not_dismissed(tmp_path):
    """Both templates that claim it, by document number, in the finding.

    Without this the report says only that nothing matched a template
    this tool knows -- which is the one thing that is not true about
    this input."""
    report = _run(tmp_path, _env(_submodel("CarbonFootprint", CARBON_FOOTPRINT)))
    finding = _one(report, "BAT-R2")
    said = finding.violation.message + " " + (finding.violation.detail or "")
    assert "IDTA 02023" in said
    assert "IDTA 02035-3" in said
    assert CARBON_FOOTPRINT in said


def test_choosing_a_profile_settles_the_shared_identifier(tmp_path):
    """`--profile` is the instruction that makes the ambiguity go away.
    It does not make a table appear: the report still says nothing was
    judged by it, and saying otherwise would be the tool inventing a
    verdict.

    Through the command line, not the library. The first version of this
    called `runner.run(profile=...)` and passed while the parser was
    refusing the very value `BAT-R2`'s remedy tells a reader to type --
    the flag was never wired, and the test exercised the layer below the
    one that was broken."""
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(
        _env(_submodel("CarbonFootprint", CARBON_FOOTPRINT))).encode("utf-8"))
    from aas_submodel_validate.cli import main
    assert main([str(path), "--profile", "02035-3"]) in (0, 1)
    report = _run(tmp_path, _env(_submodel("CarbonFootprint", CARBON_FOOTPRINT)),
                  profile="02035-3")
    assert "BAT-R2" not in _ids(report)


def test_the_remedy_names_a_value_the_parser_accepts(tmp_path):
    """A remedy is only advice if the advice can be followed. This one
    tells the reader to run `--profile` with a document number, and the
    parser has its own list of what it accepts -- two places for one
    answer to be right, so this is where they are held together."""
    from aas_submodel_validate.rules.battery import SETTLES_ONLY
    report = _run(tmp_path, _env(_submodel("CarbonFootprint", CARBON_FOOTPRINT)))
    remedy = _one(report, "BAT-R2").fix
    assert "--profile" in remedy
    path = tmp_path / "probe.json"
    path.write_bytes(json.dumps(
        _env(_submodel("CarbonFootprint", CARBON_FOOTPRINT))).encode("utf-8"))
    from aas_submodel_validate.cli import main
    for key in SETTLES_ONLY:
        assert main([str(path), "--profile", key]) in (0, 1), key


def test_the_pair_this_tool_has_tables_for_is_not_this_rules_business(tmp_path):
    """IDTA 02004 and 02035-2 share an identifier too, and `SMT-D2` owns
    that one -- the choice rides on the Selection the walk reads, so the
    verdict cannot move without the sentence. Reporting it here as well
    would be two rules answering one question, and the second would be
    the one with no table behind it."""
    from builders import hd_env
    assert "BAT-R2" not in _ids(_run(tmp_path, hd_env()))


# -- BAT-R8: conformant to the template, non-conformant to the regulation -----

def test_an_element_the_template_allows_absent_and_the_law_requires(tmp_path):
    """The finding says both halves in those words, names the element,
    and cites the provision the reading comes from."""
    report = _run(tmp_path, _env(_product_condition(absent=("RemainingCapacity",))))
    finding = _one(report, "BAT-R8")
    said = finding.violation.message + " " + (finding.violation.detail or "")
    assert "RemainingCapacity" in said
    assert "conformant to the template" in said.lower()
    assert "Annex VII Part A (1)" in said
    assert str(finding.severity) == "warning", "two published readings exist (#37)"


def test_the_element_present_draws_nothing(tmp_path):
    """The negative half. A guard that fires on both shapes is not a
    guard (LESSONS L)."""
    assert "BAT-R8" not in _ids(_run(tmp_path, _env(_product_condition())))


def test_an_absence_past_the_first_element_is_still_reported(tmp_path):
    """The walk reads every element, not the first (LESSONS K). With the
    optional element absent and two others present before where it would
    have been, the rule must still say so."""
    report = _run(tmp_path, _env(
        _product_condition(absent=("RemainingCapacity",), pad=True)))
    assert "RemainingCapacity" in _one(report, "BAT-R8").violation.subject


# -- BAT-R11: the coverage note is computed, and says what it is -------------

def test_the_coverage_note_is_computed_and_calls_itself_a_floor(tmp_path):
    """Two claims, and the second is why the first matters. The numbers
    come from the generated table at runtime -- a sentence with a number
    typed into it is a sentence that is wrong the day the table moves --
    and the note says "floor", because the templates cite no law and the
    join behind the table matched attributes by name."""
    report = _run(tmp_path, _env(_product_condition(absent=("RemainingCapacity",))))
    (note,) = [n for n in report.notes if "BAT-R8" in n]
    assert "floor" in note
    assert str(len(battery_tables.LAW_REQUIRES_TEMPLATE_OPTIONAL)) in note
    assert battery_tables.SOURCE_EDITION in note


def test_both_of_the_notes_numbers_move_with_what_they_count(monkeypatch, tmp_path):
    """"Computed" has to be measured, not asserted.

    The first number is what this run examined: a ProductCondition
    carries five of the table's rows and a Nameplate one, so a note that
    said the same number for both would be quoting rather than counting.
    The second is the table's own length, and a test cannot tell a copy
    of it from a reference to it while the table sits still -- so the
    table is moved. A hard-coded nine survives everything else in this
    file."""
    five = _run(tmp_path, _env(_product_condition(absent=("RemainingCapacity",))))
    (note,) = [n for n in five.notes if "BAT-R8" in n]
    assert "read 5 of the 9" in note

    one = _run(tmp_path, _env(_submodel(
        "Nameplate", "https://admin-shell.io/idta/digitalbatterypassport/"
                     "nameplate/1/0/Nameplate")))
    (note,) = [n for n in one.notes if "BAT-R8" in n]
    assert "read 1 of the 9" in note

    monkeypatch.setattr(battery_tables, "LAW_REQUIRES_TEMPLATE_OPTIONAL",
                        battery_tables.LAW_REQUIRES_TEMPLATE_OPTIONAL[:6])
    shrunk = _run(tmp_path, _env(_product_condition()))
    (note,) = [n for n in shrunk.notes if "BAT-R8" in n]
    assert "of the 6" in note, "the total is quoted, not counted"


def test_a_run_the_pack_never_looked_at_says_nothing(tmp_path):
    """The note is about what this run examined. A file with no battery
    submodel in it gets no coverage sentence at all -- a coverage figure
    for a pack that did not run is the report claiming work it did not
    do."""
    from builders import hd_env
    assert not [n for n in _run(tmp_path, hd_env()).notes if "BAT-R8" in n]


# -- the table is generated, and says which edition it was generated from ----

@pytest.mark.parametrize("row", battery_tables.LAW_REQUIRES_TEMPLATE_OPTIONAL,
                         ids=lambda row: row["element_id_short"])
def test_every_row_carries_what_a_finding_has_to_say(row):
    """Nine rows, and a finding needs all of it: where to look, what the
    template said, who says otherwise, and under which provision."""
    assert row["submodel_semantic_id"] and row["element_semantic_id"]
    assert row["cardinality"] == "ZeroToOne"
    assert row["citations"], row["element_id_short"]
    assert row["template"].startswith("IDTA 02035-")
