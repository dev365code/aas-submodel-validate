"""The rules a template file cannot express, each born red.

VDI 2770 classification is mandatory and speaks English; status values
come from a two-word vocabulary; dates are dates; files named must
exist; near-misses diagnose themselves. Every fixture is the golden
environment with exactly one thing bent.
"""
from __future__ import annotations

import copy
import json

import aas_core3.jsonization as jsonization
import aas_core3.verification as verification
import pytest

from aas_submodel_validate import loader, runner
from aas_submodel_validate.rules import engine, hd_tables
from aas_submodel_validate.rules import handover as handover_rules
from aas_submodel_validate.rules import handover as rules_handover
from builders import build_aasx, hd_env
from verdicts import by_id


def _write(tmp_path, env):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return path


def _findings(tmp_path, env):
    """Every finding by rule id, through the shared reader.

    Almost every test in this file starts from an environment dict
    rather than from a path, which is all this adds.
    """
    return by_id(runner.run(_write(tmp_path, env)))


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


def test_a_classification_with_no_class_id_is_the_cardinality_rules_finding(tmp_path):
    """`HD-D3` refuses a `ClassId` outside VDI 2770's twelve, and `None`
    is not a value outside them -- it is no value at all, which the
    generated cardinality rule already asks about.

    Without the `is not None` guard the rule reports "ClassId is not a
    VDI 2770 Blatt 1:2020 class" with a detail of `None` against a
    classification that simply has not stated one, at MUST, over the top
    of the rule whose question that is. Nothing measured the guard.

    The other edge is `test_a_class_id_outside_the_twelve_fails` above;
    asserted here in one line as well, because silence from a rule that
    had stopped working looks the same.
    """
    env = copy.deepcopy(hd_env())
    classification = _classification(env)
    classification["value"] = [child for child in classification["value"]
                               if child.get("idShort") != "ClassId"]
    findings = _findings(tmp_path, env)
    assert "HD-D3" not in findings, (
        "a classification that states no ClassId was told its ClassId is "
        "not one of the twelve")
    assert any(found.startswith("HD-E") for found in findings), (
        "nothing reported the missing ClassId at all, so the silence "
        "above is not the guard working")


def test_a_class_name_without_english_fails(tmp_path):
    env = copy.deepcopy(hd_env())
    for child in _classification(env)["value"]:
        if child.get("idShort") == "ClassName":
            child["value"] = [{"language": "de", "text": "Betrieb"}]
    found = _findings(tmp_path, env)
    assert "HD-D4" in found
    # The languages the ClassName does carry, which is what the reader
    # checks against. Dropped, the line said "none" and nothing noticed.
    assert found["HD-D4"].violation.detail == "languages present: de"


@pytest.mark.parametrize("unreadable", ("no ClassName", "wrong kind"),
                         ids=("absent", "wrong kind"))
def test_a_classification_this_rule_cannot_read_does_not_hide_the_next(
        tmp_path, unreadable):
    """`HD-D4` walks a document's VDI classifications, and two kinds of
    classification are not its finding: one with no `ClassName` at all
    (the generated cardinality rule's) and one whose `ClassName` is the
    wrong kind of element (the generated kind rule's, and the test above
    is why this rule stays silent about it rather than crashing).

    Both have to be skips. As stops, a document that states a
    classification of either kind before a German-only one comes back
    with no English entry unreported -- and a document with more than one
    classification is not exotic: 02004 lets a document be classified in
    several systems, and the VDI filter above keeps only the ones this
    rule can speak about, so the ones it steps past are exactly what
    a real file has.

    Measured before this was written: both stops left the whole suite
    green. Every fixture here classifies a document once.
    """
    env = copy.deepcopy(hd_env())
    classifications = _first_document(env)["value"][1]["value"]
    offending = copy.deepcopy(classifications[0])
    for child in offending["value"]:
        if child.get("idShort") == "ClassName":
            child["value"] = [{"language": "de", "text": "Betrieb"}]
    first = classifications[0]
    if unreadable == "no ClassName":
        first["value"] = [child for child in first["value"]
                          if child.get("idShort") != "ClassName"]
    else:
        for child in first["value"]:
            if child.get("idShort") == "ClassName":
                child["modelType"] = "Property"
                child["value"] = "Operation"
                child["valueType"] = "xs:string"
    classifications.append(offending)
    assert "HD-D4" in _findings(tmp_path, env), (
        "a ClassName with no English entry went unreported; the walk "
        "stopped at the classification with %s in front of it" % unreadable)


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
    findings = by_id(runner.run(packed))
    assert findings["X4"].violation.subject == "aasx/files/ghost.step"


# --- HD-D9: entity references resolve --------------------------------------


