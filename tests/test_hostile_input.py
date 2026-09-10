"""Untrusted containers must fail as findings or exit-2, never as a crash
and never by exhausting memory. These reproduce the hostile-input
review's confirmed DoS and crash cases.
"""
from __future__ import annotations

import contextlib
import json
import os
import pathlib
import stat
import tracemalloc
import types
import zipfile
from unittest import mock
from xml.etree import ElementTree

import pytest

from aas_submodel_validate import container, loader, runner
from aas_submodel_validate.cli import EXIT_ERROR, main
from aas_submodel_validate.container import AasxPackage, ContainerError
from aas_submodel_validate.registry import all_rules
from aas_submodel_validate.report import render
from builders import (
    CONTENT_TYPES,
    ORIGIN_REL,
    SPEC_REL,
    SUPPL_REL,
    build_aasx,
    corrupt_part,
    env_json,
    hd_env,
    rels,
)
from verdicts import by_id


def test_the_cap_is_the_documented_number():
    """The cap was a number no test named, so any value would have passed
    -- including one small enough to refuse real files."""
    assert container.MAX_PART_BYTES == 64 * 1024 * 1024
    assert container.MAX_TOTAL_PART_BYTES == 256 * 1024 * 1024


def test_an_oversized_spec_part_is_refused(tmp_path, monkeypatch):
    """The payload is built from the cap rather than from a constant of
    its own: a test that hard-codes the size it expects to be refused
    stops watching the moment the cap moves. (It also stops allocating
    two hundred megabytes to say so.)"""
    monkeypatch.setattr(container, "MAX_PART_BYTES", 256 * 1024)
    path = tmp_path / "big.aasx"
    over = b"<x/>" + b" " * (container.MAX_PART_BYTES + 1)
    build_aasx(path, payload=over, payload_name="aasx/env.xml")
    with AasxPackage(path) as package, pytest.raises(ContainerError, match="bytes"):
        package.read("aasx/env.xml")


def test_a_part_at_the_cap_is_still_read(tmp_path, monkeypatch):
    """The other edge. A cap only means something if the byte below it
    passes."""
    monkeypatch.setattr(container, "MAX_PART_BYTES", 256 * 1024)
    path = tmp_path / "atcap.aasx"
    at = b"<x/>" + b" " * (container.MAX_PART_BYTES - 4)
    build_aasx(path, payload=at, payload_name="aasx/env.xml")
    with AasxPackage(path) as package:
        assert len(package.read("aasx/env.xml")) == container.MAX_PART_BYTES



def test_parts_summing_exactly_to_the_total_cap_are_all_read(tmp_path, monkeypatch):
    """The total is a cap on *over*, like the part cap: X5's sentence
    says "come to over %d bytes together", so parts summing to exactly
    the cap are all served, and the read that crosses the line is the
    one refused. Both caps had their lower edge pinned and this one did
    not -- the comparison could grow an `=` and no fixture would say so.
    """
    monkeypatch.setattr(container, "MAX_TOTAL_PART_BYTES", 40)
    path = tmp_path / "attotal.aasx"
    build_aasx(path, payload=b"<x/>" + b" " * 16, payload_name="aasx/env.xml",
               files=[("aasx/a.bin", b"y" * 20), ("aasx/b.bin", b"z" * 30)])
    with AasxPackage(path) as package:
        assert len(package.read("aasx/env.xml")) == 20
        assert len(package.read("aasx/a.bin")) == 20   # exactly at the cap
        # Re-reading a counted part does not grow the total (X4 re-walks
        # the chain), so this stays legal too.
        assert len(package.read("aasx/a.bin")) == 20
        with pytest.raises(container.PartTooLarge):
            package.read("aasx/b.bin")                 # the crossing read


def test_a_read_crossing_the_total_by_one_byte_is_refused(tmp_path, monkeypatch):
    """The other edge of the same cap. The read that crosses it above goes
    over by thirty bytes, so a count that started one byte short of zero
    still refused it -- and let a container through at exactly one byte
    over. One byte is the crossing that decides where the count starts."""
    monkeypatch.setattr(container, "MAX_TOTAL_PART_BYTES", 40)
    path = tmp_path / "byone.aasx"
    build_aasx(path, payload=b"<x/>" + b" " * 16, payload_name="aasx/env.xml",
               files=[("aasx/a.bin", b"y" * 20), ("aasx/b.bin", b"z")])
    with AasxPackage(path) as package:
        package.read("aasx/env.xml")
        package.read("aasx/a.bin")                     # exactly at the cap
        with pytest.raises(container.PartTooLarge):
            package.read("aasx/b.bin")                 # one byte over


def test_the_early_total_check_reads_the_total_cap_not_the_part_cap(tmp_path, monkeypatch):
    """The refusal hoisted above the decompressor compares the same
    number the late one does. Comparing it against the *part* cap
    instead refuses a container whose running total merely passed one
    part's worth -- three small parts under a generous total, and the
    third read is the one a wrong constant loses."""
    monkeypatch.setattr(container, "MAX_PART_BYTES", 50)
    monkeypatch.setattr(container, "MAX_TOTAL_PART_BYTES", 200)
    path = tmp_path / "three.aasx"
    build_aasx(path, payload=b"<x/>" + b" " * 46, payload_name="aasx/env.xml",
               files=[("aasx/a.bin", b"a" * 50), ("aasx/b.bin", b"b" * 50)])
    with AasxPackage(path) as package:
        assert len(package.read("aasx/env.xml")) == 50
        assert len(package.read("aasx/a.bin")) == 50
        assert len(package.read("aasx/b.bin")) == 50


def test_a_directory_declaring_exactly_the_cap_still_opens(tmp_path, monkeypatch):
    """Same edge, third cap. The directory bound reads the size the
    archive itself declares, so the fixture asks the file what it
    declares and pins the cap right there."""
    path = tmp_path / "atdir.aasx"
    build_aasx(path, payload=b"{}")
    declared = container._directory_bytes(path)
    assert declared is not None and declared > 0
    monkeypatch.setattr(container, "MAX_DIRECTORY_BYTES", declared)
    with AasxPackage(path) as package:
        assert package.names()
    monkeypatch.setattr(container, "MAX_DIRECTORY_BYTES", declared - 1)
    with pytest.raises(container.DirectoryTooLarge):
        AasxPackage(path)




def test_a_missing_package_rels_is_reported_as_the_package_root(tmp_path):
    """The chain message names its source, and the package's own rels
    has none to name -- `source` is the empty string there, so the
    sentence falls back to "the package root". Losing the fallback ships
    `from ''`, which reads as the tool losing a variable."""
    path = tmp_path / "norels.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("aasx/aasx-origin", b"")
    findings = by_id(runner.run(path))
    assert "X2" in findings
    assert "the package root" in findings["X2"].violation.message


def test_a_suppl_on_the_origin_does_not_become_the_payload(tmp_path):
    """The filter admits exactly the aas-spec type. The thumbnail fixture
    below pins "not everything"; this one pins "not the other type this
    project itself knows" -- an aas-suppl declared on the origin, before
    the payload, which a filter widened to both types would read as an
    environment and fail for being a PDF."""
    suppl = "http://admin-shell.io/aasx/relationships/aas-suppl"
    path = tmp_path / "suppl-origin.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         rels([(suppl, "/aasx/files/manual.pdf"),
                               (SPEC_REL, "/aasx/env.json")]))
        archive.writestr("aasx/env.json", json.dumps(hd_env()).encode("utf-8"))
        archive.writestr("aasx/files/manual.pdf", b"%PDF-1.4")
    report = runner.run(path)
    assert report.ok, [f.id for f in report.findings]


def test_a_thumbnail_relationship_does_not_become_the_payload(tmp_path):
    """The origin's relationships are filtered to the aas-spec type, and
    every fixture's origin declared nothing else -- so the filter could
    admit everything and no verdict would move. A real package also
    declares a thumbnail; listed before the payload, an unfiltered read
    tries to parse PNG bytes as an environment and fails the file for
    carrying a picture."""
    thumb = ("http://schemas.openxmlformats.org/package/2006/"
             "relationships/metadata/thumbnail")
    path = tmp_path / "thumb.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         rels([(thumb, "/aasx/thumb.png"),
                               (SPEC_REL, "/aasx/env.json")]))
        archive.writestr("aasx/thumb.png", b"\x89PNG not an environment")
        archive.writestr("aasx/env.json", json.dumps(hd_env()).encode("utf-8"))
        archive.writestr("aasx/files/manual.pdf", b"%PDF-1.4")
    report = runner.run(path)
    assert report.ok, [f.id for f in report.findings]


def test_bytes_the_declared_encoding_cannot_decode_come_back_untouched():
    """A UTF-16 byte order mark over bytes UTF-16 refuses -- a lone
    surrogate. The promise is the docstring's: refused bytes come back
    untouched, because the parser will refuse them too and refusing here
    would be this reader inventing a verdict."""
    raw = b"\xff\xfe\x00\xd8"
    assert container.xml_as_utf8(raw) == raw


def test_only_a_declaration_at_the_top_is_rewritten():
    """The anchor is the decision, not the count: the pattern is `\\A`-
    anchored, so a document with no prolog whose *content* carries a
    whole `<?xml ... encoding=...?>`-shaped string -- a page about XML --
    keeps it. Unanchored, `count=1` strips "the first match anywhere",
    which is exactly the content. Both fixtures are UTF-16, because only
    a UTF-16 document reaches the rewrite at all.

    A first version of this test hung the mention inside an attribute,
    where the pattern's own `<?xml` prefix can never reach it -- a
    fixture no mutation of anchor or count could touch. Measured, and
    replaced with the input that decides."""
    quoted = '<x>how to write one: <?xml version="1.0" encoding="x"?></x>'
    out = container.xml_as_utf8(b"\xff\xfe" + quoted.encode("utf-16-le"))
    assert b'encoding="x"' in out, "the content's example was edited"

    prolog = '<?xml version="1.0" encoding="UTF-16"?><x/>'
    out = container.xml_as_utf8(b"\xff\xfe" + prolog.encode("utf-16-le"))
    assert b'encoding="UTF-16"' not in out, "the real declaration stayed"


@pytest.mark.parametrize("raw", (
    b"<!--<x--><!DOCTYPE r><r/>",
    b"<?pi <?><!DOCTYPE r><r/>",
))
def test_a_declaration_behind_a_lookalike_is_still_found(raw):
    """The skipped stretch may itself contain `<`. Every fixture that
    walked past a comment or a processing instruction had plain text
    inside it, so a scan that resumed anywhere vaguely after the opener
    still landed on the declaration -- including one that stepped
    *backwards* from the close and found the lookalike tag instead. With
    a `<` inside, resuming anywhere but past the close reads the inside
    as the prolog and calls the document clean.

    Asked in a child process with a time limit, because one way of
    resuming short of the close does not answer wrongly -- it does not
    answer. Two bytes before `?>` instead of two after it lands the
    `<?pi <?>` fixture back on the `<?` it just left, for ever. In
    process that is not a red test but a suite that never finishes; CI
    stops the job after its time limit, but a stopped job does not say
    which test hung, and this does."""
    assert _declares_doctype_within(raw)


def _declares_doctype_within(raw: bytes, seconds: int = 60) -> bool:
    """`container.declares_doctype(raw)`, answered by a child that is
    killed if it has not answered in `seconds`."""
    import subprocess
    import sys

    src = str(pathlib.Path(container.__file__).resolve().parents[1])
    code = ("import sys; sys.path.insert(0, %r); "
            "from aas_submodel_validate.container import declares_doctype; "
            "print(declares_doctype(sys.stdin.buffer.read()))" % src)
    try:
        done = subprocess.run([sys.executable, "-c", code], input=raw,
                              capture_output=True, timeout=seconds)
    except subprocess.TimeoutExpired:
        pytest.fail("declares_doctype gave no answer for %r within %ds" % (raw, seconds))
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    return done.stdout.strip() == b"True"


def test_a_document_quoted_after_the_root_is_not_its_prolog():
    """The root element ends the prolog, and the walk stops there.

    `declares_doctype` promises that a document may *mention* a DTD --
    in CDATA, in the text of a page about XML -- and a page about XML
    quotes whole documents, declaration and DTD included. A walk that
    went on past the root treating markup as a processing instruction
    jumps to the quoted declaration's `?>` and lands on the quoted
    `<!DOCTYPE`, refusing a conformant file for what it talks about.
    Measured before this was written: with the walk treating every
    markup it meets as a processing instruction, the whole suite still
    passed -- no fixture had a `?>` between its root and a mention."""
    raw = (b'<r><![CDATA[<?xml version="1.0"?>'
           b'<!DOCTYPE note SYSTEM "note.dtd"><note/>]]></r>')
    assert not container.declares_doctype(raw)


def test_a_four_byte_utf16_document_is_still_recognised(tmp_path):
    """`_sniff` needs four bytes to tell UTF-16 from UTF-32, and four
    bytes is enough: the guard is `< 4`, not `<= 4`, so a document of
    exactly four bytes is decided rather than passed through opaque."""
    assert container.xml_as_utf8(b"<\x00a\x00") == b"<a"


def test_the_oversized_part_is_a_finding_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(container, "MAX_PART_BYTES", 256 * 1024)
    path = tmp_path / "big.aasx"
    build_aasx(path, payload=b"<x/>" + b" " * (container.MAX_PART_BYTES + 1),
               payload_name="aasx/env.xml")
    report = runner.run(path)
    assert not report.ok
    assert "X5" in {f.id for f in report.findings}
    assert [f for f in report.findings if "could not run" in f.violation.message] == []


#: What the parser reads when nothing tells it the encoding -- measured,
#: not assumed. A byte order mark is honoured; without one it autodetects
#: UTF-16 in both byte orders, and it refuses UTF-32 in both, so nothing
#: can be smuggled in UTF-32. A guard that matches bytes matches the first
#: of these and none of the rest.
XML_ENCODINGS = ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be")

RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _declares(encoding: str) -> str:
    return "utf-16" if encoding.startswith("utf-16") else "utf-8"


def _clean_rels(encoding: str = "utf-8") -> bytes:
    return ('<?xml version="1.0" encoding="%s"?><Relationships xmlns="%s">'
            '<Relationship Type="%s" Target="/aasx/aasx-origin" Id="R0" /></Relationships>'
            % (_declares(encoding), RELS_NS, ORIGIN_REL)).encode(encoding)


#: The outermost entity the declarations below define. Named once: a
#: fixture that declares five and references a sixth is refused for being
#: undefined, which looks exactly like the guard working and is not.
_TOP = 4


