"""Spec-fidelity fixes the review found by reading the PDF against the code."""
from __future__ import annotations

import copy
import json

from aas_submodel_validate import runner
from aas_submodel_validate.rules import engine, hd_tables, td_tables
from builders import hd_env


def _findings(tmp_path, env):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return {f.id: f for f in runner.run(path).findings}


def _classification(env):
    return env["submodels"][0]["submodelElements"][0]["value"][0]["value"][1]["value"][0]


def _version(env):
    return env["submodels"][0]["submodelElements"][0]["value"][0]["value"][2]["value"][0]


def _set(container, id_short, value):
    for child in container["value"]:
        if child.get("idShort") == id_short:
            child["value"] = value
            return
    raise KeyError(id_short)


# -- HD-D4: "EN is mandatory" is about English, not the tag string "en" -------

def test_english_with_a_region_subtag_satisfies_hd_d4(tmp_path):
    env = copy.deepcopy(hd_env())
    for child in _classification(env)["value"]:
        if child.get("idShort") == "ClassName":
            child["value"] = [{"language": "en-US", "text": "Operation"}]
    assert "HD-D4" not in _findings(tmp_path, env)


def test_uppercase_english_tag_satisfies_hd_d4(tmp_path):
    env = copy.deepcopy(hd_env())
    for child in _classification(env)["value"]:
        if child.get("idShort") == "ClassName":
            child["value"] = [{"language": "EN", "text": "Operation"}]
    assert "HD-D4" not in _findings(tmp_path, env)


def test_a_class_name_only_in_german_still_fails_hd_d4(tmp_path):
    env = copy.deepcopy(hd_env())
    for child in _classification(env)["value"]:
        if child.get("idShort") == "ClassName":
            child["value"] = [{"language": "de", "text": "Betrieb"}]
    assert "HD-D4" in _findings(tmp_path, env)


# -- HD-D5: xs:boolean true is {true, 1} -------------------------------------

def test_primary_flag_as_one_counts_as_primary(tmp_path):
    env = copy.deepcopy(hd_env())
    ids_list = env["submodels"][0]["submodelElements"][0]["value"][0]["value"][0]
    ids_list["value"][0]["value"] = [c for c in ids_list["value"][0]["value"]
                                     if c.get("idShort") != "DocumentIsPrimary"]
    ids_list["value"][0]["value"].append({
        "idShort": "DocumentIsPrimary", "modelType": "Property",
        "valueType": "xs:boolean", "value": "1",
        "semanticId": {"type": "ExternalReference", "keys": [
            {"type": "GlobalReference", "value": "0173-1#02-ABH995#003"}]}})
    second = copy.deepcopy(ids_list["value"][0])
    _set(second, "DocumentIdentifier", "XF90-885")
    ids_list["value"].append(second)
    assert "HD-D5" not in _findings(tmp_path, env)


# -- HD-D8: xs:date allows extended/negative years; bounds the offset --------

def test_a_negative_year_is_a_valid_xs_date(tmp_path):
    env = copy.deepcopy(hd_env())
    _set(_version(env), "StatusSetDate", "-0001-01-01")
    assert "HD-D8" not in _findings(tmp_path, env)


def test_an_out_of_range_timezone_offset_is_rejected(tmp_path):
    env = copy.deepcopy(hd_env())
    _set(_version(env), "StatusSetDate", "2020-02-06+15:00")
    assert "HD-D8" in _findings(tmp_path, env)


def test_a_normal_offset_is_accepted(tmp_path):
    env = copy.deepcopy(hd_env())
    _set(_version(env), "StatusSetDate", "2020-02-06+02:00")
    assert "HD-D8" not in _findings(tmp_path, env)


# -- HDL3 / HD-D1: name the template's real reference type -------------------

def test_the_official_example_no_longer_gets_a_false_hdl3():
    """The example's submodel semanticId is a ModelReference -- and so is
    the template's. Once the expected type is read from the template
    instead of hardcoded to ExternalReference, the drift lint stops firing
    a finding that was never real."""
    report = runner.run("tests/corpus/idta/02004/example.json")
    assert [f for f in report.findings if f.id == "HDL3"] == []


def test_the_presence_fix_does_not_claim_an_externalreference():
    from aas_submodel_validate.registry import all_rules
    from aas_submodel_validate.rules import detect  # noqa: F401 - registers the rules
    d1 = next(r for r in all_rules() if r.id == "SMT-D1")
    assert "as the published template declares it" not in d1.fix
    assert "ExternalReference" not in d1.fix


# -- X2: an OPC relationship target relative to the source part resolves ------

def test_a_relative_spec_target_resolves(tmp_path):
    """OPC resolves a non-slash target against the source part's directory.
    A package whose origin rels names `env.json` (no leading slash) points
    at aasx/env.json, and the chain must resolve, not report a broken one."""
    import zipfile

    from builders import ORIGIN_REL, SPEC_REL, env_json, rels
    path = tmp_path / "rel.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels", rels([(SPEC_REL, "env.json")]))
        archive.writestr("aasx/env.json", env_json())
    ids = {f.id for f in runner.run(path).findings}
    assert "X2" not in ids


import pytest  # noqa: E402

VDI_CLASS_IDS = ["01-01", "02-01", "02-02", "02-03", "02-04",
                 "03-01", "03-02", "03-03", "03-04", "03-05", "03-06", "04-01"]


@pytest.mark.parametrize("class_id", VDI_CLASS_IDS)
def test_every_published_vdi_class_id_is_accepted(tmp_path, class_id):
    """The acceptance direction: all twelve Table 1 ids must pass HD-D3.
    Without this only the three in the golden and example were exercised,
    and dropping one from the set stayed green."""
    env = copy.deepcopy(hd_env())
    _set(_classification(env), "ClassId", class_id)
    assert "HD-D3" not in _findings(tmp_path, env)


