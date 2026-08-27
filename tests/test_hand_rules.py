"""The rules a template file cannot express, each born red.

VDI 2770 classification is mandatory and speaks English; status values
come from a two-word vocabulary; dates are dates; files named must
exist; near-misses diagnose themselves. Every fixture is the golden
environment with exactly one thing bent.
"""
from __future__ import annotations

import copy
import json

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.rules import handover as rules_handover
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


# -- the conformant shapes these rules must stay silent about ----------------
#
# Every rule here reads a value out of the tree, and what it does when the
# value is absent, cased differently, or one of two allowed words was
# measured rather than assumed: each fixture below is silent today, and
# each names a mutation of the rule that would break that silence. Half of
# them break it by crashing -- `runner.execute` turns a rule that raises
# into an error-severity finding whose remedy reads "This is a defect in
# the validator, not in your file; please report it", which is the worst
# sentence this tool can print about a conformant file.


def _digital_files(env):
    return next(child for child in _document_version(env)["value"]
                if child.get("idShort") == "DigitalFiles")


def test_a_class_name_with_no_entries_at_all_is_reported_not_a_crash(tmp_path):
    """A MultiLanguageProperty may carry no value: the metamodel allows
    it, the generated row accepts it, and HD-D4 has to say the English
    entry is missing rather than iterate None."""
    env = copy.deepcopy(hd_env())
    for child in _classification(env)["value"]:
        if child.get("idShort") == "ClassName":
            child.pop("value", None)
    findings = _findings(tmp_path, env)
    assert "HD-D4" in findings
    assert "none" in (findings["HD-D4"].violation.detail or "")
    assert not [f for f in findings.values()
                if "could not run" in f.violation.message]


def test_a_file_with_no_value_is_silence_not_a_crash(tmp_path):
    """`File.value` is optional. HD-D7 asks whether the container holds
    what the value names; there is nothing named, so there is nothing to
    ask -- and `None.strip()` is the alternative.

    Packed, because HD-D7 says nothing at all about a bare document: the
    fixture that asked this as loose JSON was answering the rule's own
    early return and never reached the value."""
    env = copy.deepcopy(hd_env())
    _digital_files(env)["value"][0].pop("value", None)
    packed = build_aasx(tmp_path / "p.aasx",
                        payload=json.dumps(env).encode("utf-8"))
    findings = {f.id: f for f in runner.run(packed).findings}
    assert "HD-D7" not in findings
    assert not [f for f in findings.values()
                if "could not run" in f.violation.message]


def test_the_other_status_word_is_conformant(tmp_path):
    """The vocabulary is two words and only one of them was ever written
    by a fixture, so dropping the other left the suite green -- and every
    document under review would have failed."""
    env = copy.deepcopy(hd_env())
    _set_property(_document_version(env), "StatusValue", "InReview")
    assert "HD-D6" not in _findings(tmp_path, env)


def test_a_content_type_is_matched_without_regard_to_case(tmp_path):
    """Media types are case-insensitive (RFC 2045 §5.1), so a PDF/A
    rendition declared `Application/PDF` is a PDF/A rendition. HD-D10
    would otherwise tell a conformant package it has none."""
    env = copy.deepcopy(hd_env())
    _digital_files(env)["value"][0]["contentType"] = "Application/PDF"
    assert "HD-D10" not in _findings(tmp_path, env)


@pytest.mark.parametrize("pdf_first", (True, False), ids=("pdf first", "pdf second"))
def test_a_version_carrying_more_than_the_pdf_still_has_its_pdf(tmp_path, pdf_first):
    """HD-D10 asks whether a PDF/A is *among* the renditions, not whether
    it is the only one -- and a native file beside it is what VDI 2770
    recommends, not a defect.

    Both orders, because the rule walks the files and only one order can
    see it stopping after the first: with the PDF second, reading one
    file reports a conformant version as having no rendition at all."""
    env = copy.deepcopy(hd_env())
    files = _digital_files(env)
    native = copy.deepcopy(files["value"][0])
    native["contentType"] = "application/step"
    native["value"] = "/aasx/files/model.step"
    files["value"].append(native) if pdf_first else files["value"].insert(0, native)
    assert "HD-D10" not in _findings(tmp_path, env)


