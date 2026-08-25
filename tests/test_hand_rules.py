"""The rules a template file cannot express, each born red.

VDI 2770 classification is mandatory and speaks English; status values
come from a two-word vocabulary; dates are dates; files named must
exist; near-misses diagnose themselves. Every fixture is the golden
environment with exactly one thing bent.
"""
from __future__ import annotations

import copy
import json

from aas_submodel_validate import runner
from builders import build_aasx, hd_env


def _write(tmp_path, env):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return path


def _findings(tmp_path, env):
    return {f.id: f for f in runner.run(_write(tmp_path, env)).findings}


def _first_document(env):
    return env["submodels"][0]["submodelElements"][0]["value"][0]


def _set_property(container: dict, id_short: str, value):
    for child in container["value"]:
        if child.get("idShort") == id_short:
            child["value"] = value
            return
    raise KeyError(id_short)


def _classification(env):
    return _first_document(env)["value"][1]["value"][0]


def _document_version(env):
    return _first_document(env)["value"][2]["value"][0]


def test_a_document_without_a_vdi2770_classification_fails(tmp_path):
    env = copy.deepcopy(hd_env())
    _set_property(_classification(env), "ClassificationSystem", "MyCorp Classes 1.0")
    finding = _findings(tmp_path, env)["HD-D2"]
    assert str(finding.severity) == "error"
    assert "VDI 2770" in finding.rule.fix


def test_a_class_id_outside_the_twelve_fails(tmp_path):
    env = copy.deepcopy(hd_env())
    _set_property(_classification(env), "ClassId", "99-99")
    finding = _findings(tmp_path, env)["HD-D3"]
    assert "99-99" in (finding.violation.detail or finding.violation.message)


def test_a_class_name_without_english_fails(tmp_path):
    env = copy.deepcopy(hd_env())
    for child in _classification(env)["value"]:
        if child.get("idShort") == "ClassName":
            child["value"] = [{"language": "de", "text": "Betrieb"}]
    assert "HD-D4" in _findings(tmp_path, env)


def test_two_document_ids_but_no_primary_warns(tmp_path):
    env = copy.deepcopy(hd_env())
    ids_list = _first_document(env)["value"][0]
    first = ids_list["value"][0]
    first["value"] = [c for c in first["value"] if c.get("idShort") != "DocumentIsPrimary"]
    second = copy.deepcopy(first)
    _set_property(second, "DocumentIdentifier", "XF90-885")
    ids_list["value"].append(second)
    finding = _findings(tmp_path, env)["HD-D5"]
    assert str(finding.severity) == "warning"


def test_a_status_value_outside_the_vocabulary_warns(tmp_path):
    env = copy.deepcopy(hd_env())
    _set_property(_document_version(env), "StatusValue", "Draft")
    finding = _findings(tmp_path, env)["HD-D6"]
    assert str(finding.severity) == "warning"
    assert "InReview" in finding.fix


def test_a_digital_file_missing_from_the_container_fails(tmp_path):
    packed = build_aasx(tmp_path / "p.aasx",
                        payload=json.dumps(hd_env()).encode("utf-8"))
    assert "HD-D7" in {f.id for f in runner.run(packed).findings}


def test_a_digital_file_present_in_the_container_passes(tmp_path):
    packed = build_aasx(tmp_path / "p.aasx",
                        payload=json.dumps(hd_env()).encode("utf-8"),
                        files=(("aasx/files/manual.pdf", b"%PDF-1.4"),))
    ids = {f.id for f in runner.run(packed).findings}
    assert "HD-D7" not in ids and "X4" not in ids


def test_an_environment_json_cannot_answer_d7_and_says_nothing(tmp_path):
    assert "HD-D7" not in _findings(tmp_path, copy.deepcopy(hd_env()))


def test_a_malformed_status_date_fails(tmp_path):
    env = copy.deepcopy(hd_env())
    _set_property(_document_version(env), "StatusSetDate", "06.02.2020")
    assert "HD-D8" in _findings(tmp_path, env)


def test_an_impossible_calendar_date_fails(tmp_path):
    env = copy.deepcopy(hd_env())
    _set_property(_document_version(env), "StatusSetDate", "2020-02-31")
    assert "HD-D8" in _findings(tmp_path, env)


def test_an_off_pattern_idshort_is_information_not_error(tmp_path):
    env = copy.deepcopy(hd_env())
    _document_version(env)["value"].append({
        "idShort": "Preview", "modelType": "File",
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference",
                                 "value": "0173-1#02-ABK127#002"}]},
        "contentType": "image/jpeg", "value": "/aasx/files/preview.jpg"})
    finding = _findings(tmp_path, env)["HDL1"]
    assert str(finding.severity) == "info"


