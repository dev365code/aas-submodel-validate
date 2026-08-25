"""Untrusted containers must fail as findings or exit-2, never as a crash
and never by exhausting memory. These reproduce the hostile-input
review's confirmed DoS and crash cases.
"""
from __future__ import annotations

import tracemalloc
import zipfile

import pytest

from aas_submodel_validate import container, runner
from aas_submodel_validate.cli import EXIT_ERROR, main
from aas_submodel_validate.container import AasxPackage, ContainerError
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


def _rels_with_dtd() -> bytes:
    entities = "".join('<!ENTITY e%d "%s">' % (i, ("&e%d;" % (i - 1)) * 10 if i else "x" * 64)
                       for i in range(9))
    return (('<?xml version="1.0"?><!DOCTYPE Relationships [%s]>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Type="http://admin-shell.io/aasx/relationships/aasx-origin" '
             'Target="/aasx/aasx-origin" Id="R0">&e8;</Relationship></Relationships>')
            % entities).encode("utf-8")


def test_a_rels_entity_bomb_is_refused_not_expanded(tmp_path):
    path = tmp_path / "laughs.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("_rels/.rels", _rels_with_dtd())
        archive.writestr("aasx/aasx-origin", b"")
    with AasxPackage(path) as package, pytest.raises(ContainerError, match="DOCTYPE|entit"):
        _ = package.origin


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
    text report, not written raw where it drives the terminal."""
    env = env_json("urn:not:handover")
    path = tmp_path / "env.json"
    path.write_bytes(env)
    # a submodel idShort carrying an escape sequence surfaces in the report
    import json
    doc = json.loads(env)
    doc["submodels"][0]["idShort"] = "root\x1b[31mHACK"
    path.write_bytes(json.dumps(doc).encode("utf-8"))
    main([str(path)])
    out = capsys.readouterr().out
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