@pytest.mark.parametrize("kind,first_key,conformant", (
    ("ModelReference", "AssetAdministrationShell", True),
    ("ExternalReference", "Submodel", False),
), ids=("a model reference that names no submodel",
        "an external reference wearing a Submodel key"))
def test_hd_d9_only_follows_a_model_reference_into_this_submodel(
        tmp_path, kind, first_key, conformant):
    """Two terms decide whether `HD-D9` follows a reference at all: it
    must be a `ModelReference`, and its first key must be the `Submodel`
    this file is judging. Both were unmeasured, and each one alone lets
    a reference through that the rule has no business resolving.

    The shapes that distinguish them are odd, and how odd differs, which
    is why both are here with their metamodel standing measured rather
    than argued:

    * A `ModelReference` whose first key is an `AssetAdministrationShell`
      carrying this submodel's id draws **no metamodel finding at all**.
      It is a conformant file, and without the first term the rule walks
      its remaining keys as a path inside this submodel and reports what
      it cannot find. A finding invented against a conformant file is the
      direction this project treats as worst.
    * An `ExternalReference` whose first key is a `Submodel` is refused
      by the relayed channel -- AASd-122, "for external references the
      value of type of the first key of keys shall be one of Generic
      Globally Identifiables", and a `Submodel` key is not one. So that
      file is already being reported. The guard still earns its place:
      the second finding would be untrue, and stacking an untrue finding
      on a true one is how a reader stops believing either.

    Both were checked against `aas_core3` directly rather than against a
    constraint number recalled from memory; an earlier reading of this
    same clause had `Submodel` as permitted, and it is not.
    """
    env = copy.deepcopy(hd_env())
    submodel = env["submodels"][0]
    document = submodel["submodelElements"][0]["value"][0]
    document["value"].append({
        "idShort": "DocumentedEntities", "modelType": "SubmodelElementList",
        "typeValueListElement": "ReferenceElement",
        "semanticId": {"type": "ExternalReference", "keys": [
            {"type": "GlobalReference",
             "value": "https://admin-shell.io/vdi/2770/1/0/"
                      "Document/DocumentedEntities"}]},
        "value": [{"modelType": "ReferenceElement",
                   "semanticId": {"type": "ExternalReference", "keys": [
                       {"type": "GlobalReference",
                        "value": "https://admin-shell.io/vdi/2770/1/0/"
                                 "Document/DocumentedEntity"}]},
                   "value": {"type": kind, "keys": [
                       {"type": first_key, "value": submodel["id"]},
                       {"type": "SubmodelElementCollection",
                        "value": "no-such-element"}]}}]})

    #: What the relayed channel says about this file, measured here so
    #: the docstring above cannot quietly go stale.
    reported = verification.verify(
        jsonization.environment_from_jsonable(env))
    assert (not list(reported)) is conformant

    assert "HD-D9" not in _findings(tmp_path, env), (
        "HD-D9 resolved a reference it has no business following: a %s "
        "whose first key is a %s" % (kind, first_key))


def test_the_dangling_reference_rule_does_not_read_a_conditional_clause_as_a_law():
    """`HD-D9` is a SHOULD, and the clause behind it is conditional.

    Its citation used to quote IDTA 02004-2-0 §2.2 as "the creation of an
    Entity element is required", which reads as a requirement on every
    file and is not one. Read from the published document, page 7: the
    paragraph opens "the documentation of a complex piece of equipment
    *may* include further supplier parts. These parts *can* be marked as
    separate entities", describes two categorisations, and closes "In any
    case" -- meaning in either of those two, not in every file.

    A proposal to promote this rule to MUST rested on that quote. Reading
    a conditional clause as an unconditional one is the defect the front
    page carried until 0.1.3, so the quote is pinned out of the citation
    here: what would reintroduce the argument is the sentence returning
    without its condition.
    """
    from aas_submodel_validate.registry import all_rules
    rule = next(r for r in all_rules() if r.id == "HD-D9")
    assert rule.prio == "SHOULD", (
        "HD-D9 became a %s; the clause it cites is conditional, and "
        "docs/divergences.md #41 is where that argument is kept" % rule.prio)
    assert "the creation of an Entity element is required" not in rule.spec, (
        "the citation quotes the clause without the condition that governs "
        "it, which is what made it read as a requirement on every file")
    assert "docs/divergences.md #41" in rule.spec, (
        "the citation should point at the reading it answers for")

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


def _dissolve(parent, label):
    """Take a wrapping SubmodelElementList out and leave its children
    standing where it stood -- what a file that skips the list looks
    like."""
    for index, child in enumerate(parent["value"]):
        if child.get("idShort") == label:
            parent["value"] = (parent["value"][:index] + list(child["value"])
                               + parent["value"][index + 1:])
            return
    raise KeyError(label)                        # pragma: no cover - fixture