def test_the_templates_own_singular_spelling_is_not_flagged(tmp_path):
    env = copy.deepcopy(hd_env())
    _document_version(env)["value"].append({
        "idShort": "PreviewFile", "modelType": "File",
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference",
                                 "value": "0173-1#02-ABK127#002"}]},
        "contentType": "image/jpeg", "value": "/aasx/files/preview.jpg"})
    assert "HDL1" not in _findings(tmp_path, env)


def test_an_iri_near_miss_is_diagnosed(tmp_path):
    """The official example's own defect: the Entities list carries the
    child's singular IRI. It must not silently not-match."""
    env = copy.deepcopy(hd_env())
    env["submodels"][0]["submodelElements"].append({
        "idShort": "Entites", "modelType": "SubmodelElementList",
        "typeValueListElement": "Entity",
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference",
                                 "value": "https://admin-shell.io/vdi/2770/1/0/EntityForDocumentation"}]},
        "value": []})
    finding = _findings(tmp_path, env)["HDL2"]
    assert "EntitiesForDocumentation" in (finding.violation.detail or "")


def test_an_eclass_version_drift_is_diagnosed(tmp_path):
    env = copy.deepcopy(hd_env())
    _document_version(env)["value"].append({
        "idShort": "StatusValue2", "modelType": "Property", "valueType": "xs:string",
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference",
                                 "value": "0173-1#02-ABI001#002"}]},
        "value": "Released"})
    assert "HDL2" in _findings(tmp_path, env)


def test_an_external_reference_where_the_template_says_model_is_information(tmp_path):
    """The template's submodel semanticId is a ModelReference; an instance
    that uses ExternalReference instead identifies the same template, so
    it is an information lint (HDL3), not a failure."""
    env = copy.deepcopy(hd_env())
    submodel = env["submodels"][0]
    submodel["semanticId"] = {"type": "ExternalReference",
                              "keys": [{"type": "GlobalReference",
                                        "value": "0173-1#01-AHF578#003"}]}
    finding = _findings(tmp_path, env)["HDL3"]
    assert str(finding.severity) == "info"


def test_a_duplicate_document_id_pair_warns(tmp_path):
    env = copy.deepcopy(hd_env())
    documents = env["submodels"][0]["submodelElements"][0]["value"]
    documents.append(copy.deepcopy(documents[0]))
    finding = _findings(tmp_path, env)["HDL4"]
    assert "XF90-884" in (finding.violation.detail or "")


def test_a_declared_supplementary_part_that_is_absent_warns(tmp_path):
    packed = build_aasx(tmp_path / "p.aasx",
                        payload=json.dumps(hd_env()).encode("utf-8"),
                        files=(("aasx/files/manual.pdf", b"%PDF-1.4"),),
                        suppl_targets=["aasx/files/manual.pdf",
                                       "aasx/files/ghost.step"])
    findings = {f.id: f for f in runner.run(packed).findings}
    assert findings["X4"].violation.subject == "aasx/files/ghost.step"


# --- HD-D9: entity references resolve --------------------------------------

def _with_entities_and_reference(target_idshort="Machine"):
    env = copy.deepcopy(hd_env())
    submodel = env["submodels"][0]
    submodel["submodelElements"].append({
        "idShort": "Entities", "modelType": "SubmodelElementList",
        "typeValueListElement": "Entity",
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference",
                                 "value": "https://admin-shell.io/vdi/2770/1/0/EntitiesForDocumentation"}]},
        "value": [{"modelType": "Entity", "entityType": "CoManagedEntity",
                   "idShort": "Machine",
                   "semanticId": {"type": "ExternalReference",
                                  "keys": [{"type": "GlobalReference",
                                            "value": "https://admin-shell.io/vdi/2770/1/0/EntityForDocumentation"}]}}]})
    _first_document(env)["value"].append({
        "idShort": "DocumentedEntities", "modelType": "SubmodelElementList",
        "typeValueListElement": "ReferenceElement",
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference",
                                 "value": "https://admin-shell.io/vdi/2770/1/0/Document/DocumentedEntities"}]},
        "value": [{"modelType": "ReferenceElement",
                   "semanticId": {"type": "ExternalReference",
                                  "keys": [{"type": "GlobalReference",
                                            "value": "https://admin-shell.io/vdi/2770/1/0/Document/DocumentedEntity"}]},
                   "value": {"type": "ModelReference",
                             "keys": [{"type": "Submodel", "value": "urn:example:handover"},
                                      {"type": "SubmodelElementList", "value": "Entities"},
                                      {"type": "Entity", "value": target_idshort}]}}]})
    return env


def test_an_entity_reference_that_resolves_is_clean(tmp_path):
    assert "HD-D9" not in _findings(tmp_path, _with_entities_and_reference())