def _entities() -> str:
    """Nested enough to be the shape of the attack, small enough that a
    parser which does expand it -- and this one does, measured: ten levels
    of ten reach millions of characters -- finishes instead of taking the
    suite with it."""
    return "".join('<!ENTITY e%d "%s">' % (i, ("&e%d;" % (i - 1)) * 4 if i else "x" * 16)
                   for i in range(_TOP + 1))


def _rels_with_dtd(encoding: str = "utf-8") -> bytes:
    entities = _entities()
    return (('<?xml version="1.0" encoding="%s"?><!DOCTYPE Relationships [%s]>'
             '<Relationships xmlns="%s">'
             '<Relationship Type="%s" '
             'Target="/aasx/aasx-origin" Id="R0">&e%d;</Relationship></Relationships>')
            % (_declares(encoding), entities, RELS_NS, ORIGIN_REL, _TOP)).encode(encoding)


def _archive_carrying(path, raw: bytes) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", raw)
        archive.writestr("aasx/aasx-origin", b"")


@pytest.mark.parametrize("encoding", XML_ENCODINGS)
def test_a_clean_rels_is_read_whatever_encoding_it_arrives_in(tmp_path, encoding):
    """The premise the refusal below rests on. Without it, refusing a bomb
    in an encoding would prove nothing: the parser might simply not read
    that encoding, and the guard would be taking credit for a limit that
    is not its own."""
    path = tmp_path / "clean.aasx"
    _archive_carrying(path, _clean_rels(encoding))
    with AasxPackage(path) as package:
        assert package.origin == "aasx/aasx-origin"


@pytest.mark.parametrize("encoding", XML_ENCODINGS)
def test_a_rels_entity_bomb_is_refused_whatever_encoding_it_arrives_in(tmp_path, encoding):
    """The refusal matched bytes, and a byte pattern finds `<!DOCTYPE` in
    UTF-8 and nowhere else -- so the same declaration, written UTF-16,
    walked past it and the parser expanded the entities. The gate is a
    property, not a list of encodings to keep up to date: wherever a clean
    document is read, one declaring a DOCTYPE is refused *here*, and the
    test above is what makes that sentence mean something."""
    path = tmp_path / "laughs.aasx"
    _archive_carrying(path, _rels_with_dtd(encoding))
    with AasxPackage(path) as package, pytest.raises(ContainerError, match="DOCTYPE|entit"):
        _ = package.origin


#: Encodings the parser refuses. Deciding a document the way the parser
#: decides it cuts both ways: reading one it will not read admits files
#: the rest of the ecosystem rejects, and a validator that calls a file
#: fine when no other reader can open it has done the worst thing it can.
REFUSED_ENCODINGS = ("utf-32", "utf-32-le", "utf-32-be")


@pytest.mark.parametrize("encoding", REFUSED_ENCODINGS)
def test_an_encoding_the_parser_refuses_is_not_read_here_either(tmp_path, encoding):
    """The byte order mark table decoded UTF-32 while the sniff, right
    beside it, refused unmarked UTF-32 and said why. Marked and unmarked
    have to give the same answer, because the parser gives the same
    answer to both."""
    path = tmp_path / "env.xml"
    path.write_bytes(_environment_xml(encoding))
    with pytest.raises(ElementTree.ParseError):     # what every other reader does
        ElementTree.fromstring(path.read_bytes())
    assert [e.message for e in loader.load(path).errors] == [
        "the document could not be read as an AAS environment"]


def test_only_the_declaration_loses_its_encoding(tmp_path):
    """`count=1` takes the first match anywhere in the document, and a
    file with a byte order mark and no declaration -- the shape the
    official 02003 payload has -- offers no prolog for it to land in. It
    was landing in the content instead, and docs/scope.md says this
    project reads what it is given and transforms nothing."""
    raw = ('﻿<environment xmlns="https://admin-shell.io/aas/3/0"><submodels />'
           '<note><![CDATA[<?xml version="1.0" encoding="ISO-8859-1"?>]]></note>'
           '</environment>').encode()
    assert b'encoding="ISO-8859-1"' in container.xml_as_utf8(raw)


def test_a_document_converted_to_exactly_the_bound_is_kept_converted(monkeypatch):
    """Converting UTF-16 to UTF-8 can grow a document past the bound, and
    then it is refused for its size rather than handed on unconverted.
    "Past" means more than, as everywhere this reader states a bound:
    converted to exactly the bound, the document is read converted. No
    fixture sat on that edge, so `>=` passed as well as `>`."""
    raw = '<?xml version="1.0" encoding="UTF-16"?><x>abc</x>'.encode("utf-16")
    converted = container.xml_as_utf8(raw)
    assert converted != raw and converted.startswith(b"<?xml")
    monkeypatch.setattr(container, "MAX_PART_BYTES", len(converted))
    assert container.xml_as_utf8(raw) == converted, "exactly at the bound"
    monkeypatch.setattr(container, "MAX_PART_BYTES", len(converted) - 1)
    with pytest.raises(container.PartTooLarge):
        container.xml_as_utf8(raw)


def test_a_declaration_still_loses_the_encoding_it_no_longer_has(tmp_path):
    """The other half: once the bytes are UTF-8 the declaration would be
    a fatal error if it went on naming UTF-16, so it does have to go --
    and everything else in the declaration has to stay."""
    raw = '<?xml version="1.0" encoding="utf-16" standalone="yes"?><x/>'.encode("utf-16")
    assert container.xml_as_utf8(raw) == b'<?xml version="1.0" standalone="yes"?><x/>'


SUBMODEL_ID = "urn:test:read-me"


def _environment_xml(encoding: str = "utf-8", *, dtd: bool = False, prolog: str = "") -> bytes:
    doctype = "<!DOCTYPE environment [%s]>" % _entities() if dtd else ""
    return ('<?xml version="1.0" encoding="%s"?>%s%s'
            '<environment xmlns="https://admin-shell.io/aas/3/0"><submodels>'
            "<submodel><id>%s</id></submodel>"
            "</submodels></environment>"
            % (_declares(encoding), prolog, doctype, SUBMODEL_ID)).encode(encoding)


@pytest.mark.parametrize("encoding", XML_ENCODINGS)
def test_a_bare_environment_is_read_whatever_encoding_it_arrives_in(tmp_path, encoding):
    """The same premise, one layer up: the payload reader has its own copy
    of the refusal and its own blindness.

    Asserted on what came back, not on the absence of errors. A document
    misread as empty raises nothing either, so "no errors" is also what
    the failure looks like."""
    path = tmp_path / "env.xml"
    path.write_bytes(_environment_xml(encoding))
    loaded = loader.load(path)
    assert [e.message for e in loaded.errors] == []
    assert [s.id for s in loaded.submodels] == [SUBMODEL_ID]


def test_a_document_that_only_mentions_a_doctype_is_read(tmp_path):
    """A conformant document may talk about XML -- this project validates
    technical documentation, where a page about markup is the ordinary
    case rather than the contrived one. Refusing it for carrying the
    token in its content reports a defect that is not there, and the
    repair that made the refusal see UTF-16 made it see this too."""
    path = tmp_path / "env.xml"
    path.write_bytes(_environment_xml("utf-16-le").replace(
        "<submodels>".encode("utf-16-le"),
        "<!--the legacy form used <!DOCTYPE html>--><submodels>".encode("utf-16-le")))
    loaded = loader.load(path)
    assert [e.message for e in loaded.errors] == []
    assert [s.id for s in loaded.submodels] == [SUBMODEL_ID]


def test_a_comment_in_the_prolog_does_not_hide_the_declaration_behind_it(tmp_path):
    """The walk skips comments rather than stopping at the first `<`, and
    this is the direction where stopping early would be expensive: a
    comment may contain anything shaped like a start tag, and a real
    declaration sitting after it would go unread."""
    path = tmp_path / "env.xml"
    path.write_bytes(_environment_xml(prolog="<!--see <environment> below-->", dtd=True))
    assert [e.message for e in loader.load(path).errors] == [
        "the XML declares a DOCTYPE, which is refused"]


@pytest.mark.parametrize("encoding", XML_ENCODINGS)
def test_a_bare_environment_dtd_is_refused_whatever_encoding_it_arrives_in(tmp_path, encoding):
    """Worse here than in the container: two of these encodings did not
    fail, they *passed* -- a document whose entity declarations had been
    expanded came back read, with no finding to say so."""
    path = tmp_path / "env.xml"
    path.write_bytes(_environment_xml(encoding, dtd=True))
    assert [e.message for e in loader.load(path).errors] == [
        "the XML declares a DOCTYPE, which is refused"]


# -- what a reader takes in, whoever packaged it -----------------------------

def _weighing(suffix: str, size: int) -> bytes:
    body = env_json("urn:x") if suffix == ".json" else b"<x/>"
    return body + b" " * (size - len(body))


@pytest.mark.parametrize("suffix", (".json", ".xml"))
def test_a_bare_document_over_the_cap_is_refused(tmp_path, suffix, monkeypatch):
    """The cap belonged to the container alone, so the same bytes were
    refused packaged and read whole bare. What a reader will take in has
    nothing to do with whether somebody zipped it first."""
    monkeypatch.setattr(container, "MAX_PART_BYTES", 4096)
    path = tmp_path / ("env" + suffix)
    path.write_bytes(_weighing(suffix, 4097))
    assert "X5" in {f.id for f in runner.run(path).findings}


@pytest.mark.parametrize("suffix", (".json", ".xml"))
def test_a_bare_document_at_the_cap_is_still_read(tmp_path, suffix, monkeypatch):
    """The other edge, so that the bound is a bound and not a ban."""
    monkeypatch.setattr(container, "MAX_PART_BYTES", 4096)
    path = tmp_path / ("env" + suffix)
    path.write_bytes(_weighing(suffix, 4096))
    assert "X5" not in {f.id for f in runner.run(path).findings}


def test_the_same_bytes_get_the_same_answer_bare_and_packaged(tmp_path, monkeypatch):
    """The defect in one sentence: one document, two envelopes, two
    verdicts. Neither the OPC specification nor the AAS one says anything
    about how much a reader must take in, so this bound is this project's
    -- and a bound that depends on the envelope is not a bound."""
    monkeypatch.setattr(container, "MAX_PART_BYTES", 4096)
    monkeypatch.setattr(container, "MAX_TOTAL_PART_BYTES", 16384)
    payload = _weighing(".json", 4097)
    bare = tmp_path / "env.json"
    bare.write_bytes(payload)
    packaged = build_aasx(tmp_path / "env.aasx", payload=payload)
    # Both refused, not merely agreeing: "the same answer" is also what
    # two silences look like, and that is the state this closes.
    assert "X5" in {f.id for f in runner.run(bare).findings}
    assert "X5" in {f.id for f in runner.run(packaged).findings}


def test_the_refusal_names_what_the_document_weighs(tmp_path, monkeypatch):
    """"Larger than the limit" is true of one byte over and of a hundred
    times over, and the remedy -- split it -- is different work in each
    case. The size comes from the filesystem, not from anything the
    sender declared, which is what asking before reading buys."""
    monkeypatch.setattr(container, "MAX_PART_BYTES", 4096)
    path = tmp_path / "env.json"
    path.write_bytes(_weighing(".json", 9000))
    finding = next(f for f in runner.run(path).findings if f.id == "X5")
    assert "9000" in (finding.violation.message + (finding.violation.detail or ""))


def test_a_stat_that_went_stale_does_not_buy_the_file(tmp_path, monkeypatch):
    """Asking the filesystem how big a file is describes it as it was a
    moment ago, and a supplier may still be writing it.

    The allocation is the assertion, not the verdict. Reading the whole
    file and then refusing it produces exactly the same report as never
    reading it, so a test that only looks at findings cannot tell the
    two apart -- and not reading it was the entire point. Removing the
    bound from the read left every other test in this suite green."""
    cap = 256 * 1024
    monkeypatch.setattr(container, "MAX_PART_BYTES", cap)
    path = tmp_path / "env.json"
    path.write_bytes(_weighing(".json", 8 * 1024 * 1024))

    class _Stale:                       # what stat said before the file grew
        st_size = 100
        st_mode = stat.S_IFREG | 0o644

    real = pathlib.Path.stat
    monkeypatch.setattr(pathlib.Path, "stat",
                        lambda self, *a, **kw: (_Stale() if str(self) == str(path)
                                                else real(self, *a, **kw)))
    tracemalloc.start()
    try:
        report = runner.run(path)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert "X5" in {f.id for f in report.findings}
    assert peak < 4 * cap, "read %d bytes for a %d byte cap" % (peak, cap)



def test_a_file_too_large_to_judge_gets_no_digest(tmp_path, monkeypatch):
    """The report says which bytes it judged. A file this reader refuses
    outright was not judged, so the honest answer is no digest rather
    than a digest of bytes nobody read -- and hashing it anyway would
    mean streaming a file past the very bound that refused it."""
    monkeypatch.setattr(container, "MAX_TOTAL_PART_BYTES", 64 * 1024)
    path = tmp_path / "big.json"
    path.write_bytes(_weighing(".json", 256 * 1024))
    report = runner.run(path)
    assert report.as_dict()["provenance"]["inputSha256"] is None

    # The lower edge, where the bound is written "over" like the reader's
    # other three: a file of exactly the limit is one this reader takes
    # in, so it gets a digest. Without this the comparison can grow an
    # `=` and only a file sitting on the line notices.
    import hashlib
    exact = tmp_path / "exact.json"
    payload = b"x" * container.MAX_TOTAL_PART_BYTES
    exact.write_bytes(payload)
    assert runner.run(exact).as_dict()["provenance"]["inputSha256"] == \
        hashlib.sha256(payload).hexdigest()


def test_a_read_that_runs_out_of_memory_could_not_run(tmp_path):
    """SECURITY.md promises that reading a hostile file fails as a finding
    rather than a crash, and MemoryError walked out of the loader as a
    traceback. It is not a defect in the file either, so it leaves by the
    could-not-run code rather than as a verdict about the document."""
    path = tmp_path / "env.json"
    path.write_bytes(env_json("urn:x"))
    with mock.patch("pathlib.Path.open", side_effect=MemoryError("no memory")):
        assert main([str(path), "-q"]) == EXIT_ERROR


#: Where reading a package can run this reader out of memory, and how to
#: get there without spending the memory: the archive's index, built when
#: the package is opened, and the names it declares; a part's bytes, as
#: they are decompressed; and a relationships part, as it is decoded the way
#: the parser will read it and as it is parsed -- where the parser
#: underneath ElementTree says so in its own way, as a parse error with an
#: out-of-memory code. Each walked out of the loader and the CLI as a
#: traceback, and the process left by 1 -- the code for a verdict with
#: findings, about a package nobody had finished reading -- or, for the
#: parser's own error, was told the part does not parse. The bare file
#: above has left by 2 since that was measured.
#:
#: Each is made to fail one call below the line that guards it, where a
#: test that faked the guarded line itself had left the line after it --
#: the names index, one statement on -- unguarded and unnoticed.
def _a_package(tmp_path):
    return build_aasx(tmp_path / "p.aasx", payload=env_json("urn:x"))