def _flat_ids_without_a_primary(env):
    document = _first_document(env)
    ids = document["value"][0]
    first = ids["value"][0]
    first["value"] = [child for child in first["value"]
                      if child.get("idShort") != "DocumentIsPrimary"]
    second = copy.deepcopy(first)
    _set_property(second, "DocumentIdentifier", "XF90-885")
    ids["value"] = [first, second]
    _dissolve(document, "DocumentIds")
    return "HD-D5"


def _flat_ids_repeated_by_a_second_document(env):
    documents = env["submodels"][0]["submodelElements"][0]["value"]
    documents.append(copy.deepcopy(documents[0]))
    for document in documents:
        _dissolve(document, "DocumentIds")
    return "HDL4"


def _flat_classification_without_english(env):
    for child in _classification(env)["value"]:
        if child.get("idShort") == "ClassName":
            child["value"] = [{"language": "de", "text": "Betrieb"}]
    _dissolve(_first_document(env), "DocumentClassifications")
    return "HD-D4"


def test_an_element_of_the_wrong_kind_is_not_walked_as_the_kind_it_wears(tmp_path):
    """The walk counts an element that wears a row's identity whatever its
    kind -- the count and the kind are the generated rules' findings --
    and hands the hand rules only the ones of the row's kind. A Property
    wearing a PreviewFile's identity is a kind defect HD-E34 names; it is
    not a file for HD-D7 to look up. Handed on, HD-D7 read the Property's
    string as a part name and reported the archive missing a file nobody
    declared as one. Measured before this was written: with every matched
    element handed on, the whole suite still passed -- no fixture put
    another kind where a File belongs."""
    env = copy.deepcopy(hd_env())
    _document_version(env)["value"].append({
        "idShort": "PreviewFile", "modelType": "Property", "valueType": "xs:string",
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference",
                                 "value": "0173-1#02-ABK127#002"}]},
        "value": "/aasx/files/missing.jpg"})
    packed = build_aasx(tmp_path / "p.aasx", payload=json.dumps(env).encode("utf-8"),
                        files=(("aasx/files/manual.pdf", b"%PDF-1.4"),))
    ids = {f.id for f in runner.run(packed).findings}
    assert "HD-E34" in ids, "the generated kind rule no longer names the Property"
    assert "HD-D7" not in ids, "HD-D7 looked up a Property's string as a part name"


def test_a_property_row_filled_by_another_kind_reads_as_absent(tmp_path):
    """`property_value` answers with a string or with nothing. A child that
    wears a Property's identity and is another kind -- a
    MultiLanguageProperty where `ClassificationSystem` belongs -- has a
    list for a value, and the hand rules strip what they are handed: given
    the list, they crash on a file whose defect HD-E12 names exactly.
    Measured before this was written: with the string check gone, the
    whole suite still passed -- no fixture put another kind where a
    Property belongs. The refusal in conftest is what turns such a crash
    into a failure here."""
    env = copy.deepcopy(hd_env())
    for child in _classification(env)["value"]:
        if child.get("idShort") == "ClassificationSystem":
            child["modelType"] = "MultiLanguageProperty"
            child["value"] = [{"language": "en", "text": "VDI2770:2018"}]
            child.pop("valueType", None)
    assert "HD-E12" in _findings(tmp_path, env)


@pytest.mark.parametrize("bend", (_flat_ids_without_a_primary,
                                  _flat_ids_repeated_by_a_second_document,
                                  _flat_classification_without_english),
                         ids=("D5 DocumentIds", "L4 DocumentIds",
                              "D4 DocumentClassifications"))
def test_a_file_that_skips_a_wrapping_list_is_still_read(tmp_path, bend):
    """Four hand rules navigate `child_of(parent, "<Label>s") or parent`,
    and until this test nothing anywhere exercised the second half.
    Three of the four are here; the fourth cannot reach it at all, and
    the test below this one is why.

    The template makes each of those lists `SMT/Cardinality: One`, so a
    file that states its `DocumentId`s -- or classifications, or digital
    files -- directly on their parent is not conformant, and it is
    refused for that: measured, such a file draws `HD-E03` at error and
    leaves by 1. What the fallback decides is not whether the file is
    accepted but whether this tool also says what else is wrong with it.
    It does, and that is the same reading the container chain was given
    when it stopped at the first payload it could not read: a reader that
    reports one defect sends an author away to fix it and then says the
    next one, of the same kind, on their return.

    It cannot cost a conformant file anything -- a conformant file has
    the list, `child_of` finds it, and the fallback is never reached.
    That asymmetry is the whole argument, and it is why matching by
    semanticId is what makes the reading available: a collection wearing
    `DocumentId`'s identifier is a `DocumentId` wherever a file puts it.

    Recorded as docs/divergences.md #42.
    """
    env = copy.deepcopy(hd_env())
    rule_id = bend(env)
    findings = _findings(tmp_path, env)
    assert any(found.startswith("HD-E") for found in findings), (
        "the missing wrapping list should still be reported by a generated "
        "rule; this fixture no longer shows what it says it shows")
    assert rule_id in findings, (
        "%s went unreported on a file that states the elements it reads "
        "without their wrapping list" % rule_id)


