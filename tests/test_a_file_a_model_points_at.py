"""Whether the file a model names is in the package it came in.

The rule for this exists and is one body: `engine.file_part_violations`
answers it for whichever rule asks, with the three branches a File value
needs -- an empty value names nothing, a value with a scheme is
somewhere else's, a spelling that cannot be a part name gets its own
remedy, and a name the archive does not hold is the finding.

It was asked by two packs. A Digital Nameplate carries `CompanyLogo` and
`MarkingFile` and nobody asked on its behalf, so a package whose model
points at two images it does not contain was judged clean.
"""
from __future__ import annotations

import json

from aas_submodel_validate import runner
from aas_submodel_validate.model import Severity
from builders import build_aasx, dn_env

LOGO = "aasx/files/logo.png"
CE = "aasx/files/ce.png"


def _package(tmp_path, name, *, files=(), suppl_targets=None, env=None):
    path = tmp_path / ("%s.aasx" % name)
    build_aasx(path, json.dumps(env or dn_env()).encode("utf-8"),
               files=files, suppl_targets=suppl_targets)
    return path


def _missing_part(report):
    return sorted(
        (f.id, f.violation.subject)
        for f in report.findings
        if "holds no part" in f.violation.message)


def test_a_nameplate_pointing_at_images_it_does_not_carry_is_told(tmp_path):
    """The measured miss.

    A Digital Nameplate package whose model names `/aasx/files/logo.png`
    and `/aasx/files/ce.png`, with neither in the archive and no
    aas-suppl relationship declaring them: judged clean, `ok` true, exit
    0. `X4` asks whether every *declared relationship* resolves, which
    is a different question and one this package never raises.
    """
    report = runner.run(_package(tmp_path, "bare", suppl_targets=[]))
    assert len(_missing_part(report)) == 2, (
        "the model names two files this archive does not hold and the run "
        "said: %s" % [(f.id, f.violation.message) for f in report.findings])


def test_the_same_package_with_the_files_in_it_is_silent(tmp_path):
    """The control that makes the finding above mean something."""
    report = runner.run(_package(
        tmp_path, "whole", files=((LOGO, b"\x89PNG"), (CE, b"\x89PNG"))))
    assert not _missing_part(report), _missing_part(report)
    assert report.count(Severity.ERROR) == 0, [
        (f.id, f.violation.message) for f in report.findings]


def test_a_file_value_that_is_a_url_is_somebody_elses_question(tmp_path):
    """A supplementary file held on a server is not a missing part, and
    telling a packager to add `aasx/https:/example.com/x.png` is advice
    that breaks a correct package."""
    def point_at_a_url(elements):
        for element in elements or []:
            if element.get("modelType") == "File":
                element["value"] = "https://example.com/logo.png"
            inner = element.get("value")
            if isinstance(inner, list):
                point_at_a_url(inner)

    # Every File, not the top-level ones. `MarkingFile` sits inside
    # `Markings/[0]`, so a version of this that walked one level deep
    # left it pointing at a part and read the finding it drew as a false
    # positive on a URL.
    env = dn_env()
    for submodel in env["submodels"]:
        point_at_a_url(submodel.get("submodelElements"))
    report = runner.run(_package(tmp_path, "remote", env=env,
                                 suppl_targets=[]))
    assert not _missing_part(report), _missing_part(report)


def test_a_bare_environment_is_not_asked_about_packaging(tmp_path):
    """An environment JSON names files this rule cannot see. Silence
    there is honesty rather than laxity -- the finding would name a
    defect in packaging that is not present to be defective."""
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(dn_env()).encode("utf-8"))
    report = runner.run(path)
    assert not _missing_part(report), _missing_part(report)


def test_the_relationship_question_and_the_value_question_are_both_asked(tmp_path):
    """They are different questions and a package can fail either alone.

    `X4` reads the aas-suppl relationships; this reads the model's File
    values. A package that declares a relationship to an absent part
    raises both, and the fix text for each says which question it is
    answering.
    """
    report = runner.run(_package(tmp_path, "declared",
                                 suppl_targets=[LOGO, CE]))
    assert len(_missing_part(report)) == 2, _missing_part(report)
    assert [f.id for f in report.findings if f.id == "X4"], (
        "X4 stopped asking its own question: %s"
        % sorted({f.id for f in report.findings}))


def test_every_pack_with_a_file_row_asks(tmp_path):
    """Asked of the behaviour, not of a naming convention.

    The body that answers this was called from two packs while four
    tables declare File rows. A gate listing the rule ids that ask would
    pin today's spelling and say nothing about a pack added tomorrow;
    this builds, for each pack that declares File rows, a package whose
    model names a part the archive does not hold, and requires the run
    to say so.
    """
    from aas_submodel_validate.rules import detect

    def sid(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    def build(rows, counter):
        """The minimal tree holding every File row this table declares,
        each at the place the table puts it."""
        out = []
        for row in rows:
            if row["kind"] == "File":
                counter[0] += 1
                out.append({"modelType": "File", "idShort": row["label"],
                            "semanticId": sid(row["sid"]),
                            "contentType": "image/png",
                            "value": "/aasx/files/absent-%d.png" % counter[0]})
                continue
            inner = build(row["children"], counter)
            if not inner:
                continue
            element = {"modelType": row["kind"], "idShort": row["label"],
                       "semanticId": sid(row["sid"]), "value": inner}
            if row["kind"] == "SubmodelElementList":
                element["typeValueListElement"] = inner[0]["modelType"]
                element["orderRelevant"] = True
            out.append(element)
        return out

    for index, pack in enumerate(detect.PACKS):
        rows = [row for row in pack.tables.ROWS if row["kind"] == "File"]
        if not rows:
            continue
        counter = [0]
        env = {"submodels": [{
            "modelType": "Submodel", "id": "urn:test:p%d" % index,
            "idShort": "S", "semanticId": sid(pack.semantic_id),
            "submodelElements": build(pack.tables.TREE, counter)}]}
        assert counter[0] == len(rows), (counter[0], len(rows))
        report = runner.run(_package(tmp_path, "pack%d" % index, env=env,
                                     suppl_targets=[]))
        assert _missing_part(report), (
            "%s declares File rows %s; a package naming parts it does not "
            "hold drew nothing about them: %s"
            % (pack.name, [row["label"] for row in rows],
               sorted({f.id for f in report.findings})))