def _a_package_whose_chain_is_utf16(tmp_path):
    """Its relationships part written UTF-16, which is read by converting it
    -- the conversion is where the memory goes."""
    path = tmp_path / "utf16.aasx"
    declared = rels([(ORIGIN_REL, "/aasx/aasx-origin")]).decode("utf-8")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", declared.replace("utf-8", "utf-16").encode("utf-16"))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels", rels([(SPEC_REL, "/aasx/env.json")]))
        archive.writestr("aasx/env.json", env_json("urn:x"))
    return path


def _indexing_runs_out(tmp_path):
    return _a_package(tmp_path), mock.patch.object(
        zipfile.ZipFile, "_RealGetContents", side_effect=MemoryError("simulated"))


def _naming_runs_out(tmp_path):
    return _a_package(tmp_path), mock.patch.object(
        zipfile.ZipFile, "namelist", side_effect=MemoryError("simulated"))


def _a_part_runs_out(tmp_path):
    real = zipfile.ZipExtFile.read

    def read(self, *args, **kwargs):
        if self.name == "aasx/env.json":
            raise MemoryError("simulated")
        return real(self, *args, **kwargs)
    return _a_package(tmp_path), mock.patch.object(zipfile.ZipExtFile, "read", read)


def _decoding_a_relationships_part_runs_out(tmp_path):
    converting = mock.Mock()
    converting.sub.side_effect = MemoryError("simulated")
    return (_a_package_whose_chain_is_utf16(tmp_path),
            mock.patch.object(container, "_DECLARED_ENCODING", converting))


def _parsing_a_relationships_part_runs_out(tmp_path):
    return _a_package(tmp_path), mock.patch.object(
        ElementTree, "fromstring", side_effect=MemoryError("simulated"))


def _the_parser_runs_out(tmp_path):
    ran_out = ElementTree.ParseError("out of memory: line 1, column 0")
    ran_out.code = 1        # expat's XML_ERROR_NO_MEMORY
    return _a_package(tmp_path), mock.patch.object(ElementTree, "fromstring", side_effect=ran_out)


MEMORY_RUNS_OUT = {
    "indexing-the-archive": _indexing_runs_out,
    "listing-its-names": _naming_runs_out,
    "reading-a-part": _a_part_runs_out,
    "decoding-a-relationships-part": _decoding_a_relationships_part_runs_out,
    "parsing-a-relationships-part": _parsing_a_relationships_part_runs_out,
    "the-parser-saying-it-ran-out": _the_parser_runs_out,
}


@pytest.mark.parametrize("where", sorted(MEMORY_RUNS_OUT))
def test_a_package_that_runs_this_reader_out_of_memory_is_refused(tmp_path, where):
    """Refused under X5, whose question this is -- whether the input fits
    in what this reader will take in -- and told what the reader knows:
    that it stopped before the end, and why. Not X1 or X2, whose remedies
    repair an archive or a chain that nobody has seen broken."""
    path, running_out = MEMORY_RUNS_OUT[where](tmp_path)
    assert runner.run(path).judged, "the package does not read without the fault"
    with running_out:
        report = runner.run(path)
    findings = by_id(report)
    assert set(findings) == {"X5"}, sorted(findings)
    assert findings["X5"].fix == loader.limit_remedy("memory", building=False)
    assert "ran out of memory" in findings["X5"].violation.message
    # Filed under what was being read: the package, the part, or -- for the
    # package's own chain -- nothing narrower than the package.
    filed_under = {"indexing-the-archive": str(path), "listing-its-names": str(path),
                   "reading-a-part": "aasx/env.json"}.get(where)
    assert findings["X5"].violation.subject == filed_under
    assert not report.judged


def test_a_payload_whose_relationships_ran_this_reader_out_of_memory_is_still_read(
        tmp_path):
    """The one place in a package where the stop does not end the run: the
    payload's own relationships part, read to see which supplementary
    files it declares. What ran out is refused, and said so; the payload
    beside it was read, and is judged -- a run that is incomplete, not one
    that could not run."""
    path = build_aasx(tmp_path / "p.aasx", payload=env_json("urn:x"),
                      files=[("aasx/files/manual.pdf", b"%PDF-1.4")])
    real = ElementTree.fromstring

    def fromstring(text, *args, **kwargs):
        if b"aas-suppl" in text:
            raise MemoryError("simulated")
        return real(text, *args, **kwargs)

    with mock.patch.object(ElementTree, "fromstring", fromstring):
        report = runner.run(path)
    (stopped,) = [f for f in report.findings if f.id == "X5"]
    assert stopped.fix == loader.limit_remedy("memory", building=False)
    assert stopped.violation.subject == "aasx/_rels/env.json.rels"
    assert report.judged and not report.complete


def test_a_remembered_answer_does_not_keep_what_reading_it_held(tmp_path):
    """Remembering a failure kept the exception, its traceback, and every
    frame the traceback passed through -- the loader's own among them,
    holding the bytes of the part it had just read. A payload with no
    relationships part of its own is the common case, and its bytes stayed
    alive through every rule after it: measured, a 24 MiB payload held 48
    MiB when the metamodel channel started, where the tree before held 24.
    What is remembered is what the failure said."""
    import gc

    payload = env_json()[:-1] + b" " * (8 * 1024 * 1024) + b"}"
    path = build_aasx(tmp_path / "p.aasx", payload=payload)
    tracemalloc.start()
    try:
        loaded = loader.load(path)
        gc.collect()
        held, _ = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert loaded.submodels
    assert held < 4 * 1024 * 1024, "%.1f MiB still held after loading" % (held / 2 ** 20)


def test_an_index_that_ran_out_of_memory_half_built_is_not_answered_from(tmp_path):
    """Resolving a relationship's target builds the archive's lookup
    indexes, in place, and running out of memory halfway left one half
    built -- which the File rule then asked, and was told that a part the
    archive holds is missing. Built whole or not at all, the rule asks
    again and gets the truth. And the stop came after the relationships
    part was parsed to its end, so it is not told the rest was not read."""
    path = build_aasx(tmp_path / "hd.aasx", payload=json.dumps(hd_env()).encode(),
                      files=[("aasx/files/Manual.pdf", b"%PDF-1.4")],
                      suppl_targets=["aasx/files/OTHER.pdf"])
    assert "HD-D7" not in by_id(runner.run(path))
    real = container.ascii_folded
    calls = []

    def folded(value):
        calls.append(value)
        if len(calls) == 6:
            raise MemoryError("simulated")
        return real(value)

    with mock.patch.object(container, "ascii_folded", folded):
        report = runner.run(path)
    findings = by_id(report)
    assert "HD-D7" not in findings, findings["HD-D7"].violation.message
    assert findings["X5"].fix == loader.limit_remedy("memory", building=True)


#: A cap the fixtures below sit a UTF-16 document across: wider than the
#: document is in UTF-16, narrower than it is in UTF-8. CJK is two bytes in
#: UTF-16 and three in UTF-8, so a run of it grows across the line.
_STRADDLE_CAP = 40000


#: Encoding declarations this reader cannot act on: a name with a NUL in
#: it (the codec lookup raises `ValueError`), a codec no reader has and a
#: name that is not a text encoding (`LookupError`). `_as_utf8` caught only
#: the second kind, so the first crashed it; and a relationships part is
#: handed to the parser as bytes, which reads the declaration and raises
#: the same family a step later, where nothing caught it.
_UNHONOURABLE = ["latin\x001", "no-such-codec", "base64"]


@pytest.mark.parametrize("declared", _UNHONOURABLE,
                         ids=["nul-in-the-name", "unknown-codec", "not-a-text-codec"])
def test_a_relationships_part_the_reader_cannot_decode_is_a_finding_not_a_crash(
        tmp_path, declared):
    """The chain's own relationships part, handed to the parser as bytes so
    the declaration is read. Each such name left the process by a traceback
    and exit 1 -- a defect in this reader on a file it never read. It is a
    container defect now, and the run does not crash."""
    rels_part = ('<?xml version="1.0" encoding="%s"?><Relationships xmlns="%s">'
                 '<Relationship Type="%s" Target="/aasx/aasx-origin" Id="R0"/>'
                 '</Relationships>' % (declared, RELS_NS, ORIGIN_REL)).encode("ascii")
    path = tmp_path / "p.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels_part)
        archive.writestr("aasx/aasx-origin", b"")
    code = main([str(path), "-f", "json"])          # must not raise
    report = runner.run(path)
    assert not report.complete and not report.judged
    assert code == 2, code


@pytest.mark.parametrize("declared", _UNHONOURABLE,
                         ids=["nul-in-the-name", "unknown-codec", "not-a-text-codec"])
@pytest.mark.parametrize("where", ["bare", "payload"])
def test_a_document_the_reader_cannot_decode_does_not_crash(tmp_path, declared, where):
    """A bare document and a payload, where a NUL in the name reached the
    same decode and crashed. It does not crash now; whether it then reads
    (the parser, fed a decoded string, ignores a declaration it cannot use)
    or is refused is the parser's to decide -- the point here is the process
    does not leave by a traceback."""
    doc = ('<?xml version="1.0" encoding="%s"?>'
           '<environment xmlns="https://admin-shell.io/aas/3/0"/>' % declared).encode("ascii")
    if where == "bare":
        path = tmp_path / "probe.xml"
        path.write_bytes(doc)
    else:
        path = build_aasx(tmp_path / "p.aasx", payload=doc, payload_name="aasx/env.xml")
    code = main([str(path), "-f", "json"])          # must not raise
    assert code in (0, 1, 2), code


@pytest.mark.filterwarnings("ignore:Duplicate name")
@pytest.mark.parametrize("order", ["defective-first", "defective-last"])
def test_an_archive_naming_one_part_twice_is_refused(tmp_path, order):
    """A ZIP holding two members of the identical name is malformed OPC --
    a part name identifies one part -- and which bytes a reader gets is
    which entry its ZIP library hands back. This reader kept the last and
    said nothing: two `aasx/env.json` entries, the defective one first,
    were read as the clean one and the container passed complete at exit 0,
    while a consumer's tool might extract the other. It is refused."""
    good = json.dumps(hd_env()).encode()
    bad = b'{"broken"'
    first, second = (bad, good) if order == "defective-first" else (good, bad)
    path = tmp_path / "p.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels", rels([(SPEC_REL, "/aasx/env.json")]))
        archive.writestr("aasx/env.json", first)
        archive.writestr("aasx/env.json", second)      # the same name, twice
    report = runner.run(path)
    ids = by_id(report)
    assert not report.complete, "an archive naming one part twice passed as complete"
    assert "X1" in ids, sorted(ids)


def _package_with_rels(tmp_path, rels_name: str, rels_body: bytes,
                       suppl_present=("aasx/files/manual.pdf",)):
    """A conformant Handover package plus a hand-written relationships part
    for the payload, stored under `rels_name`, declaring a missing suppl
    file -- so a reader that reads the part draws X4, and one that passes
    over it draws nothing."""
    path = tmp_path / "p.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels", rels([(SPEC_REL, "/aasx/env.json")]))
        archive.writestr("aasx/env.json", json.dumps(hd_env()).encode())
        for name in suppl_present:
            archive.writestr(name, b"%PDF-1.4")
        archive.writestr(rels_name, rels_body)
    return path


_DECLARES_A_MISSING_SUPPL = (
    '<Relationship Type="%s" Target="/aasx/files/missing.pdf" Id="R1"/>' % SUPPL_REL)


@pytest.mark.parametrize("rels_name", [
    "aasx/_rels/Env.json.rels",
    "aasx/_rels/env.json.rels".replace("_rels", "_rels/./"),
], ids=["case-twin", "dot-segment"])
def test_a_relationships_part_under_an_equivalent_name_is_still_read(tmp_path, rels_name):
    """A payload's relationships part stored under a name equivalent to the
    one OPC computes -- the same folding (ECMA-376 6.2.2.3) and path
    normalisation the File rule and target resolution already apply -- was
    looked for by its exact spelling only, found absent, and passed over as
    "declares none". The suppl file it declared and the archive lacks drew
    no X4, and the container came back complete at exit 0."""
    body = ('<?xml version="1.0"?><Relationships xmlns="%s">%s</Relationships>'
            % (RELS_NS, _DECLARES_A_MISSING_SUPPL)).encode("utf-8")
    path = _package_with_rels(tmp_path, rels_name, body)
    report = runner.run(path)
    ids = by_id(report)
    assert "X4" in ids, "the equivalent-named relationships part was not read: %s" % sorted(ids)
    assert ids["X4"].violation.subject == "aasx/files/missing.pdf"


@pytest.mark.parametrize("body", [
    '<?xml version="1.0"?><NotRelationships xmlns="%s">%s</NotRelationships>',
    '<?xml version="1.0"?><Relationships>%s%s</Relationships>',
    '<?xml version="1.0"?><Relationships xmlns="urn:wrong">%s%s</Relationships>',
], ids=["wrong-root", "no-namespace", "namespace-typo"])
def test_a_relationships_part_that_is_not_one_is_a_container_defect(tmp_path, body):
    """A part in the relationships slot whose root is not OPC's
    `Relationships` -- another element, no namespace, the wrong namespace --
    parsed, and `root.iter` found no relationships in it, so it came back as
    "declares none": a missing suppl file drew no X4 and the run was
    complete at exit 0. It is a defect in the archive, reported, not an
    empty declaration."""
    filled = (body % (RELS_NS, _DECLARES_A_MISSING_SUPPL)) if body.count("%s") == 2 \
        else body % _DECLARES_A_MISSING_SUPPL
    path = _package_with_rels(tmp_path, "aasx/_rels/env.json.rels", filled.encode("utf-8"))
    report = runner.run(path)
    ids = by_id(report)
    assert not report.complete, "a relationships part that is not one passed as complete"
    assert ids, "no finding at all"


def _utf16_across_the_cap(inner: str) -> bytes:
    """A UTF-16 XML document under `_STRADDLE_CAP` bytes as it is stored and
    over it once converted to UTF-8: read, then abandoned by the conversion,
    which is what let the parser see the bytes and their DTD."""
    pad = "中" * 15000        # 30 KB in UTF-16, 45 KB in UTF-8
    body = '<?xml version="1.0" encoding="UTF-16"?>%s<!--%s-->' % (inner, pad)
    return body.encode("utf-16")


@pytest.mark.parametrize("target", ["/aasx/files/from-the-dtd.pdf", "/aasx/files/manual.pdf"],
                         ids=["dtd-target", "real-target"])
