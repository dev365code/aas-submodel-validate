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


def test_the_relationship_remedy_does_not_undo_a_correct_declaration(tmp_path):
    """One missing part, both rules, and X4 offered two ways out as equals:
    add the part, or delete the relationship. Where a File value names the
    part too, deleting leaves it missing. The remedy now says what deleting
    does and does not do, and offers correcting the name first -- a name no
    part can carry has no part to add.
    """
    report = runner.run(_package(tmp_path, "declared-too",
                                 suppl_targets=[LOGO, CE]))
    assert len(_missing_part(report)) == 2, _missing_part(report)
    (remedy,) = {f.fix for f in report.findings if f.id == "X4"}
    assert "removes only the declaration" in remedy, remedy
    assert remedy.startswith("Correct the relationship's target"), remedy


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


def test_a_row_the_template_calls_online_is_not_asked_for_a_part(tmp_path):
    """02023 declares two File rows and they do not mean the same thing.

    The vendored template's own description for `PcfRuleOnlineReference`
    is "Online PCF calculation methodology reference that provides
    detailed instructions and guidelines for calculating a product's
    carbon footprint" -- a pointer to somebody else's published method,
    not a file the supplier packs. Installing the question on
    `kind == "File"` alone made it a MUST that the file be in the
    container, with the remedy "Add the file to the .aasx".

    Measured, with the other File row held at a real part so only this
    one moves: three of four ways an online reference is actually
    written -- `www.…/standard.pdf`, `ghgprotocol.org`,
    `//www.…/standard.pdf` -- failed the package and told the supplier
    to put a standards body's PDF inside their own `.aasx`. Only the
    fully-formed `https://` spelling was spared, and only because a
    scheme makes the rule look elsewhere.

    `ExplanatoryStatement` is the other row and it is a real attachment
    (`docs/divergences.md` #55), so it keeps the question.
    """
    import json

    from builders import build_aasx, pcf_env

    def judged(value):
        document = json.loads(json.dumps(pcf_env()))

        def walk(node):
            if isinstance(node, dict):
                if node.get("modelType") == "File":
                    node["value"] = (value if node.get("idShort")
                                     == "PcfRuleOnlineReference"
                                     else "/aasx/files/held.pdf")
                for child in node.values():
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(document)
        path = build_aasx(tmp_path / ("cf-%d.aasx" % abs(hash(value))),
                          payload=json.dumps(document).encode("utf-8"),
                          files=(("aasx/files/held.pdf", b"%PDF-1.4 "),))
        return [finding for finding in runner.run(str(path)).findings
                if finding.rule.id == "PCF-D1"
                and "PcfRuleOnlineReference" in (finding.violation.subject or "")]

    for spelling in ("https://ghgprotocol.org/standard.pdf",
                     "www.ghgprotocol.org/standard/product-standard.pdf",
                     "ghgprotocol.org",
                     "//www.ghgprotocol.org/standard.pdf"):
        assert not judged(spelling), (
            "%r: the template calls this row an online reference and the "
            "report tells the supplier to put the file in their package"
            % spelling)


def test_the_other_file_row_of_that_pack_still_asks(tmp_path):
    """The exclusion is one row, not the rule.

    A pack that stopped asking entirely would pass this file too, so the
    row that *is* an attachment is asked in the same breath.
    """
    import json

    from builders import build_aasx, pcf_env

    document = json.loads(json.dumps(pcf_env()))

    def walk(node):
        if isinstance(node, dict):
            if node.get("modelType") == "File":
                node["value"] = ("/aasx/files/absent.pdf"
                                 if node.get("idShort") == "ExplanatoryStatement"
                                 else "https://ghgprotocol.org/standard.pdf")
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(document)
    path = build_aasx(tmp_path / "cf-attachment.aasx",
                      payload=json.dumps(document).encode("utf-8"), files=())
    drawn = [finding for finding in runner.run(str(path)).findings
             if finding.rule.id == "PCF-D1"]
    assert drawn, "the pack stopped asking about the row that is an attachment"


