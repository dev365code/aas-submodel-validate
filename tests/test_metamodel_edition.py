"""Which edition of the AAS metamodel this reader reads, and what it says
to a document written in another.

This reader reads metamodel 3.0. An XML document names its edition in
its namespace -- `https://admin-shell.io/aas/3/0` for 3.0, `.../3/1` for
3.1, `http://www.admin-shell.io/aas/2/0` before 3.0 -- so a document of
another edition is refused and told which edition it is, rather than
told to fix a syntax that may well be sound. The edition is read off the
namespace alone: nothing here knows a file by name, and the tests put
the same bytes -- an official sample's -- in several namespaces to show
it, including namespaces that only look like an edition's and must be
told nothing of the kind.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from aas_submodel_validate import runner

CORPUS = Path(__file__).resolve().parent / "corpus" / "idta"
TD_AAS31 = CORPUS / "02003" / "sample-2.0.1-for-aas-3.1.aasx"
HD_AAS31 = CORPUS / "02004" / "template-sample-2.0.1-for-aas-3.1.aasx"
DN_AAS2 = CORPUS / "02006" / "sample-2.0.aasx"
TD_JSON = CORPUS / "02003" / "sample-2.0.json"
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


#: What a 3.1 document is told, word for word: a substring cannot tell a
#: remedy from one with a demand bolted on, or with its two editions
#: swapped. The census in `test_registry` holds the same sentence.
REMEDY_31 = (
    "This reader reads AAS metamodel 3.0, and an XML document names its "
    "edition in its namespace: this one names 3.1 "
    "(`https://admin-shell.io/aas/3/1`), and was read no further. To be "
    "judged here it has to be written in metamodel 3.0. Nothing here is a "
    "verdict on the document -- it was refused, not judged.")


@pytest.mark.parametrize("package", [TD_AAS31, HD_AAS31], ids=["02003", "02004"])
def test_a_package_in_the_3_1_namespace_is_told_its_edition(package):
    finding = _x3(runner.run(package))
    assert finding.violation.message == OTHER % "3.1", finding.violation.message
    assert finding.fix == REMEDY_31, finding.fix


@pytest.mark.parametrize("namespace, edition", [
    ("https://admin-shell.io/aas/3/1", "3.1"),
    ("https://admin-shell.io/aas/3/2", "3.2"),
    ("https://admin-shell.io/aas/3/10", "3.10"),
    ("http://www.admin-shell.io/aas/2/0", "2.0"),
], ids=["3.1", "3.2", "3.10", "2.0"])
def test_a_bare_document_is_told_the_edition_its_namespace_names(tmp_path, namespace, edition):
    """The same bytes -- the 3.1 Technical Data sample's payload -- in each
    namespace. The edition named is read off the namespace, so one no
    published file uses yet is named too."""
    finding = _x3(_bare(tmp_path, _payload(TD_AAS31).replace(AAS31, namespace.encode())))
    assert finding.violation.message == OTHER % edition, finding.violation.message
    assert "(`%s`)" % namespace in finding.fix, finding.fix


@pytest.mark.parametrize("namespace", [
    "https://admin-shell.io/aas/03/0",
    "https://admin-shell.io/aas/\uff13/\uff10",
    "https://admin-shell.io/aas/\u0663/\u0661",
    "http://admin-shell.io/aas/3/1",
    "https://www.admin-shell.io/aas/3/1",
    "http://www.admin-shell.io/aas/3/1",
    "https://admin-shell.io/aas/2/0",
    "https://admin-shell.io/aas/3/1000",
    "https://admin-shell.io/aas/3/1&#10;",
    "https://admin-shell.io/aas/3/1/extra",
], ids=["leading-zero", "fullwidth-digits", "arabic-indic-digits", "http-no-www",
        "https-www", "pre-3-host-for-3", "3-host-for-2", "four-digits",
        "trailing-newline", "longer-path"])
def test_a_namespace_that_only_resembles_an_edition_s_names_none(tmp_path, namespace):
    """No edition is written `03.0`, in fullwidth digits, or in a host
    form no edition uses, and a report that named one would be telling
    the author of a typo that the reader lacks an edition. These keep
    the standing remedy, and aas-core's detail, which quotes the
    namespace as written."""
    finding = _x3(_bare(tmp_path, _payload(TD_AAS31).replace(AAS31, namespace.encode())))
    assert finding.violation.message == "the document could not be read as an AAS environment"
    assert finding.fix == finding.rule.fix


def test_the_edition_is_the_root_element_s_and_nobody_else_s(tmp_path):
    """"Read off the root element's namespace and nothing else": the 3.0
    sample bytes with a 3.1 namespace mentioned in a comment before the
    root and worn by the root's first child, which its parser rejects. The
    root is 3.0's, so there is no other edition to name -- not the first
    namespace in the text, and not the first element to close."""
    text = _payload(TD_AAS31).replace(AAS31, b"https://admin-shell.io/aas/3/0")
    root_ends = text.index(b">", text.index(b"<environment")) + 1
    text = (text[:root_ends].replace(b"<environment",
                                     b"<!-- exported from https://admin-shell.io/aas/3/1 -->"
                                     b"<environment", 1)
            + b'<x:note xmlns:x="https://admin-shell.io/aas/3/1"/>' + text[root_ends:])
    finding = _x3(_bare(tmp_path, text))
    assert finding.violation.message == "the document could not be read as an AAS environment"
    assert finding.fix == finding.rule.fix


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
    finding = _x3(_bare(tmp_path, _payload(TD_AAS31).replace(AAS31, b"urn:example:not-aas")))
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


def _bare_submodel(namespace: bytes) -> bytes:
    """The official 3.1 sample's Submodel on its own, as a bare document,
    in `namespace`."""
    from xml.etree import ElementTree
    ns = AAS31.decode()
    root = ElementTree.fromstring(_payload(TD_AAS31))
    submodel = root.find("{%s}submodels/{%s}submodel" % (ns, ns))
    return ElementTree.tostring(submodel).replace(AAS31, namespace)


def test_a_bare_submodel_in_the_3_1_namespace_is_told_its_edition(tmp_path):
    """A bare `submodel` root is read by the submodel reader, and told the
    same; in the 3.0 namespace the same Submodel is read and judged."""
    finding = _x3(_bare(tmp_path, _bare_submodel(AAS31)))
    assert finding.violation.message == OTHER % "3.1", finding.violation.message
    report = _bare(tmp_path, _bare_submodel(b"https://admin-shell.io/aas/3/0"))
    assert [f.id for f in report.findings if f.id == "X3"] == []
    assert report.submodels_judged == 1


@pytest.mark.parametrize("which", ["json", "aasx", "refused", "missing"])
def test_every_report_names_the_edition_this_reader_reads(tmp_path, which):
    """`summary.metamodel`: the edition this reader reads, and whose
    constraints the `meta` channel relays -- 3.0, whatever the input and
    whether or not anything in it was read."""
    path = {"json": TD_JSON, "aasx": EXAMPLE, "refused": TD_AAS31,
            "missing": tmp_path / "missing.aasx"}[which]
    assert runner.run(path).as_dict()["summary"]["metamodel"] == "3.0"
