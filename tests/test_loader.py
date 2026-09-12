"""Four ways a submodel arrives, one loaded shape coming out.

.aasx with XML or JSON payload, an environment as bare .json or .xml,
and a single Submodel as .json. Whatever breaks on the way in is
recorded as data (for the container rules to report), never raised —
except a path that cannot be read at all, which is the caller's mistake
rather than the file's.
"""
from __future__ import annotations

import codecs
import json
import zipfile
from unittest import mock
from xml.etree import ElementTree

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
    assert loaded.environments == []


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


def test_a_directory_is_refused_as_not_a_file(tmp_path):
    """Named as what it is, with the remedy for it. Without its own
    branch a directory still fails -- opening it raises -- but under the
    access remedy for an operating system saying no, which sends the
    reader to check permissions on something that was never a file.
    Measured before this was written: with the branch gone, the whole
    suite still passed; no test handed the reader a directory."""
    folder = tmp_path / "looks-like.json"
    folder.mkdir()
    with pytest.raises(UnreadablePath, match="not a file") as refused:
        load(folder)
    # The remedy for this, not the access remedy: that one says "every
    # directory above it", so a fragment like "directory" passed either way.
    assert "Point this at a file rather than at a directory" in refused.value.fix, (
        refused.value.fix)


def test_a_bare_submodel_that_cannot_be_built_says_why(tmp_path):
    """The error branch for a single Submodel -- a document that says it
    is one and is not -- had never run: every bare Submodel in the suite
    was a good one. Measured before this was written: with the line that
    words its reason broken, the whole suite still passed, and a file
    that should have been told it lacks an `id` would have stopped the
    reader instead."""
    path = tmp_path / "submodel.json"
    path.write_text(json.dumps({"modelType": "Submodel"}), "utf-8")
    (error,) = load(path).errors
    assert error.message == "the document could not be read as a Submodel"
    assert error.detail.startswith("DeserializationException: "), error.detail
    assert "'id'" in error.detail, error.detail


def test_a_refused_doctype_points_at_the_part_or_the_file(tmp_path):
    """Where the refusal is said to be. A packaged payload is named by its
    part and a bare file by its path -- what the parse failure beside it
    says, and that one a test pinned. This one nothing read: naming the
    archive for a packaged part, or nothing at all for a bare file, both
    passed the suite."""
    doc = (b'<?xml version="1.0"?><!DOCTYPE environment [<!ENTITY a "b">]>'
           b'<environment xmlns="https://admin-shell.io/aas/3/0"/>')
    packed = build_aasx(tmp_path / "p.aasx", payload=doc, payload_name="aasx/env.xml")
    (refused,) = [e for e in load(packed).errors if "DOCTYPE" in e.message]
    assert refused.subject == "aasx/env.xml"
    bare = tmp_path / "env.xml"
    bare.write_bytes(doc)
    (refused,) = [e for e in load(bare).errors if "DOCTYPE" in e.message]
    assert refused.subject == str(bare)


def test_a_bare_file_that_is_not_an_environment_is_named_by_its_path(tmp_path):
    """The parse failure's `at` for a file with no part to name. The
    packaged case had a test; the bare one fell back on the path and
    nothing checked that it did."""
    bare = tmp_path / "env.xml"
    bare.write_bytes(b"<environment>not the AAS namespace</environment>")
    (error,) = load(bare).errors
    assert error.message == "the document could not be read as an AAS environment"
    assert error.subject == str(bare)