# -- the remedy a finding carries has to be about the finding ----------------
#
# Every one of these sentences ships to a user and none of them was read
# by a test, so each was free to describe a rule other than the one it
# sits on. Three did.


#: The four reference labels HD-D9 reads, with the list each lives in.
#: Only the first is about Entities; the walk's own docstring says the
#: other three are document-to-document references and that §2.2's
#: Entity-creation wording is not their clause. Every fixture in the
#: suite used the first, so the loop could have read one label and the
#: remedy could go on telling all four to add an Entity.
D9_LABELS = (
    ("DocumentedEntity", "DocumentedEntities",
     "https://admin-shell.io/vdi/2770/1/0/Document/DocumentedEntity",
     "https://admin-shell.io/vdi/2770/1/0/Document/DocumentedEntities", False),
    ("RefersTo", "RefersToEntities", "0173-1#02-ABK288#002",
     "0173-1#02-ABK288#002", True),
    ("BasedOn", "BasedOnReferences", "0173-1#02-ABK289#002",
     "0173-1#02-ABK289#002", True),
    ("TranslationOf", "TranslationOfEntities", "0173-1#02-ABK290#002",
     "0173-1#02-ABK290#002", True),
)


@pytest.mark.parametrize("label,list_name,item_sid,list_sid,under_version",
                         D9_LABELS, ids=[row[0] for row in D9_LABELS])
def test_a_dangling_reference_is_reported_and_names_its_own_label(
        tmp_path, label, list_name, item_sid, list_sid, under_version):
    """Each of the four, and the remedy naming the one it is about.

    `BasedOn` is where it showed: its author was being told to add an
    Entity to a list that has nothing to do with the reference. Only
    `DocumentedEntity` may say Entity, and it is the only one that does."""
    env = copy.deepcopy(hd_env())
    parent = _document_version(env) if under_version else _first_document(env)
    parent["value"].append({
        "idShort": list_name, "modelType": "SubmodelElementList",
        "typeValueListElement": "ReferenceElement",
        "semanticId": {"type": "ExternalReference", "keys": [
            {"type": "GlobalReference", "value": list_sid}]},
        "value": [{"modelType": "ReferenceElement",
                   "semanticId": {"type": "ExternalReference", "keys": [
                       {"type": "GlobalReference", "value": item_sid}]},
                   "value": {"type": "ModelReference", "keys": [
                       {"type": "Submodel", "value": "urn:example:handover"},
                       {"type": "SubmodelElementList", "value": "Documents"},
                       {"type": "SubmodelElementCollection", "value": "77"}]}}]})
    remedy = _findings(tmp_path, env)["HD-D9"].fix
    assert label in remedy
    if label != "DocumentedEntity":
        assert "Entity" not in remedy and "Entities" not in remedy


def test_the_primary_remedy_asks_for_what_the_rule_asks_for(tmp_path):
    """HD-D5 fires on several DocumentIds and none marked primary. It
    says nothing about several being marked -- measured: a file with two
    primaries draws no finding -- and the template bounds
    DocumentIsPrimary per DocumentId, not per Document.

    The remedy used to say "set it on exactly one", which is a check this
    rule does not make and a requirement this project has not vendored."""
    env = copy.deepcopy(hd_env())
    document_ids = next(child for child in _first_document(env)["value"]
                        if child.get("idShort") == "DocumentIds")
    second = copy.deepcopy(document_ids["value"][0])
    _set_property(second, "DocumentIdentifier", "OTHER-1")
    _set_property(second, "DocumentIsPrimary", "true")
    document_ids["value"].append(second)
    assert "HD-D5" not in _findings(tmp_path, env), "two primaries is not this rule"

    _set_property(document_ids["value"][0], "DocumentIsPrimary", "false")
    _set_property(second, "DocumentIsPrimary", "false")
    remedy = _findings(tmp_path, env)["HD-D5"].fix
    assert "exactly one" not in remedy
    assert "per DocumentId" in remedy


