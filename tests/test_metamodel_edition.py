"""Which edition of the AAS metamodel a run reads, and what it says to a
document written in another.

This reader reads metamodel 3.0. An XML document names its edition in
its namespace -- `https://admin-shell.io/aas/3/0` for 3.0, `.../3/1` for
3.1, `http://www.admin-shell.io/aas/2/0` before 3.0 -- so a document of
another edition is refused and told which edition it is, rather than
told to fix a syntax that may well be sound. The edition is read off the
namespace alone: nothing here knows a file by name, and the tests put
the same bytes in several namespaces to show it.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from aas_submodel_validate import runner
from builders import hd_env

CORPUS = Path(__file__).resolve().parent / "corpus" / "idta"
TD_AAS31 = CORPUS / "02003" / "sample-2.0.1-for-aas-3.1.aasx"
HD_AAS31 = CORPUS / "02004" / "template-sample-2.0.1-for-aas-3.1.aasx"
DN_AAS2 = CORPUS / "02006" / "sample-2.0.aasx"
EXAMPLE = (Path(__file__).resolve().parents[1]
           / "src" / "aas_submodel_validate" / "data" / "example" / "idta-02004-2.0.aasx")

AAS31 = b"https://admin-shell.io/aas/3/1"
OTHER = "the document is written in AAS metamodel %s, which this reader does not read"


def _payload(package) -> bytes:
    with zipfile.ZipFile(package) as archive:
        [name] = [n for n in archive.namelist() if n.endswith(".aas.xml")]
        return archive.read(name)


def _x3(report):
    [finding] = [f for f in report.findings if f.id == "X3"]
    return finding


def _bare(tmp_path, data: bytes):
    path = tmp_path / "env.xml"
    path.write_bytes(data)
    return runner.run(path)


@pytest.mark.parametrize("package", [TD_AAS31, HD_AAS31], ids=["02003", "02004"])
def test_a_package_in_the_3_1_namespace_is_told_its_edition(package):
    finding = _x3(runner.run(package))
    assert finding.violation.message == OTHER % "3.1", finding.violation.message
    assert "names 3.1 (`https://admin-shell.io/aas/3/1`)" in finding.fix, finding.fix
    assert "was refused, not judged" in finding.fix
    assert finding.fix != finding.rule.fix, "told to fix a syntax that is sound"


@pytest.mark.parametrize("namespace, edition", [
    ("https://admin-shell.io/aas/3/1", "3.1"),
    ("https://admin-shell.io/aas/3/2", "3.2"),
    ("http://www.admin-shell.io/aas/2/0", "2.0"),
], ids=["3.1", "3.2", "2.0"])
def test_a_bare_document_is_told_the_edition_its_namespace_names(tmp_path, namespace, edition):
    """The same bytes -- the 3.1 Technical Data sample's payload -- in each
    namespace. The edition named is read off the namespace, so one no
    published file uses yet is named too."""
    finding = _x3(_bare(tmp_path, _payload(TD_AAS31).replace(AAS31, namespace.encode())))
    assert finding.violation.message == OTHER % edition, finding.violation.message
    assert "(`%s`)" % namespace in finding.fix, finding.fix


def test_in_the_3_0_namespace_the_same_bytes_are_read(tmp_path):
    report = _bare(tmp_path, _payload(TD_AAS31).replace(AAS31, b"https://admin-shell.io/aas/3/0"))
    assert [f.id for f in report.findings if f.id == "X3"] == []
    assert report.submodels_judged == 1


def test_a_3_0_document_its_parser_rejects_keeps_the_standing_remedy(tmp_path):
    """The 3.0 control: in 3.0's own namespace, a document the parser
    rejects -- an element no environment has -- is told what it always
    was: that it could not be read, and to fix what the parser names."""
    text = _payload(TD_AAS31).replace(AAS31, b"https://admin-shell.io/aas/3/0")
    text = text.replace(b"<submodels>", b"<submodelz>", 1).replace(b"</submodels>", b"</submodelz>", 1)
    finding = _x3(_bare(tmp_path, text))
    assert finding.violation.message == "the document could not be read as an AAS environment"
    assert finding.fix == finding.rule.fix


def test_a_document_in_no_edition_s_namespace_keeps_the_standing_remedy(tmp_path):
    """Not a metamodel namespace at all: no edition to name, and the
    standing remedy is the true one."""
    finding = _x3(_bare(tmp_path, b'<environment xmlns="urn:example:not-aas"/>'))
    assert finding.violation.message == "the document could not be read as an AAS environment"
    assert finding.fix == finding.rule.fix


def test_the_aas_2_payload_is_told_its_edition(tmp_path):
    """The 2.0 package given 3.0's relationship types reaches its payload,
    which names 2.0."""
    out = io.BytesIO()
    with zipfile.ZipFile(DN_AAS2) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.endswith(".rels"):
                data = data.replace(b"http://www.admin-shell.io/aasx/relationships/",
                                    b"http://admin-shell.io/aasx/relationships/")
            zout.writestr(info, data)
    path = tmp_path / "dn.aasx"
    path.write_bytes(out.getvalue())
    finding = _x3(runner.run(path))
    assert finding.violation.message == OTHER % "2.0", finding.violation.message


def test_a_bare_submodel_in_the_3_1_namespace_is_told_its_edition(tmp_path):
    """A bare `submodel` root is read by the submodel reader, and told the
    same."""
    report = _bare(tmp_path, b'<submodel xmlns="https://admin-shell.io/aas/3/1">'
                             b'<id>urn:example:sm</id></submodel>')
    finding = _x3(report)
    assert finding.violation.message == OTHER % "3.1", finding.violation.message


@pytest.mark.parametrize("which", ["json", "aasx", "refused"])
def test_every_report_says_which_edition_it_read_the_input_as(tmp_path, which):
    """`summary.metamodel`: the edition this run read the input as, and
    whose constraints the `meta` channel relays -- 3.0, whether the input
    was judged, packaged, or refused for naming another."""
    if which == "json":
        path = tmp_path / "env.json"
        path.write_text(json.dumps(hd_env()), "utf-8")
    else:
        path = EXAMPLE if which == "aasx" else TD_AAS31
    assert runner.run(path).as_dict()["summary"]["metamodel"] == "3.0"