def test_the_digital_files_fallback_is_shadowed_by_its_own_guard(tmp_path):
    """The fourth of those four lines is written exactly like the other
    three and cannot do what they do. This pins why, because the reason
    is in the template rather than in the code and reading the code will
    not show it.

    02004 gives `DigitalFiles` and its sole child `DigitalFile` **one**
    identifier, `0173-1#02-ABK126#002`, where it gives `DocumentIds` and
    `DocumentId` two different ones. That sharing is docs/divergences.md
    #39, and the direction it already guards -- asking for the item and
    getting the list -- is spied on by `test_engine_seam.py` across a
    whole run. This is the other direction, which only a file missing
    the list can reach, so that spy never sees it. Matching does not consult element
    kind once an identifier hits (`_matches_row`), so on a version that
    states its file flat, `child_of(version, "DigitalFiles")` returns the
    `File` itself -- truthy -- and `or version` never runs. The rule then
    asks that `File` for its children, a `File` has a string where a list
    would be, and the answer is nothing.

    What it costs: such a file gets no HD-D7 and no HD-D10. It is already
    refused -- the list is `SMT/Cardinality: One` and a generated rule
    says so -- so nothing passes that should fail. It is a finding not
    made, on a file that is failing anyway.

    Why it is recorded and not repaired: the obvious repair, asking for
    the children directly when the list lookup comes back empty, reports
    HD-D10 against the *list element* when a version carries an empty
    `DigitalFiles`, because the list wears the child's identifier too.
    Trading a missing finding for a finding with the wrong subject is not
    an improvement, and the alternative -- teaching matching to consult
    kind -- is the walk's business and not one rule's
    (docs/divergences.md #11, #42).

    The last assertion is the one that keeps this honest: the fallback's
    own expression *does* find the file. The line is not wrong; it is
    unreachable.
    """
    env = copy.deepcopy(hd_env())
    _dissolve(_document_version(env), "DigitalFiles")
    path = _write(tmp_path, env)
    submodel = loader.load(path).submodels[0]
    version = submodel.submodel_elements[0].value[0].value[2].value[0]

    guard = engine.child_of(version, "DigitalFiles", hd_tables)
    assert type(guard).__name__ == "File", (
        "child_of no longer mistakes the flat File for its list; if that "
        "changed on purpose, this limitation and divergences #42 are stale")
    assert engine.children_of(guard, "DigitalFile", hd_tables) == [], (
        "a File has no children to read")
    assert len(engine.children_of(version, "DigitalFile", hd_tables)) == 1, (
        "the fallback expression itself finds the file; the line is "
        "unreachable, not wrong")

    assert "HD-D10" not in _findings(tmp_path, env), (
        "HD-D10 now reads a flat DigitalFile -- good, but #42 and the "
        "docstring above say it cannot, so one of them needs rewriting")


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
    findings = by_id(runner.run(packed))
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


def test_a_file_with_an_empty_content_type_is_reported_as_carrying_none(tmp_path):
    """The detail lists the content types the version carries and says
    `none` when there is nothing to list -- a file whose `contentType` is
    empty. Every fixture printed a non-empty list, so the `none` could go
    and the line would end on a bare colon."""
    env = copy.deepcopy(hd_env())
    _digital_files(env)["value"][0]["contentType"] = ""
    found = _findings(tmp_path, env)
    assert found["HD-D10"].violation.detail == "content types present: none"


