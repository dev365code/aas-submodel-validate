"""Every pack names an element whose identifier nearly matches a row.

02004's and 02003's packs have registered a near-miss lint from the start
(`HDL2`, `TDL1`), and 02035-2's inherits 02004's (`DBP2L2`). The other
five did not, so in them an identifier one version suffix or one last
segment off took rows out of the run with nothing among the findings
naming the element that did it: what did was in `summary` -- a record
in `unmatchedElements`, and `scopeNotExamined` where its row went
unentered -- which a pipeline reading findings never sees, and a drifted
element that left nothing unasked -- a property or a file, with no rows
beneath it, or a container beside an intact sibling that had asked its
rows -- left not even that (docs/divergences.md #23). Each now
registers the same lint, with the same title, clause and remedy, so the
finding reads alike whichever
pack drew it.
"""
from __future__ import annotations

import copy
import json

import pytest

from aas_submodel_validate import runner
from builders import contact_env, dn_env, hs_env, pcf_env, sn_env


def _find(node, short):
    if isinstance(node, dict):
        if node.get("idShort") == short:
            return node
        for value in node.values():
            found = _find(value, short)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find(value, short)
            if found is not None:
                return found
    return None


#: (lint id, fixture, element to drift, identifier it carries, the drift)
CASES = [
    ("DNL1", dn_env, "SerialNumber", "0112/2///61987#ABA951#009",
     "0112/2///61987#ABA951#008"),
    ("CIL1", contact_env, "TelephoneNumber", "0173-1#02-AAO136#002",
     "0173-1#02-AAO136#003"),
    ("PCFL1", pcf_env, "ProductCarbonFootprints",
     "https://admin-shell.io/idta/CarbonFootprint/ProductCarbonFootprints/1/0",
     "https://admin-shell.io/idta/CarbonFootprint/ProductCarbonFootprints/1/1"),
    ("HSL1", hs_env, "Gearbox", "https://admin-shell.io/idta/HierarchicalStructures/Node/1/0",
     "https://admin-shell.io/idta/HierarchicalStructures/Node/1/1"),
    ("SNL1", sn_env, "URIOfTheProduct", "0173-1#02-AAY811#001", "0173-1#02-AAY811#002"),
]


def _run(tmp_path, env, name):
    path = tmp_path / name
    path.write_text(json.dumps(env), encoding="utf-8")
    return runner.run(path)


@pytest.mark.parametrize("lint, fixture, short, carried, drifted", CASES,
                         ids=[case[0] for case in CASES])
def test_a_drifted_identifier_is_named_by_the_pack_s_lint(tmp_path, lint, fixture, short,
                                                          carried, drifted):
    env = copy.deepcopy(fixture())
    element = _find(env, short)
    assert element["semanticId"]["keys"][0]["value"] == carried, element["semanticId"]
    element["semanticId"]["keys"][0]["value"] = drifted
    report = _run(tmp_path, env, "%s.json" % lint)
    named = [f for f in report.findings if f.id == lint]
    assert len(named) == 1, [(f.id, f.violation.subject) for f in report.findings]
    [finding] = named
    assert finding.severity.value == "warning", finding.severity
    assert finding.violation.subject.endswith("/" + short), finding.violation.subject
    assert drifted in finding.violation.detail and carried in finding.violation.detail


@pytest.mark.parametrize("lint, fixture", [(case[0], case[1]) for case in CASES],
                         ids=[case[0] for case in CASES])
def test_the_golden_fixture_draws_no_near_miss(tmp_path, lint, fixture):
    report = _run(tmp_path, fixture(), "%s-golden.json" % lint)
    assert not [f for f in report.findings if f.id == lint], report.findings


def _items(env, list_short):
    return _find(env, list_short)["value"]


def _bump(element, old, new):
    key = element["semanticId"]["keys"][0]
    assert old in key["value"], key["value"]
    key["value"] = key["value"].replace(old, new)


def test_a_drifted_list_item_is_named_by_its_index(tmp_path):
    """Every case above drifts one element that has an idShort. A list
    item has none, its subject ends in its index, and a version bump on
    every item of a list is the likeliest drift there is."""
    env = copy.deepcopy(pcf_env())
    [footprint] = _items(env, "ProductCarbonFootprints")
    _bump(footprint, "ProductCarbonFootprint/1/0", "ProductCarbonFootprint/1/1")
    named = [f.violation.subject for f in _run(tmp_path, env, "pcf-item.json").findings
             if f.id == "PCFL1"]
    assert named == ["CarbonFootprint/ProductCarbonFootprints/[0]"], named

    env = copy.deepcopy(dn_env())
    [marking] = _items(env, "Markings")
    _bump(marking, "#001", "#002")
    named = [f.violation.subject for f in _run(tmp_path, env, "dn-item.json").findings
             if f.id == "DNL1"]
    assert named == ["Nameplate/Markings/[0]"], named


