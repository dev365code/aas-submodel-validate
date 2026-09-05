"""The OPC chain, verified link by link.

An .aasx is not "a ZIP with files in it": the payload is found by
following relationships, and a container whose chain is broken has no
payload however plausible its entry names look. Every test that breaks a
link expects a refusal that names the missing link.
"""
from __future__ import annotations

import pytest

from aas_submodel_validate.container import AasxPackage, ContainerError, PartTooLarge
from builders import build_aasx, env_json


def test_a_wellformed_container_resolves_its_chain(tmp_path):
    packed = build_aasx(tmp_path / "ok.aasx", payload=b'{"submodels": []}')
    with AasxPackage(packed) as package:
        assert package.origin == "aasx/aasx-origin"
        assert package.spec_parts == ["aasx/env.json"]
        assert package.read("aasx/env.json") == b'{"submodels": []}'


def test_real_world_rels_carry_a_byte_order_mark(tmp_path):
    """The official IDTA example writes its .rels files with a UTF-8 BOM;
    a reader that chokes on it rejects the reference material."""
    packed = build_aasx(tmp_path / "bom.aasx", bom=True)
    with AasxPackage(packed) as package:
        assert package.spec_parts == ["aasx/env.json"]


def test_not_a_zip_is_refused(tmp_path):
    path = tmp_path / "no.aasx"
    path.write_bytes(b"PK is just how it starts, this is not one")
    with pytest.raises(ContainerError, match="ZIP"):
        AasxPackage(path)


def test_a_missing_package_rels_names_the_missing_link(tmp_path):
    packed = build_aasx(tmp_path / "x.aasx", root_rels=False)
    with AasxPackage(packed) as package, pytest.raises(ContainerError, match="_rels/.rels"):
        _ = package.origin


def test_a_missing_origin_relationship_names_the_relationship(tmp_path):
    packed = build_aasx(tmp_path / "x.aasx", origin_rel=False)
    with AasxPackage(packed) as package, pytest.raises(ContainerError, match="aasx-origin"):
        _ = package.origin


def test_a_missing_spec_relationship_names_the_relationship(tmp_path):
    packed = build_aasx(tmp_path / "x.aasx", spec_rel=False)
    with AasxPackage(packed) as package, pytest.raises(ContainerError, match="aas-spec"):
        _ = package.spec_parts


def test_a_spec_target_that_does_not_exist_is_reported(tmp_path):
    packed = build_aasx(tmp_path / "x.aasx", payload_name="aasx/env.json")
    import zipfile

    rewritten = tmp_path / "gone.aasx"
    with zipfile.ZipFile(packed) as src, zipfile.ZipFile(rewritten, "w") as dst:
        for name in src.namelist():
            if name != "aasx/env.json":
                dst.writestr(name, src.read(name))
    with AasxPackage(rewritten) as package, pytest.raises(ContainerError, match="env.json"):
        package.read(package.spec_parts[0])


def test_a_relationship_target_without_a_slash_resolves_against_its_part(tmp_path):
    """OPC resolves a target that begins with "/" against the package
    root and any other target against the directory of the part whose
    relationships it is (docs/divergences.md #13). That reading is why
    this reader accepts conformant packages other tools reject -- and
    until now no test had ever exercised the branch that does it.

    Written before touching that code, not after: a branch nothing
    watches is a branch a refactor may quietly change.
    """
    path = build_aasx(tmp_path / "rel.aasx", payload=env_json(),
                      files=[("aasx/files/manual.pdf", b"%PDF-1.4 ")],
                      relative_targets=True)
    with AasxPackage(path) as package:
        assert package.origin == "aasx/aasx-origin"
        assert package.spec_parts == ["aasx/env.json"]
        suppl = [target for _type, target, _external in package.relationships("aasx/env.json")]
        assert suppl == ["aasx/files/manual.pdf"]


def test_both_spellings_of_a_relationship_reach_the_same_parts(tmp_path):
    """Absolute and relative are two ways of writing one package, so they
    have to produce one answer."""
    payload, parts = env_json(), [("aasx/files/manual.pdf", b"%PDF-1.4 ")]
    absolute = build_aasx(tmp_path / "abs.aasx", payload=payload, files=parts)
    relative = build_aasx(tmp_path / "rel.aasx", payload=payload, files=parts,
                          relative_targets=True)
    with AasxPackage(absolute) as a, AasxPackage(relative) as b:
        assert a.spec_parts == b.spec_parts
        assert a.relationships("aasx/env.json") == b.relationships("aasx/env.json")


def test_a_part_read_twice_counts_once(tmp_path, monkeypatch):
    """The total the container refuses on is distinct bytes handed out,
    not reads. X4 re-walks the chain a second rule already walked, and
    counting those bytes twice made the refusal depend on which rule
    happened to cross the line first -- a container passing or failing by
    rule registration order.

    the changelog records that repair; nothing tested it. Removing the
    `_counted` guard left the whole suite green, so the cap is lowered
    here instead of the archive being made enormous: the same part read
    twice must not refuse, and a *different* part of the same size must.
    """
    from aas_submodel_validate import container as container_module

    blob = b"x" * 40_000
    packed = build_aasx(tmp_path / "p.aasx",
                        files=[("aasx/a.bin", blob), ("aasx/b.bin", blob)])
    monkeypatch.setattr(container_module, "MAX_TOTAL_PART_BYTES", 60_000)
    with AasxPackage(packed) as package:
        assert package.read("aasx/a.bin") == blob
        assert package.read("aasx/a.bin") == blob
        with pytest.raises(PartTooLarge, match="together"):
            package.read("aasx/b.bin")
