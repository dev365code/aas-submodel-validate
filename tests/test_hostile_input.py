"""Untrusted containers must fail as findings or exit-2, never as a crash
and never by exhausting memory. These reproduce the hostile-input
review's confirmed DoS and crash cases.
"""
from __future__ import annotations

import pathlib
import stat
import tracemalloc
import zipfile
from unittest import mock

import pytest

from aas_submodel_validate import container, loader, runner
from aas_submodel_validate.cli import EXIT_ERROR, main
from aas_submodel_validate.container import AasxPackage, ContainerError
from aas_submodel_validate.registry import all_rules
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


def _environment_xml(encoding: str = "utf-8", *, dtd: bool = False) -> bytes:
    doctype = "<!DOCTYPE environment [%s]>" % _entities() if dtd else ""
    return ('<?xml version="1.0" encoding="%s"?>%s'
            '<environment xmlns="https://admin-shell.io/aas/3/0"><submodels /></environment>'
            % (_declares(encoding), doctype)).encode(encoding)


@pytest.mark.parametrize("encoding", XML_ENCODINGS)
def test_a_bare_environment_is_read_whatever_encoding_it_arrives_in(tmp_path, encoding):
    """The same premise, one layer up: the payload reader has its own copy
    of the refusal and its own blindness."""
    path = tmp_path / "env.xml"
    path.write_bytes(_environment_xml(encoding))
    assert [e.message for e in loader.load(path).errors] == []


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


@pytest.mark.parametrize("how", ("declared_size", "method", "encrypted", "stream"))
def test_a_part_that_cannot_be_decompressed_is_a_finding(tmp_path, how):
    """An archive may describe a part wrongly. Reading it then fails
    inside zipfile, with an exception this reader never declared -- and
    the promise is that a container defect is a finding, not a crash.

    Exit 1 alone does not prove it: a crash and a finding leave the same
    code. So the report has to come back."""
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