def test_a_relationships_part_whose_utf8_form_is_over_the_cap_is_refused(
        tmp_path, monkeypatch, target):
    """A UTF-16 relationships part read as it stood, whose UTF-8 form crosses
    the cap: the conversion was abandoned, `declares_doctype` could not see
    `<!DOCTYPE` in UTF-16, and the parser decoded the UTF-16 and expanded the
    DTD -- so a nested-entity DTD, refused at any smaller size, was not, and
    the size bound it crossed was not applied either. It is refused for its
    size now, whatever it names, and the DTD is never reached."""
    monkeypatch.setattr(container, "MAX_PART_BYTES", _STRADDLE_CAP)
    monkeypatch.setattr(container, "MAX_TOTAL_PART_BYTES", 4 * _STRADDLE_CAP)
    rels_part = _utf16_across_the_cap(
        '<!DOCTYPE Relationships [<!ENTITY t "%s">]>'
        '<Relationships xmlns="%s"><Relationship Type="%s" Target="&t;" Id="R1"/>'
        '</Relationships>' % (target, RELS_NS, SUPPL_REL))
    assert len(rels_part) < _STRADDLE_CAP < len(rels_part.decode("utf-16").encode("utf-8")), (
        "the fixture no longer straddles the cap")
    path = tmp_path / "p.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels", rels([(SPEC_REL, "/aasx/env.json")]))
        archive.writestr("aasx/env.json", env_json("urn:x"))
        archive.writestr("aasx/files/manual.pdf", b"%PDF-1.4")
        archive.writestr("aasx/_rels/env.json.rels", rels_part)
    report = runner.run(path)
    ids = by_id(report)
    assert "X4" not in ids, "the DTD (or an over-cap part) was read: %s" % (
        ids.get("X4") and ids["X4"].violation.subject)
    assert "X5" in ids, sorted(ids)
    assert ids["X5"].violation.subject == "aasx/_rels/env.json.rels"
    assert not report.complete


@pytest.mark.parametrize("zipped", [False, True], ids=["bare", "packaged"])
def test_an_xml_document_whose_utf8_form_is_over_the_cap_is_refused(
        tmp_path, monkeypatch, zipped):
    """The same for a payload, where it was caught only because decoding the
    unconverted UTF-16 as UTF-8 failed and it fell to not-UTF-8 -- an answer
    about encoding, not size, and one that hid that a DTD in it was never
    looked at. It is refused for its size, bare or packaged."""
    monkeypatch.setattr(container, "MAX_PART_BYTES", _STRADDLE_CAP)
    monkeypatch.setattr(container, "MAX_TOTAL_PART_BYTES", 4 * _STRADDLE_CAP)
    body = _utf16_across_the_cap(
        '<!DOCTYPE environment [<!ENTITY t "x">]>'
        '<environment xmlns="https://admin-shell.io/aas/3/0"/>')
    assert len(body) < _STRADDLE_CAP < len(body.decode("utf-16").encode("utf-8"))
    path = tmp_path / ("p.aasx" if zipped else "probe.xml")
    if zipped:
        build_aasx(path, payload=body, payload_name="aasx/env.xml")
    else:
        path.write_bytes(body)
    report = runner.run(path)
    ids = by_id(report)
    assert "X5" in ids, sorted(ids)
    assert not report.complete


def test_a_parts_relationships_are_read_once_whoever_asks(tmp_path):
    """The loader reads a payload's own relationships where a failure can
    be loaded as an error, and X4 reads them again to walk what they
    declare -- skipping a part it cannot read, on the reasoning that the
    loader has reported it. Asked twice, the two answers could differ: a
    second parse that ran out of memory where the first had not was skipped
    as reported, and nothing had reported it. The X4 finding vanished and
    the run left by 0 calling itself complete. Asked once, the second
    answer is the first."""
    path = build_aasx(tmp_path / "p.aasx", payload=env_json("urn:x"),
                      suppl_targets=["aasx/files/missing.pdf"])
    real = ElementTree.fromstring

    def a_second_read_runs_out():
        parses = []

        def fromstring(text, *args, **kwargs):
            if b"aas-suppl" in text:
                parses.append(text)
                if len(parses) > 1:
                    raise MemoryError("simulated")
            return real(text, *args, **kwargs)
        return parses, mock.patch.object(ElementTree, "fromstring", fromstring)

    parses, running_out = a_second_read_runs_out()
    with running_out:
        report = runner.run(path)
    assert len(parses) == 1, "read %d times" % len(parses)
    assert "X4" in by_id(report), sorted(by_id(report))
    assert report.complete
    # The shape the defect had: a warning a build fails on under -W, gone,
    # and the run leaving by 0.
    parses, running_out = a_second_read_runs_out()
    with running_out:
        assert main([str(path), "-W", "-q"]) == 1


_PAYLOAD_RELS = "aasx/_rels/env.json.rels"


def _its_relationships_declare_a_dtd(tmp_path, monkeypatch):
    path = build_aasx(tmp_path / "p.aasx", payload=env_json())
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(_PAYLOAD_RELS, _rels_with_dtd())
    return path, contextlib.nullcontext()


def _its_relationships_are_too_large(tmp_path, monkeypatch):
    monkeypatch.setattr(container, "MAX_PART_BYTES", 4096)
    path = build_aasx(tmp_path / "p.aasx", payload=env_json())
    padded = rels([(SUPPL_REL, "/aasx/files/a.pdf")]).replace(
        b"<Relationships", b"<!--" + b" " * 5000 + b"--><Relationships", 1)
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(_PAYLOAD_RELS, padded)
    return path, contextlib.nullcontext()


def _its_relationships_run_out(tmp_path, monkeypatch):
    path = build_aasx(tmp_path / "p.aasx", payload=env_json(),
                      suppl_targets=["aasx/files/a.pdf"])
    real = ElementTree.fromstring

    def fromstring(text, *args, **kwargs):
        if b"aas-suppl" in text:
            raise MemoryError("simulated")
        return real(text, *args, **kwargs)
    return path, mock.patch.object(ElementTree, "fromstring", fromstring)


def _its_relationships_cannot_be_read(tmp_path, monkeypatch):
    path = build_aasx(tmp_path / "p.aasx", payload=env_json(),
                      suppl_targets=["aasx/files/a.pdf"])
    corrupt_part(path, _PAYLOAD_RELS, "stream")
    return path, contextlib.nullcontext()


@pytest.mark.parametrize("refused", [_its_relationships_declare_a_dtd,
                                     _its_relationships_are_too_large,
                                     _its_relationships_run_out,
                                     _its_relationships_cannot_be_read],
                         ids=["dtd", "too-large", "out-of-memory", "unreadable"])
def test_a_refusal_of_a_payloads_relationships_is_filed_under_that_part(
        tmp_path, monkeypatch, refused):
    """A payload's own relationships part refused -- for a DTD, for its
    size, for memory, for bytes the archive cannot yield -- was filed under
    the payload's name. The payload was read and judged, so one report said
    "judged 1 of 1" and, beside it, that the document was refused and not
    judged, or that the reader stopped before its end. Filed under the part
    that was refused, the two agree."""
    path, fault = refused(tmp_path, monkeypatch)
    with fault:
        report = runner.run(path)
    assert report.submodels_judged == 1, "the payload was not judged"
    refusals = [f for f in report.findings if f.id in {"X1", "X2", "X5"}]
    assert [f.violation.subject for f in refusals] == [_PAYLOAD_RELS], [
        (f.id, f.violation.subject) for f in refusals]
    for finding in report.findings:
        said = finding.fix or ""
        if "not judged" in said or "stopped before the end" in said:
            assert finding.violation.subject != "aasx/env.json", (finding.id, said)


def _security_note() -> str:
    return " ".join((pathlib.Path(__file__).resolve().parents[1]
                     / "SECURITY.md").read_text("utf-8").split())


#: The sentence the tests below hold the code to. It said the run leaves by
#: the could-not-run code, full stop, and that is false wherever something
#: beside the refusal was read and judged: that run has a verdict about what
#: it read, and leaves by it.
_WHERE_NOTHING_COULD_BE_JUDGED = (
    "What it refuses to read, it does not judge, and the report says so; "
    "where nothing could be judged, the run leaves by the could-not-run exit "
    "code rather than reporting a verdict it does not have.")


def test_the_security_note_says_when_the_could_not_run_code_applies(tmp_path, capsys):
    """The other half of that sentence. A package with two payloads, one of
    which runs this reader out of memory: the other is read and judged, so
    the run leaves by the code for its verdict and not by 2 -- and the
    report says the verdict is not a full one."""
    assert _WHERE_NOTHING_COULD_BE_JUDGED in _security_note()
    path = tmp_path / "two.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         rels([(SPEC_REL, "/aasx/a.json"), (SPEC_REL, "/aasx/b.json")]))
        archive.writestr("aasx/a.json", env_json())
        archive.writestr("aasx/b.json", env_json())
    real = zipfile.ZipExtFile.read

    def read(self, *args, **kwargs):
        if self.name == "aasx/b.json":
            raise MemoryError("simulated")
        return real(self, *args, **kwargs)

    with mock.patch.object(zipfile.ZipExtFile, "read", read):
        report = runner.run(path)
        code = main([str(path)])
    assert report.judged and not report.complete
    assert [f.violation.subject for f in report.findings if f.id == "X5"] == ["aasx/b.json"]
    assert code == 1
    assert "not a full verdict" in capsys.readouterr().out


@pytest.mark.parametrize("where", sorted(MEMORY_RUNS_OUT))
def test_the_security_note_holds_where_a_package_runs_this_reader_out_of_memory(
        tmp_path, where, capsys):
    """SECURITY.md says what becomes of hostile input and of what this
    reader refuses to read, and a package that ran it out of memory did
    neither: a traceback, nothing on stdout, exit 1. The sentences are read
    off the page, so the page cannot change without this noticing, and
    neither can what the run does."""
    text = _security_note()
    assert "parsing failures become findings, not crashes" in text
    assert _WHERE_NOTHING_COULD_BE_JUDGED in text
    path, running_out = MEMORY_RUNS_OUT[where](tmp_path)
    with running_out:
        code = main([str(path), "-f", "json"])
    document = json.loads(capsys.readouterr().out)
    assert document["findings"], "the report did not say so"
    assert document["summary"]["judged"] is False
    assert code == EXIT_ERROR


def _archive_declaring_one_part_many_times(path, part_bytes: int, declarations: int):
    body = "".join('<Relationship Type="%s" Target="/aasx/env.json" Id="R%d"/>'
                   % (SPEC_REL, i) for i in range(declarations))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         ('<?xml version="1.0"?><Relationships xmlns="%s">%s</Relationships>'
                          % (RELS_NS, body)).encode("utf-8"))
        archive.writestr("aasx/env.json", b'{"submodels":[]}' + b" " * part_bytes)
    return path


def _bytes_decompressed(work):
    """What the ZIP layer actually handed out, whoever asked for it.

    The cap is a promise about work done, and the only way to see work
    done is to count it where it happens."""
    total = [0]
    real = zipfile.ZipExtFile.read

    def counted(self, *args, **kwargs):
        data = real(self, *args, **kwargs)
        total[0] += len(data)
        return data

    with mock.patch.object(zipfile.ZipExtFile, "read", counted):
        work()
    return total[0]


def test_one_part_declared_many_times_is_still_one_part(tmp_path, monkeypatch):
    """The total is bounded per *part*, and a part is a part however many
    relationships name it. Declaring one twice cost two decompressions
    and counted one, so a few bytes of relationship bought a part's worth
    of work each and the total never arrived: measured, sixty-four
    declarations of a one-megabyte part reached sixteen times the cap
    from an archive of two kilobytes, with no finding and a report
    calling itself complete."""
    cap, together = 64 * 1024, 4 * 64 * 1024
    monkeypatch.setattr(container, "MAX_PART_BYTES", cap)
    monkeypatch.setattr(container, "MAX_TOTAL_PART_BYTES", together)
    path = _archive_declaring_one_part_many_times(tmp_path / "many.aasx", cap - 64, 64)
    read = _bytes_decompressed(lambda: runner.run(path))
    assert read <= together + cap, "decompressed %d bytes for a %d byte cap" % (read, together)


def test_a_container_over_the_total_stops_paying_for_the_rest(tmp_path, monkeypatch):
    """Once the total is past, every remaining part was decompressed in
    full before being refused -- the refusal came after the work it
    exists to avoid. Twenty parts at the cap cost twenty parts."""
    cap, together = 64 * 1024, 2 * 64 * 1024
    monkeypatch.setattr(container, "MAX_PART_BYTES", cap)
    monkeypatch.setattr(container, "MAX_TOTAL_PART_BYTES", together)
    body = "".join('<Relationship Type="%s" Target="/aasx/p%d.json" Id="R%d"/>'
                   % (SPEC_REL, i, i) for i in range(20))
    path = tmp_path / "wide.aasx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         ('<?xml version="1.0"?><Relationships xmlns="%s">%s</Relationships>'
                          % (RELS_NS, body)).encode("utf-8"))
        for i in range(20):
            archive.writestr("aasx/p%d.json" % i, b'{"submodels":[]}' + b" " * (cap - 64))
    read = _bytes_decompressed(lambda: runner.run(path))
    assert read <= together + cap, "decompressed %d bytes for a %d byte cap" % (read, together)


def test_a_refused_dtd_is_not_reported_as_a_syntax_error(tmp_path):
    """X3 relays the payload stage, and that stage holds more than
    documents which would not parse: one whose DTD this reader refuses
    parses perfectly, as the premise below shows. Telling its author to
    fix syntax that is not wrong is the remedy this project promised not
    to write -- refusing to read is this tool's decision, not theirs."""
    path = tmp_path / "env.xml"
    path.write_bytes(_environment_xml(dtd=True))
    ElementTree.fromstring(path.read_bytes())        # the premise: it parses
    finding = next(f for f in runner.run(path).findings if f.id == "X3")
    assert "fix the syntax" not in finding.fix, "told to repair syntax that is not wrong"
    assert "DTD" in finding.fix


def test_a_refused_rels_is_not_reported_as_a_broken_chain(tmp_path):
    """Routing the refusal to the chain stage -- which is what stopped it
    being swallowed -- handed it X2's remedy, and nothing says the chain
    is broken: this reader declined to read one of its parts, so what that
    part names is not known. The same false imperative in a second place,
    made by the repair for the first."""
    path = build_aasx(tmp_path / "refused.aasx", payload=env_json("urn:x"))
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("aasx/_rels/env.json.rels", _rels_with_dtd())
    finding = next(f for f in runner.run(path).findings if f.id == "X2")
    assert "Repair the chain" not in finding.fix
    assert "DTD" in finding.fix


