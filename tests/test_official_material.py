"""What this validator says about the official IDTA example, pinned by name.

The published reference material is the first input a real-world tool
meets, so what we report against it is a contract: every finding named,
not counted -- a count stays green while the set underneath it churns.
The defects pinned here are the example's, verified against the
published bytes; the repaired copy shows each finding is about exactly
the thing repaired.
"""
from __future__ import annotations

import json

from aas_submodel_validate import runner

JSON_EXAMPLE = "tests/corpus/idta/02004/example.json"
AASX_EXAMPLE = "tests/corpus/idta/02004/example.aasx"

#: The remedy sentences, written out rather than read from the registry.
#: Read from the registry they would agree with any rewording, and a
#: reworded remedy is exactly what promoting a rule body to a factory can
#: do without moving an id or a subject.
_D6_FIX = ("Set StatusValue to 'InReview' or 'Released' (exact casing). The "
           "vendored concept description is where those two come from, and it "
           "says they 'should be used' -- which is why this is a warning.")
_L2_FIX = ("Correct the semanticId to the template's spelling; a near-miss "
           "matches nothing, and every rule that would have applied to the "
           "element silently stops applying.")
_L5_FIX = ("Write ClassificationSystem exactly as 'VDI 2770 Blatt 1:2020' -- "
           "the value \u00a72.3 says identifies the mandatory system. "
           "'VDI2770:2020' is the template's example artefact and other tools "
           "matching on the specified string will not recognise it.")
_D10_FIX = ("Add a DigitalFile with contentType application/pdf (a PDF/A file, "
            "per VDI 2770) to this DocumentVersion. A content type cannot "
            "prove PDF/A conformance, so this is a warning, not an error.")


def _named(report):
    return sorted((f.id, f.violation.subject or "") for f in report.findings
                  if f.id != "META")


def test_the_official_example_by_name():
    report = runner.run(JSON_EXAMPLE)
    assert report.ok  # nothing rises to error severity
    assert _named(report) == sorted([
        # the status vocabulary is 'Released'; the example writes 'released'
        ("HD-D6", "HandoverDocumentation/Documents/Datasheet/DocumentVersions/DocumentVersion_en"),
        ("HD-D6", "HandoverDocumentation/Documents/Datasheet/DocumentVersions/DocumentVersion_de"),
        ("HD-D6", "HandoverDocumentation/Documents/Datasheet/DocumentVersions/DocumentVersion_en_de_fr"),
        ("HD-D6", "HandoverDocumentation/Documents/CADmodel/DocumentVersions/DocumentVersion_file"),
        ("HD-D6", "HandoverDocumentation/Documents/CADmodel/DocumentVersions/DocumentVersion_URL"),
        # the Entities list carries the child's singular IRI (divergence #2)
        ("HDL2", "HandoverDocumentation/Entites"),
        # the template's example spelling of the VDI system (divergence #9)
        ("HDL5", "HandoverDocumentation/Documents/Datasheet"),
        ("HDL5", "HandoverDocumentation/Documents/CADmodel"),
        # the CAD-model versions ship STEP only -- no PDF/A rendition (§2.1)
        ("HD-D10", "HandoverDocumentation/Documents/CADmodel/DocumentVersions/DocumentVersion_file"),
        ("HD-D10", "HandoverDocumentation/Documents/CADmodel/DocumentVersions/DocumentVersion_URL"),
    ])