def test_the_missing_file_remedy_does_not_borrow_x4s_requirement(tmp_path):
    """HD-D7 asks whether the container holds the entry the File value
    names. Whether an aas-suppl relationship declares it is X4's
    question, and a package can satisfy both without D7 requiring one --
    the remedy said otherwise as though it were this rule's demand."""
    packed = build_aasx(tmp_path / "p.aasx",
                        payload=json.dumps(hd_env()).encode("utf-8"))
    remedy = next(f.fix for f in runner.run(packed).findings if f.id == "HD-D7")
    assert "X4" in remedy, remedy


# -- a defect in the second of several -------------------------------------
#
# Every rule below walks a list and checks each item. The golden
# environment holds one Document, one classification, one version and one
# file, and the official example's two Documents are both conformant and
# its five versions all say `released` -- so stopping after the first item
# changed nothing any fixture could see. Six loops, each of them a MUST or
# a lint that would simply go quiet.


def _second_document_missing_the_classification(env):
    documents = env["submodels"][0]["submodelElements"][0]
    second = copy.deepcopy(documents["value"][0])
    for classification in _classifications_of(second):
        _set_property(classification, "ClassificationSystem", "SomethingElse")
    documents["value"].append(second)


def _classifications_of(document):
    return next(child for child in document["value"]
                if child.get("idShort") == "DocumentClassifications")["value"]


def _add_second_classification(env, bend):
    classifications = next(child for child in _first_document(env)["value"]
                           if child.get("idShort") == "DocumentClassifications")
    extra = copy.deepcopy(classifications["value"][0])
    bend(extra)
    classifications["value"].append(extra)


def _second_classification_with_a_foreign_class_id(env):
    _add_second_classification(env, lambda c: _set_property(c, "ClassId", "99-99"))


def _second_classification_without_english(env):
    def bend(classification):
        for child in classification["value"]:
            if child.get("idShort") == "ClassName":
                child["value"] = [{"language": "de", "text": "Betrieb"}]
    _add_second_classification(env, bend)


def _second_classification_spelled_the_other_way(env):
    _add_second_classification(
        env, lambda c: _set_property(c, "ClassificationSystem", "VDI2770:2020"))


def _second_version_with_a_broken_date(env):
    versions = next(child for child in _first_document(env)["value"]
                    if child.get("idShort") == "DocumentVersions")
    second = copy.deepcopy(versions["value"][0])
    _set_property(second, "StatusSetDate", "06.02.2020")
    versions["value"].append(second)


def _a_preview_file_the_container_lacks(env):
    """The DigitalFile beside it has to be present, or the first label
    answers on its own and the second is never reached -- which is the
    thing this case exists to notice."""
    _document_version(env)["value"].append({
        "idShort": "PreviewFile", "modelType": "File", "contentType": "image/png",
        "value": "/aasx/files/absent-preview.png",
        "semanticId": {"type": "ExternalReference", "keys": [
            {"type": "GlobalReference", "value": "0173-1#02-ABK127#002"}]}})


def _a_second_digital_file_the_container_lacks(env):
    """Two files under one label, the second absent. The label loop and
    the element loop inside it are different decisions."""
    files = next(child for child in _document_version(env)["value"]
                 if child.get("idShort") == "DigitalFiles")
    second = copy.deepcopy(files["value"][0])
    second["value"] = "/aasx/files/absent-annex.pdf"
    files["value"].append(second)


