"""Four ways a submodel arrives, one loaded shape coming out.

.aasx with XML or JSON payload, an environment as bare .json or .xml,
and a single Submodel as .json. Whatever breaks on the way in is
recorded as data (for the container rules to report), never raised —
except a path that cannot be read at all, which is the caller's mistake
rather than the file's.
"""
from __future__ import annotations

import json
import zipfile

import pytest
from aas_core3 import jsonization, xmlization

from aas_submodel_validate import container
from aas_submodel_validate.loader import UnreadablePath, load
from builders import (
    CONTENT_TYPES,
    ORIGIN_REL,
    SPEC_REL,
    build_aasx,
    corrupt_part,
    env_json,
    rels,
)


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


@pytest.mark.parametrize("how", ("zip", "bounds"))
def test_one_unreadable_part_does_not_hide_the_ones_behind_it(tmp_path, monkeypatch, how):
    """The container's version of the rule the runner keeps for rules: one
    broken thing must not silence the rest. A spec part that will not
    decompress is recorded and the loop goes on, because the archive may
    name several payloads and the reader was handed all of them.

    Turning either `continue` in that loop into a `break` leaves the
    submodels behind it unread -- and unread is not the same as absent:
    the report would come back with one container finding, no template
    findings, and `judged: false`, which says this reader learned nothing
    about a file it could have judged."""
    if how == "bounds":
        monkeypatch.setattr(container, "MAX_PART_BYTES", 4096)
    names = ["aasx/bad.json", "aasx/good.json"]
    path = tmp_path / "two.aasx"
    payload = env_json() if how == "zip" else b" " * 8192 + env_json()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         rels([(SPEC_REL, "/" + name) for name in names]))
        archive.writestr(names[0], payload)
        archive.writestr(names[1], env_json())
    if how == "zip":
        corrupt_part(path, names[0], "method")
    loaded = load(path)
    assert [error.stage for error in loaded.errors] == [how]
    assert len(loaded.submodels) == 1, "the part behind the broken one went unread"


def test_a_file_this_reader_cannot_identify_is_the_callers_mistake(tmp_path):
    """Three suffixes are read and everything else is refused before a
    byte is opened. Falling through to the XML branch instead would judge
    a file by a reading nobody chose -- and report a defect in a document
    that was never claimed to be one."""
    path = tmp_path / "notes.txt"
    path.write_bytes(env_json())
    with pytest.raises(UnreadablePath, match="cannot tell what"):
        load(path)


@pytest.mark.parametrize("suffix", (".xml", ".json"))
def test_a_document_over_the_bound_is_not_parsed_anyway(tmp_path, monkeypatch, suffix):
    """`_read_bounded` answers None when it refused, and each caller has
    to stop there. Carrying None into the parser is not a different
    verdict, it is a crash inside a reader whose one promise about hostile
    input is that there is not one.

    Both branches, because each asks the question separately and only one
    of them was being asked."""
    monkeypatch.setattr(container, "MAX_PART_BYTES", 512)
    path = tmp_path / ("big" + suffix)
    path.write_bytes(b" " * 600)
    loaded = load(path)
    assert [error.stage for error in loaded.errors] == ["bounds"]


def test_json_that_is_not_an_object_is_a_finding_not_a_crash(tmp_path):
    """Whether the document is a bare Submodel is asked of a mapping, and
    JSON offers four other things it could be. A list reaching `.get` is
    an AttributeError from inside the loader, which is the shape this
    project reports rather than raises."""
    path = tmp_path / "list.json"
    path.write_bytes(b"[1, 2, 3]")
    loaded = load(path)
    assert [error.stage for error in loaded.errors] == ["payload"]
    assert not loaded.submodels