def test_two_items_carrying_one_drift_are_both_named(tmp_path):
    """Two elements, two findings. `summary.unmatchedElements` holds one
    record for the pair -- they carry one drift between them -- and the
    lint names each element it is about."""
    env = copy.deepcopy(pcf_env())
    items = _items(env, "ProductCarbonFootprints")
    items.append(copy.deepcopy(items[0]))
    for footprint in items:
        _bump(footprint, "ProductCarbonFootprint/1/0", "ProductCarbonFootprint/1/1")
    named = [f.violation.subject for f in _run(tmp_path, env, "pcf-items.json").findings
             if f.id == "PCFL1"]
    assert named == ["CarbonFootprint/ProductCarbonFootprints/[0]",
                     "CarbonFootprint/ProductCarbonFootprints/[1]"], named


def test_every_pack_s_near_miss_lint_is_tdl1_under_another_name():
    """The same kind, severity, title, clause, remedy and route as `TDL1`,
    compared with it rather than copied from it: a remedy pinned as a
    literal held while `TDL1`'s own was reworded, and nothing held the
    title, the clause or the kind -- a lint registered as a template rule
    read `kind: template` in the JSON and every test passed."""
    from aas_submodel_validate.registry import all_rules

    rules = {rule.id: rule for rule in all_rules()}

    def shape(rule):
        return (rule.kind, rule.prio, rule.title, rule.spec, rule.fix, rule.path)
    for lint in ("DNL1", "CIL1", "PCFL1", "HSL1", "SNL1", "DBP5L1"):
        assert shape(rules[lint]) == shape(rules["TDL1"]), lint


def test_a_tie_goes_to_the_row_nothing_here_matched(tmp_path):
    """`InstallationDath` is one edit from `InstallationDate` and one from
    `InstallationPath`. The file carries its `InstallationDate`, so the
    drift is of the row nothing here matched: naming the first of the two
    told the file to become the date it already carried, and a file that
    followed that remedy drew two errors."""
    env = copy.deepcopy(sn_env())
    _bump(_find(env, "InstallationPath"), "SoftwareNameplateInstance/InstallationPath",
          "SoftwareNameplateInstance/InstallationDath")
    [lint] = [f for f in _run(tmp_path, env, "sn-tie.json").findings if f.id == "SNL1"]
    assert lint.violation.detail.endswith("SoftwareNameplateInstance/InstallationPath"), \
        lint.violation.detail


def test_a_version_drift_of_a_matched_row_does_not_end_the_search(tmp_path):
    """An element one version off `URIOfTheProduct`, which the file
    carries, and -- through a supplemental -- one version off
    `ManufacturerName`, which it lacks. Both are as near as anything can
    be, so the row nothing matched is named, and the missing
    `ManufacturerName` is graded as the correction it is. Stopping at the
    first version drift named the product URI the file already carried."""
    env = copy.deepcopy(sn_env())
    kind = _find(env, "SoftwareNameplateType")
    kind["value"] = [child for child in kind["value"]
                     if child.get("idShort") != "ManufacturerName"]
    kind["value"].append({
        "idShort": "Drifted", "modelType": "MultiLanguageProperty",
        "semanticId": {"type": "ExternalReference", "keys": [
            {"type": "GlobalReference", "value": "0173-1#02-AAY811#002"}]},
        "supplementalSemanticIds": [{"type": "ExternalReference", "keys": [
            {"type": "GlobalReference", "value": "0173-1#02-AAO677#003"}]}],
        "value": [{"language": "en", "text": "x"}]})
    report = _run(tmp_path, env, "sn-two-drifts.json")
    [lint] = [f for f in report.findings if f.id == "SNL1"]
    assert lint.violation.detail.endswith("0173-1#02-AAO677#002"), lint.violation.detail
    [missing] = [f for f in report.findings if f.id == "SN-E03"]
    assert missing.fixability == 2, (missing.fixability, missing.fixability_why)


