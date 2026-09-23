"""The runs `docs/scope.md` shows, run.

A page of worked examples is a page of claims. Each row there names an
exit code and an `ok`, and the two that matter most are the pair that
both say `ok: true` where only one of them judged anything -- the whole
reason `submodelsJudged` is in the report.
"""
from __future__ import annotations

import json
import pathlib

from aas_submodel_validate import runner
from aas_submodel_validate.cli import main
from aas_submodel_validate.model import Severity
from builders import dn_env

#: Resolved from this file, not from wherever pytest was started.
#: A bare relative path here raised `FileNotFoundError` when the suite
#: was run from `tests/`, and sixty-one other places in this suite
#: already take the root the same way.
ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "scope.md"

#: An identifier no pack answers for, so a supplied table is the only
#: thing that could judge a submodel declaring it.
OPEN_TEMPLATE_SID = "urn:test:states-no-rule"


def _metamodel_complaint(tmp_path):
    """A Nameplate whose `ManufacturerName` has no idShort: the
    metamodel objects, the template does not."""
    environment = dn_env()
    for element in environment["submodels"][0]["submodelElements"]:
        if element.get("idShort") == "ManufacturerName":
            element.pop("idShort")
            break
    else:                                        # pragma: no cover
        raise AssertionError("the fixture no longer carries that element")
    path = tmp_path / "meta.json"
    path.write_bytes(json.dumps(environment).encode("utf-8"))
    return path


def _unsupported(tmp_path):
    path = tmp_path / "unsupported.json"
    path.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:u", "idShort": "Other",
        "semanticId": {"type": "ExternalReference", "keys": [{
            "type": "GlobalReference",
            "value": "https://example.com/SomeTemplate/1/0"}]}}]}
    ).encode("utf-8"))
    return path


def test_a_metamodel_complaint_alone_is_a_pass(tmp_path):
    report = runner.run(_metamodel_complaint(tmp_path))
    assert report.ok and report.count(Severity.WARNING) == 1, (
        report.ok, [(f.id, f.severity) for f in report.findings])
    assert report.submodels_judged == 1
    assert {f.id for f in report.findings} == {"META"}


def test_strict_meta_promotes_the_same_finding(tmp_path):
    report = runner.run(_metamodel_complaint(tmp_path), strict_meta=True)
    assert not report.ok and report.count(Severity.ERROR) == 1, (
        report.ok, [(f.id, f.severity) for f in report.findings])
    assert {f.id for f in report.findings} == {"META"}, (
        "the promotion changed which rules spoke, not only how loudly")


def test_a_template_with_no_table_is_not_called_wrong(tmp_path):
    report = runner.run(_unsupported(tmp_path))
    assert {f.id for f in report.findings} == {"SMT-D1"}
    assert report.submodels_judged == 0 and report.submodels_seen == 1


def test_the_pass_that_judged_nothing(tmp_path):
    """The row the page is really for: `ok` true, and nothing judged."""
    report = runner.run(_unsupported(tmp_path), allow_unmatched=True)
    assert report.ok and not report.findings, [
        (f.id, f.violation.message) for f in report.findings]
    assert report.submodels_judged == 0, (
        "a pass that judged nothing has stopped saying so, which is the one "
        "thing this row exists to show")


def test_a_refused_input_still_names_the_bytes_it_refused(tmp_path):
    path = tmp_path / "refused.aasx"
    path.write_bytes(b"not a zip at all")
    report = runner.run(path)
    assert not report.complete
    assert report.input_sha256, "a refusal that names no bytes names a filename"
    assert "X1" in {f.id for f in report.findings}


def test_the_section_is_still_there_and_still_a_table():
    """A guard, and only that.

    This used to hold the claim: it looked for a heading and five
    substrings, none of them a number, so the table's whole `exit`
    column could be wrong -- or the tool's own exit codes could change
    -- and it stayed green. Both were measured. The claim lives in
    `test_every_row_of_the_table_is_run_and_says_what_it_claims` now,
    which runs the page. What is left here is the thing that test needs
    in order to run at all.
    """
    page = PAGE.read_text("utf-8")
    assert "## What a pass means, run by run" in page
    assert "| run | exit | `ok` | what it means |" in page
    for phrase in ("submodelsJudged", "provenance.template.rows",
                   "exits **64**"):
        assert phrase in page, phrase


def _rows_of_the_page():
    """The table, parsed out of the page: (label, exit, ok)."""
    block = PAGE.read_text("utf-8").split(
        "| run | exit | `ok` | what it means |", 1)[1]
    block = block.split("\n\n", 1)[0]
    rows = []
    for line in block.split("\n"):
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4 or set(cells[0]) <= set("-: "):
            continue
        rows.append((cells[0], cells[1], cells[2]))
    return rows