@pytest.mark.parametrize("raw, remedy", [
    (b"[" * 200000 + b"]" * 200000, "nesting"),
    (b'{"submodels": [], "note": "\xff"}', "NOT_UTF8"),
], ids=["this-interpreter's-limit", "not-utf-8"])
def test_a_packaged_json_part_is_answered_the_way_the_same_bare_file_is(tmp_path, raw, remedy):
    """The same bytes, zipped or not. A bare `.json` that nests past this
    interpreter's stack is told it was refused rather than judged, and one
    that is not UTF-8 is told to save it as UTF-8 -- and the same bytes as
    the payload of a package were told, both times, to fix the syntax
    their parser rejects: the part had no classifier at all. There is no
    syntax to fix in either, and a reader who zipped their file should not
    get a different answer about it than one who did not."""
    from aas_submodel_validate import loader

    bare = tmp_path / "bare.json"
    bare.write_bytes(raw)
    (bare_error,) = load(bare).errors
    expected = (getattr(loader, remedy) if remedy.isupper()
                else loader.limit_remedy(remedy, building=False))
    assert bare_error.fix == expected, bare_error.fix

    packed = build_aasx(tmp_path / "packed.aasx", payload=raw)
    (part_error,) = [e for e in load(packed).errors if e.stage == "payload"]
    assert part_error.message == bare_error.message
    # The same answer, except where the remedy is different work: bytes
    # that are not UTF-8 inside a package are fixed by saving the document
    # and rebuilding the package, not by saving "the file".
    packaged = getattr(loader, remedy + "_IN_A_PACKAGE", None) if remedy.isupper() else None
    assert part_error.fix == (packaged or bare_error.fix), part_error.fix
    assert part_error.subject == "aasx/env.json"


def _collection_chain(depth):
    """A Submodel whose one element is a collection `depth` levels deep --
    valid JSON that `json.loads` reads and that building then runs out of
    stack on."""
    element = {"idShort": "leaf", "modelType": "Property", "valueType": "xs:string",
               "value": "x"}
    for level in range(depth):
        element = {"idShort": "c%d" % level, "modelType": "SubmodelElementCollection",
                   "value": [element]}
    return {"id": "urn:test:deep", "modelType": "Submodel", "submodelElements": [element]}


def _stopped(error, reason, *, building):
    from aas_submodel_validate import loader

    assert error.message == "this reader could not build the document", error.message
    assert error.fix == loader.limit_remedy(reason, building=building), error.fix


@pytest.mark.parametrize("zipped", [False, True], ids=["bare", "packaged"])
def test_a_document_that_runs_out_of_stack_is_not_told_it_is_json(tmp_path, zipped):
    """Out of stack before its syntax error: a thousand brackets and then
    text that is not JSON at all. The reader stops at the brackets, and it
    used to say "This document is JSON ... Nothing is wrong with what you
    sent" -- neither of which anyone knows about a document nobody read to
    the end, and here both are false. It is told where the reader stopped
    and why, and nothing it does not know."""
    raw = b"[" * 100000 + b" this is not json"
    path = tmp_path / ("p.aasx" if zipped else "bare.json")
    build_aasx(path, payload=raw) if zipped else path.write_bytes(raw)
    (error,) = [e for e in load(path).errors if e.stage == "payload"]
    _stopped(error, "nesting", building=False)
    assert "Nothing is wrong" not in error.fix and "is JSON" not in error.fix


def test_what_the_reader_did_not_reach_is_not_declared_sound(tmp_path):
    """The same defect, an unknown key, on either side of a collection too
    deep to build. Before it, the defect is reported. After it, the reader
    never gets there -- and the answer used to be that nothing was wrong
    with the file. It is now that the reader stopped, which is true in
    both orders."""
    deep = json.dumps(_collection_chain(350))
    after = '{"submodels": [%s], "bogus": true}' % deep
    before = '{"bogus": true, "submodels": [%s]}' % deep
    json.loads(after)                              # valid JSON: the stop is in building
    for name, text in (("after", after), ("before", before)):
        (tmp_path / (name + ".json")).write_text(text, "utf-8")
    (stopped,) = load(tmp_path / "after.json").errors
    # Read to the end -- `json.loads` took the whole text -- and stopped
    # while building: saying "what comes after was not read" would be
    # false here, where saying the document is JSON is true.
    _stopped(stopped, "nesting", building=True)
    (reported,) = load(tmp_path / "before.json").errors
    assert reported.message == "the document could not be read as an AAS environment"
    assert "bogus" in reported.detail and reported.fix is None


