"""Shapes where an independent validator reads the standard differently.

Each case here is a submodel shape on which this project and at least one
other published AAS validator return different answers. The other answer is
*evidence*, never the expected value: what these tests pin is this
project's reading, so that changing it is a decision somebody makes rather
than a diff nobody noticed. Where the difference is a policy this project
has already chosen, the test names the entry that chose it.

The shapes are rebuilt from this repository's own fixtures rather than
copied in, so they have one author and stay honest when a fixture moves.
"""
from __future__ import annotations

import copy
import json

from aas_submodel_validate import runner
from aas_submodel_validate.rules import dn_tables
from builders import dn_env


def _ids(tmp_path, env, name="env.json"):
    path = tmp_path / name
    path.write_bytes(json.dumps(env).encode("utf-8"))
    report = runner.run(path)
    return ({finding.rule.id for finding in report.findings
             if finding.rule.kind != "meta"}, report)


def test_the_golden_nameplate_is_clean_on_both_readings(tmp_path):
    """The control. A disagreement on a defective file means nothing if the
    two disagree on a conformant one as well."""
    drawn, report = _ids(tmp_path, dn_env())
    assert drawn == set()
    assert report.not_asked == []


def test_a_suppliers_own_extra_element_passes_without_comment(tmp_path):
    """A vendor Property the template does not mention is not a defect
    here. The template states a minimum and not a whitelist
    (docs/divergences.md #19), so an element of the supplier's own passes
    and nothing is reported about it.

    A structural validator that treats the template as a closed set answers
    "unexpected element" on the same file. That is a different reading of
    what a template *is*, not a bug on either side, and this is the reading
    this project published."""
    env = copy.deepcopy(dn_env())
    env["submodels"][0]["submodelElements"].append({
        "idShort": "VendorExtra", "modelType": "Property",
        "valueType": "xs:string", "value": "x",
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference",
                                 "value": "urn:example:vendor-extra"}]}})
    drawn, report = _ids(tmp_path, env)
    assert drawn == set(), "a supplier's own element must not draw a finding"
    assert report.not_asked == [], (
        "an extra element must not be blamed for an absence either")


def test_a_template_identity_carried_as_a_supplemental_still_answers(tmp_path):
    """The asymmetry worth writing down.

    At the *submodel* level this project reads the main semanticId only,
    because a published template wears one of our anchors in a supplemental
    and reading those would let one template answer for another
    (docs/divergences.md #28). At the *element* level the supplementals do
    count: an element whose main identifier is the supplier's own but which
    carries the template's identifier alongside it is the element the
    template means, and refusing it would fault a file for saying more than
    the minimum.

    So `URIOfTheProduct` -- mandatory, exactly one -- is satisfied here even
    though its main identifier is unknown, and the run is clean. A validator
    that reads main identifiers only reports the mandatory element missing
    on the same file. Measured, and pinned, because the two levels reading
    differently is the kind of thing that gets "tidied" into one rule.
    """
    row = dn_tables.BY_ID["DN-E01"]
    assert row["card"] == (1, 1), "this case rests on the row being mandatory"

    env = copy.deepcopy(dn_env())
    for element in env["submodels"][0]["submodelElements"]:
        if element.get("idShort") == "URIOfTheProduct":
            element["supplementalSemanticIds"] = [element["semanticId"]]
            element["semanticId"] = {
                "type": "ExternalReference",
                "keys": [{"type": "GlobalReference",
                          "value": "urn:example:suppliers-own"}]}
    drawn, report = _ids(tmp_path, env)
    assert "DN-E01" not in drawn, (
        "the template's identifier was present as a supplemental; faulting "
        "the mandatory element would fault a file for saying more")
    assert report.not_asked == []


def test_an_element_without_an_id_short_is_judged_not_crashed_on(tmp_path):
    """A malformed file must still get a verdict. An element missing its
    `idShort` violates the metamodel, and that is relayed from the metamodel
    channel rather than invented here -- but the run completes, judges the
    submodel, and exits without an exception.

    Named because it is the case where an independent implementation raised
    a null-pointer exception instead of answering. A validator that cannot
    answer is worse than one that answers "this is malformed"."""
    env = copy.deepcopy(dn_env())
    for element in env["submodels"][0]["submodelElements"]:
        if element.get("idShort") == "URIOfTheProduct":
            del element["idShort"]
    path = tmp_path / "no-id-short.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    report = runner.run(path)          # must not raise
    assert report.submodels_judged == 1
    relayed = {finding.rule.id for finding in report.findings
               if finding.rule.kind == "meta"}
    assert relayed == {"META"}, (
        "the metamodel violation must be relayed, not silently dropped")
