"""Four ways a submodel arrives, one loaded shape coming out.

.aasx with XML or JSON payload, an environment as bare .json or .xml,
and a single Submodel as .json. Whatever breaks on the way in is
recorded as data (for the container rules to report), never raised —
except a path that cannot be read at all, which is the caller's mistake
rather than the file's.
"""
from __future__ import annotations

import json

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
    one.

    Counted at `open`, which is where the read happens now that it is
    bounded. A counter aimed at the call the loader no longer makes
    would have gone on reporting one read forever."""
    import pathlib as _pathlib
    path = tmp_path / "env.json"
    path.write_bytes(env_json())
    opens = []
    original = _pathlib.Path.open
    monkeypatch.setattr(_pathlib.Path, "open",
                        lambda self, *a, **kw: (opens.append(str(self)),
                                                original(self, *a, **kw))[1])
    load(path)
    assert opens.count(str(path)) == 1


def test_an_environment_json_is_parsed_once(tmp_path, monkeypatch):
    """Read once and parsed twice.

    The JSON branch has to parse the document to learn whether it is an
    environment or a bare submodel, and then handed the *bytes* on -- so
    the environment case built the same tree a second time, and held both
    at once while it did. Measured on a 10.2 MiB environment: 0.22 s and
    58 MiB on top of a reader whose entire bound is 64 MiB of bytes, and
    the tree is several times the bytes it came from. Nothing saw it: the
    read-once test above counts opens, and one open was all there was."""
    path = tmp_path / "env.json"
    path.write_bytes(env_json())
    parsed = []
    original = json.loads
    monkeypatch.setattr(json, "loads",
                        lambda text, *a, **kw: (parsed.append(len(text)),
                                                original(text, *a, **kw))[1])
    loaded = load(path)
    assert not loaded.errors
    assert loaded.environment is not None, "the environment branch was not taken"
    assert len(parsed) == 1, "parsed %d times, on %r characters" % (len(parsed), parsed)