def test_a_version_with_no_files_does_not_hide_the_next_version(tmp_path):
    """The existing pair above walks the files inside one version. This
    walks the versions.

    A `DocumentVersion` carrying no `DigitalFile` at all is not this
    rule's finding -- absence is the cardinality rule's -- so the walk
    steps past it. Stepping past has to mean continuing: a version with
    no files, followed by one whose only rendition is a STEP model, is a
    file that should draw `HD-D10` and would come back clean if the walk
    stopped at the first.

    Measured before this was written: turning that skip into a stop left
    the whole suite green, because no fixture had an empty version in
    front of an offending one.
    """
    env = copy.deepcopy(hd_env())
    versions = _first_document(env)["value"][2]["value"]
    offending = copy.deepcopy(versions[0])
    for child in offending["value"]:
        if child.get("idShort") == "DigitalFiles":
            for digital in child["value"]:
                digital["contentType"] = "application/step"
                digital["value"] = "/aasx/files/model.step"
    #: The first version keeps its identity and loses its files, so the
    #: only thing that differs between the two is what the rule reads.
    empty = versions[0]
    empty["value"] = [child for child in empty["value"]
                      if child.get("idShort") != "DigitalFiles"]
    versions.append(offending)
    assert "HD-D10" in _findings(tmp_path, env), (
        "a version whose only rendition is not a PDF was not reported; "
        "the walk stopped at the version in front of it")


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



def test_a_reference_the_walk_skips_does_not_hide_the_one_behind_it(tmp_path):
    """The walk steps past a reference it cannot judge; it does not stop.

    `HD-D9` reads a list of ReferenceElements and skips the ones it has
    no question about -- an external reference, or one pointing into
    another submodel, which this reader cannot resolve offline. A skip
    that ended the walk instead would let one unjudgeable reference hide
    every dangling one behind it, and the file would come back clean.

    Measured before this was written: turning either of those two skips
    into a stop left the whole suite green, because every fixture put
    the dangling reference first or alone.
    """
    env = copy.deepcopy(hd_env())
    parent = _first_document(env)
    dangling = {"type": "ModelReference", "keys": [
        {"type": "Submodel", "value": "urn:example:handover"},
        {"type": "SubmodelElementList", "value": "Documents"},
        {"type": "SubmodelElementCollection", "value": "77"}]}
    def item(value):
        return {"modelType": "ReferenceElement",
                "semanticId": {"type": "ExternalReference", "keys": [
                    {"type": "GlobalReference",
                     "value": "https://admin-shell.io/vdi/2770/1/0/"
                              "Document/DocumentedEntity"}]},
                "value": value}
    parent["value"].append({
        "idShort": "DocumentedEntities", "modelType": "SubmodelElementList",
        "typeValueListElement": "ReferenceElement",
        "semanticId": {"type": "ExternalReference", "keys": [
            {"type": "GlobalReference",
             "value": "https://admin-shell.io/vdi/2770/1/0/"
                      "Document/DocumentedEntities"}]},
        "value": [
            #: Not a ModelReference at all -- nothing to resolve, so the
            #: walk has no question about it and steps past.
            item({"type": "ExternalReference", "keys": [
                {"type": "GlobalReference", "value": "https://example.com/x"}]}),
            #: And one naming a submodel that is not this one, which this
            #: reader cannot follow offline; also stepped past.
            item({"type": "ModelReference", "keys": [
                {"type": "Submodel", "value": "urn:example:elsewhere"},
                {"type": "SubmodelElementCollection", "value": "77"}]}),
            #: The one that is actually broken, behind both of them.
            item(dangling),
        ]})
    assert "HD-D9" in _findings(tmp_path, env), (
        "a dangling reference behind two the walk steps past was not "
        "reported; the walk stopped instead of continuing")


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
    # Mixed case was refused until RFC 5646 §2.1.1 was read against it:
    # capitalisation "MUST NOT be taken to carry meaning". The tag is
    # folded before the question is asked; the question is unchanged.
    ("eN", True), ("En", True), ("En-gb", True),
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
    # And it is the metamodel's verdict, not a copy that agreed on the
    # day it was written. Identity used to say that, and cannot now
    # that the tag is folded first, so the same thing is said as a law
    # the wrapper obeys: whatever aas-core3 answers about the folded
    # tag is what this answers, for every tag. A hand-rolled pattern
    # would have to reproduce that function exactly to pass, which is
    # the property identity was standing in for.
    for probe in ("en", "EN", "En", "eN", "en-GB", "EN-gb", "eng", "enm",
                  "english", "de", "de-DE", "", "x", "en_GB", "e-n"):
        assert (handover_rules._english(probe)
                is verification.is_bcp_47_for_english(probe.lower())), probe
    assert verification.is_bcp_47_for_english(tag.lower()) is is_english


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


@pytest.mark.parametrize("tag", ["en", "EN", "En", "eN", "en-US", "EN-us",
                                 "en-GB", "En-gb"])
