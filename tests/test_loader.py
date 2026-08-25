"""Four ways a submodel arrives, one loaded shape coming out.

.aasx with XML or JSON payload, an environment as bare .json or .xml,
and a single Submodel as .json. Whatever breaks on the way in is
recorded as data (for the container rules to report), never raised —
except a path that cannot be read at all, which is the caller's mistake
rather than the file's.
"""
from __future__ import annotations

import pytest
from aas_core3 import jsonization, xmlization

from aas_submodel_validate.loader import UnreadablePath, load
from builders import build_aasx, env_json


def test_an_environment_json_file(tmp_path):
    path = tmp_path / "env.json"
    path.write_bytes(env_json())
    loaded = load(path)
    assert loaded.form == "environment-json"
    assert [s.id for s in loaded.submodels] == ["urn:test:submodel"]
    assert loaded.errors == []


def test_a_bare_submodel_json_file(tmp_path):
    import json
    document = json.loads(env_json())["submodels"][0]
    path = tmp_path / "submodel.json"
    path.write_bytes(json.dumps(document).encode("utf-8"))
    loaded = load(path)
    assert loaded.form == "submodel-json"
    assert len(loaded.submodels) == 1
    assert loaded.environment is None


def test_an_environment_xml_file(tmp_path):
    environment = jsonization.environment_from_jsonable(
        __import__("json").loads(env_json()))
    path = tmp_path / "env.xml"
    path.write_text(xmlization.to_str(environment), "utf-8")
    loaded = load(path)
    assert loaded.form == "environment-xml"
    assert [s.id for s in loaded.submodels] == ["urn:test:submodel"]


def test_an_aasx_with_json_payload(tmp_path):
    packed = build_aasx(tmp_path / "p.aasx", payload=env_json())
    loaded = load(packed)
    assert loaded.form == "aasx"
    assert loaded.container is not None
    assert [s.id for s in loaded.submodels] == ["urn:test:submodel"]


def test_an_aasx_with_xml_payload(tmp_path):
    environment = jsonization.environment_from_jsonable(
        __import__("json").loads(env_json()))
    packed = build_aasx(tmp_path / "p.aasx",
                        payload=xmlization.to_str(environment).encode("utf-8"),
                        payload_name="aasx/env.xml")
    loaded = load(packed)
    assert [s.id for s in loaded.submodels] == ["urn:test:submodel"]


def test_a_byte_order_mark_on_json_is_honoured(tmp_path):
    path = tmp_path / "env.json"
    path.write_bytes(b"\xef\xbb\xbf" + env_json())
    assert load(path).submodels


def test_a_broken_chain_is_data_not_an_exception(tmp_path):
    packed = build_aasx(tmp_path / "p.aasx", origin_rel=False)
    loaded = load(packed)
    assert loaded.submodels == []
    assert [e.stage for e in loaded.errors] == ["chain"]


def test_a_garbage_payload_names_its_part(tmp_path):
    packed = build_aasx(tmp_path / "p.aasx", payload=b"{ not json")
    loaded = load(packed)
    assert [e.stage for e in loaded.errors] == ["payload"]
    assert loaded.errors[0].subject == "aasx/env.json"


def test_not_a_zip_is_data_too(tmp_path):
    path = tmp_path / "p.aasx"
    path.write_bytes(b"not a container")
    assert [e.stage for e in load(path).errors] == ["zip"]


def test_a_missing_path_is_the_callers_problem(tmp_path):
    with pytest.raises(UnreadablePath):
        load(tmp_path / "no-such-file.aasx")


def test_an_environment_json_is_read_from_disk_once(tmp_path, monkeypatch):
    """The JSON branch read the whole file, decided it was an environment
    rather than a bare submodel, and then read it again -- the second
    time outside any guard, where the .xml branch had learned to put
    one."""
    import pathlib as _pathlib
    path = tmp_path / "env.json"
    path.write_bytes(env_json())
    reads = []
    original = _pathlib.Path.read_bytes
    monkeypatch.setattr(_pathlib.Path, "read_bytes",
                        lambda self: (reads.append(str(self)), original(self))[1])
    load(path)
    assert reads.count(str(path)) == 1
