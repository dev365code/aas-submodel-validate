"""What this tool says about IDTA's own files that it refuses, pinned as
it is.

Three published files are refused rather than judged: the samples
upstream publishes beside 02004 2.0.1 and 02003 2.0.1 a second time, for
metamodel 3.1, and the 02006 2.0 sample, an AAS 2.0 package upstream
keeps under `deprecated/`. They are IDTA's own material, so the refusal
is a regression surface like any verdict. Each is pinned beside
a mutation of itself that isolates the reason: a change that moved one
of them for another reason would pass the first test and fail the
second.
"""
from __future__ import annotations

import copy
import io
import json
import zipfile
from pathlib import Path

import pytest

from aas_submodel_validate import runner

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "corpus" / "idta"
DN_AAS2 = CORPUS / "02006" / "sample-2.0.aasx"
HD_AAS31 = CORPUS / "02004" / "template-sample-2.0.1-for-aas-3.1.aasx"
TD_AAS31 = CORPUS / "02003" / "sample-2.0.1-for-aas-3.1.aasx"
TD_JSON = CORPUS / "02003" / "sample-2.0.json"
ORIGIN_2 = b"http://www.admin-shell.io/aasx/relationships/aasx-origin"

AAS30 = b"https://admin-shell.io/aas/3/0"
AAS31 = b"https://admin-shell.io/aas/3/1"


def _rewritten(source, tmp_path, change):
    """The package again, every member passed through `change(name, data)`."""
    out = io.BytesIO()
    with zipfile.ZipFile(source) as zin, \
            zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            zout.writestr(info, change(info.filename, zin.read(info.filename)))
    path = tmp_path / source.name
    path.write_bytes(out.getvalue())
    return path


def _own(report):
    return sorted(f.id for f in report.findings if f.rule.kind != "meta")


def test_the_aas_2_sample_is_refused_at_its_relationships():
    """Its relationship types are AAS 2.0's, `http://www.admin-shell.io/
    aasx/relationships/...`, and this reader follows 3.0's: the chain is
    not followed (`X2`), nothing is judged, and the report says which type
    the package declared -- not that it declares none, and not to repair a
    chain that may be whole in its own vocabulary."""
    report = runner.run(DN_AAS2)
    assert _own(report) == ["X2"], _own(report)
    assert (report.ok, report.submodels_seen) == (False, 0)
    [finding] = report.findings
    assert ORIGIN_2.decode() in finding.violation.message, finding.violation.message
    assert "declares no aasx-origin relationship" not in finding.violation.message
    assert finding.fix != finding.rule.fix, finding.fix


def test_with_no_origin_relationship_at_all_the_chain_is_to_be_repaired(tmp_path):
    """The control: the same package with its origin relationship removed
    declares none, and that is what it is told, with the standing remedy."""
    path = _rewritten(DN_AAS2, tmp_path, lambda name, data: data.replace(
        ORIGIN_2, b"http://example.com/not-a-relationship") if name == "_rels/.rels" else data)
    report = runner.run(path)
    [finding] = report.findings
    assert (finding.id, finding.fix) == ("X2", finding.rule.fix)
    assert "declares no aasx-origin relationship" in finding.violation.message


def test_given_3_0_relationships_the_aas_2_payload_is_refused_in_turn(tmp_path):
    """The mutation that isolates it: with 3.0's relationship types the
    chain resolves, and the payload -- an AAS 2.0 environment -- does not
    parse (`X3`)."""
    path = _rewritten(DN_AAS2, tmp_path, lambda name, data: data.replace(
        b"http://www.admin-shell.io/aasx/relationships/",
        b"http://admin-shell.io/aasx/relationships/") if name.endswith(".rels") else data)
    report = runner.run(path)
    assert _own(report) == ["X3"], _own(report)
    [finding] = report.findings
    assert "http://www.admin-shell.io/aas/2/0" in finding.violation.detail, \
        finding.violation.detail