def test_english_is_english_however_it_is_capitalised(tag):
    """RFC 5646 §2.1.1: "language tags and their subtags ... are to be
    treated as case insensitive ... there exist conventions for the
    capitalization of some of the subtags, but these MUST NOT be taken
    to carry meaning."

    aas-core3's predicate is `^(en|EN)(-.*)?$`, which takes all-lower
    and all-upper and refuses the two mixed spellings. This rule is a
    MUST, so a file writing `En` was told it had no English entry -- on
    a line that printed `languages present: En, de` directly above.

    The tag is folded before the question is asked, which is not a
    reading of our own: it is the same predicate, handed the tag in the
    form the standard says means the same thing. `eng` stays refused --
    it is a valid tag whose preferred value is `en`, and refusing it is
    a different argument (docs/divergences.md #35)."""
    from aas_submodel_validate.rules.handover import _english

    assert _english(tag), (
        "%r names English and this rule says it does not" % tag)


@pytest.mark.parametrize("tag", ["eng", "de", "e", "english", "ены"])
def test_what_is_not_english_stays_not_english(tag):
    """The control. Folding case must not widen the answer to anything
    else -- `eng` above all, which is well-formed, means English, and is
    the tag IANA marks as not preferred."""
    from aas_submodel_validate.rules.handover import _english

    assert not _english(tag), "%r is not the tag this rule asks for" % tag


def test_a_trailing_space_does_not_hide_the_classification(tmp_path):
    """`"VDI 2770 Blatt 1:2020 "` names the mandatory system. Compared
    byte for byte it named nothing, so HD-D2 -- a MUST, which moves the
    exit code -- reported that the file has no VDI 2770 classification
    and told the reader to add one, while the file plainly carried it.
    `xs:string` admits trailing whitespace, so the metamodel channel has
    no second opinion to offer either.

    Two rows of this document already fold whitespace for exactly this
    reason and say so: #34 for `xs:boolean`, because reading strictly
    "would report a document as having no primary identifier when it
    plainly marks one", and #31 for `xs:date`, because "a finding on a
    conformant file is the one direction with no second opinion". Both
    are attached to rules that do not move the exit code. The strict
    reading was attached to one that does, which is the asymmetry this
    project declares, backwards."""
    from aas_submodel_validate.rules.handover import VDI2770_SYSTEM

    env = copy.deepcopy(hd_env())
    for child in _classification(env)["value"]:
        if child.get("idShort") == "ClassificationSystem":
            child["value"] = VDI2770_SYSTEM + " "
    assert "HD-D2" not in _findings(tmp_path, env), (
        "a trailing space made the mandatory classification invisible")


@pytest.mark.parametrize("value,drawn", [
    # The repair's own case: a substring test called this a URI and let
    # a value that is a perfectly good part name walk past a MUST.
    ("files/a://absent.pdf", True),
    # Somewhere else's file. Not this container's question.
    ("http://example.com/a.pdf", False),
    ("https://example.com/a.pdf", False),
    ("urn:iso:std:iso:1234", False),
    ("mailto:docs@example.com", False),
    ("data:application/pdf;base64,AAA=", False),
    # A drive letter is a legal one-letter scheme in RFC 3986 and is a
    # drive letter every time it appears in a File value. Reading it as
    # a scheme let an absent Windows path stop being asked about.
    ("C:\\docs\\manual.pdf", True),
    ("c:/docs/manual.pdf", True),
    # Whitespace is not a scheme's business. A leading space made this
    # no scheme at all and drew a MUST on a file whose only fault was
    # the space -- in the same commit that taught the classification
    # rule to forgive exactly that.
    (" http://example.com/a.pdf", False),
    ("\thttps://example.com/a.pdf", False),
])
def test_which_file_values_are_this_containers_business(tmp_path, value, drawn):
    """`HD-D7` asks whether a File value names a part the container
    holds. A value naming something outside the container is not that
    question, and the test for "outside" was `"://" in value` -- a
    substring, not a scheme.

    Nothing in the suite moved when that was replaced, in either
    direction, and the replacement changed the verdict on five shapes
    of value. A change to what a MUST rule decides, with no fixture
    naming the shapes it decides differently, is a change nobody can
    review."""
    env = copy.deepcopy(hd_env())
    placed = 0
    for element in _document_version(env)["value"]:
        if element.get("idShort") != "DigitalFiles":
            continue
        for entry in element["value"]:
            entry["value"] = value
            placed += 1
    assert placed == 1, "the fixture no longer has exactly one File to set"
    # In a container, because the branch under test is "the archive
    # holds no part at this value" and a bare document has no archive
    # to hold one.
    packed = build_aasx(tmp_path / "p.aasx",
                        payload=json.dumps(env).encode("utf-8"))
    drawn_ids = {f.id for f in runner.run(packed).findings}
    assert ("HD-D7" in drawn_ids) is drawn, (
        "%r: expected HD-D7 %s, got %s"
        % (value, "drawn" if drawn else "silent", sorted(drawn_ids)))