def test_a_dangling_entity_reference_warns(tmp_path):
    finding = _findings(tmp_path, _with_entities_and_reference("Ghost"))["HD-D9"]
    assert str(finding.severity) == "warning"
    assert "Ghost" in (finding.violation.detail or "")


def test_a_reference_into_another_submodel_is_honestly_skipped(tmp_path):
    env = _with_entities_and_reference()
    reference = _first_document(env)["value"][-1]["value"][0]["value"]
    reference["keys"][0]["value"] = "urn:someone:elses:submodel"
    reference["keys"][2]["value"] = "Ghost"
    assert "HD-D9" not in _findings(tmp_path, env)


# --- readings forced by the official material -------------------------------

def test_sml_children_without_semantic_ids_still_count(tmp_path):
    """The official example ships every list child without a semanticId
    (their identity is the list's); counting them as absent failed the
    reference material five rules at a time. In a list scope the child
    row matches by element kind when no semanticId is there to speak."""
    env = copy.deepcopy(hd_env())
    version = _document_version(env)
    for child in version["value"]:
        if child.get("idShort") in ("Language", "DigitalFiles"):
            for grandchild in child["value"]:
                grandchild.pop("semanticId", None)
    ids = set(_findings(tmp_path, env))
    assert "HD-E16" not in ids and "HD-E33" not in ids


def test_an_empty_file_value_is_not_a_missing_part(tmp_path):
    """The official example's CAD document carries PreviewFile value=""
    -- an empty value names nothing, which is not the same defect as
    naming something absent."""
    env = copy.deepcopy(hd_env())
    _document_version(env)["value"].append({
        "idShort": "PreviewFile", "modelType": "File",
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference",
                                 "value": "0173-1#02-ABK127#002"}]},
        "contentType": "image/jpeg", "value": ""})
    packed = build_aasx(tmp_path / "p.aasx", payload=json.dumps(env).encode("utf-8"),
                        files=(("aasx/files/manual.pdf", b"%PDF-1.4"),))
    assert "HD-D7" not in {f.id for f in runner.run(packed).findings}


def test_the_templates_example_spelling_counts_as_vdi_but_draws_the_lint(tmp_path):
    """§2.3's identifying value is "VDI 2770 Blatt 1:2020"; the template's
    own ExampleValue -- and therefore the official example -- writes
    "VDI2770:2020". Both count as the mandatory system (failing the
    official example on the template's own example spelling would be
    dogma), and the non-canonical spelling draws HDL5 instead."""
    env = copy.deepcopy(hd_env())
    _set_property(_classification(env), "ClassificationSystem", "VDI2770:2020")
    findings = _findings(tmp_path, env)
    assert "HD-D2" not in findings
    hdl5 = findings["HDL5"]
    assert str(hdl5.severity) == "warning"
    assert "VDI 2770 Blatt 1:2020" in hdl5.fix


def test_class_rules_still_apply_under_the_example_spelling(tmp_path):
    env = copy.deepcopy(hd_env())
    _set_property(_classification(env), "ClassificationSystem", "VDI2770:2020")
    _set_property(_classification(env), "ClassId", "99-99")
    assert "HD-D3" in _findings(tmp_path, env)


def test_list_children_resolve_by_index_even_when_misnamed(tmp_path):
    """ModelReferences address list children by position. The official
    example writes "Documents / 0 / ..." while its list children carry
    (illegal) idShorts -- the index must still resolve, because the
    idShort is the AASd-120 violation, not the reference."""
    env = _with_entities_and_reference()
    reference = _first_document(env)["value"][-1]["value"][0]["value"]
    reference["keys"] = [
        {"type": "Submodel", "value": "urn:example:handover"},
        {"type": "SubmodelElementList", "value": "Documents"},
        {"type": "SubmodelElementCollection", "value": "0"},
    ]
    # golden's Document SMC has no idShort, so also pin the harder shape:
    _first_document(env)["idShort"] = "Datasheet"
    assert "HD-D9" not in _findings(tmp_path, env)


def test_an_element_level_reference_type_drift_is_linted(tmp_path):
    """The engine records reference-type drift per element, not only on
    the submodel; give a Property a ModelReference where the template
    declares ExternalReference and HDL3 must fire for that element."""
    env = copy.deepcopy(hd_env())
    version = _document_version(env)
    for child in version["value"]:
        if child.get("idShort") == "Version":
            child["semanticId"]["type"] = "ModelReference"
            child["semanticId"]["keys"][0]["type"] = "GlobalReference"
    findings = _findings(tmp_path, env)
    assert "HDL3" in findings
    assert "Version" in (findings["HDL3"].violation.subject or "")
