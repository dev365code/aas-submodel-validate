"""What the battery-passport templates permit and the regulation does not.

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
#: The one element BAT-R8 reads, and where it sits. Two collections down
#: inside IDTA 02035-4's TechnicalData -- written out rather than read
#: from the table under test, because a fixture built from the table
#: passes whatever the table says.
TECHNICAL_DATA = "https://admin-shell.io/idta/digitalbatterypassport/TechnicalData/1/0"
PROPERTY_AREAS = "0173-1#02-ABK163#002"
ROUND_TRIP = ("urn:samm:io.admin-shell.idta.batterypass."
              "technical_data:1.0.0#roundTripEnergyEfficiency")
EFFICIENCY_FADE = "0173-1#02-ABL827#002"

#: An element the pack knows about and does not report: whether the law
#: requires it depends on the battery's category.
REMAINING_CAPACITY = ("urn:samm:io.admin-shell.idta.batterypass."
                      "product_condition:1.0.2#remainingCapacity")
PRODUCT_CONDITION = ("urn:samm:io.admin-shell.idta.batterypass."
                     "product_condition:1.0.2#ProductCondition")


def _external(value: str) -> dict:
    return {"type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": value}]}


def _collection(id_short: str, semantic_id: str, value=(), *,
                supplemental: str = None) -> dict:
    """`supplemental` moves the identifier out of `semanticId` and into a
    supplemental, leaving a vendor's own identifier in its place -- the
    shape a real instance takes when it carries both."""
    element = {"idShort": id_short, "modelType": "SubmodelElementCollection",
               "semanticId": _external(semantic_id), "value": list(value)}
    if supplemental is not None:
        element["semanticId"] = _external(supplemental)
        element["supplementalSemanticIds"] = [_external(semantic_id)]
    return element


def _submodel(id_short: str, semantic_id: str, elements=()) -> dict:
    return {"modelType": "Submodel", "id": "urn:example:%s" % id_short.lower(),
            "idShort": id_short, "semanticId": _external(semantic_id),
            "submodelElements": list(elements)}


def _env(*submodels) -> dict:
    return {"assetAdministrationShells": [], "submodels": list(submodels),
            "conceptDescriptions": []}


def _technical_data(*, fade: bool = True, pad: bool = False,
                    vendor_identified: bool = False,
                    fade_id_short: str = "EnergyRoundTripEfficiencyFade",
                    fade_semantic_id: str = EFFICIENCY_FADE) -> dict:
    """An 02035-4 TechnicalData whose round-trip efficiency collection
    does or does not carry the efficiency-fade element.

    Two collections deep, which is where the element lives. A rule that
    walked the top level alone would call it absent from the version that
    carries it -- the finding this project treats as worst.

    `pad` puts a sibling collection in front, so a walk that stopped at
    the first element would miss what follows."""
    inner = [_collection("EnergyRoundTripEfficiency", "urn:samm:io.admin-shell."
                         "idta.batterypass.technical_data:1.0.0#"
                         "energyRoundTripEfficiency")]
    if fade:
        inner.append(_collection(
            fade_id_short, fade_semantic_id,
            supplemental="urn:vendor:fade" if vendor_identified else None))
    areas = []
    if pad:
        areas.append(_collection("CapacityEnergyVoltage", "urn:samm:io."
                                 "admin-shell.idta.batterypass.technical_data:"
                                 "1.0.0#capacityEnergyVoltage"))
    areas.append(_collection("RoundTripEnergyEfficiency", ROUND_TRIP, inner))
    return _submodel("TechnicalData", TECHNICAL_DATA,
                     [_collection("TechnicalPropertyAreas", PROPERTY_AREAS, areas)])


def _product_condition() -> dict:
    """An 02035-5 ProductCondition with none of the five elements whose
    obligation depends on the battery's category. Nothing is reported
    about it, which is the point."""
    return _submodel("ProductCondition", PRODUCT_CONDITION, [])


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
    from aas_submodel_validate.rules.battery import _settles_only
    report = _run(tmp_path, _env(_submodel("CarbonFootprint", CARBON_FOOTPRINT)))
    remedy = _one(report, "BAT-R2").fix
    assert "--profile" in remedy
    path = tmp_path / "probe.json"
    path.write_bytes(json.dumps(
        _env(_submodel("CarbonFootprint", CARBON_FOOTPRINT))).encode("utf-8"))
    from aas_submodel_validate.cli import main
    for key in _settles_only():
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
    report = _run(tmp_path, _env(_technical_data(fade=False)))
    finding = _one(report, "BAT-R8")
    said = finding.violation.message + " " + (finding.violation.detail or "")
    assert "EnergyRoundTripEfficiencyFade" in said
    assert "conformant to the template" in said.lower()
    assert "Annex IV Part A (4)" in said
    assert str(finding.severity) == "warning", "two published readings exist (#37)"
    # No index id in what a reader receives: `longlist:77` resolves to a
    # file that ships in neither the wheel nor the sdist.
    assert "longlist:" not in said and "ec-datapoints:" not in said


def test_the_element_present_two_collections_down_draws_nothing(tmp_path):
    """The negative half, and the one that matters most here: the
    element sits inside TechnicalPropertyAreas/RoundTripEnergyEfficiency,
    so a walk over the submodel's own elements alone reports it absent
    from a file that carries it. A guard that fires on both shapes is not
    a guard."""
    assert "BAT-R8" not in _ids(_run(tmp_path, _env(_technical_data())))


def test_an_element_identified_through_a_supplemental_is_present(tmp_path):
    """A vendor identifier in `semanticId` and the template's in a
    supplemental. The walk has read supplementals since the day a
    conformant file built that way came back failing, and this rule read
    only the main one -- the same defect, in a new pack, with the suite
    green."""
    env = _env(_technical_data(fade=True, vendor_identified=True))
    assert "BAT-R8" not in _ids(_run(tmp_path, env))


def test_the_element_is_found_by_identifier_and_not_by_its_name(tmp_path):
    """The project's loudest rule, and every fixture above gives the
    element a matching idShort *and* a matching semanticId, so nothing
    separated them. These two do: the right identifier under a name
    nobody expects is present, and the expected name over a foreign
    identifier is not."""
    renamed = _env(_technical_data(fade=True, fade_id_short="Whatever"))
    assert "BAT-R8" not in _ids(_run(tmp_path, renamed)), \
        "matched on the name instead of the identifier"

    impostor = _env(_technical_data(fade=True, fade_semantic_id="urn:vendor:other"))
    assert "BAT-R8" in _ids(_run(tmp_path, impostor)), \
        "the name alone was taken for the element"


def test_an_absence_past_the_first_element_is_still_reported(tmp_path):
    """The walk reads every element, not the first. With a sibling
    property area in front of the one that would have carried it, the
    rule must still say so."""
    report = _run(tmp_path, _env(_technical_data(fade=False, pad=True)))
    assert "EnergyRoundTripEfficiencyFade" in _one(report, "BAT-R8").violation.subject


def test_an_element_whose_obligation_depends_on_the_category_is_not_reported(tmp_path):
    """Eight of the nine disagreements are conditional on the battery's
    category, and no rule here reads one. Remaining capacity is required
    for light means of transport and voluntary for electric vehicles;
    the capacity threshold for exhaustion is required for EVs and marked
    *not to be filled* for everything else. Reporting either without the
    category tells one manufacturer to add what another's guidance
    forbids.

    So: a ProductCondition carrying none of its five draws nothing from
    this rule -- and the coverage note says how many were withheld, which
    is the difference between a silence and a secret."""
    report = _run(tmp_path, _env(_product_condition()))
    assert "BAT-R8" not in _ids(report)
    assert not [n for n in report.notes if "BAT-R8" in n], \
        "a submodel this rule reports nothing about is not coverage"


def test_two_submodels_of_one_kind_do_not_inflate_what_was_read(tmp_path):
    """Two battery modules in one file is an ordinary shape, and the note
    counted rows per submodel and added them up: "read 10 of the 9"."""
    report = _run(tmp_path, _env(_technical_data(fade=False),
                                 _technical_data(fade=False)))
    (note,) = [n for n in report.notes if "BAT-R8" in n]
    assert "looked at 1 of the 1" in note


def test_the_set_of_packs_the_walk_answers_for_is_the_registry_s(tmp_path):
    """`BAT-R2` steps aside for a collision the walk can judge, and it
    decides that from a list of document numbers written out by hand.
    Nothing derived it, so a pack landing or leaving moved one list and
    not the other -- and a stale entry makes this rule say "no table for
    either" about a collision that now has one.

    Held against the two registries that actually know."""
    from aas_submodel_validate.rules import battery, detect, profiles
    registered = {pack.name for pack in detect.PACKS}
    registered |= {profile.default_name for profile in profiles.PROFILES}
    registered |= {profile.name for profile in profiles.PROFILES}
    named = {name.split(" (")[-1].rstrip(")") for name in registered}
    assert battery._known_to_the_walk() == named, sorted(named)
    # And the shape it is read for: every document number in it is one a
    # collision could name, spelled the way `SHARED_SUBMODEL_IDS` spells
    # its claimants.
    assert all(name.startswith("IDTA ") for name in named), sorted(named)


# -- the coverage note is computed, and says what it is ---------------------

def test_the_coverage_note_is_computed_and_calls_itself_a_floor(tmp_path):
    """Two claims, and the second is why the first matters. The numbers
    come from the generated tables at runtime -- a sentence with a number
    typed into it is a sentence that is wrong the day the table moves --
    and the note says "floor", because the templates cite no law and the
    join behind the table matched attributes by name."""
    report = _run(tmp_path, _env(_technical_data(fade=False)))
    (note,) = [n for n in report.notes if "BAT-R8" in n]
    assert "floor" in note
    assert str(len(battery_tables.LAW_REQUIRES_TEMPLATE_OPTIONAL)) in note
    assert str(len(battery_tables.CONDITIONAL_ON_CATEGORY)) in note
    assert battery_tables.SOURCE_EDITION in note


def test_the_note_counts_what_it_reads_and_what_it_withholds(monkeypatch, tmp_path):
    """"Computed" has to be measured, not asserted.

    Three numbers, three ways to be quoted rather than counted: what this
    run examined, how many the pack can report at all, and how many it is
    holding back. The tables are moved to see the last two follow -- a
    test cannot tell a copy of a length from a reference to it while the
    table sits still."""
    report = _run(tmp_path, _env(_technical_data(fade=False)))
    (note,) = [n for n in report.notes if "BAT-R8" in n]
    assert "looked at 1 of the 1" in note
    assert "8 more are known to disagree" in note

    monkeypatch.setattr(battery_tables, "CONDITIONAL_ON_CATEGORY",
                        battery_tables.CONDITIONAL_ON_CATEGORY[:3])
    report = _run(tmp_path, _env(_technical_data(fade=False)))
    (note,) = [n for n in report.notes if "BAT-R8" in n]
    assert "3 more are known to disagree" in note, "the withheld count is quoted"


def test_a_run_the_pack_never_looked_at_says_nothing(tmp_path):
    """The note is about what this run examined. A file with no battery
    submodel in it gets no coverage sentence at all -- a coverage figure
    for a pack that did not run is the report claiming work it did not
    do."""
    from builders import hd_env
    assert not [n for n in _run(tmp_path, hd_env()).notes if "BAT-R8" in n]


# -- the table is generated, and says which edition it was generated from ----

@pytest.mark.parametrize("row", battery_tables.LAW_REQUIRES_TEMPLATE_OPTIONAL
                         + battery_tables.CONDITIONAL_ON_CATEGORY,
                         ids=lambda row: row["element_id_short"])
def test_every_row_carries_what_a_finding_has_to_say(row):
    """Nine rows across the two tables, and a finding needs all of it:
    where to look, what the template said, and under which provision."""
    assert row["submodel_semantic_id"] and row["element_semantic_id"]
    assert row["cardinality"] == "ZeroToOne"
    assert row["citations"], row["element_id_short"]
    assert row["template"].startswith("IDTA 02035-")
    assert row["categories"], "a row with no category reading cannot be sorted"


def test_each_row_carries_its_own_editions_identifier():
    """Two templates are pinned at more than one edition, and the
    generator joined a row to its template by document number alone --
    the last edition in the index won, so a row could carry one
    edition's version string beside another edition's identifier and
    hash. `--check` cannot see that: it compares bytes to bytes, and
    both are what the generator would write.

    Where an identifier carries its own version, it has to be the row's.
    IDTA 02035-5 writes `:1.0.2#` in its SAMM URN; 02035-4 writes no
    version at all, and those rows are simply skipped here rather than
    given a weaker check that would pass for anything."""
    import re
    rows = (battery_tables.LAW_REQUIRES_TEMPLATE_OPTIONAL
            + battery_tables.CONDITIONAL_ON_CATEGORY)
    checked = 0
    for row in rows:
        found = re.search(r":(\d+\.\d+\.\d+)#", row["submodel_semantic_id"])
        if not found:
            continue
        checked += 1
        assert found.group(1) == row["template_version"].lstrip("V"), \
            (row["element_id_short"], row["submodel_semantic_id"],
             row["template_version"])
    assert checked, "no row's identifier carries a version any more"


def test_the_table_does_not_depend_on_the_index_s_ordering():
    """The generator joins a row to its template by document number and
    edition. By number alone the last edition in the index wins, which
    today happens to be the right one -- a latent defect the content
    cannot show, because the content is identical until the index is
    written in a different order.

    So the order is changed. Reversing the template map must leave the
    generated table byte-identical; keyed by number alone it does not."""
    import importlib.util
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "extract_battery_rules", root / "tools" / "extract_battery_rules.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    if not generator.DATA.is_dir():
        pytest.skip("the indexes are not in this tree (an sdist ships the table)")

    straight = generator.render()
    original = generator._load

    def reversed_templates(name):
        loaded = original(name)
        if name == "requirements-idta.json":
            templates = loaded["counts"]["templates"]
            loaded["counts"]["templates"] = dict(reversed(list(templates.items())))
        return loaded

    generator._load = reversed_templates
    try:
        assert generator.render() == straight
    finally:
        generator._load = original


def test_the_two_tables_are_sorted_by_whether_a_category_decides_it():
    """The split is the safety, so it is asserted rather than trusted.

    A row belongs in the reported table only when every category in every
    source that cites it reads as required. The capacity threshold for
    exhaustion is the case that makes this worth a test: the guidance
    marks it *not to be filled* for light means of transport, so
    reporting it without the category tells an LMT manufacturer to add a
    field their guidance forbids."""
    required = {"required", "required-by-batteries-regulation"}
    for row in battery_tables.LAW_REQUIRES_TEMPLATE_OPTIONAL:
        assert all(verdict in required for _name, verdict in row["categories"]), \
            row["element_id_short"]
    for row in battery_tables.CONDITIONAL_ON_CATEGORY:
        assert any(verdict not in required for _name, verdict in row["categories"]), \
            row["element_id_short"]
    threshold = [row for row in battery_tables.CONDITIONAL_ON_CATEGORY
                 if row["element_id_short"] == "CapacityThresholdExhaustion"]
    assert threshold, "the row that inverts is not among the withheld"
    assert ("LMT", "not-to-be-filled") in threshold[0]["categories"]


def test_the_divergence_row_counts_the_index_it_cites():
    """Row 36 states two numbers about the requirements index, and both
    were wrong.

    It said the index holds ten template editions and that this
    repository vendors three of them. The index holds twelve, and one of
    the three vendored templates is among them -- 02004 is indexed at a
    different edition than the one vendored here, and 02003 is not
    indexed at all. An evidence ledger whose numbers do not survive
    being counted is worth less than no ledger.
    """
    import hashlib
    import json
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    index = root / "data" / "battery-passport" / "requirements-idta.json"
    if not index.is_file():
        pytest.skip("the indexes are not in this tree (an sdist ships the table)")
    editions = json.loads(index.read_text(encoding="utf-8"))["counts"]["templates"]
    digests = {entry["sha256"] for entry in editions.values()}

    vendored = sorted((root / "src" / "aas_submodel_validate" / "data" / "smt")
                      .rglob("template.json"))
    assert vendored, "no vendored template to compare"
    shared = sum(1 for path in vendored
                 if hashlib.sha256(path.read_bytes()).hexdigest() in digests)

    row = [line for line in (root / "docs" / "divergences.md")
           .read_text(encoding="utf-8").splitlines() if line.startswith("| 36 |")]
    assert row, "divergence 36 is gone"
    numbers = re.search(r"indexes (\w+) template editions; this repository "
                        r"vendors (\w+) of those", row[0])
    assert numbers, "row 36 no longer states both counts in a readable shape"
    words = {"one": 1, "two": 2, "three": 3, "ten": 10, "eleven": 11,
             "twelve": 12, "thirteen": 13}
    assert words[numbers.group(1)] == len(editions)
    assert words[numbers.group(2)] == shared