def test_every_word_of_the_official_verdict():
    """The same ten findings, whole: severity, message, detail and the
    remedy sentence, not only the id and the subject.

    The pair above is what a reader of the *set* needs; this is what a
    reader of one *finding* gets. Rules are about to be shared between
    two packs by promoting their bodies to factories, and the promotion
    that keeps every id and subject in place while rewording a message is
    the one nothing above would notice. Read as a set because the report
    is ordered elsewhere (tests/test_report_order.py) and this is not a
    test about order.
    """
    report = runner.run(JSON_EXAMPLE)
    whole = {(f.id, str(f.severity), f.violation.subject, f.violation.message,
              f.violation.detail, f.fix)
             for f in report.findings if f.id != "META"}
    assert whole == {
        ("HD-D6", "warning",
         "HandoverDocumentation/Documents/Datasheet/DocumentVersions/DocumentVersion_en",
         "StatusValue is outside the vocabulary", "'released'", _D6_FIX),
        ("HD-D6", "warning",
         "HandoverDocumentation/Documents/Datasheet/DocumentVersions/DocumentVersion_de",
         "StatusValue is outside the vocabulary", "'released'", _D6_FIX),
        ("HD-D6", "warning",
         "HandoverDocumentation/Documents/Datasheet/DocumentVersions/DocumentVersion_en_de_fr",
         "StatusValue is outside the vocabulary", "'released'", _D6_FIX),
        ("HD-D6", "warning",
         "HandoverDocumentation/Documents/CADmodel/DocumentVersions/DocumentVersion_file",
         "StatusValue is outside the vocabulary", "'released'", _D6_FIX),
        ("HD-D6", "warning",
         "HandoverDocumentation/Documents/CADmodel/DocumentVersions/DocumentVersion_URL",
         "StatusValue is outside the vocabulary", "'released'", _D6_FIX),
        ("HDL2", "warning", "HandoverDocumentation/Entites",
         "semanticId almost matches the template",
         "https://admin-shell.io/vdi/2770/1/0/EntityForDocumentation, where the "
         "template says https://admin-shell.io/vdi/2770/1/0/EntitiesForDocumentation",
         _L2_FIX),
        ("HDL5", "warning", "HandoverDocumentation/Documents/Datasheet",
         "ClassificationSystem spells the VDI system non-canonically",
         "'VDI2770:2020'", _L5_FIX),
        ("HDL5", "warning", "HandoverDocumentation/Documents/CADmodel",
         "ClassificationSystem spells the VDI system non-canonically",
         "'VDI2770:2020'", _L5_FIX),
        ("HD-D10", "warning",
         "HandoverDocumentation/Documents/CADmodel/DocumentVersions/DocumentVersion_file",
         "no DigitalFile is a PDF; VDI 2770 requires a PDF/A rendition",
         "content types present: application/step", _D10_FIX),
        ("HD-D10", "warning",
         "HandoverDocumentation/Documents/CADmodel/DocumentVersions/DocumentVersion_URL",
         "no DigitalFile is a PDF; VDI 2770 requires a PDF/A rendition",
         "content types present: application/step", _D10_FIX),
    }


def test_the_metamodel_channel_reports_the_known_seventy_seven():
    report = runner.run(JSON_EXAMPLE)
    meta = [f for f in report.findings if f.id == "META"]
    assert len(meta) == 77
    assert sum("AASd-120" in f.violation.message for f in meta) == 33


def test_both_serialisations_get_the_same_answer():
    """One example, two official forms; a validator whose verdict depends
    on the packaging is measuring the packaging."""
    from_json = runner.run(JSON_EXAMPLE)
    from_aasx = runner.run(AASX_EXAMPLE)
    assert _named(from_json) == _named(from_aasx)
    assert (sorted(f.violation.message for f in from_json.findings)
            == sorted(f.violation.message for f in from_aasx.findings))


def test_a_repaired_copy_comes_back_clean(tmp_path):
    """Each repair below undoes exactly one pinned finding; a clean result
    proves the findings were about those defects and nothing else.
    (The 77 metamodel findings belong to aas-core3.0's channel and are
    not repaired here.)"""
    from pathlib import Path
    document = json.loads(Path(JSON_EXAMPLE).read_text("utf-8-sig"))
    submodel = document["submodels"][0]
    for element in submodel["submodelElements"]:
        if element.get("idShort") == "Entites":                    # HDL2
            element["semanticId"]["keys"][0]["value"] = \
                "https://admin-shell.io/vdi/2770/1/0/EntitiesForDocumentation"
    def repair(container):
        for child in container.get("value", []) if isinstance(container.get("value"), list) else []:
            if child.get("idShort") == "StatusValue" and child.get("value") == "released":
                child["value"] = "Released"                        # HD-D6
            if child.get("idShort") == "ClassificationSystem":
                child["value"] = "VDI 2770 Blatt 1:2020"           # HDL5
            if child.get("idShort") == "DigitalFiles":             # HD-D10
                for f in child.get("value", []):
                    f["contentType"] = "application/pdf"
            repair(child)
    for element in submodel["submodelElements"]:
        repair(element)
    path = tmp_path / "repaired.json"
    path.write_text(json.dumps(document), "utf-8")
    report = runner.run(path)
    assert [f.id for f in report.findings if f.id != "META"] == []