def test_a_rels_this_reader_refused_is_not_a_clean_bill(tmp_path):
    """A spec part whose relationships part declares a DTD is refused --
    by the guard that exists for exactly that -- and the refusal was
    swallowed with the case it shares an exception type with, "this part
    declares no relationships". The container came back `ok`, zero
    findings, exit 0, calling itself complete: a clean bill on something
    this reader would not read."""
    payload = env_json("urn:x")
    path = build_aasx(tmp_path / "refused.aasx", payload=payload)
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("aasx/_rels/env.json.rels", _rels_with_dtd())
    report = runner.run(path)
    assert report.as_dict()["summary"]["complete"] is False


def _wide_archive(path, entries, *, name="%07d", comment=b""):
    """A conformant .aasx with `entries` extra entries beside it.

    Every field is truthful and every part is honest; the only excess is
    how many names the directory declares. This is the shape the caps
    above cannot see: nothing here is decompressed, and the archive is
    small, because the entries hold nothing at all."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         rels([(SPEC_REL, "/aasx/env.json")]))
        archive.writestr("aasx/env.json", env_json())
        for i in range(entries):
            archive.writestr(name % i, b"")
        if comment:
            archive.comment = comment
    return path


def _directory_bytes(path):
    with open(path, "rb") as handle:
        end = zipfile._EndRecData(handle)
    return end[zipfile._ECD_SIZE]


def test_an_archive_that_declares_too_many_names_is_refused(tmp_path, monkeypatch):
    """A ZIP's directory is indexed whole before any cap here applies:
    zipfile builds a record per entry inside `ZipFile()`, and the caps
    above are about decompressing parts, which has not begun.

    Measured, on an archive that is otherwise perfect -- valid chain,
    conformant payload, `complete: true`, only real template findings:
    800,000 empty entries weigh 68.7 MiB on disk and 523 MiB in memory.
    Linear, with no ceiling. The bound is on the directory's own bytes
    because that number is the one zipfile acts on: it reads exactly
    `size_cd` bytes and stops."""
    path = _wide_archive(tmp_path / "wide.aasx", 4000)
    monkeypatch.setattr(container, "MAX_DIRECTORY_BYTES", 8 * 1024)
    with pytest.raises(container.DirectoryTooLarge):
        AasxPackage(path)
    report = runner.run(path)
    assert "X5" in {f.id for f in report.findings}
    assert report.as_dict()["summary"]["judged"] is False


def test_the_refusal_names_the_bound_it_actually_applied(tmp_path, monkeypatch):
    """X5 built its remedy from the *form* of the input and dropped the
    one the loader wrote for this refusal, so an archive turned away for
    its directory was told about document size and part totals -- two
    numbers that had nothing to do with why it was refused, and one
    instruction ("send the part that needs checking on its own") that
    would not have helped, since the directory is indexed whichever part
    you ask for.

    The rule's own docstring already said the remedy is per-input. It was
    per-form."""
    path = _wide_archive(tmp_path / "wide.aasx", 4000)
    monkeypatch.setattr(container, "MAX_DIRECTORY_BYTES", 8 * 1024)
    remedy = next(f.fix for f in runner.run(path).findings if f.id == "X5")
    assert "directory" in remedy
    assert "%d MiB" % (container.MAX_PART_BYTES // 1024 ** 2) not in remedy, \
        "the remedy names a cap this refusal did not apply"


def test_an_archive_under_the_bound_still_opens(tmp_path, monkeypatch):
    """A bound, not a ban. The margin against real packages is what makes
    this safe to ship: the two official example containers declare 13 and
    16 entries, for directories of 1,119 and 1,331 bytes."""
    path = _wide_archive(tmp_path / "narrow.aasx", 40)
    monkeypatch.setattr(container, "MAX_DIRECTORY_BYTES", _directory_bytes(path))
    with AasxPackage(path) as package:
        assert package.names()
    assert runner.run(path).as_dict()["summary"]["judged"] is True


def test_the_refusal_is_cheaper_than_the_indexing_it_prevents(tmp_path, monkeypatch):
    """The point of the bound is where it sits. A check after
    `ZipFile()` returns would be green on every test above and would have
    bought nothing: the memory is spent by the time it could look."""
    path = _wide_archive(tmp_path / "wide.aasx", 4000)

    def peak(cap):
        monkeypatch.setattr(container, "MAX_DIRECTORY_BYTES", cap)
        tracemalloc.start()
        try:
            with contextlib.suppress(container.DirectoryTooLarge):
                AasxPackage(path).close()
            return tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()

    refused = peak(8 * 1024)
    indexed = peak(64 * 1024 * 1024)
    assert refused < indexed / 4, "refusing cost %d against %d to index" % (refused, indexed)


def test_the_bound_agrees_with_the_reader_it_guards(tmp_path, monkeypatch):
    """The refusal is read through `zipfile`'s own account of the archive
    rather than a second reading of it, and that is the whole design.

    A file comment containing the end-of-directory signature sends
    zipfile's `rfind` into the comment: it reports a directory of zero
    bytes and then builds zero entries. A more careful reader would find
    the real record and refuse an archive zipfile opens -- which is the
    over-refusal this project exists not to commit. Asserted as
    agreement, not as a number: whatever the guard reads is what the
    opener will act on."""
    for entries, comment in ((2000, b""), (2000, b"PK\x05\x06" + b"\x00" * 18),
                             (0, b""), (200, b"a" * 60_000)):
        path = _wide_archive(tmp_path / ("agree-%d-%d.aasx" % (entries, len(comment))),
                             entries, comment=comment)
        declared = _directory_bytes(path)
        with zipfile.ZipFile(path) as archive:
            built = len(archive.infolist())
        assert built * 46 <= declared, (
            "%d entries built from a directory declared at %d bytes"
            % (built, declared))


def test_a_directory_too_wide_to_count_in_two_bytes_is_still_measured(tmp_path,
                                                                      monkeypatch):
    """Past 65,535 entries a ZIP moves its real record into a ZIP64 one
    and leaves sentinels behind in the old fields. The count is the field
    that overflows; the size is the field this bound reads, and both go
    through the same reader either way.

    Both directions, because a ZIP64 record does not itself mean large."""
    wide = _wide_archive(tmp_path / "zip64.aasx", 70_000)
    assert _directory_bytes(wide) > 0, "the ZIP64 record was not read"
    monkeypatch.setattr(container, "MAX_DIRECTORY_BYTES", 8 * 1024)
    with pytest.raises(container.DirectoryTooLarge):
        AasxPackage(wide)
    monkeypatch.setattr(container, "MAX_DIRECTORY_BYTES", 64 * 1024 * 1024)
    with AasxPackage(wide) as package:
        assert "aasx/env.json" in package.names()


def test_a_file_that_is_not_a_zip_is_still_not_a_zip(tmp_path, monkeypatch):
    """The guard runs before the archive is opened, so it sees files that
    are not archives. "Cannot find the directory" must not become "the
    directory is too large" -- X1 tells an author to re-create the
    package and X5 tells them it was refused, and only one of those is
    true here."""
    path = tmp_path / "not.aasx"
    path.write_bytes(b"this is not a ZIP file at all")
    monkeypatch.setattr(container, "MAX_DIRECTORY_BYTES", 1)
    ids = {f.id for f in runner.run(path).findings}
    assert "X1" in ids and "X5" not in ids


def test_the_guard_fails_towards_reading_the_file(tmp_path, monkeypatch):
    """It reads the archive's own account of itself through a private
    stdlib entry point, deliberately -- the alternative is a second
    reading that can disagree with the opener. If that entry point ever
    goes away, the bound goes away and the file is still read. A guard
    that took its own blindness for a refusal would refuse files this
    reader has always accepted.

    Modelled as a `zipfile` with its private names removed and its public
    ones intact, which is the shape such a Python would have. Patching
    the real `_EndRecData` instead models nothing: `ZipFile` calls it
    too, so the opener breaks in the same breath and the test proves only
    that a broken stdlib breaks."""
    path = _wide_archive(tmp_path / "fine.aasx", 10)
    public_only = types.SimpleNamespace(
        **{name: getattr(zipfile, name) for name in dir(zipfile)
           if not name.startswith("_")})
    assert not hasattr(public_only, "_EndRecData")
    monkeypatch.setattr(container, "zipfile", public_only)
    assert container._directory_bytes(path) is None, "the guard still measured"
    assert runner.run(path).as_dict()["summary"]["judged"] is True


def test_the_private_names_this_bound_leans_on_are_still_there():
    """The tripwire. The bound is read through `zipfile._EndRecData` and
    its `_ECD_*` offsets, which are private, undocumented and unchanged
    for about twenty-five years. If a future Python moves them the test
    above keeps passing -- the guard fails open, by design -- and this
    one goes red in CI instead of the bound quietly disappearing at a
    user's site."""
    assert callable(getattr(zipfile, "_EndRecData", None))
    assert zipfile._ECD_SIZE == 5


#: The prolog walk decides two ways, and only one of them was asked.
#: Refusing to read a DTD is the cheap direction to be wrong in; saying a
#: document declares one when it does not is the expensive one -- the
#: finding is false, and its remedy ("Remove the DTD") names something
#: that is not there.
@pytest.mark.parametrize("body,why", (
    (b"no angle brackets at all", "nothing that could open a declaration"),
    (b"<!--a comment that never closes <!DOCTYPE x>", "an unclosed comment"),
    (b"<?a processing instruction that never closes <!DOCTYPE x>", "an unclosed PI"),
    (b"", "no bytes at all"),
))
def test_a_document_that_declares_no_doctype_is_not_refused_for_one(body, why):
    """Each of these leaves the walk with no declaration to find, and the
    two ways it can end -- running out of `<`, and running off the end of
    the prolog -- both have to answer no.

    The unclosed comment is the one that decides it: the DOCTYPE inside
    is inside a comment, which is where a parser will never look, so
    reporting it would refuse a file for the text of a remark."""
    assert not container.declares_doctype(body), why


def test_a_declaration_behind_a_comment_is_found_without_a_declaration_in_front(tmp_path):
    """The walk skips comments rather than stopping at the first `<`, and
    the fixtures for that all open with `<?xml ...?>` -- so skipping the
    PI and skipping the comment came to the same thing and the comment
    step was never asked on its own.

    An XML declaration is optional. A document that opens with a comment,
    with something tag-shaped inside it, and carries its DOCTYPE behind
    that, is the shape the walk exists for."""
    path = tmp_path / "env.xml"
    path.write_bytes(b"<!--see <environment> below--><!DOCTYPE environment []>"
                     b'<environment xmlns="https://admin-shell.io/aas/3/0"/>')
    assert [e.message for e in loader.load(path).errors] == [
        "the XML declares a DOCTYPE, which is refused"]


def test_a_container_at_the_total_is_still_read(tmp_path, monkeypatch):
    """The other edge of the total, which the single-part cap has had
    since it was written and this one never did. A container whose parts
    come to exactly the total is inside it; refusing there would turn the
    bound into a bound on one byte less, silently."""
    monkeypatch.setattr(container, "MAX_PART_BYTES", 256 * 1024)
    monkeypatch.setattr(container, "MAX_TOTAL_PART_BYTES", 3 * 64 * 1024)
    path = _spec_parts_archive(tmp_path / "attotal.aasx", count=3, each=64 * 1024)
    with AasxPackage(path) as package:
        read = sum(len(package.read("aasx/env%d.json" % i)) for i in range(3))
    assert read == container.MAX_TOTAL_PART_BYTES


def test_a_part_read_twice_at_the_total_is_not_a_refusal(tmp_path, monkeypatch):
    """A part counts once however many relationships name it -- X4 walks
    the chain again -- and the comment beside the counter says why:
    counting it twice made the refusal depend on which rule happened to
    cross the line.

    The total is asked twice, once before a part is decompressed and once
    after, and only the second edge was pinned. At exactly the total the
    two questions differ: a re-read adds nothing, so it must pass, and a
    pre-check that refuses on equality turns a container this reader has
    already accepted into one it will not finish reading."""
    monkeypatch.setattr(container, "MAX_PART_BYTES", 256 * 1024)
    monkeypatch.setattr(container, "MAX_TOTAL_PART_BYTES", 3 * 64 * 1024)
    path = _spec_parts_archive(tmp_path / "reread.aasx", count=3, each=64 * 1024)
    with AasxPackage(path) as package:
        for index in range(3):
            package.read("aasx/env%d.json" % index)
        assert len(package.read("aasx/env0.json")) == 64 * 1024