def test_a_bare_submodel_too_deep_to_build_is_told_the_reader_stopped(tmp_path):
    """The one form that still told a document this reader could not
    build to fix the syntax its parser rejects: a bare Submodel, which is
    read by its own branch and was never asked why building failed."""
    path = tmp_path / "submodel.json"
    path.write_text(json.dumps(_collection_chain(350)), "utf-8")
    (error,) = load(path).errors
    _stopped(error, "nesting", building=True)


def _collection_chain_xml(depth, tail=""):
    """The same chain written as AAS XML, with `tail` after the root.

    aas-core3.0 builds XML as the parser streams it -- each element as it
    is reached -- so a document it runs out of stack on was stopped before
    its end, and whatever comes after, a syntax error included, was never
    looked at."""
    opened = "".join("<submodelElementCollection><idShort>c%d</idShort><value>" % level
                     for level in range(depth))
    closed = "</value></submodelElementCollection>" * depth
    leaf = "<property><idShort>leaf</idShort><valueType>xs:string</valueType></property>"
    return ('<environment xmlns="https://admin-shell.io/aas/3/0"><submodels><submodel>'
            "<id>urn:test:deep</id><submodelElements>%s%s%s</submodelElements>"
            "</submodel></submodels></environment>%s" % (opened, leaf, closed, tail))


def _xml_at(tmp_path, name, text, zipped):
    path = tmp_path / (name + (".aasx" if zipped else ".xml"))
    if zipped:
        build_aasx(path, payload=text.encode("utf-8"), payload_name="aasx/env.xml")
    else:
        path.write_text(text, "utf-8")
    return path


@pytest.mark.parametrize("zipped", [False, True], ids=["bare", "packaged"])
def test_xml_too_deep_to_follow_is_told_the_reader_stopped(tmp_path, zipped):
    """Three hundred and fifty collections, one inside the next, is AAS XML
    this interpreter runs out of stack on -- and the classifier was asked
    of JSON only, so it was told to open the document and fix the syntax
    its parser rejects. There is no syntax to fix, and here there is a
    syntax error, after the point the reader stopped: it is told that the
    reader stopped and why, and nothing about the rest. The same answer
    zipped or not."""
    text = _collection_chain_xml(350, tail="<<< this is not XML")
    bare = [e for e in load(_xml_at(tmp_path, "bare", text, False)).errors
            if e.stage == "payload"]
    (error,) = [e for e in load(_xml_at(tmp_path, "probe", text, zipped)).errors
                if e.stage == "payload"]
    _stopped(error, "nesting", building=False)
    assert "RecursionError" in error.detail, error.detail
    assert (error.message, error.fix) == (bare[0].message, bare[0].fix)
    assert error.subject == ("aasx/env.xml" if zipped else str(tmp_path / "probe.xml"))


def test_the_deepest_xml_this_reader_builds_is_read_and_one_more_level_is_not(tmp_path):
    """Near the edge, found rather than assumed: how deep a document may
    nest before the stack runs out depends on the interpreter and on how
    deep the caller already is, so the edge is searched for here by the
    call the reader makes. One level short of it the document is read
    whole and nothing is refused; at it the refusal is the stack's, and
    not a syntax error."""
    def loaded_at(depth):
        return load(_xml_at(tmp_path, "d%d" % depth, _collection_chain_xml(depth), False))

    shallow, deep = 1, 350
    assert loaded_at(deep).errors, "the top of the search does not stop"
    while shallow < deep:
        middle = (shallow + deep) // 2
        if loaded_at(middle).errors:
            deep = middle
        else:
            shallow = middle + 1
    edge = shallow
    # A reader that stops a hundred levels in is broken, not bounded.
    assert edge > 100, edge
    below = loaded_at(edge - 1)
    assert not below.errors and [s.id for s in below.submodels] == ["urn:test:deep"]
    (stopped,) = loaded_at(edge).errors
    _stopped(stopped, "nesting", building=False)


def _parse_runs_out(monkeypatch):
    def out_of_memory(text):
        raise MemoryError()
    monkeypatch.setattr(xmlization, "environment_from_str", out_of_memory)


