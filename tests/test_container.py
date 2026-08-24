"""The OPC chain, verified link by link.

An .aasx is not "a ZIP with files in it": the payload is found by
following relationships, and a container whose chain is broken has no
payload however plausible its entry names look. Every test that breaks a
link expects a refusal that names the missing link.
"""
from __future__ import annotations

import pytest

from aas_submodel_validate.container import AasxPackage, ContainerError
from builders import build_aasx


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