def test_the_security_note_names_the_caps_it_promises():
    """SECURITY.md said the bound was the same packaged or bare. It is
    not: a container may deliver four times what a bare document may,
    because its parts are bounded each and again together.

    The whole clause is derived, not each number looked for on its own --
    the page names 64 MiB twice, so "is 64 somewhere in the file" stays
    true while the sentence around it says something else. Measured: it
    did, under the first version of this test."""
    text = " ".join((pathlib.Path(__file__).resolve().parents[1]
                     / "SECURITY.md").read_text("utf-8").split())
    single = container.MAX_PART_BYTES // 1024 ** 2
    together = container.MAX_TOTAL_PART_BYTES // 1024 ** 2
    assert ("one document at %d MiB, and a container's parts at %d MiB each "
            "and %d MiB together" % (single, single, together)) in text
    assert container.MAX_TOTAL_PART_BYTES // container.MAX_PART_BYTES == 4
    assert "four times what a bare document may" in text
    # And the third bound, which is not about bytes read at all. The page
    # used to name it in the list of things it does *not* cover, so the
    # sentence has to move as well as the number.
    assert ("directory of names is bounded too, at %d MiB"
            % (container.MAX_DIRECTORY_BYTES // 1024 ** 2)) in text
    assert "and a ZIP's own directory" not in text


@pytest.mark.parametrize("name,body", (
    ("sm.json", json.dumps({"modelType": "Submodel", "id": "urn:x"}).encode()),
    ("env.json", env_json("urn:x")),
    ("env.xml", b"<environment/>"),
))
def test_the_refusal_tells_a_bare_document_something_it_can_do(tmp_path, monkeypatch,
                                                               name, body):
    """"Send the part", "split the container": two things a bare document
    does not have. Telling an author to do something they cannot is the
    remedy this project promised not to write, and the model already
    carries the per-instance field for saying otherwise.

    The `.json` sentence covers both an environment and a single Submodel
    because the bound is applied before the branch that tells them apart
    -- a reader that has just declined to open a file does not then get
    to say what was inside it."""
    monkeypatch.setattr(container, "MAX_PART_BYTES", 512)
    path = tmp_path / name
    path.write_bytes(body + b" " * 600)
    fix = next(f for f in runner.run(path).findings if f.id == "X5").fix
    assert "container" not in fix, "a bare document was told about a container"
    assert "submodels" in fix
    # Every form, not just the divisible one. An environment holding a
    # single submodel does not divide either, and telling its author to
    # send fewer is the same impossible instruction in a second place.
    assert "cannot be checked here" in fix, "the indivisible case went unsaid"
    # And the remedy has to be a remedy. Both assertions above pass on a
    # one-word string; these are what it has to carry to be worth
    # printing -- the bound the reader hit, and whose decision it was.
    assert "%d MiB" % (container.MAX_PART_BYTES // 1024 ** 2) in fix
    assert "refused, not judged" in fix


def test_the_terminal_summary_says_when_it_is_not_a_full_verdict(tmp_path, monkeypatch):
    """The JSON report grew a field to tell a refusal from a verdict, and
    the person at the terminal reads the same run. One error on a file
    nobody opened looks exactly like one error on a file that was read
    and found wanting -- which is the control below."""
    monkeypatch.setattr(container, "MAX_PART_BYTES", 512)
    refused = tmp_path / "big.json"
    refused.write_bytes(b" " * 600)
    assert "not a full verdict" in render(runner.run(refused))

    judged = tmp_path / "unmatched.json"
    judged.write_bytes(env_json("urn:nobody:recognises:this"))
    rendered = render(runner.run(judged))
    assert rendered.startswith("error"), "the control stopped drawing a finding"
    assert "not a full verdict" not in rendered


#: The four ways content goes unread, named where the loader names them.
#: A pin that used one of them let the other three go on claiming a full
#: verdict: measured, narrowing the field to the bounds stage alone left
#: every test here green.
UNREAD_STAGES = ("zip", "chain", "payload", "bounds")


def _input_unread_at(stage, tmp_path, monkeypatch):
    if stage == "bounds":
        monkeypatch.setattr(container, "MAX_PART_BYTES", 512)
        path = tmp_path / "big.json"
        path.write_bytes(b" " * 600)
        return path
    if stage == "chain":
        return build_aasx(tmp_path / "nochain.aasx", root_rels=False)
    if stage == "payload":
        return build_aasx(tmp_path / "unparsable.aasx", payload=b"{ not json")
    path = build_aasx(tmp_path / "corrupt.aasx")
    corrupt_part(path, "aasx/env.json", "method")
    return path


@pytest.mark.parametrize("stage", UNREAD_STAGES)
def test_an_input_that_went_unread_says_the_verdict_is_incomplete(stage, tmp_path,
                                                                  monkeypatch):
    """A refused file came back `ok: false`, one error, 123 rules checked
    -- which is what a judged file that failed looks like. Nothing was
    read. A consumer had the string "X5" and nothing else to tell the two
    apart, and the same is true of an archive that would not open, a
    chain going nowhere and a part that would not parse."""
    path = _input_unread_at(stage, tmp_path, monkeypatch)
    report = runner.run(path)
    assert [e.stage for e in loader.load(path).errors] != [], "the fixture stopped failing"
    assert report.as_dict()["summary"]["complete"] is False
    assert "not a full verdict" in render(report)


@pytest.mark.parametrize("stage", UNREAD_STAGES)
def test_an_input_nothing_was_learned_about_leaves_by_the_could_not_run_code(
        stage, tmp_path, monkeypatch, capsys):
    """X5's remedy ended "Nothing is wrong with what you sent; it was
    refused, not judged" -- and the run then exited 1, the code for
    judged and found wanting. Two sentences about one run, disagreeing,
    across the seam between a rule's prose and a return value, which is
    why no test held it.

    The report still prints. Exit 2 used to mean stdout was empty, and
    giving that up is the cost: a refusal carries a remedy naming what to
    do about it, and losing that to tidy a contract is the wrong trade."""
    path = _input_unread_at(stage, tmp_path, monkeypatch)
    assert main([str(path)]) == EXIT_ERROR
    printed = capsys.readouterr()
    assert "fix:" in printed.out, "the refusal stopped saying what to do"
    assert str(path) in printed.err, "nothing on stderr, so -q explains nothing"
    assert runner.run(path).as_dict()["summary"]["judged"] is False


def test_an_environment_read_beside_a_broken_part_is_still_a_verdict(tmp_path):
    """Judged is about what reached the rules, and an environment reaches
    them whether or not it holds a submodel this tool has a table for: the
    walk sees it, and the metamodel channel verifies it. An environment
    with a shell and no submodels, beside a relationships part that would
    not parse, was called `nothing judged` and left by 2 -- the code a gate
    is told means "could not run" -- while the metamodel channel had
    verified the shell and found its idShort. Read is what was incomplete;
    judged it was."""
    shell_env = json.dumps({"assetAdministrationShells": [{
        "modelType": "AssetAdministrationShell", "id": "urn:shell",
        "idShort": "bad idShort!",
        "assetInformation": {"assetKind": "Instance", "globalAssetId": "urn:asset"}}]})
    path = tmp_path / "shell.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels", rels([(SPEC_REL, "/aasx/env.json")]))
        archive.writestr("aasx/env.json", shell_env.encode())
        archive.writestr("aasx/_rels/env.json.rels",
                         b'<?xml version="1.0"?><Relationships xmlns="%s"><oops></Relationships>'
                         % RELS_NS.encode())
    report = runner.run(path)
    assert report.judged and not report.complete
    ids = by_id(report)
    assert "SMT-D1" in ids, "the environment that reached the rules drew no verdict"
    assert any(f.id == "META" for f in report.findings), "the metamodel channel did not run"
    assert main([str(path), "-q"]) == 1


def test_a_part_that_went_unread_beside_one_that_did_not_is_still_a_verdict(tmp_path):
    """The other side of the same line, and the reason the rule is about
    what was judged rather than about what was read.

    An archive with one good payload and one that will not parse is
    incomplete, and it is also judged: the submodel that arrived was
    walked and its findings are real. Sending this to exit 2 would put
    genuine errors behind a code a gate is told means "tool problem"."""
    names = ["aasx/good.json", "aasx/bad.json"]
    path = tmp_path / "one-good-one-bad.aasx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         rels([(SPEC_REL, "/" + name) for name in names]))
        archive.writestr(names[0], env_json())
        archive.writestr(names[1], b"{ not json")
    document = runner.run(path).as_dict()
    assert document["summary"] == dict(document["summary"], complete=False, judged=True)
    assert main([str(path), "-q"]) == 1


def test_a_document_that_holds_no_submodel_is_judged_and_found_lacking(tmp_path):
    """The other end of the predicate, and the reason it is two questions
    and not one.

    An environment that parses perfectly and declares no submodels was
    read, and walked, and found to hold nothing this tool knows -- which
    is a verdict, and SMT-D1's. Asking only "did any submodel arrive"
    would send it to exit 2 as if the reader had failed, and would take
    SMT-D1's finding down with it: the file that says nothing at all
    would become the one file this validator has no opinion about."""
    path = tmp_path / "empty.json"
    path.write_bytes(b'{"submodels": []}')
    report = runner.run(path)
    assert report.as_dict()["summary"] == dict(report.as_dict()["summary"],
                                               complete=True, judged=True)
    assert "SMT-D1" in {f.id for f in report.findings}
    assert main([str(path), "-q"]) == 1


def test_a_report_that_read_everything_says_so(tmp_path):
    clean = tmp_path / "clean.json"
    clean.write_bytes(env_json("urn:x"))
    report = runner.run(clean)
    assert report.as_dict()["summary"]["complete"] is True
    assert "not a full verdict" not in render(report)


def test_the_cap_the_remedy_names_is_the_cap(monkeypatch):
    """The remedy spelled the two limits out by hand, so either constant
    could have moved without the sentence that tells the reader about it
    moving too -- and the test above pins the constants, not the prose."""
    fix = next(r for r in all_rules() if r.id == "X5").fix
    assert "%d MiB" % (container.MAX_PART_BYTES // 1024 ** 2) in fix
    assert "%d MiB" % (container.MAX_TOTAL_PART_BYTES // 1024 ** 2) in fix


@pytest.mark.parametrize("suffix", (".xml", ".json", ".aasx"))
def test_a_directory_exits_two_whatever_it_is_named(tmp_path, suffix):
    """Exit 2 means the tool could not run, and a directory is a
    directory whatever it is called. The contract held for one extension
    because that branch guarded its read; the other two reported a defect
    in a file they had not managed to open."""
    target = tmp_path / ("d" + suffix)
    target.mkdir()
    assert main([str(target), "-q"]) == EXIT_ERROR


def test_a_clean_container_still_reads(tmp_path):
    path = build_aasx(tmp_path / "ok.aasx", payload=env_json())
    with AasxPackage(path) as package:
        assert package.spec_parts == ["aasx/env.json"]


def test_control_characters_do_not_reach_the_terminal_raw(tmp_path, capsys):
    """An attacker-chosen idShort with an ESC byte must be escaped in the
    text report, not written raw where it drives the terminal.

    The byte has to reach the report before the escaping can be tested,
    and the first version of this did not get it there: an unrecognised
    submodel draws SMT-D1, whose detail is the semanticId it saw, and the
    idShort appears nowhere. Reverting the escaping left this green. So
    the fixture is a Handover file with a broken row, whose finding names
    the path the attacker chose -- and the escaped spelling is asserted
    too, because "no ESC in the output" is also what an empty report
    looks like.
    """
    import copy
    import json

    from aas_submodel_validate.rules import hd_tables
    from builders import break_row, hd_env

    env = copy.deepcopy(hd_env())
    env["submodels"][0]["submodelElements"][0]["value"][0]["idShort"] = "Doc\x1b[31mHACK"
    env = break_row(env, hd_tables.BY_LABEL["Title"], hd_tables)
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    main([str(path)])
    out = capsys.readouterr().out
    assert "\\x1b" in out, "the attacker's idShort never reached the report"
    assert "\x1b" not in out


@pytest.mark.parametrize("how", ("declared_size", "method", "encrypted", "stream",
                                 "version"))
def test_a_part_that_cannot_be_decompressed_is_a_finding(tmp_path, how):
    """An archive may describe a part wrongly. Reading it then fails
    inside zipfile, with an exception this reader never declared -- and
    the promise is that a container defect is a finding, not a crash.

    Exit 1 alone does not prove it: a crash and a finding leave the same
    code. So the report has to come back.

    "version" is the one that got in. It fails while the directory is
    read, inside `ZipFile()` itself, and the open site carried a shorter
    list of exceptions than the read site did -- so `NotImplementedError`
    walked past every handler in this project and a two-byte edit to any
    .aasx printed a traceback."""
    path = build_aasx(tmp_path / "p.aasx", payload=env_json())
    corrupt_part(path, "aasx/env.json", how)
    report = runner.run(path)
    # X1 specifically, not "one of the container rules": the finding has
    # to be the one whose remedy is true. X2 says repair the chain, and
    # the chain here is perfect.
    assert "X1" in {f.id for f in report.findings}
    assert not report.ok


def _spec_parts_archive(path, count, each):
    """An archive whose origin declares `count` spec payloads, each of
    `each` honest bytes. Every field is truthful; the only excess is how
    many of them there are."""
    payload = b'{"submodels": []}' + b" " * (each - 17)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        names = ["aasx/env%d.json" % i for i in range(count)]
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         rels([(SPEC_REL, "/" + name) for name in names]))
        for name in names:
            archive.writestr(name, payload)
    return path


def test_a_part_that_understates_its_size_buys_no_memory(tmp_path, monkeypatch):
    """The cap was read off the ZIP directory, which is a number the file
    carries rather than one this reader measured. A part that declares a
    hundred bytes and holds eight megabytes passed the cap and was then
    decompressed whole. The refusal that followed came after the memory
    was already spent."""
    monkeypatch.setattr(container, "MAX_PART_BYTES", 256 * 1024)
    path = build_aasx(tmp_path / "p.aasx", payload=b"A" * (8 * 1024 * 1024))
    corrupt_part(path, "aasx/env.json", "declared_size")
    tracemalloc.start()
    try:
        with AasxPackage(path) as package, pytest.raises(ContainerError):
            package.read("aasx/env.json")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 4 * 256 * 1024, "read %d bytes for a 256 KiB cap" % peak


def test_the_parts_of_one_container_are_bounded_in_total(tmp_path, monkeypatch):
    """Every part may sit under the cap while the container as a whole
    does not. Nothing here lies: the archive is small because the parts
    compress, and each one is honest about its size."""
    monkeypatch.setattr(container, "MAX_PART_BYTES", 256 * 1024)
    monkeypatch.setattr(container, "MAX_TOTAL_PART_BYTES", 512 * 1024)
    path = _spec_parts_archive(tmp_path / "many.aasx", count=12, each=200 * 1024)
    report = runner.run(path)
    assert "X5" in {f.id for f in report.findings}


def test_a_container_under_both_caps_still_reads(tmp_path, monkeypatch):
    """The other side of the boundary: caps that refuse everything are
    not caps, they are a broken reader."""
    monkeypatch.setattr(container, "MAX_PART_BYTES", 256 * 1024)
    monkeypatch.setattr(container, "MAX_TOTAL_PART_BYTES", 512 * 1024)
    path = _spec_parts_archive(tmp_path / "few.aasx", count=2, each=100 * 1024)
    report = runner.run(path)
    assert "X5" not in {f.id for f in report.findings}


def test_an_unreadable_relationship_part_is_not_a_clean_bill(tmp_path):
    """The archive names a part, declares supplementary files against it,
    and cannot yield the bytes that say which. Every layer above treated
    that as "declares nothing": X4 catches ContainerError and moves on,
    and the loader never reads a spec part's own relationships, so no
    other voice speaks. A defective container came back with no findings
    and exit 0 -- the one outcome SECURITY.md says cannot happen."""
    path = build_aasx(tmp_path / "p.aasx", payload=env_json(),
                      suppl_targets=["aasx/files/absent.pdf"])
    corrupt_part(path, "aasx/_rels/env.json.rels", "stream")
    report = runner.run(path)
    assert not report.ok, "a container this broken must not pass"
    assert {f.id for f in report.findings} & {"X1", "X5"}


def test_a_name_that_is_not_utf8_is_refused_and_not_judged(tmp_path):
    """A ZIP entry name in a legacy code page, with the header bit that
    claims UTF-8 set anyway. That is what a packager on a Korean or
    Japanese Windows produces, and the AAS payload inside is perfectly
    conformant.

    `UnicodeDecodeError` is a `ValueError`, and `ValueError` was not in
    the tuple of things this reader treats as "could not open". So it
    left by 1 with a traceback -- and 1 is the code for *a verdict with
    findings*, about a file nothing had read. The comment above that
    tuple describes this exact shape of defect from the last time it
    happened, one exception family over.
    """
    import struct

    from aas_submodel_validate.cli import EXIT_ERROR, main

    good = tmp_path / "good.aasx"
    build_aasx(good, payload=json.dumps(hd_env()).encode("utf-8"))
    raw = bytearray(good.read_bytes())
    # The central directory is where the names a reader sees live, so
    # that is where the lie has to be: bit 11 of the flags says "this
    # name is UTF-8" and the bytes under it are cp949.
    entry = raw.find(b"PK\x01\x02")
    assert entry > 0, "fixture shape changed; no central directory"
    flags = struct.unpack_from("<H", raw, entry + 8)[0]
    struct.pack_into("<H", raw, entry + 8, flags | 0x800)
    raw[entry + 46:entry + 50] = b"\xbb\xe7\xc1\xf8"
    broken = tmp_path / "cp949-name.aasx"
    broken.write_bytes(bytes(raw))

    assert main(["-q", str(broken)]) == EXIT_ERROR, (
        "an archive this reader cannot read must leave by the code for "
        "could-not-run; leaving by 1 says a verdict was reached")


@pytest.mark.allow_relay_stop
def test_a_year_too_long_to_convert_is_a_finding_and_not_a_crash(tmp_path):
    """A date whose year runs to 4,301 digits.

    CPython refuses `int()` over 4,300 digits -- a denial-of-service
    guard added in 3.9.14, 3.10.7 and 3.11 -- and aas-core3's own
    `is_xs_date` calls it. That call happens inside the relayed
    metamodel channel, which is the one channel this reader runs
    without isolation, so the exception left through `main` and the
    process died with a traceback and exit 1.

    One is the code for *a verdict with findings*, so a pipeline could
    not tell a crash from a judgement, and `-f json` handed it an empty
    stdout to parse. The first line of this file says what that must
    never be: untrusted input fails as findings or exit 2, never as a
    crash. And the same file, on an interpreter one patch level older,
    came back `ok`.
    """
    import copy

    from aas_submodel_validate.cli import EXIT_FINDINGS, EXIT_OK, main

    env = copy.deepcopy(hd_env())

    def stamp(node):
        if isinstance(node, dict):
            if node.get("idShort") == "StatusSetDate":
                node["value"] = "9" + "0" * 4300 + "-01-01"
            for value in node.values():
                stamp(value)
        elif isinstance(node, list):
            for value in node:
                stamp(value)

    stamp(env)
    path = tmp_path / "long-year.json"
    path.write_text(json.dumps(env), "utf-8")
    assert main(["-q", str(path)]) in (EXIT_OK, EXIT_FINDINGS), (
        "a value this reader cannot convert must come back as a verdict")
    # And a verdict, not a rule falling over. Exit code alone cannot
    # tell those apart -- a crashed rule is reported as a finding and
    # leaves by 1 like any other -- so the report is read: nothing in
    # it may say a rule could not run.
    from aas_submodel_validate.runner import COULD_NOT_RUN, run

    # Of this project's own rules. The relayed channel calls
    # aas-core3's `is_xs_date`, which does convert the year, and there
    # is nothing here that can stop it -- what the isolation guarantees
    # is that it comes back as a finding instead of a traceback, which
    # the exit code above already says. What this asserts is the other
    # half: no rule *here* fell over, which is what stops being true if
    # the conversion comes back into `values.py`.
    crashed = [f for f in run(path).findings
               if f.violation.message == COULD_NOT_RUN and f.id != "META"]
    assert not crashed, (
        "the year was converted after all and something fell over: %s"
        % [f.id for f in crashed])


@pytest.mark.parametrize("encoding", ["iso-8859-1", "iso-8859-15", "cp1252"])
def test_a_legacy_encoding_the_parser_reads_is_read_here_too(tmp_path, encoding):
    """An XML document that declares a legacy code page and carries one
    non-ASCII character in it.

    `xml_as_utf8` says it decides the encoding "the way the parser
    decides it", and the sibling test in this file says the standard is
    "what every other reader does". ElementTree reads these, aas-core3
    reads these, and this reader refused them -- the declaration was
    dropped and the bytes handed to `raw.decode("utf-8-sig")`, which
    raised, and the reader answered `X3 the document could not be read
    as an AAS environment` with a remedy telling the author to fix
    syntax that is not wrong. UTF-32 is refused by the same standard and
    stays refused, which is what makes this a gap rather than a choice:
    it is in neither list.

    German-language industrial documents are the likeliest place for
    one, which is this project's audience."""
    from aas_submodel_validate.cli import EXIT_OK, main
    from aas_submodel_validate.container import xml_as_utf8

    body = ('<?xml version="1.0" encoding="%s"?>'
            '<environment xmlns="https://admin-shell.io/aas/3/0">'
            '<submodels><submodel><id>urn:a:b</id>'
            '<idShort>Größe</idShort>'
            '</submodel></submodels></environment>' % encoding)
    path = tmp_path / ("legacy-%s.xml" % encoding)
    path.write_bytes(body.encode(encoding))

    # What the reader hands downstream has to be the document, decoded.
    handed = xml_as_utf8(path.read_bytes())
    assert b"Gr\xc3\xb6\xc3\x9fe" in handed, (
        "%s: the declaration was dropped and the bytes went on as they "
        "arrived" % encoding)
    assert main(["-q", "--allow-unmatched", str(path)]) == EXIT_OK, (
        "%s: a document every other reader reads was refused" % encoding)


# -- what a report may repeat back ------------------------------------------


def test_a_value_a_file_supplied_cannot_grow_the_report_without_bound():
    """A report interpolates what a file said, and nothing bounded it.

    Measured before the bound: a 200 KB File value produced a
    200,670-character report with a 200,016-character detail. The bound
    on the input is 64 MiB, so the report was bounded by that and
    nothing smaller.
    """
    from aas_submodel_validate.model import MAX_REPORTED_CHARACTERS, Violation

    violation = Violation("m", detail="X" * 200000)
    assert len(violation.detail) == MAX_REPORTED_CHARACTERS
    assert violation.detail.endswith("(199000 more characters, not shown)")


def test_every_field_is_bounded_and_not_only_the_one_that_was_found():
    """Capping the single place a value was found is the mistake this
    project has met before: the class stays and the next rule to
    interpolate a value reopens it. `Violation` is the funnel every
    finding is built through, so the bound is there and applies to all
    of its text."""
    from aas_submodel_validate.model import MAX_REPORTED_CHARACTERS, Violation

    huge = "Y" * (MAX_REPORTED_CHARACTERS * 3)
    violation = Violation(huge, subject=huge, detail=huge, fix=huge, spec=huge)
    for name in ("message", "subject", "detail", "fix", "spec"):
        assert len(getattr(violation, name)) == MAX_REPORTED_CHARACTERS, name


def test_a_value_under_the_bound_is_handed_back_untouched():
    """The direction that costs more. A bound that rewrites short text
    would put an ellipsis in every report."""
    from aas_submodel_validate.model import Violation

    violation = Violation("m", detail="content types present: application/step")
    assert violation.detail == "content types present: application/step"
    assert Violation("m").detail is None


def test_nothing_this_project_writes_comes_near_the_bound():
    """The measurement that chose the number, kept as a test.

    The bound exists to cut what a file supplied. If a sentence this
    project writes ever approaches it, the bound is cutting our own
    words and the number needs raising rather than the sentence
    shortening."""
    from aas_submodel_validate import rules  # noqa: F401 - importing registers
    from aas_submodel_validate.model import MAX_REPORTED_CHARACTERS
    from aas_submodel_validate.registry import all_rules

    authored = []
    for rule in all_rules():
        for name in ("title", "fix", "spec"):
            text = getattr(rule, name, None)
            if text:
                authored.append((len(text), rule.id, name))
    authored.sort(reverse=True)
    longest = authored[0]
    assert longest[0] < MAX_REPORTED_CHARACTERS * 0.6, (
        "%s's %s is %d characters against a bound of %d -- raise the bound"
        % (longest[1], longest[2], longest[0], MAX_REPORTED_CHARACTERS))


def test_the_whole_report_is_bounded_by_the_findings_it_carries(tmp_path):
    """End to end, in both forms a reader gets."""
    import json

    from aas_submodel_validate import runner
    from aas_submodel_validate.report import render
    from builders import build_aasx, hd_env

    payload = json.dumps(hd_env()).replace(
        "/aasx/files/manual.pdf", "/aasx/files/" + "A" * 200000 + ".pdf")
    path = build_aasx(tmp_path / "huge.aasx", payload=payload.encode("utf-8"),
                      files=(("aasx/files/manual.pdf", b"%PDF-1.4"),))
    report = runner.run(str(path))
    assert report.findings, "the fixture stopped producing a finding"
    assert len(render(report)) < 6000, len(render(report))
    assert len(json.dumps(report.as_dict())) < 9000, len(json.dumps(report.as_dict()))


# -- work a refused or unreferenced member may cost --------------------------


def _archive_of(path, members, referenced=False):
    """A conformant package plus `members` compressible entries, either
    referenced by a supplemental relationship or not referenced at all."""
    import zipfile

    from builders import CONTENT_TYPES, ORIGIN_REL, SPEC_REL, hd_env, rels

    suppl = [("http://admin-shell.io/aasx/relationships/aasx-suppl",
              "/aasx/files/big%05d.bin" % index) for index in range(members)]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         rels([(SPEC_REL, "/aasx/env.json")] + (suppl if referenced else [])))
        archive.writestr("aasx/env.json", json.dumps(hd_env()).encode("utf-8"))
        archive.writestr("aasx/files/manual.pdf", b"%PDF-1.4")
        for index in range(members):
            archive.writestr("aasx/files/big%05d.bin" % index, b"\0" * 2_000_000)
    return path


@pytest.mark.parametrize("referenced", [False, True])
def test_members_this_reader_never_opens_cost_it_nothing(tmp_path, referenced):
    """A filter in front of a counter deletes the counter: if an item is
    rejected before its cost is charged, an input where everything is
    rejected does unbounded work. A sibling project measured a small
    upload inflating to 400 MB of member and taking nine seconds, with a
    clean report at the end.

    It does not arise here, and the reason is structural rather than
    lucky. This reader opens only what the relationship chain hands it;
    a supplemental target is asked for by *name*, which takes no bytes
    out of the archive; and `read` compares the member's **declared**
    size against the bound before anything is decompressed. There is no
    point at which a member is inflated and then discarded.

    So this asserts the byte ledger rather than a stopwatch. Two hundred
    members declaring 400 MB -- above the 256 MB total bound -- in an
    archive of a few hundred kilobytes, and the reader charges itself
    for the payload and the one file it was pointed at.
    """
    from aas_submodel_validate import container

    path = _archive_of(tmp_path / "many.aasx", 200, referenced=referenced)
    declared = 200 * 2_000_000
    assert declared > container.MAX_TOTAL_PART_BYTES
    assert path.stat().st_size < 2_000_000, "the fixture stopped being compressible"

    report = runner.run(str(path))
    assert report.complete and report.judged
    assert [f.id for f in report.findings] == [], [f.id for f in report.findings]

    # The ledger the bound is kept on. Everything the reader actually
    # took out of the archive, against everything the archive declares.
    with container.AasxPackage(str(path)) as package:
        # `spec_parts` walks the chain from the origin, so this is the
        # whole of what the reader is handed.
        for part in package.spec_parts:
            package.read(part)
        charged = package._read_total
    assert charged < 100_000, charged
    assert charged * 100 < declared, (charged, declared)


# -- every codec zipfile can open, not the ones somebody remembered ----------

#: The compression methods this Python can both write and read. Derived,
#: because the point of the gate below is that the list of things that
#: can go wrong while opening an archive is not a list anybody keeps
#: correctly by hand -- it had already been extended twice, once for
#: `NotImplementedError` and once for `UnicodeDecodeError`, each time
#: after a real file walked past every handler.
def _writable_methods():
    methods = []
    for name, method in (("stored", zipfile.ZIP_STORED),
                         ("deflate", zipfile.ZIP_DEFLATED),
                         ("bzip2", zipfile.ZIP_BZIP2),
                         ("lzma", zipfile.ZIP_LZMA)):
        try:
            zipfile._get_compressor(method)
        except Exception:      # this build lacks the module
            continue
        methods.append((name, method))
    return methods


def _recompressed(tmp_path, method, name):
    """The same conformant .aasx, written with one compression method."""
    plain = tmp_path / ("plain-%s.aasx" % name)
    build_aasx(plain, payload=json.dumps(hd_env()).encode())
    out = tmp_path / ("%s.aasx" % name)
    with zipfile.ZipFile(plain) as zin, zipfile.ZipFile(out, "w", method) as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info.filename))
    return out