def test_matched_means_matched_in_that_place(tmp_path):
    """Two configuration entries; in the second, `ConfigurationType` is
    written `ConfigurationTyth`, two edits from its own row and two from
    the identifier the template gives `ConfigurationURI`. The first entry
    matched both rows, and that is not this place: here only the URI is
    carried, so the drift is of `ConfigurationType`. Read run-wide, both
    rows had matched, the first won, and the remedy made the entry's URI
    a second one."""
    env = copy.deepcopy(sn_env())
    paths = _find(env, "ConfigurationPaths")
    second = copy.deepcopy(paths["value"][0])
    kind = next(child for child in second["value"] if child.get("idShort") == "ConfigurationType")
    _bump(kind, "SoftwareNameplateInstance/ConfigurationType",
          "SoftwareNameplateInstance/ConfigurationTyth")
    paths["value"].append(second)
    [lint] = [f for f in _run(tmp_path, env, "sn-two-entries.json").findings if f.id == "SNL1"]
    assert lint.violation.detail.endswith("SoftwareNameplateInstance/ConfigurationType"), \
        lint.violation.detail


def test_a_tie_moves_the_charge_with_the_name(tmp_path):
    """`SoftwareNameplateInstance` misspelt `SoftwareNameplatIance` is as
    near its own row as `SoftwareNameplateType`'s, which the file carries.
    Taken for the type, the instance's rules were charged to nothing;
    taken for the instance, they are charged to it."""
    env = copy.deepcopy(sn_env())
    instance = _find(env, "SoftwareNameplateInstance")
    _bump(instance, "SoftwareNameplate/SoftwareNameplateInstance",
          "SoftwareNameplate/SoftwareNameplatIance")
    report = _run(tmp_path, env, "sn-instance-tie.json")
    [record] = [r for r in report.unmatched if r.subject.endswith("SoftwareNameplateInstance")]
    assert record.resembles.endswith("SoftwareNameplate/SoftwareNameplateInstance"), record.resembles
    assert "SN-E21" in record.unasked, record.unasked


def test_a_tie_between_rows_nothing_matched_goes_to_the_first(tmp_path):
    """With `InstallationDate` gone too, nothing here matched either row,
    and the first in the table is named."""
    env = copy.deepcopy(sn_env())
    instance = _find(env, "SoftwareNameplateInstance")
    instance["value"] = [child for child in instance["value"]
                         if child.get("idShort") != "InstallationDate"]
    _bump(_find(env, "InstallationPath"), "SoftwareNameplateInstance/InstallationPath",
          "SoftwareNameplateInstance/InstallationDath")
    [lint] = [f for f in _run(tmp_path, env, "sn-tie-both.json").findings if f.id == "SNL1"]
    assert lint.violation.detail.endswith("SoftwareNameplateInstance/InstallationDate"), \
        lint.violation.detail


def test_the_nearest_row_is_the_one_the_rest_of_the_report_uses(tmp_path):
    """The row the lint names is the row the drift is charged under, and
    the one a missing sibling's grade asks about. `InstallationDate` is
    missing and `InstallationPaths` resembles `InstallationPath`, not it:
    its error is a 5, nothing here resembling it, where the first row near
    enough graded it a 2 -- one element carrying an identifier close to
    its own -- beside a lint naming the other row."""
    env = copy.deepcopy(sn_env())
    instance = _find(env, "SoftwareNameplateInstance")
    instance["value"] = [child for child in instance["value"]
                         if child.get("idShort") != "InstallationDate"]
    _bump(_find(env, "InstallationPath"), "SoftwareNameplateInstance/InstallationPath",
          "SoftwareNameplateInstance/InstallationPaths")
    report = _run(tmp_path, env, "sn-charge.json")
    [missing] = [f for f in report.findings if f.id == "SN-E25"]
    assert missing.fixability == 5, (missing.fixability, missing.fixability_why)


def test_the_nearest_row_is_the_one_named(tmp_path):
    """02007's rows under one collection share a stem and differ by a few
    letters. `InstallationPaths` is one edit from `InstallationPath` and
    three from `InstallationDate`, which comes first in the table; the
    first row near enough was the one named, and the remedy told the file
    to become the date it already carried."""
    env = copy.deepcopy(sn_env())
    element = _find(env, "InstallationPath")
    _bump(element, "SoftwareNameplateInstance/InstallationPath",
          "SoftwareNameplateInstance/InstallationPaths")
    report = _run(tmp_path, env, "sn-nearest.json")
    [lint] = [f for f in report.findings if f.id == "SNL1"]
    assert lint.violation.detail.endswith("SoftwareNameplateInstance/InstallationPath"), \
        lint.violation.detail