@pytest.mark.parametrize("rule_id,bend,packed", (
    ("HD-D2", _second_document_missing_the_classification, False),
    ("HD-D3", _second_classification_with_a_foreign_class_id, False),
    ("HD-D4", _second_classification_without_english, False),
    ("HDL5", _second_classification_spelled_the_other_way, False),
    ("HD-D8", _second_version_with_a_broken_date, False),
    ("HD-D7", _a_preview_file_the_container_lacks, True),
    ("HD-D7", _a_second_digital_file_the_container_lacks, True),
))
def test_a_defect_in_the_second_of_several_is_still_reported(tmp_path, rule_id,
                                                             bend, packed):
    """The first of each of these is conformant and the second is not.

    HD-D7's pair is not two files but two *labels* -- `DigitalFile` and
    `PreviewFile` -- which is the same shape one level over: the rule
    walks the File rows its table declares, and reading only the first
    leaves the preview unchecked. The sibling decision was pinned for
    TD-D2 when it was found there; this is the one that was not."""
    env = copy.deepcopy(hd_env())
    bend(env)
    if packed:
        path = build_aasx(tmp_path / "p.aasx",
                          payload=json.dumps(env).encode("utf-8"),
                          files=(("aasx/files/manual.pdf", b"%PDF-1.4"),))
        found = {f.id for f in runner.run(path).findings}
    else:
        found = set(_findings(tmp_path, env))
    assert rule_id in found


def _a_second_reference_that_dangles(env):
    """One list, two references, the first resolving. The label loop and
    the element loop inside it are separate decisions."""
    def reference(target):
        return {"modelType": "ReferenceElement",
                "semanticId": {"type": "ExternalReference", "keys": [
                    {"type": "GlobalReference", "value": "0173-1#02-ABK289#002"}]},
                "value": {"type": "ModelReference", "keys": [
                    {"type": "Submodel", "value": "urn:example:handover"},
                    {"type": "SubmodelElementList", "value": "Documents"},
                    {"type": "SubmodelElementCollection", "value": target}]}}

    _document_version(env)["value"].append({
        "idShort": "BasedOnReferences", "modelType": "SubmodelElementList",
        "typeValueListElement": "ReferenceElement",
        "semanticId": {"type": "ExternalReference", "keys": [
            {"type": "GlobalReference", "value": "0173-1#02-ABK289#002"}]},
        "value": [reference("0"), reference("77")]})


def _a_second_submodel_with_a_dangling_reference(env):
    """A second Handover submodel whose reference goes nowhere. HD-D9
    walks submodels through a different helper from the rules that read
    `instances_of`, so covering one says nothing about the other."""
    second = copy.deepcopy(env["submodels"][0])
    second["id"] = "urn:example:handover:2"
    second["idShort"] = "HandoverDocumentation2"
    version = second["submodelElements"][0]["value"][0]
    version = next(child for child in version["value"]
                   if child.get("idShort") == "DocumentVersions")["value"][0]
    version["value"].append({
        "idShort": "BasedOnReferences", "modelType": "SubmodelElementList",
        "typeValueListElement": "ReferenceElement",
        "semanticId": {"type": "ExternalReference", "keys": [
            {"type": "GlobalReference", "value": "0173-1#02-ABK289#002"}]},
        "value": [{"modelType": "ReferenceElement",
                   "semanticId": {"type": "ExternalReference", "keys": [
                       {"type": "GlobalReference", "value": "0173-1#02-ABK289#002"}]},
                   "value": {"type": "ModelReference", "keys": [
                       {"type": "Submodel", "value": "urn:example:handover:2"},
                       {"type": "SubmodelElementList", "value": "Documents"},
                       {"type": "SubmodelElementCollection", "value": "77"}]}}]})
    env["submodels"].append(second)


def _a_second_submodel_missing_the_classification(env):
    """A second Handover submodel in the same environment. Every rule
    that walks submodels reads them through the same helper, and nothing
    anywhere gave it more than one to read."""
    second = copy.deepcopy(env["submodels"][0])
    second["id"] = "urn:example:handover:2"
    second["idShort"] = "HandoverDocumentation2"
    document = second["submodelElements"][0]["value"][0]
    for classification in _classifications_of(document):
        _set_property(classification, "ClassificationSystem", "SomethingElse")
    env["submodels"].append(second)


