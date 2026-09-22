"""The five runs `docs/scope.md` shows, run.

A page of worked examples is a page of claims. Each row there names an
exit code and an `ok`, and the two that matter most are the pair that
both say `ok: true` where only one of them judged anything -- the whole
reason `submodelsJudged` is in the report.
"""
from __future__ import annotations

import json

from aas_submodel_validate import runner
from aas_submodel_validate.cli import main
from aas_submodel_validate.model import Severity
from builders import dn_env

PAGE = "docs/scope.md"


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


def test_a_usage_error_exits_64_and_writes_nothing(capsys):
    import pytest

    with pytest.raises(SystemExit) as raised:
        main(["--no-such-option"])
    assert raised.value.code == 64, raised.value.code
    assert not capsys.readouterr().out


def test_the_page_says_the_five_this_tree_produces():
    """The table's exit codes, against the rows above.

    Held as the set of codes the page names, because the page is where a
    reader learns which of them means "could not judge" rather than
    "judged and failed".
    """
    import pathlib

    page = pathlib.Path(PAGE).read_text("utf-8")
    assert "## What a pass means, in five runs" in page
    for phrase in ("`--strict-meta`", "`SMT-D1`", "`--allow-unmatched`",
                   "submodelsJudged", "exits **64**"):
        assert phrase in page, phrase