def _payload_stream_bytes(path):
    """Where the biggest member's compressed stream sits in the file."""
    with zipfile.ZipFile(path) as archive:
        entry = max(archive.infolist(), key=lambda info: info.compress_size)
    start = entry.header_offset + 30 + len(entry.filename)
    return start, start + entry.compress_size


@pytest.mark.parametrize("name,method", _writable_methods())
def test_a_corrupt_stream_is_a_verdict_and_never_a_traceback(tmp_path, name, method,
                                                             capsys):
    """One byte of a compressed member, every codec, both ends of the
    stream.

    An LZMA member with a byte flipped in its stream raised
    `_lzma.LZMAError` -- a direct child of `Exception`, so outside
    `container.UNREADABLE` -- through the container, the loader and the
    CLI. The process left by 1 with nothing on stdout, and 1 is the code
    for *a verdict with findings*: a crash in this reader arriving
    dressed as a defect in the supplier's file, which is the one
    confusion this project works hardest to prevent.

    Where in the stream decided which: a byte in the header raised a CRC
    error and came back as `X1` at exit 2, and a byte further in
    crashed. Seventeen of thirty-eight positions tried, on the published
    0.1.2.

    Written for every method this Python can produce rather than for the
    one that was found. Two codecs had already been added to that tuple
    one incident at a time.
    """
    archive = _recompressed(tmp_path, method, name)
    start, end = _payload_stream_bytes(archive)
    raw = bytearray(archive.read_bytes())
    probe = tmp_path / "probe.aasx"
    codes = set()
    for offset in list(range(start, min(start + 12, end))) + \
            list(range(max(start, end - 12), end)):
        broken = bytearray(raw)
        broken[offset] ^= 0xFF
        probe.write_bytes(bytes(broken))
        # No `pytest.raises`: an escaping exception is the defect, so it
        # has to reach the assertion rather than the report.
        code = main([str(probe), "-q"])
        codes.add(code)
        capsys.readouterr()
    assert codes <= {EXIT_ERROR, 0, 1}, (name, codes)
    assert EXIT_ERROR in codes, \
        "%s: no corruption of the payload stream was refused at all" % name


