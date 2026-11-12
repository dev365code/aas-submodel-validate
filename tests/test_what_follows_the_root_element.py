"""After its root element an XML document holds comments, processing
instructions and whitespace, and nothing else.

XML 1.0 §2.1: `[1] document ::= prolog element Misc*`, and `[27] Misc ::=
Comment | PI | S`. aas-core3.0 reads a document as far as its root
element's end tag and stops there, so whatever came after it went unread
-- text, a second element, a second document -- and the file was judged
on what came first and could pass. A package's relationships part with
the same tail was refused all along; the document that part names was
not.
"""
from __future__ import annotations

import aas_core3.jsonization as jsonization
import aas_core3.xmlization as xmlization
import pytest

from aas_submodel_validate import runner
from builders import build_aasx, contact_env

#: What may follow the root element.
ALLOWED = {"whitespace": "\n  \t\n", "newlines": "\n\n\n", "comment": "\n<!-- after -->\n",
           "instruction": "\n<?after this?>\n"}

#: What may not. `None` is the document itself, a second time.
REFUSED = {"text": "\nx", "element": "\n<other/>", "second-root": None,
           "cdata": "\n<![CDATA[x]]>", "character-reference": "\n&#65;",
           "doctype": "\n<!DOCTYPE environment>"}

PLACES = ("environment", "submodel", "aasx")


def _document(place):
    environment = jsonization.environment_from_jsonable(contact_env())
    if place == "submodel":
        return xmlization.to_str(environment.submodels[0])
    return xmlization.to_str(environment)


def _write(tmp_path, place, document, tail):
    data = (document + tail).encode("utf-8")
    if place == "aasx":
        path = tmp_path / "package.aasx"
        build_aasx(path, data, payload_name="aasx/env.xml")
    else:
        path = tmp_path / ("%s.xml" % place)
        path.write_bytes(data)
    return path


@pytest.mark.parametrize("place", PLACES)
@pytest.mark.parametrize("tail", sorted(ALLOWED))
def test_comments_instructions_and_whitespace_may_follow_the_root(tmp_path, place, tail):
    report = runner.run(_write(tmp_path, place, _document(place), ALLOWED[tail]))
    assert report.judged and report.ok, [(f.id, f.violation.message) for f in report.findings]


@pytest.mark.parametrize("place", PLACES)
@pytest.mark.parametrize("tail", sorted(REFUSED))
def test_anything_else_after_the_root_is_refused_where_it_is(tmp_path, place, tail):
    document = _document(place)
    after = REFUSED[tail] if REFUSED[tail] is not None else "\n" + document
    report = runner.run(_write(tmp_path, place, document, after))
    assert not report.judged, [(f.id, f.violation.message) for f in report.findings]
    [finding] = [f for f in report.findings if f.id == "X3"]
    assert "after its root element" in finding.violation.message, finding.violation.message
    assert finding.violation.line == document.count("\n") + 2, finding.violation.line
    assert "comments, processing instructions and whitespace" in finding.violation.fix


def test_a_declared_encoding_does_not_stand_in_for_the_tail(tmp_path):
    """A document declaring `US-ASCII` has a refusal of its own, for a
    byte outside ASCII, found where it is. One that declares it and
    holds only ASCII is refused for what follows its root, and on the
    line that is."""
    document = '<?xml version="1.0" encoding="US-ASCII"?>\n' + _document("environment")
    report = runner.run(_write(tmp_path, "environment", document, "\nx"))
    [finding] = [f for f in report.findings if f.id == "X3"]
    assert "after its root element" in finding.violation.message, finding.violation.message
    assert finding.violation.line == document.count("\n") + 2, finding.violation.line
