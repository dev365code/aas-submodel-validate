"""The rules a template file cannot express, each born red.

VDI 2770 classification is mandatory and speaks English; status values
come from a two-word vocabulary; dates are dates; files named must
exist; near-misses diagnose themselves. Every fixture is the golden
environment with exactly one thing bent.
"""
from __future__ import annotations

import copy
import json

import aas_core3.verification as verification
import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.rules import handover as handover_rules
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



def _file_values(env):
    """Every File value the environment names, canonicalised the way the
    container does."""
    found = set()

    def walk(node):
        if isinstance(node, dict):
            if node.get("modelType") == "File" and isinstance(node.get("value"), str):
                found.add(node["value"].lstrip("/"))
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(env)
    return found

def test_a_file_the_archive_holds_needs_no_suppl_relationship(tmp_path):
    """HD-D7 asks whether the container holds the entry the File value
    names. Whether an `aas-suppl` relationship declares it is X4's
    question, and its remedy demanded one as though it were this rule's.

    Measured rather than read off the sentence: a package holding the
    parts and declaring no relationships at all draws nothing from this
    rule. The sentence itself is held in the remedy census, because an
    assertion that the word "X4" appears in it passes for the borrowing
    it was written to forbid."""
    env = copy.deepcopy(hd_env())
    named = sorted(_file_values(env))
    assert named, "the fixture stopped naming files"
    packed = build_aasx(tmp_path / "p.aasx",
                        payload=json.dumps(env).encode("utf-8"),
                        files=[(name, b"%PDF-1.4") for name in named],
                        suppl_targets=[])
    assert "HD-D7" not in {f.id for f in runner.run(packed).findings}


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
    """IDTA 02004-2-0 §2.3, Table 1 -- the freely published table this
    project validates against; VDI 2770 Blatt 1:2020 itself was not
    opened. The vendored template carries only an ExampleValue (`03-02`),
    not the list, so the set cannot be re-derived from bytes this project
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
    meant them.

    The metamodel refuses both spellings and the relayed channel reports
    that -- asserted below, because a divergence resting on a second
    opinion has to notice the second opinion going away, and this one
    did not. It is a weaker backstop than the word suggests: `META` is a
    `SHOULD`, so it reaches a reader and not an exit code (#17, and
    `tests/test_values.py`). What makes the leniency cost nothing here is
    that HD-D5 is a `SHOULD` too (docs/divergences.md #34).

    `yes` is not a boolean in any reading and is not accepted."""
    env = copy.deepcopy(hd_env())
    document_ids = next(child for child in _first_document(env)["value"]
                        if child.get("idShort") == "DocumentIds")
    second = copy.deepcopy(document_ids["value"][0])
    _set_property(second, "DocumentIdentifier", "OTHER-1")
    document_ids["value"].append(second)
    for entry in document_ids["value"]:
        _set_property(entry, "DocumentIsPrimary", value)
    findings = _findings(tmp_path, env)
    assert ("HD-D5" not in findings) is is_primary
    if value in ("TRUE", " true "):
        assert "META" in findings, "the second opinion went away"




def test_a_list_child_is_told_to_delete_its_id_short_not_rename_it(tmp_path):
    """Five of the six rows that carry an idShort pattern sit directly
    inside a SubmodelElementList, where AASd-120 forbids an idShort at
    all -- so on those rows this lint can only fire on a file that
    already breaks the metamodel.

    Its one standing sentence said "any unique idShort is legal; this is
    tidiness, not conformance", and told the author to rename. Doing that
    leaves the violation exactly where it was. Measured here: the meta
    channel raises AASd-120 on the same file, six times, and it raises
    nothing once the idShorts are gone."""
    env = copy.deepcopy(hd_env())
    for element in _every_list_child(env):
        element["idShort"] = "Whatever"
    findings = _findings(tmp_path, env)
    assert "Remove this idShort" in findings["HDL1"].fix
    assert "AASd-120" in findings["HDL1"].fix
    assert "META" in findings, "the metamodel channel stopped seeing AASd-120"


def _every_list_child(env):
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("modelType") == "SubmodelElementList":
                found.extend(c for c in node.get("value", []) if isinstance(c, dict))
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(env)
    assert found, "the fixture stopped holding a list"
    return found


def test_a_class_id_under_another_system_is_not_this_rules_business(tmp_path):
    """The twelve are the twelve of a *published edition*, and this rule
    only ever looks at a classification whose system the file has already
    declared to be that edition.

    Which decides what a thirteenth class would cost. A later VDI 2770
    naming more classes names itself differently, and a classification
    declaring that system is not one this rule reads -- so the set going
    stale is not how a conformant file gets failed here. What would do it
    is the set being wrong about the edition it claims, which is a
    question about where the twelve were read, not about when."""
    env = copy.deepcopy(hd_env())
    classification = _classification(env)
    _set_property(classification, "ClassificationSystem", "VDI 2770 Blatt 1:2027")
    _set_property(classification, "ClassId", "05-01")
    findings = _findings(tmp_path, env)
    assert "HD-D3" not in findings
    # Escaping D3 is not passing. With no classification in the accepted
    # spellings the mandatory-classification rule fires, at MUST: a
    # later-edition file fails *as not being this template*, which is
    # the template's verdict and the honest reading of what the pinned
    # twelve cost (docs/divergences.md #33). The first version of this
    # test asserted the silence alone, which read as "such a file is
    # fine" -- it is not, and saying so is the point.
    assert "HD-D2" in findings