@pytest.mark.parametrize("path", [HD_AAS31, TD_AAS31], ids=["02004", "02003"])
def test_a_sample_for_metamodel_3_1_is_refused_for_its_namespace(path):
    report = runner.run(path)
    assert _own(report) == ["X3"], _own(report)
    [finding] = report.findings
    assert AAS31.decode() in finding.violation.detail, finding.violation.detail
    assert (report.ok, report.submodels_seen) == (False, 0)


def test_in_the_3_0_namespace_the_technical_data_sample_is_judged_and_passes(tmp_path):
    """The mutation that isolates the 02003 one: the same bytes in the 3.0
    namespace parse, are judged against 02003's table, and draw no rule of
    this project's -- the refusal is the namespace and nothing else."""
    path = _rewritten(TD_AAS31, tmp_path, lambda name, data: data.replace(AAS31, AAS30)
                      if name.endswith(".aas.xml") else data)
    report = runner.run(path)
    assert _own(report) == [], _own(report)
    assert (report.submodels_seen, report.submodels_judged) == (1, 1)
    assert report.ok


def test_in_the_3_0_namespace_the_handover_sample_is_set_aside_as_a_template(tmp_path):
    """The 02004 one is a template -- `kind: Template` -- whatever its name
    says. In the 3.0 namespace it parses and is set aside rather than
    judged, as every template is."""
    path = _rewritten(HD_AAS31, tmp_path, lambda name, data: data.replace(AAS31, AAS30)
                      if name.endswith(".aas.xml") else data)
    report = runner.run(path)
    assert _own(report) == [], _own(report)
    assert (report.submodels_seen, report.submodels_judged,
            report.submodels_specified) == (1, 0, 1)


def test_the_scope_page_says_which_metamodel_is_read():
    """The page that says what this project refuses names the metamodel it
    reads and what happens to the others, and the runs above are what it
    says."""
    scope = " ".join((ROOT / "docs" / "scope.md").read_text("utf-8").split())
    assert "an XML document in the 3.1 namespace (`https://admin-shell.io/aas/3/1`) is refused (`X3`)" in scope
    assert "an AAS 2.0 package, whose relationships are declared in 2.0's vocabulary, is refused at them (`X2`)" in scope




def _judged(tmp_path, env):
    path = tmp_path / "env.json"
    path.write_text(json.dumps(env), "utf-8")
    return runner.run(path)


def _first(elements, kind):
    """The first element of `kind`, depth first."""
    for element in elements or []:
        if element.get("modelType") == kind:
            return element
        value = element.get("value")
        if isinstance(value, list) and value and isinstance(value[0], dict):
            found = _first(value, kind)
            if found is not None:
                return found
    return None


def _aasd_120(report):
    return sum("AASd-120" in f.violation.message for f in report.findings
               if f.rule.kind == "meta")


def test_a_json_document_written_for_3_1_is_read_as_3_0(tmp_path):
    """JSON carries no metamodel edition, so the scope page says a 3.1 one
    is read as 3.0, and these are the two halves of that, on IDTA's own
    02003 sample: what 3.1 alone permits does not parse -- a File with no
    `contentType` -- and what 3.1 relaxed is relayed as 3.0 states it.
    Every list in the sample gives its items idShorts, which 3.0 forbids
    (AASd-120) and 3.1 no longer does; the relay says so once per list,
    and a list whose items lose their idShorts drops out of the count."""
    official = json.loads(TD_JSON.read_text("utf-8"))
    env = copy.deepcopy(official)
    _first(env["submodels"][0]["submodelElements"], "File").pop("contentType")
    assert _own(_judged(tmp_path, env)) == ["X3"]
    before = _judged(tmp_path, official)
    assert _aasd_120(before) >= 1
    env = copy.deepcopy(official)
    for item in _first(env["submodels"][0]["submodelElements"], "SubmodelElementList")["value"]:
        item.pop("idShort")
    after = _judged(tmp_path, env)
    assert _own(after) == _own(before)
    assert _aasd_120(after) == _aasd_120(before) - 1, (_aasd_120(before), _aasd_120(after))