def _the_parser_says_it_ran_out(monkeypatch):
    """How the parser underneath says it: a parse error with expat's
    out-of-memory code, which aas-core3.0 passes through untouched (its
    reader catches no parse error)."""
    def out_of_memory(text):
        error = ElementTree.ParseError("out of memory: line 1, column 0")
        error.code = 1
        raise error
    monkeypatch.setattr(xmlization, "environment_from_str", out_of_memory)


def _decoding_runs_out(monkeypatch):
    """Before the parser: the document converted to UTF-8 the way the
    parser will read it, which for UTF-16 is a copy of the whole of it."""
    converting = mock.Mock()
    converting.sub.side_effect = MemoryError()
    monkeypatch.setattr(container, "_DECLARED_ENCODING", converting)


@pytest.mark.parametrize("running_out", [_parse_runs_out, _the_parser_says_it_ran_out,
                                         _decoding_runs_out],
                         ids=["parsing", "the-parser-saying-so", "decoding"])
@pytest.mark.parametrize("zipped", [False, True], ids=["bare", "packaged"])
def test_xml_that_runs_this_reader_out_of_memory_is_told_the_reader_stopped(
        tmp_path, monkeypatch, zipped, running_out):
    """The interpreter's other limit, reached the same way: XML is built as
    the parser streams it, so running out of memory is a stop before the
    end, and what the document holds past that point is not known. Three
    places it can happen, and the decoding one sat before the guard: a
    UTF-16 document that ran out there left by a traceback."""
    text = _collection_chain_xml(3).replace(
        "<environment", '<?xml version="1.0" encoding="UTF-16"?><environment', 1)
    path = tmp_path / ("probe.aasx" if zipped else "probe.xml")
    if zipped:
        build_aasx(path, payload=text.encode("utf-16"), payload_name="aasx/env.xml")
    else:
        path.write_bytes(text.encode("utf-16"))
    assert not load(path).errors, "the document does not read without the fault"
    running_out(monkeypatch)
    (error,) = [e for e in load(path).errors if e.stage == "payload"]
    _stopped(error, "memory", building=False)


@pytest.mark.parametrize("zipped", [False, True], ids=["bare", "packaged"])
def test_a_file_cut_short_in_a_character_is_told_it_looks_cut_short(tmp_path, zipped):
    """Bytes that end halfway through a character are a copy or download
    that stopped early, not a file saved in the wrong encoding -- telling
    its author to save it as UTF-8 sends them to change a setting that was
    never wrong.

    Inside a package the remedy is not to send it again: an archive cut
    short fails as an archive before any part is read, and a part that is
    read has matched the archive's own checksum -- these are the bytes the
    packaging tool wrote, and resending brings the same ones."""
    from aas_submodel_validate import loader

    raw = '{"submodels": [], "note": "\u00e4"}'.encode("utf-8")[:-3]
    path = tmp_path / ("p.aasx" if zipped else "bare.json")
    build_aasx(path, payload=raw) if zipped else path.write_bytes(raw)
    (error,) = [e for e in load(path).errors if e.stage == "payload"]
    assert error.fix == (loader.CUT_SHORT_IN_A_PACKAGE if zipped else loader.CUT_SHORT), error.fix


def test_a_byte_order_mark_does_not_move_where_decoding_is_said_to_stop(tmp_path):
    """The UTF-8 remedy points the reader at the position the finding
    names, and that position counted from after the byte order mark
    `utf-8-sig` had taken off -- three bytes short of the byte in the
    file. The bad byte sits well inside the document: next to its end, a
    different defect changed the message too and this passed for that."""
    raw = b"\xef\xbb\xbf" + b'{"submodels": [], "x": "\xff", "padding": "%s"}' % (b"y" * 40)
    path = tmp_path / "bom.json"
    path.write_bytes(raw)
    (error,) = load(path).errors
    assert "position %d:" % raw.index(b"\xff") in error.detail, error.detail


@pytest.mark.parametrize("tail, cut", [
    (b"\xc3", True),
    (b"\xe4\xb8", True),
    (b"\xff", False),
    (b"\xb0", False),
    (b"\xed\xa4", False),
], ids=["one-of-two", "two-of-three", "starts-nothing", "a-continuation-alone",
        "a-surrogate"])
