"""Untrusted containers must fail as findings or exit-2, never as a crash
and never by exhausting memory. These reproduce the hostile-input
review's confirmed DoS and crash cases.
"""
from __future__ import annotations

import zipfile

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.cli import EXIT_ERROR, main
from aas_submodel_validate.container import AasxPackage, ContainerError
from builders import build_aasx, corrupt_part, env_json


def test_an_oversized_spec_part_is_refused_before_it_is_read(tmp_path):
    """A small archive whose spec part inflates to gigabytes must be
    refused off the ZIP directory, not decompressed into memory."""
    path = tmp_path / "bomb.aasx"
    huge = b"<x/>" + b" " * (200 * 1024 * 1024)
    build_aasx(path, payload=huge, payload_name="aasx/env.xml")
    with AasxPackage(path) as package, pytest.raises(ContainerError, match="bytes"):
        package.read("aasx/env.xml")


def test_the_bomb_is_a_finding_end_to_end(tmp_path):
    path = tmp_path / "bomb.aasx"
    build_aasx(path, payload=b"<x/>" + b" " * (200 * 1024 * 1024),
               payload_name="aasx/env.xml")
    report = runner.run(path)
    assert not report.ok
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


def test_a_directory_named_dot_xml_exits_two_not_crash(tmp_path):
    directory = tmp_path / "package.xml"
    directory.mkdir()
    assert main([str(directory)]) == EXIT_ERROR


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


@pytest.mark.parametrize("how", ("declared_size", "method", "encrypted"))
def test_a_part_that_cannot_be_decompressed_is_a_finding(tmp_path, how):
    """An archive may describe a part wrongly. Reading it then fails
    inside zipfile, with an exception this reader never declared -- and
    the promise is that a container defect is a finding, not a crash.

    Exit 1 alone does not prove it: a crash and a finding leave the same
    code. So the report has to come back."""
    path = build_aasx(tmp_path / "p.aasx", payload=env_json())
    corrupt_part(path, "aasx/env.json", how)
    report = runner.run(path)
    assert {f.id for f in report.findings} & {"X1", "X2", "X3"}
    assert not report.ok