@pytest.mark.parametrize("rule_id,bend", (
    ("HD-D9", _a_second_reference_that_dangles),
    ("HD-D2", _a_second_submodel_missing_the_classification),
    ("HD-D9", _a_second_submodel_with_a_dangling_reference),
))
def test_a_defect_past_the_first_of_several_is_still_reported(tmp_path, rule_id, bend):
    """Two more loops of the same shape as the six above, one level out.

    HD-D9 walks the references inside each label as well as the labels
    themselves. And every rule that walks *submodels* had only ever been
    handed one: the golden environment carries a single Handover
    submodel, so reading the first and stopping was invisible for all of
    them."""
    env = copy.deepcopy(hd_env())
    bend(env)
    assert rule_id in _findings(tmp_path, env)


# -- three closed vocabularies, and both of their edges ---------------------
#
# Each of these is a set spelled inline, and each was guarded on one side
# only: fixtures prove the members are accepted and nothing proved a
# non-member is refused. Widening any of them is over-acceptance -- the
# rule goes on reporting, and stops reporting the thing it was written
# for.


def test_the_class_vocabulary_is_the_twelve_vdi_publishes():
    """VDI 2770 Blatt 1:2020 Table 1. The vendored template carries only
    an ExampleValue (`03-02`), not the list, so this set is read from the
    standard's own table and cannot be re-derived from bytes this project
    hash-verifies (docs/divergences.md #33).

    A thirteenth would be accepted silently, and the rule that exists to
    say "this class is not one of VDI's" would stop saying it about
    whatever was added."""
    assert frozenset({
        "01-01",
        "02-01", "02-02", "02-03", "02-04",
        "03-01", "03-02", "03-03", "03-04", "03-05", "03-06",
        "04-01",
    }) == rules_handover.VDI2770_CLASS_IDS


@pytest.mark.parametrize("value,is_primary", (
    ("true", True), ("1", True),
    ("TRUE", True), (" true ", True),
    ("false", False), ("0", False), ("yes", False), ("", False),
))
def test_which_spellings_mark_a_document_id_primary(tmp_path, value, is_primary):
    """`xs:boolean` writes true as `true` or `1`. This rule folds case
    and trims first, so `TRUE` and a padded value are read as the author
    meant them -- the metamodel refuses both spellings and the relayed
    channel says so, which is the second opinion that makes the leniency
    safe (docs/divergences.md #34).

    `yes` is not a boolean in any reading and is not accepted."""
    env = copy.deepcopy(hd_env())
    document_ids = next(child for child in _first_document(env)["value"]
                        if child.get("idShort") == "DocumentIds")
    second = copy.deepcopy(document_ids["value"][0])
    _set_property(second, "DocumentIdentifier", "OTHER-1")
    document_ids["value"].append(second)
    for entry in document_ids["value"]:
        _set_property(entry, "DocumentIsPrimary", value)
    assert ("HD-D5" not in _findings(tmp_path, env)) is is_primary


@pytest.mark.parametrize("tag,is_english", (
    ("en", True), ("EN", True), ("en-GB", True), ("en-us", True),
    ("eng", False), ("enm", False), ("english", False), ("de", False),
))
def test_which_language_tags_count_as_english(tmp_path, tag, is_english):
    """BCP 47's primary subtag for English is `en`, optionally with a
    region. `eng` is ISO 639-2 and a legal BCP 47 tag, and it is refused
    here -- the AAS metamodel names BCP 47, whose canonical form prefers
    the two-letter code (docs/divergences.md #35).

    Loosening the test to `startswith("en")` would make `enm` -- Middle
    English -- satisfy a rule about the mandatory English class name."""
    env = copy.deepcopy(hd_env())
    for child in _classification(env)["value"]:
        if child.get("idShort") == "ClassName":
            child["value"] = [{"language": tag, "text": "Operation"}]
    assert ("HD-D4" not in _findings(tmp_path, env)) is is_english