#: The values that decide what a File value is, and the two rules that
#: decide it. `HD-D7` and `TD-D2` were verbatim twins and the repair
#: that replaced a substring test with a scheme test reached one of
#: them, so for a day one reported a defect the other stayed silent
#: about -- in both directions, both MUST. One table, asked of both.
FILE_VALUES = [
    ("files/a://absent.pdf", True),
    ("http://example.com/a.pdf", False),
    ("urn:iso:std:iso:1234", False),
    ("mailto:docs@example.com", False),
    ("data:application/pdf;base64,AAA=", False),
    ("C:\\docs\\manual.pdf", True),
    ("c:/docs/manual.pdf", True),
    (" http://example.com/a.pdf", False),
    ("\thttps://example.com/a.pdf", False),
    # A part the archive holds, with whitespace around it. Folding the
    # value for the scheme question and not for the two that follow
    # drew a MUST on a file whose only fault was a space.
    (" aasx/files/manual.pdf ", False),
    ("aasx/files/manual.pdf\n", False),
]


@pytest.mark.parametrize("value,drawn", FILE_VALUES)
def test_hd_d7_reads_a_file_value_the_way_td_d2_does(tmp_path, value, drawn):
    env = copy.deepcopy(hd_env())
    placed = 0
    for element in _document_version(env)["value"]:
        if element.get("idShort") != "DigitalFiles":
            continue
        for entry in element["value"]:
            entry["value"] = value
            placed += 1
    assert placed == 1, "the fixture no longer has exactly one File to set"
    packed = build_aasx(tmp_path / "p.aasx",
                        payload=json.dumps(env).encode("utf-8"),
                        files=(("aasx/files/manual.pdf", b"%PDF-1.4"),))
    drawn_ids = {f.id for f in runner.run(packed).findings}
    assert ("HD-D7" in drawn_ids) is drawn, (
        "%r: expected HD-D7 %s, got %s"
        % (value, "drawn" if drawn else "silent", sorted(drawn_ids)))


#: The values a rule reads out of a closed vocabulary, and whether
#: whitespace around them changes the answer. Four rules read one this
#: way; three learned to fold and the fourth did not, and two mutations
#: of the folding survived a review round because nothing asked them
#: together.
@pytest.mark.parametrize("rule_id,label,good", [
    ("HD-D2", "ClassificationSystem", "VDI 2770 Blatt 1:2020"),
    ("HD-D3", "ClassId", "03-02"),
    ("HD-D6", "StatusValue", "Released"),
])
@pytest.mark.parametrize("pad", ["%s", " %s", "%s ", " %s ", "\t%s\n"])
def test_whitespace_around_a_vocabulary_value_is_not_the_defect(
        tmp_path, rule_id, label, good, pad):
    """XML Schema's `xs:string` admits whitespace, so the metamodel
    channel has no second opinion to offer, and a finding on a
    conformant file is the direction with none. Rows 31 and 34 of the
    divergences fold for exactly that reason."""
    env = copy.deepcopy(hd_env())
    placed = 0

    def stamp(node):
        nonlocal placed
        if isinstance(node, dict):
            if node.get("idShort") == label:
                node["value"] = pad % good
                placed += 1
            for child in node.values():
                stamp(child)
        elif isinstance(node, list):
            for child in node:
                stamp(child)

    stamp(env)
    assert placed, "the fixture has no %s to set" % label
    assert rule_id not in _findings(tmp_path, env), (
        "%s: %r drew %s, and the value is the one the rule asks for"
        % (label, pad % good, rule_id))


def test_two_half_stated_identifiers_are_not_the_same_pair(tmp_path):
    """`HDL4` compares `(domain, identifier)` pairs and steps past one
    that states only half, because a missing half is the cardinality
    rule's finding. Take that guard away and the halves that *are* there
    get compared as if they were whole pairs.

    Two documents carry the same `DocumentIdentifier` here and neither
    states a domain. Whether they are duplicates is not knowable from
    that -- an identifier means nothing without the domain it is issued
    under, which is why the pair is a pair. Without the guard both
    collapse to `(None, identifier)` and the second is reported for
    sharing a pair neither of them stated. It is the worst direction
    this project knows: a finding invented out of what a file did not
    say, and it moves the exit code.
    """
    env = copy.deepcopy(hd_env())
    documents = env["submodels"][0]["submodelElements"][0]["value"]
    twin = copy.deepcopy(documents[0])
    documents.append(twin)
    for document in documents:
        document_id = document["value"][0]["value"][0]
        document_id["value"] = [child for child in document_id["value"]
                                if child.get("idShort") != "DocumentDomainId"]
    assert "HDL4" not in _findings(tmp_path, env), (
        "two documents that never stated a domain were reported for "
        "sharing one")

    stated = copy.deepcopy(hd_env())
    documents = stated["submodels"][0]["submodelElements"][0]["value"]
    documents.append(copy.deepcopy(documents[0]))
    assert "HDL4" in _findings(tmp_path, stated), (
        "a pair both documents do state went unreported, so the silence "
        "above proves nothing")