def test_asking_where_the_files_are_does_not_cost_elements_times_parts(
        tmp_path, monkeypatch):
    """This rule joins a document to the parts a container holds, and a
    join is where this project has met a quadratic before.

    It is linear today for a reason that lives somewhere else: the
    container builds its name indexes once and answers from them. Remove
    those guards and the work goes as elements times parts while every
    verdict stays identical -- so nothing that reads findings notices,
    and the suite stays green.

    Counted, not timed: a stopwatch on a shared machine measures the
    machine. The count that discriminates is not the total -- building
    an index is linear in parts and that is fine -- but whether ONE MORE
    ELEMENT costs more when the container holds more parts. Measured
    here at two widths, that extra cost is the same number at forty
    parts and at four hundred. Under a product it would grow with them.

    Bounded below as well: the same runs must go on drawing their
    findings, because a gate that only counts work is passed by doing
    none, and a deleted rule would sail under any ceiling.
    """
    import json

    from aas_submodel_validate import container as container_module
    from builders import build_aasx, dn_env

    def widened(markings):
        """The nameplate with `markings` entries, each naming a file the
        package does not hold -- so each one is an element this rule has
        to ask the container about."""
        document = json.loads(json.dumps(dn_env()))

        def marks(node):
            if isinstance(node, dict):
                if node.get("idShort") == "Markings":
                    first = node["value"][0]
                    node["value"] = [json.loads(json.dumps(first))
                                     for _ in range(markings)]
                    for seat, entry in enumerate(node["value"]):
                        def name(inner, seat=seat):
                            if isinstance(inner, dict):
                                if inner.get("modelType") == "File":
                                    inner["value"] = "/aasx/files/gone-%d.png" % seat
                                for child in inner.values():
                                    name(child)
                            elif isinstance(inner, list):
                                for child in inner:
                                    name(child)
                        name(entry)
                    return True
                return any(marks(child) for child in node.values())
            if isinstance(node, list):
                return any(marks(child) for child in node)
            return False

        assert marks(document), "the fixture no longer has a Markings list"
        return document

    def asked(markings, parts):
        document = widened(markings)
        held = tuple(("aasx/files/filler-%04d.bin" % index, b"x")
                     for index in range(parts))
        path = build_aasx(tmp_path / ("cost-%d-%d.aasx" % (markings, parts)),
                          payload=json.dumps(document).encode("utf-8"),
                          files=held)
        counted = []
        real = container_module.canonical_part_name
        monkeypatch.setattr(container_module, "canonical_part_name",
                            lambda value: (counted.append(1), real(value))[1])
        try:
            report = runner.run(str(path))
        finally:
            monkeypatch.setattr(container_module, "canonical_part_name", real)
        drawn = [finding for finding in report.findings
                 if finding.rule.id == "DN-D2"]
        return len(counted), len(drawn)

    few_narrow, drawn_few_narrow = asked(2, 40)
    many_narrow, drawn_many_narrow = asked(12, 40)
    few_wide, drawn_few_wide = asked(2, 400)
    many_wide, drawn_many_wide = asked(12, 400)

    # Below: the work is still done and still reported, at both widths.
    assert drawn_few_narrow and drawn_few_wide, (drawn_few_narrow, drawn_few_wide)
    assert drawn_many_narrow > drawn_few_narrow, (drawn_few_narrow, drawn_many_narrow)
    assert drawn_many_wide == drawn_many_narrow, (drawn_many_wide, drawn_many_narrow)

    # Above: what ten more elements cost must not depend on how many
    # parts the container holds.
    at_forty = many_narrow - few_narrow
    at_four_hundred = many_wide - few_wide
    assert at_forty > 0, (few_narrow, many_narrow)
    assert at_four_hundred <= at_forty * 2, (
        "ten more elements cost %d more lookups in a package of forty parts "
        "and %d in one of four hundred -- the join is growing with the "
        "product of the two" % (at_forty, at_four_hundred))