def test_a_single_document_id_needs_no_primary_flag(tmp_path):
    """HD-D5 only wants a primary flag when there are at least two ids; a
    lone id with no flag is fine (§2.6). The boundary was never tested."""
    env = copy.deepcopy(hd_env())
    ids_list = env["submodels"][0]["submodelElements"][0]["value"][0]["value"][0]
    ids_list["value"][0]["value"] = [c for c in ids_list["value"][0]["value"]
                                     if c.get("idShort") != "DocumentIsPrimary"]
    assert "HD-D5" not in _findings(tmp_path, env)


def test_a_near_valid_date_still_fires_hd_d8(tmp_path):
    """The false-negative direction: a month with one digit is not xs:date."""
    env = copy.deepcopy(hd_env())
    _set(_version(env), "StatusSetDate", "2020-2-06")
    assert "HD-D8" in _findings(tmp_path, env)


# -- HDL2: a near-miss must be near, not merely same-namespace -----------------

def _root_element(env, sid_value):
    env = copy.deepcopy(env)
    env["submodels"][0]["submodelElements"].append({
        "idShort": "X", "modelType": "SubmodelElementList",
        "typeValueListElement": "Entity",
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference", "value": sid_value}]},
        "value": []})
    return env


def test_a_genuine_singular_plural_typo_is_a_near_miss(tmp_path):
    env = _root_element(hd_env(),
                        "https://admin-shell.io/vdi/2770/1/0/EntityForDocumentation")
    assert "HDL2" in _findings(tmp_path, env)


def test_an_unrelated_neighbour_in_the_namespace_is_not_a_near_miss(tmp_path):
    env = _root_element(hd_env(), "https://admin-shell.io/vdi/2770/1/0/Documentation")
    assert "HDL2" not in _findings(tmp_path, env)


def test_a_wholly_different_last_segment_is_not_a_near_miss(tmp_path):
    env = _root_element(hd_env(),
                        "https://admin-shell.io/vdi/2770/1/0/SomethingCompletelyElse")
    assert "HDL2" not in _findings(tmp_path, env)


# -- HDL2: how near "near" is, at both ends of a segment's length -------------
#
# The three fixtures above all sit far from the boundary: one typo at
# distance 3 against a bound of 6, and two neighbours nowhere near it. So
# every constant in `max(3, len(tail) // 4)` could be moved -- the floor
# to 0, the divisor to 5, the `max` to `min` -- and all three stayed
# green. What each part of that expression is for is asserted here, with
# the identifiers taken from the vendored tables rather than invented,
# because a bound tested against made-up strings is a bound tested
# against nothing.


def test_a_template_version_drift_in_an_iri_is_a_near_miss():
    """The floor exists for short segments, and IDTA writes the shortest
    one there is: a submodel template's IRI ends in its version, so the
    last segment of ClassificationSystemUrl is a single character.

    A quarter of one character is nothing. Scale alone would put the
    bound at zero and refuse to call `.../2/1` near `.../2/0` -- and a
    file written against the next revision of a template would then
    simply not match, with no line in the report saying why. That is the
    silent pass this lint exists to prevent."""
    expected = td_tables.BY_LABEL["ClassificationSystemUrl"]["sid"]
    assert expected.endswith("/2/0"), "the value this bound was measured on moved"
    drifted = expected[:-1] + "1"
    assert engine._near_miss({drifted}, [expected]) == (drifted, expected)


def test_two_different_irdis_under_one_list_are_not_a_near_miss():
    """And the other half of the same expression: the segment comparison
    is for IRIs, and the guard that says so is load-bearing.

    ECLASS composites are built the same shape -- a list's identifier,
    a slash, its item's -- so without the guard they take the IRI branch
    too. Two items belonging to different lists differ in one character
    of a twenty-character tail, which is well inside the bound, and they
    are not a typo for each other: `AHF580` and `AHF581` are separate
    ECLASS properties. Version drift in an IRDI is real and is caught
    above this, by the stem comparison, which is what knows a `#003` from
    a `#004`."""
    expected = hd_tables.BY_LABEL["DocumentId"]["sid"]
    other_item = hd_tables.BY_LABEL["DocumentClassification"]["sid"].rsplit("/", 1)[1]
    seen = expected.rsplit("/", 1)[0] + "/" + other_item
    assert seen != expected and "://" not in seen
    assert engine._near_miss({seen}, [expected]) is None


# -- HD-D10: VDI 2770 wants a PDF/A rendition (§2.1) --------------------------

def test_a_version_whose_only_file_is_not_pdf_is_flagged(tmp_path):
    env = copy.deepcopy(hd_env())
    for child in _version(env)["value"]:
        if child.get("idShort") == "DigitalFiles":
            child["value"][0]["contentType"] = "application/step"
    finding = _findings(tmp_path, env)["HD-D10"]
    assert str(finding.severity) == "warning"


def test_a_version_with_a_pdf_rendition_passes_hd_d10(tmp_path):
    assert "HD-D10" not in _findings(tmp_path, hd_env())


def test_the_official_examples_cad_model_draws_the_pdfa_warning():
    """The ammunition: the published example's CAD-model versions ship STEP
    only, so §2.1's PDF/A expectation is unmet -- a finding no other tool
    currently reports about the reference material."""
    report = runner.run("tests/corpus/idta/02004/example.json")
    d10 = [f for f in report.findings if f.id == "HD-D10"]
    assert d10
    assert all("CADmodel" in (f.violation.subject or "") for f in d10)