def test_one_document_repeating_its_own_pair_is_not_two_documents(tmp_path):
    """`HDL4` says "two documents share one (domain, identifier) pair",
    and the guard that makes that sentence true is `seen[pair] !=
    subject`. Drop it and a document that states the same pair twice is
    reported for sharing it with itself -- a message that is not true of
    the file, sending an author to look for a second document that does
    not exist.

    Both edges on one fixture, because the negative alone would pass on a
    rule that had stopped working: the twin `DocumentId` stays silent
    where it is, and reports the moment it belongs to somebody else.

    Whether one document repeating its own identifier is worth saying
    anything about is a separate question and not this rule's -- it would
    be a different sentence, and inventing it here would put it under a
    published rule id.
    """
    env = copy.deepcopy(hd_env())
    documents = env["submodels"][0]["submodelElements"][0]["value"]
    ids = documents[0]["value"][0]
    ids["value"].append(copy.deepcopy(ids["value"][0]))
    assert "HDL4" not in _findings(tmp_path, env), (
        "a document was reported for sharing an identifier pair with "
        "itself; the rule's own sentence says two documents")

    moved = copy.deepcopy(hd_env())
    documents = moved["submodels"][0]["submodelElements"][0]["value"]
    twin = copy.deepcopy(documents[0])
    twin["value"][0]["value"] = [copy.deepcopy(documents[0]["value"][0]["value"][0])]
    documents.append(twin)
    assert "HDL4" in _findings(tmp_path, moved), (
        "the same pair under a second document went unreported, so the "
        "silence above proves nothing")


def test_an_incomplete_document_id_does_not_hide_the_duplicate_behind_it(
        tmp_path):
    """`HDL4` walks a document's `DocumentId`s, and one naming only half
    a pair is not this rule's finding -- a missing half is the
    cardinality rule's -- so the walk steps past it.

    Stepping past has to mean continuing. A document carrying an
    incomplete `DocumentId` first and a duplicate of another document's
    pair second is a duplicate that comes back unreported if the walk
    stops at the first one it cannot read.

    Measured before this was written: turning that skip into a stop left
    the whole suite green, because every fixture that duplicates a pair
    states the pair in the document's first `DocumentId`.
    """
    env = copy.deepcopy(hd_env())
    documents = env["submodels"][0]["submodelElements"][0]["value"]
    twin = copy.deepcopy(documents[0])
    ids_list = twin["value"][0]
    duplicate = copy.deepcopy(ids_list["value"][0])
    #: Half a pair. The rule reads None for the missing half, and None is
    #: what makes it step past rather than compare.
    incomplete = ids_list["value"][0]
    incomplete["value"] = [child for child in incomplete["value"]
                           if child.get("idShort") != "DocumentDomainId"]
    ids_list["value"] = [incomplete, duplicate]
    documents.append(twin)
    assert "HDL4" in _findings(tmp_path, env), (
        "a duplicate identifier pair went unreported; the walk stopped at "
        "the incomplete DocumentId in front of it")


@pytest.mark.parametrize("pad", ["%s", " %s", "%s ", "\t%s\n"])
def test_two_identifier_pairs_are_the_same_pair_however_they_are_padded(
        tmp_path, pad):
    """`HDL4` compares two documents' `(domain, identifier)` pairs, and
    both halves are plain `xs:string` -- so the metamodel channel has no
    second opinion, which is the condition rows 31 and 34 give for
    folding. Three rules folded and this one did not, so a space at the
    end of one identifier made two identical pairs look different and
    the duplicate went unreported."""
    env = copy.deepcopy(hd_env())
    documents = env["submodels"][0]["submodelElements"][0]["value"]
    twin = copy.deepcopy(documents[0])

    def stamp(node):
        if isinstance(node, dict):
            if node.get("idShort") in ("DocumentDomainId", "DocumentIdentifier"):
                node["value"] = pad % node["value"]
            for child in node.values():
                stamp(child)
        elif isinstance(node, list):
            for child in node:
                stamp(child)

    stamp(twin)
    documents.append(twin)
    assert "HDL4" in _findings(tmp_path, env), (
        "%r padding hid a duplicate identifier pair" % pad)