@pytest.mark.parametrize("bom", [b"", codecs.BOM_UTF8], ids=["no-mark", "byte-order-mark"])
@pytest.mark.parametrize("zipped", [False, True], ids=["bare", "packaged"])
def test_whether_the_bytes_were_cut_short_is_read_from_the_last_ones(
        tmp_path, tail, cut, bom, zipped):
    """Bytes that end inside a character were cut short. Bytes that end on
    one no character can finish from -- a byte no character starts with, a
    continuation byte with nothing before it, the start of a surrogate,
    which UTF-8 never encodes -- are in the wrong encoding. Only the first
    kind was measured, and the half of the question asked of the bytes
    could be deleted with the suite green. With a byte order mark in front
    the decoder counts from after it, and the question has to be asked of
    the bytes the file holds, zipped or not."""
    from aas_submodel_validate import loader

    raw = bom + b'{"submodels": [], "note": "' + tail
    path = tmp_path / ("p.aasx" if zipped else "probe.json")
    build_aasx(path, payload=raw) if zipped else path.write_bytes(raw)
    (error,) = [e for e in load(path).errors if e.stage == "payload"]
    if zipped:
        expected = loader.CUT_SHORT_IN_A_PACKAGE if cut else loader.NOT_UTF8_IN_A_PACKAGE
    else:
        expected = loader.CUT_SHORT if cut else loader.NOT_UTF8
    assert error.fix == expected, error.fix


@pytest.mark.parametrize("value", ["abc", "\u00e9"], ids=["bad-base64", "not-ascii"])
@pytest.mark.parametrize("zipped", [False, True], ids=["bare", "packaged"])
def test_what_building_raises_is_the_documents_whatever_its_type(tmp_path, zipped, value):
    """A Blob value that is not base64 fails while building the environment
    -- a `binascii.Error`, which is a `ValueError`, or a
    `UnicodeEncodeError`. Raised while *decoding* those types mean this
    interpreter's digit limit and bytes that are not UTF-8; raised while
    building they are the document's defect, and only which step raised
    tells the two apart. Measured on the classifier this replaced: with
    that step left marked as decoding, both came back wrong -- one told
    nothing was being judged, one told to save the file as UTF-8 -- and
    the suite passed; no fixture carried a Blob. The classifier now asks
    for a decode error by name, so the encode error no longer depends on
    the step; the `ValueError` still does, and both stay pinned."""
    env = {"submodels": [{"id": "urn:test:blob", "modelType": "Submodel",
                          "submodelElements": [{"idShort": "b", "modelType": "Blob",
                                                "contentType": "application/octet-stream",
                                                "value": value}]}]}
    raw = json.dumps(env).encode("utf-8")
    path = tmp_path / ("p.aasx" if zipped else "bare.json")
    build_aasx(path, payload=raw) if zipped else path.write_bytes(raw)
    (error,) = [e for e in load(path).errors if e.stage == "payload"]
    assert error.message == "the document could not be read as an AAS environment"
    assert error.fix is None, error.fix


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
    assert loaded.environments, "the environment branch was not taken"
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


def test_the_extension_remedy_does_not_promise_xml_for_a_bare_submodel(tmp_path):
    """The remedy for an extension this reader cannot place said `.json or
    .xml for an AAS environment or a bare Submodel` -- but a bare Submodel
    is read from `.json` only, and one given as `.xml` is read as an
    environment, fails, and is told to fix a syntax that is not wrong. The
    remedy promised a route the reader does not have. It names `.json` for
    a bare Submodel and `.xml` for an environment now."""
    path = tmp_path / "notes.txt"
    path.write_bytes(env_json())
    with pytest.raises(UnreadablePath, match="cannot tell what") as exc_info:
        load(path)
    fix = exc_info.value.fix
    assert "a bare Submodel" in fix
    # A bare Submodel sits with .json and before .xml: it is the .json route,
    # not the .xml one.
    assert fix.index(".json") < fix.index("a bare Submodel") < fix.index(".xml"), fix


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


