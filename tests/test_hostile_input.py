"""Untrusted containers must fail as findings or exit-2, never as a crash
and never by exhausting memory. These reproduce the hostile-input
review's confirmed DoS and crash cases.
"""
from __future__ import annotations

import contextlib
import json
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
    build_aasx,
    corrupt_part,
    env_json,
    rels,
)


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


def test_a_read_that_runs_out_of_memory_could_not_run(tmp_path):
    """SECURITY.md promises that reading a hostile file fails as a finding
    rather than a crash, and MemoryError walked out of the loader as a
    traceback. It is not a defect in the file either, so it leaves by the
    could-not-run code rather than as a verdict about the document."""
    path = tmp_path / "env.json"
    path.write_bytes(env_json("urn:x"))
    with mock.patch("pathlib.Path.open", side_effect=MemoryError("no memory")):
        assert main([str(path), "-q"]) == EXIT_ERROR


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
    being swallowed -- handed it X2's remedy, and the chain is not broken:
    it names the parts it should, and this reader declined to read one of
    them. The same false imperative in a second place, made by the repair
    for the first."""
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
    """X5's remedy ends "Nothing is wrong with what you sent; it was
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