def test_the_reader_names_every_decompressor_error_it_can_meet():
    """`UNREADABLE` is a tuple of exception families and the question it
    answers is "can this reader open the archive". Each codec zipfile
    supports has its own error type, and the tuple carried two of the
    four.

    Named here as well so the tuple cannot quietly shed one: a codec
    dropped from `UNREADABLE` leaves the parametrised test above red on
    one input, and this red on the reason."""
    import lzma
    import zlib as _zlib
    for family in (_zlib.error, lzma.LZMAError, OSError, zipfile.BadZipFile):
        assert issubclass(family, container.UNREADABLE), family


# -- the interpreter's limits are not the document's syntax ------------------

def _limit_finding(tmp_path, payload: str):
    path = tmp_path / "probe.json"
    path.write_text(payload, "utf-8")
    report = runner.run(path)
    return by_id(report), report


def test_a_document_this_interpreter_cannot_build_is_not_bad_syntax(tmp_path):
    """Two hundred thousand open brackets is well-formed JSON.

    `json.loads` raises `RecursionError` on it -- the interpreter running
    out of stack, not the document being wrong -- and every failure in
    that call was reported as "the file is not JSON" with a remedy
    telling the reader to open the document and fix the syntax its parser
    rejects. There is no syntax to fix. The reader is sent to look for a
    defect that is not there, which is the one direction this project
    treats as worse than silence.

    `LoadError.fix` was built for exactly this and its own comment says
    so -- "the payload stage carries both a document that would not parse
    and one this reader refused to read, and 'fix the syntax' is false of
    the second" -- and the JSON path never used it.
    """
    findings, report = _limit_finding(tmp_path, "[" * 200000 + "]" * 200000)
    assert "X3" in findings, sorted(findings)
    said = findings["X3"]
    whole = " ".join(filter(None, (said.violation.message,
                                   said.violation.detail, said.fix)))
    assert "RecursionError" in whole, whole
    assert "is not JSON" not in said.violation.message, said.violation.message
    assert "fix the syntax" not in (said.fix or "").lower(), said.fix
    # Refused rather than judged, the shape X5 uses one layer over -- and
    # nothing more, since nothing more is known about a document this
    # reader did not read to the end.
    assert "not judged" in (said.fix or ""), said.fix
    assert not report.judged


def test_a_genuine_syntax_error_still_says_so(tmp_path):
    """The control. A repair that called every failure a limit would
    tell somebody with a real typo that their file is fine."""
    findings, _ = _limit_finding(tmp_path, "{ not json")
    said = findings["X3"]
    assert "is not JSON" in said.violation.message, said.violation.message
    assert "fix the syntax" in (said.fix or "").lower(), said.fix


def test_bytes_that_do_not_decode_are_the_files_defect_and_not_ours(tmp_path):
    """JSON exchanged between systems is UTF-8 (RFC 8259, 8.1), so bytes
    that do not decode are something wrong with the file. They were
    reported as this interpreter's limit instead -- "Nothing is wrong
    with what you sent" -- because `UnicodeDecodeError` is a
    `ValueError`, and the classifier set aside only the decode error
    `json` raises, not the one raised a step earlier by decoding the
    bytes. Measured on the reader as it was: a `.json` file with one
    0xFF byte in a string printed exactly that."""
    path = tmp_path / "probe.json"
    path.write_bytes(b'{"submodels": [], "note": "\xff"}')
    said = by_id(runner.run(path))["X3"]
    assert "is not JSON" in said.violation.message, said.violation.message
    assert "UnicodeDecodeError" in (said.violation.detail or ""), said.violation.detail
    assert "not judged" not in (said.fix or ""), said.fix
    # And the remedy is the encoding's. The first repair of this left the
    # standing advice in place -- "fix the syntax its parser rejects" --
    # for a file with no syntax to fix; 0.1.0 already recorded that
    # sentence as wrong for an encoding problem, one format over.
    assert said.fix == loader.NOT_UTF8, said.fix


def test_the_limits_are_told_apart_by_type_and_not_by_message():
    """Every way this interpreter refuses a well-formed document,
    including the one that cannot be reached on the Python running this.

    Python 3.11 refuses to build an integer from more than
    `sys.get_int_max_str_digits()` digits and raises a bare `ValueError`;
    3.9 has no such limit, so an end-to-end fixture for it passes here by
    not existing. Asked of the classifier, which has no version in it."""
    from aas_submodel_validate.loader import _is_an_interpreter_limit

    assert _is_an_interpreter_limit(RecursionError("too deep"))
    assert _is_an_interpreter_limit(MemoryError())
    assert _is_an_interpreter_limit(
        ValueError("Exceeds the limit (4300 digits) for integer string conversion"))
    # A decode error is a ValueError and is the one thing here that is
    # about the document. Told apart by type: the message is upstream
    # prose and not ours to pattern-match.
    assert not _is_an_interpreter_limit(
        json.JSONDecodeError("Expecting value", "{ not json", 2))
    # And the other decode error, raised before `json` sees a character:
    # bytes that are not UTF-8 are the file's too.
    assert not _is_an_interpreter_limit(
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"))


@pytest.mark.parametrize("raised, decoding, reason", [
    (RecursionError("too deep"), True, "nesting"),
    (RecursionError("too deep"), False, "nesting"),
    (MemoryError(), True, "memory"),
    (MemoryError(), False, "memory"),
    (ValueError("Exceeds the limit (4300 digits) for integer string conversion"), True, "number"),
], ids=["nesting-decoding", "nesting-building", "memory-decoding", "memory-building",
        "a-number-too-long"])
def test_every_reason_this_reader_stops_is_said_and_nothing_more(raised, decoding, reason):
    """Each reason the reader can stop short gets its own clause, and the
    sentence says only what is known: that it stopped, and why. The digit
    limit exists from CPython 3.11, 3.10.7 and 3.9.14 on, so the one interpreter
    that runs this suite locally cannot produce it end to end -- it is
    asked of the classifier, which has no version in it."""
    message, remedy = loader._failure(raised, decoding=decoding)
    assert message == "this reader could not build the document"
    assert remedy == loader.limit_remedy(reason, building=not decoding)
    # Read to the end only when the stop was in building.
    assert ("stopped building" in remedy) is (not decoding), remedy
    assert "Nothing is wrong" not in remedy and "is JSON" not in remedy
    assert "not judged" in remedy


@pytest.mark.parametrize("raised, decoding", [
    (ValueError("Incorrect padding"), False),
    (UnicodeEncodeError("ascii", "\u00e9", 0, 1, "ordinal not in range(128)"), False),
    (json.JSONDecodeError("Expecting value", "{ not json", 2), True),
], ids=["a-value-error-while-building", "an-encode-error-while-building", "bad-syntax"])
def test_what_is_the_documents_gets_the_standing_advice(raised, decoding):
    """The same types, raised by the document rather than by this
    interpreter, are not the reader's to explain away."""
    assert loader._failure(raised, decoding=decoding) is None


def test_being_cut_short_is_read_from_the_bytes_and_not_from_the_message():
    """Whether the bytes stop halfway through a character is a question
    about the bytes. The first version asked the codec's own prose for it
    ("unexpected end of data"), which this module otherwise refuses to
    pattern-match; worded any other way, the same bytes still end
    halfway."""
    raw = b'{"note": "\xc3'
    exc = UnicodeDecodeError("utf-8", raw, len(raw) - 1, len(raw), "worded some other way")
    assert loader._failure(exc, decoding=True) == ("the file is not JSON", loader.CUT_SHORT)


def test_bytes_that_stop_halfway_through_a_character_are_told_apart_from_the_wrong_encoding():
    cut = b'{"note": "\xc3'
    wrong = b'{"note": "\xff"}'
    for raw, remedy in ((cut, loader.CUT_SHORT), (wrong, loader.NOT_UTF8)):
        try:
            raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            assert loader._failure(exc, decoding=True) == ("the file is not JSON", remedy)


def test_a_path_under_a_directory_we_cannot_enter_is_refused_not_crashed(tmp_path):
    """`Path.exists()` raises when the parent cannot be traversed.

    Neither existence question was guarded, so the process left by 1 with
    nothing on stdout and a raw `PermissionError` traceback on stderr --
    1 being the code for *a verdict with findings*. Nothing was judged.
    The same confusion as an LZMA member two hundred lines up, arriving
    one layer earlier: before this reader has opened anything, while it
    is still asking whether there is a file at all.

    `_read_bounded` has had the answer since it was written -- catch
    `OSError`, raise `UnreadablePath` -- and the two questions above it
    did not.

    An ordinary shape: a delivery dropped into a directory whose mode
    the exporter set, or a mounted share the build user cannot enter.
    """
    locked = tmp_path / "locked"
    locked.mkdir()
    target = locked / "env.json"
    target.write_text(json.dumps(hd_env()), "utf-8")
    os.chmod(locked, 0o000)
    try:
        try:
            target.exists()
        except PermissionError:
            pass
        else:
            # Two ways this happens and the message used to name only
            # one. Running as root is the obvious one; the other is the
            # interpreter, measured here: `Path.exists()` raises on an
            # untraversable parent through 3.13 and returns False on
            # 3.14, so on 3.14 there is nothing to catch and the tool
            # answers "no such file" instead. Still exit 2 either way.
            pytest.skip("`Path.exists()` did not raise on a directory this "
                        "process cannot enter -- either it can (root) or "
                        "this interpreter swallows it (3.14 does). Nothing "
                        "to measure here; the exit code is 2 either way")
        code = main([str(target), "-q"])
    finally:
        os.chmod(locked, 0o755)
    assert code == EXIT_ERROR, (
        "a path this reader cannot reach came back as %d; 1 is the code "
        "for a verdict with findings and nothing was judged" % code)


def test_the_existence_questions_answer_with_a_refusal_not_an_oserror(tmp_path,
                                                                     monkeypatch):
    """Every `OSError` the two questions can raise, not the one that was
    found.

    A locked directory is what a reader meets; a stale NFS handle, a name
    too long for the filesystem and a symlink loop reach the same two
    calls and raise different members of the same family. Injected,
    because a fixture for each is a fixture for the platform that has
    it."""
    from aas_submodel_validate import loader

    target = tmp_path / "env.json"
    target.write_text(json.dumps(hd_env()), "utf-8")
    for error in (PermissionError(13, "Permission denied"),
                  OSError(40, "Too many levels of symbolic links"),
                  OSError(63, "File name too long")):
        def raising(self, _exc=error):
            raise _exc
        monkeypatch.setattr(pathlib.Path, "exists", raising)
        with pytest.raises(loader.UnreadablePath) as caught:
            loader.load(target)
        assert "cannot read" in str(caught.value), str(caught.value)
        assert type(error).__name__ in str(caught.value), str(caught.value)


# -- one contract on exit 2, whatever the extension ---------------------------

def _refused(tmp_path, name: str, how: str):
    """A file this reader cannot read, refused two different ways."""
    path = tmp_path / name
    if how == "permission":
        path.write_bytes(b"PK\x03\x04" if name.endswith(".aasx")
                         else json.dumps(hd_env()).encode())
        os.chmod(path, 0o000)
    else:                                   # a shape this reader cannot open
        path.write_bytes(b"not a container, not a document")
    return path


@pytest.mark.parametrize("name", ["probe.aasx", "probe.json", "probe.xml"])
@pytest.mark.parametrize("how", ["permission", "format"])
def test_a_refusal_prints_a_report_whatever_the_extension(tmp_path, name, how,
                                                          capsys):
    """One contract on exit 2, not one per extension.

    The same permission denial gave `.aasx` an `X1` finding and a JSON
    document a consumer could parse, and gave `.json` and `.xml` an empty
    stdout -- so a pipeline that parses stdout broke on two of three
    extensions for a condition none of them caused. The split was not a
    decision: `runner.run` says an unreadable path propagates as the
    caller's mistake, and the container reader happened to catch the same
    refusal one layer in and make a finding of it.
    """
    path = _refused(tmp_path, name, how)
    if how == "permission":
        try:
            path.read_bytes()
        except PermissionError:
            pass
        else:
            os.chmod(path, 0o644)
            pytest.skip("this process can read a 0o000 file (running as root?)")
    try:
        code = main([str(path), "-f", "json"])
        printed = capsys.readouterr().out
    finally:
        os.chmod(path, 0o644)
    assert code == EXIT_ERROR, code
    assert printed.strip(), "exit 2 with nothing on stdout for %s/%s" % (name, how)
    document = json.loads(printed)
    assert document["findings"], document["summary"]
    assert document["summary"]["judged"] is False


@pytest.mark.parametrize("name", ["probe.aasx", "probe.json", "probe.xml"])
def test_the_remedy_for_a_refusal_names_the_reason_it_was_refused(tmp_path, name,
                                                                  capsys):
    """A remedy built from the error and not from the extension.

    Told to re-create the archive with an AAS packaging tool, an author
    whose file is merely unreadable goes and rebuilds a document that was
    never wrong. That is the fault repaired one layer over for a
    `RecursionError` reported as bad syntax, and it is the same sentence
    here: this reader's difficulty is not the document's defect.
    """
    path = _refused(tmp_path, name, "permission")
    try:
        path.read_bytes()
    except PermissionError:
        pass
    else:
        os.chmod(path, 0o644)
        pytest.skip("this process can read a 0o000 file (running as root?)")
    try:
        main([str(path), "-f", "json"])
        document = json.loads(capsys.readouterr().out)
    finally:
        os.chmod(path, 0o644)
    remedies = " ".join(f.get("fix") or "" for f in document["findings"]).lower()
    assert "permission" in remedies or "readable" in remedies, remedies
    for wrong in ("re-create", "recreate", "packaging tool", "repackage"):
        assert wrong not in remedies, (wrong, remedies)


def test_each_refusal_gets_its_own_remedy_and_not_one_sentence(tmp_path,
                                                               monkeypatch):
    """Derived from the error, which means the errors have to differ.

    A single sentence for every refusal reads as derivation and is not:
    a mutation that gave the permission remedy to every `OSError` passed
    the whole suite, because the only failure any fixture produced was a
    permission denial. A stale handle and a symlink loop are not
    permissions problems and telling their reader to check the mode
    sends them somewhere there is nothing to find -- the same fault as
    telling an unreadable archive to re-create itself.
    """
    from aas_submodel_validate.loader import _access_remedy

    permission = _access_remedy(PermissionError(13, "Permission denied"))
    loop = _access_remedy(OSError(40, "Too many levels of symbolic links"))
    out_of_memory = _access_remedy(MemoryError())

    assert "readable by the account" in permission, permission
    for other in (loop, out_of_memory):
        assert other != permission, other
        assert "readable by the account" not in other, other
    assert "OSError" in loop, loop
    assert "memory" in out_of_memory.lower(), out_of_memory
    # And all three say the thing that makes them remedies rather than
    # accusations: what you sent was not read, so it was not judged.
    for sentence in (permission, loop, out_of_memory):
        assert "not judged" in sentence, sentence