#: The five ways the chain can refuse, each at the clause that catches it.
#: Every one of these clauses could be deleted with the suite green: the
#: exception it names reached no fixture, so the handler was a promise
#: about hostile input that had never been kept. Two of them catch the
#: *same* exception the other two do, one link further along -- the root
#: relationships part against a payload's own -- and a fixture for one
#: says nothing about the other.
_RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_DTD_RELS = ('<?xml version="1.0"?><!DOCTYPE Relationships '
             '[<!ENTITY a "x">]><Relationships xmlns="%s"/>' % _RELS_NS).encode()
_WIDE_RELS = ('<?xml version="1.0"?><Relationships xmlns="%s"><!-- %s --></Relationships>'
              % (_RELS_NS, "x" * 4000)).encode()


def _chain(path, *, root_rels=None, spec="/aasx/env.json", part_rels=None):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", root_rels if root_rels is not None
                         else rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels", rels([(SPEC_REL, spec)]))
        archive.writestr("aasx/env.json", env_json())
        if part_rels is not None:
            archive.writestr("aasx/_rels/env.json.rels", part_rels)
    return path


@pytest.mark.parametrize("how,stage,read_anyway,says", (
    ("root rels over the bound", "bounds", False, None),
    ("root rels declares a DTD", "chain", False, "Remove the DTD"),
    ("a spec part the chain does not reach", "chain", False, None),
    ("a part's own rels over the bound", "bounds", True, None),
    ("a part's own rels will not parse", "chain", True, None),
))
def test_every_way_the_chain_refuses_is_caught_and_staged(tmp_path, monkeypatch,
                                                          how, stage, read_anyway,
                                                          says):
    """Caught, staged as itself, carrying its own remedy where it has
    one, and -- where the payload was already read -- not costing the
    submodel that arrived before it.

    The stage is what the container rules read to choose a finding, so
    getting it wrong hands the author a remedy for a defect they do not
    have: "bounds" says this reader refused, "chain" says the package's
    relationships do not reach what they name.

    The remedy matters separately, and the DTD clause is why. It is a
    subclass of the clause below it, so deleting it changes no stage --
    the parent catches the same exception and stages it the same way. All
    that goes is the sentence telling the author which part holds the
    declaration and why this reader will not expand it."""
    path = tmp_path / "chain.aasx"
    if "over the bound" in how:
        monkeypatch.setattr(container, "MAX_PART_BYTES", 512)
    if how.startswith("root rels over"):
        _chain(path, root_rels=_WIDE_RELS)
    elif how.startswith("root rels declares"):
        _chain(path, root_rels=_DTD_RELS)
    elif how.startswith("a spec part"):
        _chain(path, spec="/aasx/absent.json")
    elif "own rels over" in how:
        _chain(path, part_rels=_WIDE_RELS)
    else:
        _chain(path, part_rels=b"<not xml")
    loaded = load(path)
    assert [error.stage for error in loaded.errors] == [stage]
    assert bool(loaded.submodels) is read_anyway
    if says:
        assert says in (loaded.errors[0].fix or ""), loaded.errors[0].fix
def test_one_unreachable_spec_part_does_not_hide_the_next(tmp_path):
    """The chain reports every part it could not read, not the first.

    A package may declare more than one `aas-spec` payload, and each is
    read in turn. A reader that stopped at the first failure would tell
    an author to fix one thing, and tell them the same thing again after
    they fixed it -- the shape this project treats as worst after
    inventing a defect: making somebody run the tool twice to learn what
    the first run already knew.

    Measured before this was written: turning that loop's `continue`
    into a `break` left the whole suite green, because no fixture
    declared two payloads that both fail.
    """
    path = tmp_path / "two.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        #: Two payloads the origin names and the archive does not hold.
        #: `read` refuses each with a ContainerError, which the chain
        #: records and walks past.
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         rels([(SPEC_REL, "/aasx/first.json"),
                               (SPEC_REL, "/aasx/second.json")]))
    loaded = load(path)
    named = " ".join(error.message for error in loaded.errors)
    assert "first.json" in named and "second.json" in named, (
        "the chain stopped at the first payload it could not read: %s"
        % [error.message for error in loaded.errors])