@pytest.mark.parametrize("tag,is_english", (
    ("en", True), ("EN", True), ("en-GB", True), ("EN-GB", True),
    ("eN", False), ("En", False),
    ("eng", False), ("enm", False), ("english", False), ("de", False),
    ("", False),
))
def test_which_language_tags_count_as_english(tmp_path, tag, is_english):
    """What counts as English is aas-core3's answer, not one written here
    (docs/divergences.md #35). These rows say what that answer is, and
    the second assertion says whose it is.

    `eng` was accepted here for a while, on the reading that BCP 47's
    grammar admits a three-letter primary subtag and that a file using
    it passes the metamodel's verification. Both are true and neither is
    the question. The grammar is well-formedness -- `english` clears it
    too, the primary subtag being `2*3ALPHA / 4ALPHA / 5*8ALPHA` -- and
    the verification never asks whether a ClassName is *English*. Where
    the metamodel does need to know, it ships `is_bcp_47_for_english`,
    and that says `en` or `EN` with an optional region."""
    env = copy.deepcopy(hd_env())
    for child in _classification(env)["value"]:
        if child.get("idShort") == "ClassName":
            child["value"] = [{"language": tag, "text": "Operation"}]
    assert ("HD-D4" not in _findings(tmp_path, env)) is is_english
    # And it is the metamodel's verdict, not a copy that agreed on the
    # day it was written: the rule holds the function itself, so an
    # aas-core3 upgrade that moves the answer moves the rule and turns
    # these rows red together. Asserting only the function's behaviour
    # was measured insufficient -- a hand-rolled copy inside the rule
    # passed it.
    assert handover_rules._english is verification.is_bcp_47_for_english
    assert verification.is_bcp_47_for_english(tag) is is_english


def test_a_class_name_of_the_wrong_kind_is_the_files_defect_not_the_tools(tmp_path):
    """A rule that meets the wrong kind of element must say whose defect
    it is, and it said the wrong one.

    `ClassName` is a MultiLanguageProperty, and a file declaring it a
    `Property` gave `AttributeError: 'str' object has no attribute
    'language'` -- caught by the isolation that turns a raising rule into
    a finding, and then reported with the remedy that isolation carries:
    "This is a defect in the validator, not in your file; please report
    it." It is a defect in the file, the generated rule beside it already
    says which element is the wrong kind, and the reader is sent to open
    an issue instead. From a plant that is a trip outside to ask a
    question nobody can answer.
    """
    env = copy.deepcopy(hd_env())
    classification = _classification(env)
    for child in classification["value"]:
        if child.get("idShort") == "ClassName":
            child["modelType"] = "Property"
            child["value"] = "Operation"
            child["valueType"] = "xs:string"
            break
    else:                                        # pragma: no cover - fixture
        raise AssertionError("the fixture has no ClassName to bend")

    findings = _findings(tmp_path, env)
    for finding in findings.values():
        assert "could not run" not in finding.violation.message, \
            "%s crashed on an element of the wrong kind" % finding.id
        assert "defect in the validator" not in (finding.fix or ""), \
            "%s blames the tool for something in the file" % finding.id
    # And the file is still wrong, so something has to say so.
    assert any(f.severity is not None and f.id.startswith("HD-E")
               for f in findings.values()), \
        "nothing reported an element declared as the wrong kind"


@pytest.mark.parametrize("element,kind", [
    ("ClassName", "Range"),
    ("ClassName", "Capability"),
    ("ClassName", "Operation"),
    ("ClassName", "Entity"),
    ("ClassName", "SubmodelElementCollection"),
    ("ClassId", "MultiLanguageProperty"),
    ("DocumentClassifications", "MultiLanguageProperty"),
])
def test_no_rule_blames_itself_for_an_element_of_the_wrong_kind(tmp_path,
                                                               element, kind):
    """The first attempt at this fixed one shape and claimed all of them.

    Its commit said eight rules crashed on wrong `modelType` and none
    does now. Sweeping every kind the metamodel has says otherwise:
    seven more crashed, because the guard was written where the value
    was read and the hole was one level up -- `child_of` iterated
    `getattr(element, "value", None) or []` where its sibling
    `children_of` had checked `isinstance(value, list)` since it was
    written. A `Range` has no `value` at all; a `Property` has a string,
    and iterating a string yields characters.

    Every one of these reported "the rule itself could not run -- a
    defect in the validator, not in your file; please report it", about
    a defect in the file that the generated rule beside it names
    exactly."""
    env = copy.deepcopy(hd_env())

    def bend(node):
        if isinstance(node, dict):
            if node.get("idShort") == element:
                node["modelType"] = kind
                node.pop("value", None)
                node.pop("valueType", None)
                return True
            return any(bend(v) for v in node.values())
        if isinstance(node, list):
            return any(bend(v) for v in node)
        return False

    assert bend(env), "the fixture has no %s to bend" % element
    findings = _findings(tmp_path, env)
    for finding in findings.values():
        assert "could not run" not in finding.violation.message, \
            "%s crashed on a %s declared as a %s" % (finding.id, element, kind)