def _all_open_template(tmp_path):
    """A template whose only element is open content, so it states no
    rule this reader can check and its table comes out with no rows."""
    def ref(value):
        return {"type": "GlobalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    path = tmp_path / "all-open-template.json"
    path.write_text(json.dumps({"submodels": [{
        "kind": "Template", "idShort": "T", "id": "urn:t",
        "semanticId": ref(OPEN_TEMPLATE_SID),
        "submodelElements": [{
            "modelType": "SubmodelElementCollection", "idShort": "Free",
            "semanticId": ref("https://admin-shell.io/SMT/General/Arbitrary"),
            "qualifiers": [{"type": "SMT/Cardinality",
                            "valueType": "xs:string", "value": "One"}],
            "value": []}]}]}), encoding="utf-8")
    return path


def _declares_the_open_template(tmp_path):
    from builders import env_json

    path = tmp_path / "declares-open.json"
    path.write_bytes(env_json(OPEN_TEMPLATE_SID))
    return path


def _not_a_template(tmp_path):
    path = tmp_path / "not-a-template.json"
    path.write_text('{"hello": "world"}', encoding="utf-8")
    return path


def _refused(tmp_path):
    path = tmp_path / "refused.aasx"
    path.write_bytes(b"not a zip at all")
    return path


def test_every_row_of_the_table_is_run_and_says_what_it_claims(tmp_path, capsys):
    """The page is the fixture, not something restated in Python.

    The table's `exit` column was asserted nowhere: six of the tests
    above call `runner.run`, which returns a report and no exit code,
    and the seventh looked for five substrings, none of them a number.
    Measured, twice: setting every `exit` cell to 7 and flipping every
    `ok` cell left this file green, and changing the tool's own
    `EXIT_FINDINGS` and `EXIT_ERROR` left it green too. A claim nothing
    reads drifts in either direction, and both directions had a way in.

    So each row is looked up by its own words, run through `main` -- the
    entrance a build uses -- and compared against what the page prints.
    A row this file has no run for fails rather than passes: a claim
    nobody can produce is the thing being guarded against.
    """
    argv_for = {
        "a file whose only complaint is from the metamodel":
            lambda: [str(_metamodel_complaint(tmp_path))],
        "the same file with `--meta error`":
            lambda: [str(_metamodel_complaint(tmp_path)), "--meta", "error"],
        "a submodel of a template this build has no table for, and no `--template`":
            lambda: [str(_unsupported(tmp_path))],
        "the same with `--allow-unmatched`":
            lambda: [str(_unsupported(tmp_path)), "--allow-unmatched"],
        "the same again with `--require-all-judged`":
            lambda: [str(_unsupported(tmp_path)), "--allow-unmatched",
                     "--require-all-judged"],
        "a supplied table that states no rule this reader can check":
            lambda: [str(_declares_the_open_template(tmp_path)), "--template",
                     str(_all_open_template(tmp_path)), "--require-all-judged"],
        "an input this reader refuses to read":
            lambda: [str(_refused(tmp_path))],
        "a `--template` this reader refuses to read":
            lambda: [str(_metamodel_complaint(tmp_path)), "--template",
                     str(_not_a_template(tmp_path))],
    }

    rows = _rows_of_the_page()
    assert rows, "the table did not parse"
    unrunnable = [label for label, _exit, _ok in rows if label not in argv_for]
    assert not unrunnable, (
        "the page shows a run this file cannot produce: %s" % unrunnable)

    for label, printed_exit, printed_ok in rows:
        capsys.readouterr()
        # `main` returns the code on the paths that produce a report and
        # raises for a usage error, so both are read the same way here.
        try:
            code = main(argv_for[label]() + ["-f", "json"])
        except SystemExit as left:              # pragma: no cover - usage only
            code = left.code
        written = capsys.readouterr().out
        assert str(code) == printed_exit, (
            "%r: the page says exit %s and the run left with %s"
            % (label, printed_exit, code))
        if printed_ok == "no report":
            assert not written.strip(), (
                "%r: the page says no report and the run wrote %d bytes"
                % (label, len(written)))
            continue
        assert written.strip(), (
            "%r: the page states `ok` %s and the run wrote no report"
            % (label, printed_ok))
        assert str(json.loads(written)["ok"]).lower() == printed_ok, (
            "%r: the page says `ok` %s and the report says %s"
            % (label, printed_ok, json.loads(written)["ok"]))
