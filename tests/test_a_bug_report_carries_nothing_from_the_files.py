"""A bug report is written for a person to attach, and carries nothing from the
files it was about.

`smtv FILE --bug-report` writes a diagnostic bundle beside the run: the shape
of the input -- sizes, methods, flags, hashes -- and what the run said, by rule
id and count. Nothing is sent; the bundle is a file here. What is held below is
the promise that makes it safe to attach: every place a sender can write
something -- a member's name, a folder in the package, an idShort, an
identifier, a value, a description, an XML comment, the archive's comment, an
extra field, a PDF's text, the directory the file sat in -- carries a marker,
and the marker is in the bundle in no form a reader could decode it from. And
the bundle changes nothing about the verdict.
"""
from __future__ import annotations

import base64
import copy
import io
import json
import os
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

import pytest

import aas_submodel_validate.bundle as bundling
import aas_submodel_validate.cli as cli
from builders import build_aasx, dn_env, sn_env

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "corpus"

#: Written wherever a sender can write. Long and odd enough that a match is a leak.
CANARY = "Qz7Canary4Vx9Kp"


@pytest.fixture(autouse=True)
def not_written():
    """Every bundle that could not be drawn or written, in this test.

    The run says such a failure in one line and goes on, which is right for a
    person's run and is silence in a test: a defect in drawing a bundle would
    pass every test here that did not look for that line. So every test looks.
    One that expects a bundle to fail says so by emptying this list.
    """
    seen = []
    said = cli._say

    def listening(*parts):
        if parts and str(parts[0]).startswith("The diagnostic bundle could not be written"):
            seen.append(str(parts[0]))
        said(*parts)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cli, "_say", listening)
        yield seen
    assert not seen, "a bundle could not be drawn or written: %s" % seen


def _forms(text):
    """Every way the canary could sit in the bundle's bytes and still be read."""
    raw = text.encode("utf-8")
    forms = {raw, raw.lower(), raw.upper(), text.encode("utf-16-le"), text.encode("utf-16-be"),
             raw.hex().encode(), raw.hex().upper().encode()}
    for pad in (b"", b"x", b"xx"):
        coded = base64.b64encode(pad + raw)
        forms.add(coded[4:-4])              # the part that does not depend on what surrounds it
    return forms


def _as_bytes(value):
    """Every list of whole numbers in the bundle, read back as bytes the ways a
    list of numbers can hold text: one byte each, or two either way round. The
    bundle is mostly numbers, and a name carried as `[81, 122, 55, ...]` is a
    name carried."""
    if isinstance(value, dict):
        for inner in value.values():
            yield from _as_bytes(inner)
    elif isinstance(value, list):
        numbers = [v for v in value if type(v) is int]
        if numbers and len(numbers) == len(value):
            if all(0 <= v < 256 for v in numbers):
                yield bytes(numbers)
            if all(0 <= v < 65536 for v in numbers):
                yield b"".join(v.to_bytes(2, "little") for v in numbers)
                yield b"".join(v.to_bytes(2, "big") for v in numbers)
        for inner in value:
            yield from _as_bytes(inner)


def _leaks(data):
    """The canary in the bundle's bytes, or in any list of numbers in it."""
    places = [data, *_as_bytes(json.loads(data))]
    return [form for form in _forms(CANARY) for place in places if form in place]


def _marked_environment() -> dict:
    """The Digital Nameplate's golden environment with the canary in every
    place its author writes: each idShort, the submodel's id, every string
    value and every language string -- and one element this tool has no row
    for, which the report then names. idShorts are not what matches, so the
    verdict is still about a real submodel."""
    env = copy.deepcopy(dn_env())
    submodel = env["submodels"][0]
    submodel["id"] = "urn:%s:nameplate" % CANARY
    pending = [submodel]
    while pending:
        element = pending.pop()
        if element.get("idShort"):
            element["idShort"] = element["idShort"] + CANARY
        for text in element.get("description") or []:
            text["text"] = "%s description" % CANARY
        value = element.get("value")
        if isinstance(value, str) and element.get("valueType") in (None, "xs:string"):
            element["value"] = "%s value" % CANARY
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and "language" in item:
                    item["text"] = "%s text" % CANARY
                elif isinstance(item, dict):
                    pending.append(item)
        pending.extend(element.get("submodelElements") or [])
    submodel["submodelElements"].append({
        "idShort": "Doc%s" % CANARY, "modelType": "File", "contentType": "application/pdf",
        "value": "/aasx/files/%s/%s-file.pdf" % (CANARY, CANARY),
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference", "value": "urn:%s:doc" % CANARY}]}})
    return env


def _package(tmp_path):
    """An AASX with the canary in every place a sender writes: the environment
    above, a PDF under a folder and a file named by it, the archive's comment,
    and two extra fields on the PDF's entry."""
    built = tmp_path / "built.aasx"
    name = "aasx/files/%s/%s-file.pdf" % (CANARY, CANARY)
    pdf = ("%%PDF-1.7\n1 0 obj\n<< /Title (%s) >>\nendobj\n(%s body)\n%%%%EOF\n"
           % (CANARY, CANARY)).encode()
    build_aasx(built, payload=json.dumps(_marked_environment()).encode("utf-8"),
               files=[(name, pdf)])
    buf = io.BytesIO()
    with zipfile.ZipFile(built) as given, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.comment = ("%s archive comment" % CANARY).encode()
        for info in given.infolist():
            if info.filename == name:
                # One extra field of no standard, and the one Info-ZIP writes
                # for a name that is not ASCII -- version, the CRC of the name
                # in the header, and the name in UTF-8. A walk over them that
                # is one byte off reads names out of the second.
                unicode_path = (b"\x01" + zlib.crc32(name.encode()).to_bytes(4, "little")
                                + name.encode())
                info.extra = (b"\xfe\xca" + len(CANARY.encode()).to_bytes(2, "little")
                              + CANARY.encode() + b"\x75\x70"
                              + len(unicode_path).to_bytes(2, "little") + unicode_path)
            zf.writestr(info, given.read(info.filename))
    where = tmp_path / ("drop-%s" % CANARY)
    where.mkdir()
    path = where / ("%s.aasx" % CANARY)
    path.write_bytes(buf.getvalue())
    return path


def _document(tmp_path):
    """A bare XML environment with the canary in a comment, an idShort, an
    identifier and a value."""
    where = tmp_path / ("xml-%s" % CANARY)
    where.mkdir()
    path = where / ("%s.xml" % CANARY)
    path.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<!-- %(c)s in a comment -->
<environment xmlns="https://admin-shell.io/aas/3/0">
  <submodels>
    <submodel>
      <idShort>Sub%(c)s</idShort>
      <id>urn:%(c)s:submodel</id>
      <semanticId>
        <type>ExternalReference</type>
        <keys><key><type>GlobalReference</type><value>urn:%(c)s:template</value></key></keys>
      </semanticId>
      <submodelElements>
        <property>
          <idShort>Prop%(c)s</idShort>
          <valueType>xs:string</valueType>
          <value>%(c)s value</value>
        </property>
      </submodelElements>
    </submodel>
  </submodels>
</environment>
""" % {"c": CANARY}, encoding="utf-8")
    return path


def _bundle(tmp_path, capsys, *args):
    out = tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)
    code = cli.main([*args, "--bug-report", "--bundle-out", str(out)])
    captured = capsys.readouterr()
    written = sorted(out.iterdir())
    return code, captured, written


def test_nothing_a_sender_wrote_is_in_the_bundle_of_a_package(tmp_path, capsys):
    path = _package(tmp_path)
    code, captured, written = _bundle(tmp_path, capsys, str(path),
                                      "--note", "the verdict looks wrong to me")
    assert CANARY in captured.out, "the report does not carry the canary, so nothing was tested"
    assert len(written) == 1, written
    data = written[0].read_bytes()
    leaks = _leaks(data)
    assert not leaks, "the bundle carries the canary as %s" % leaks[:3]
    assert CANARY not in written[0].name
    # And what it does carry is there: the shape, the rule ids, the note.
    bundle = json.loads(data)
    members = bundle["input"]["members"]
    assert bundle["input"]["kind"] == "zip" and members["count"] >= 5, members
    # Each row is numbers of the kind its field names, so nothing can ride in
    # a field as a list or a string; and of an extra field, the ids of its
    # records and not a byte of what they hold.
    for row in members["rows"]:
        field = dict(zip(members["rowFields"], row))
        assert len(row) == len(members["rowFields"]), row
        assert all(type(field[k]) is int
                   for k in ("i", "size", "csize", "method", "flagBits", "nameLen")), row
        assert all(field[k] is None or type(field[k]) is int
                   for k in ("sameNameAs", "sameFoldedNameAs")), row
        assert type(field["utf8Flag"]) is bool, row
        assert all(type(x) is int for x in field["extraIds"]), row
    assert [0xCAFE, 0x7075] in [dict(zip(members["rowFields"], row))["extraIds"]
                                for row in members["rows"]]
    assert bundle["input"]["fileKinds"]["pdf"] == 1, bundle["input"]["fileKinds"]
    assert bundle["run"]["findings"], "the bundle says nothing about the run"
    assert bundle["run"]["exitCode"] == code
    assert bundle["user"] == {"note": "the verdict looks wrong to me"}
    assert "<input-1>" in bundle["invocation"]["argv"]
    assert captured.err.rstrip().endswith("Nothing was sent.")


def test_nothing_a_sender_wrote_is_in_the_bundle_of_a_document(tmp_path, capsys):
    path = _document(tmp_path)
    code, captured, written = _bundle(tmp_path, capsys, str(path), "-f", "json")
    assert CANARY in captured.out, "the report does not carry the canary, so nothing was tested"
    assert len(written) == 1, written
    data = written[0].read_bytes()
    assert not _leaks(data), _leaks(data)[:3]
    bundle = json.loads(data)
    assert bundle["input"]["kind"] == "file" and bundle["input"]["members"]["count"] == 0
    assert "SMT-D1" in bundle["run"]["findings"], bundle["run"]["findings"]
    assert bundle["run"]["exitCode"] == code == 1



def test_what_the_run_did_not_examine_is_counted_and_not_named(tmp_path, capsys):
    """The report names the places it did not examine and the elements that
    sat there, by the file's own idShorts and identifiers. The bundle says how
    many."""
    env = copy.deepcopy(sn_env())
    spec = "https://admin-shell.io/idta/SoftwareNameplate/1/0/"
    for element in env["submodels"][0]["submodelElements"]:
        element["semanticId"]["keys"][0]["value"] = "%s%s%s" % (spec, element["idShort"], CANARY)
        element["idShort"] = element["idShort"] + CANARY
    path = tmp_path / ("%s.json" % CANARY)
    path.write_text(json.dumps(env), encoding="utf-8")
    code, captured, written = _bundle(tmp_path, capsys, str(path), "-f", "json")
    places = json.loads(captured.out)["summary"]["scopeNotExamined"]
    assert CANARY in json.dumps(places), "no place names the canary, so nothing was tested"
    data = written[0].read_bytes()
    assert not _leaks(data), _leaks(data)[:3]
    run = json.loads(data)["run"]
    assert run["scopeNotExamined"] == run["summary"]["scopeNotExamined"] == len(places) == 2


def test_the_same_run_gives_the_same_bytes(tmp_path, capsys):
    path = str(_package(tmp_path))
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = _bundle(tmp_path / "a", capsys, path)[2][0]
    second = _bundle(tmp_path / "b", capsys, path)[2][0]
    assert first.read_bytes() == second.read_bytes()
    assert first.name == second.name


def test_a_failure_of_this_tool_writes_a_bundle_and_leaves_as_it_did(tmp_path, capsys,
                                                                     monkeypatch):
    """A defect that escapes the run left as a traceback before this existed,
    and still does -- the exception is raised again, so the process leaves
    with the same code. Before it goes, the bundle is written."""
    path = str(_package(tmp_path))

    def breaks(*_args, **_kwargs):
        raise KeyError("%s in the message" % CANARY)
    monkeypatch.setattr(cli.runner, "run", breaks)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(KeyError):
        cli.main([path, "--no-bundle"])
    assert not list(tmp_path.glob("bug-report-*.json")), "--no-bundle wrote a bundle"
    capsys.readouterr()
    with pytest.raises(KeyError):
        cli.main([path, "--show-bundle"])
    assert not list(tmp_path.glob("bug-report-*.json")), "--show-bundle wrote a bundle"
    shown = capsys.readouterr().err
    assert cli.SHOWN in shown and '"trigger": "crash"' in shown, shown
    with pytest.raises(KeyError):
        cli.main([path])
    written = list(tmp_path.glob("bug-report-*.json"))
    assert len(written) == 1
    data = written[0].read_bytes()
    assert not _leaks(data)
    bundle = json.loads(data)
    assert bundle["bundle"]["trigger"] == "crash"
    assert bundle["error"]["type"] == "KeyError"
    assert bundle["error"]["tracebackFrames"], bundle["error"]
    assert all(not frame["file"].startswith("/") for frame in bundle["error"]["tracebackFrames"])
    err = capsys.readouterr().err
    assert "defect in this tool" in err and err.rstrip().endswith(cli.SENT), err


def test_a_process_that_fails_leaves_by_the_same_code_with_or_without_the_bundle(tmp_path):
    """The code a defect leaves by, measured on a real process: the same
    whether a bundle is written or not."""
    path = str(_package(tmp_path))
    breaking = ("import sys, aas_submodel_validate.runner as r\n"
                "def breaks(*a, **k):\n    raise KeyError('x')\n"
                "r.run = breaks\n"
                "from aas_submodel_validate.cli import main\n"
                "sys.exit(main(sys.argv[1:]))\n")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    codes = []
    for more in (["--no-bundle"], []):
        done = subprocess.run([sys.executable, "-c", breaking, path, *more], cwd=str(tmp_path),
                              capture_output=True, text=True, timeout=120, env=env)
        assert "Traceback" in done.stderr, done.stderr
        codes.append(done.returncode)
    assert codes[0] == codes[1] == 1, codes
    assert len(list(tmp_path.glob("bug-report-*.json"))) == 1


def test_a_path_that_is_not_there_is_not_called_a_defect_or_a_refusal(tmp_path, capsys,
                                                                     monkeypatch):
    """A mistyped path is the caller's, not this tool's: no bundle is written
    for it, nothing calls it a defect, and nobody is asked to report it."""
    monkeypatch.chdir(tmp_path)
    assert cli.main([str(tmp_path / "not-there.aasx")]) == cli.EXIT_ERROR
    assert not list(tmp_path.glob("bug-report-*.json")), "a mistyped path wrote a bundle"
    err = capsys.readouterr().err
    assert "defect in this tool" not in err and cli.REFUSED not in err, err


def test_a_large_archive_is_listed_up_to_the_limit(tmp_path, capsys):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for i in range(5001):
            zf.writestr("m%d.txt" % i, b"")
    path = tmp_path / "many.aasx"
    path.write_bytes(buf.getvalue())
    _code, _captured, written = _bundle(tmp_path, capsys, str(path))
    bundle = json.loads(written[0].read_bytes())
    assert bundle["input"]["members"]["count"] == 5001
    assert bundle["input"]["members"]["listed"] <= 5000
    assert len(bundle["input"]["members"]["rows"]) == bundle["input"]["members"]["listed"]
    assert written[0].stat().st_size <= 256 * 1024


def _inputs():
    found = sorted(p for p in CORPUS.rglob("*") if p.suffix in (".aasx", ".json", ".xml"))
    assert found, "no corpus to compare"
    return found


@pytest.mark.parametrize("path", _inputs(), ids=lambda p: p.name)
@pytest.mark.parametrize("fmt", ["text", "json"])
def test_asking_for_a_bundle_changes_no_verdict(path, fmt, tmp_path, capsys):
    plain = cli.main([str(path), "-f", fmt])
    before = capsys.readouterr()
    code, captured, written = _bundle(tmp_path, capsys, str(path), "-f", fmt)
    assert code == plain, "asking for a bundle moved the exit code"
    assert captured.out == before.out, "asking for a bundle changed the report"
    # And it was written. A bundle that fails to draw is said in one line and
    # the run goes on, which is right for the run and would be silence here.
    assert len(written) == 1 and "could not be written" not in captured.err, captured.err
    # What stderr said before is still said, first; the bundle's lines follow.
    assert captured.err.startswith(before.err.replace(cli.REFUSED + "\n", "")), captured.err


def _refused(tmp_path):
    path = tmp_path / "not-a-package.aasx"
    path.write_bytes(b"this is not an archive")
    return path


@pytest.mark.parametrize("flags", [[], ["-q"], ["-f", "json"]], ids=["text", "quiet", "json"])
def test_a_refused_file_is_told_how_to_report_it_once(flags, tmp_path, capsys):
    path = _refused(tmp_path)
    plain = cli.main([str(path), *flags])
    captured = capsys.readouterr()
    assert captured.err.count(cli.REFUSED) == 1, captured.err
    assert cli.REFUSED not in captured.out
    assert captured.err.rstrip().endswith(cli.REFUSED), "the sentence is not the last word"
    # Asked for a bundle, the run makes one and does not also say how to.
    code, captured, written = _bundle(tmp_path, capsys, str(path), *flags)
    assert code == plain and len(written) == 1
    assert cli.REFUSED not in captured.err, captured.err
    assert json.loads(written[0].read_bytes())["bundle"]["trigger"] == "refusal"


def test_a_file_that_was_judged_is_not_asked_to_be_reported(tmp_path, capsys):
    path = tmp_path / "env.json"
    path.write_text(json.dumps(dn_env()), encoding="utf-8")
    assert cli.main([str(path)]) == cli.EXIT_OK
    assert cli.REFUSED not in capsys.readouterr().err
    _code, _captured, written = _bundle(tmp_path, capsys, str(path))
    assert json.loads(written[0].read_bytes())["bundle"]["trigger"] == "manual"


@pytest.mark.parametrize("spelling", ["--bundle-out={}", "--bundle={}"])
def test_a_path_given_in_one_word_stays_out_too(spelling, tmp_path, capsys):
    """`--bundle-out=DIR` and the option cut short are the same option to the
    parser, and a bundle that copied the command line would carry the
    directory -- and the user name in it -- whole."""
    out = tmp_path / ("out-%s" % CANARY)
    out.mkdir()
    code = cli.main([str(_document(tmp_path)), "--bug-report", spelling.format(out)])
    capsys.readouterr()
    written = list(out.iterdir())
    assert code == 1 and len(written) == 1
    data = written[0].read_bytes()
    assert not [form for form in _forms(CANARY) if form in data]
    assert "<out-1>" in json.loads(data)["invocation"]["argv"]


def test_the_options_are_named_and_the_paths_are_not(tmp_path, capsys):
    template = tmp_path / ("tpl-%s.json" % CANARY)
    template.write_text(json.dumps({"submodels": []}), encoding="utf-8")
    cli.main([str(_document(tmp_path)), "--bug-report", "--bundle-out", str(tmp_path),
              "--template", str(template), "--meta", "info", "-W", "--note", CANARY])
    capsys.readouterr()
    [written] = list(tmp_path.glob("bug-report-*.json"))
    bundle = json.loads(written.read_bytes())
    argv = bundle["invocation"]["argv"]
    assert "--template" in argv and "<path-1>" in argv and "--meta=info" in argv, argv
    assert "--warnings-as-errors" in argv and "--note" in argv and "<note>" in argv, argv
    del bundle["user"]           # the one place a person's own words are kept
    assert CANARY not in json.dumps(bundle), argv


def test_a_long_note_stays_within_the_limit(tmp_path, capsys):
    code, captured, written = _bundle(tmp_path, capsys, str(_document(tmp_path)),
                                      "--note", "x" * 300_000)
    assert written, "no bundle was written, so nothing below was checked"
    assert written[0].stat().st_size <= 256 * 1024
    assert json.loads(written[0].read_bytes())["user"]["note"].endswith(
        "[cut at 2,000 characters]")


def test_a_bundle_that_cannot_be_written_stops_nothing(tmp_path, capsys, monkeypatch,
                                                      not_written):
    """A working directory nobody can write to is not a reason for the exit
    code to move."""
    one = str(_document(tmp_path))

    def refuses(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied")
    plain = cli.main([one])
    before = capsys.readouterr().out
    monkeypatch.setattr(cli.bundling, "write", refuses)
    assert cli.main([one, "--bug-report"]) == plain
    captured = capsys.readouterr()
    assert captured.out == before
    assert captured.err.count("could not be written") == 1, captured.err
    not_written.clear()


def test_a_bundle_that_cannot_be_drawn_stops_nothing(tmp_path, capsys, monkeypatch,
                                                    not_written):
    """Whatever goes wrong in drawing the bundle, not only in writing it, is
    said once and the run leaves with the same report and the same code."""
    one = str(_document(tmp_path))
    plain = cli.main([one])
    before = capsys.readouterr().out

    def breaks(**_kwargs):
        raise ValueError("drawing the bundle fell over")
    monkeypatch.setattr(cli.bundling, "build", breaks)
    assert cli.main([one, "--bug-report"]) == plain
    captured = capsys.readouterr()
    assert captured.out == before
    assert captured.err.count("could not be written") == 1, captured.err
    not_written.clear()


def test_a_note_the_console_could_not_decode_stops_nothing(tmp_path, capsys):
    """A note typed in another code page arrives holding bytes the locale could
    not decode. The run is the same run, and the bundle keeps what it can of
    the note."""
    one = str(_document(tmp_path))
    plain = cli.main([one, "-f", "json"])
    before = capsys.readouterr().out
    code, captured, written = _bundle(tmp_path, capsys, one, "-f", "json",
                                      "--note", "M\udcfcller")
    assert code == plain and captured.out == before
    assert json.loads(written[0].read_bytes())["user"]["note"] == "M�ller"


def test_an_input_that_reads_back_short_is_not_described_by_what_came_back(tmp_path,
                                                                         monkeypatch):
    """What is read again for the bundle has to be what the file says it holds,
    or it is not the input the run read."""
    path = _document(tmp_path)
    monkeypatch.setattr(bundling.container, "open_regular", lambda _path: io.BytesIO(b""))
    shape = bundling.fingerprint(str(path))
    monkeypatch.undo()
    assert shape["kind"] == "stream" and shape["size"] is None, shape


def test_with_stderr_closed_the_bundle_adds_nothing_to_the_report(tmp_path, capsys,
                                                                 monkeypatch, not_written):
    """With stderr closed -- `2>&-`, or pythonw with no console -- there is no
    `sys.stderr`, and a line printed to it would go to stdout, into the JSON a
    machine is about to read. The bundle's lines and the sentence after a
    refusal are said nowhere then."""
    refused = str(_refused(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(sys, "__stderr__", None)
    plain = cli.main(["-f", "json", refused, "--no-bundle"])
    before = capsys.readouterr().out
    assert cli.main(["-f", "json", refused, "--bug-report"]) == plain
    assert capsys.readouterr().out == before, "a line meant for a person is in the report"
    assert cli.REFUSED not in before


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no named pipes here")
def test_a_pipe_is_described_without_being_read_again(tmp_path):
    """The bundle does not open a pipe a second time and wait for a writer
    that is gone."""
    pipe = tmp_path / "pipe.json"
    os.mkfifo(pipe)
    done = subprocess.run([sys.executable, "-m", "aas_submodel_validate", str(pipe),
                           "--bug-report", "--bundle-out", str(tmp_path)],
                          capture_output=True, text=True, timeout=120,
                          env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert done.returncode == cli.EXIT_ERROR, done.stderr
    written = list(tmp_path.glob("bug-report-*.json"))
    assert written and json.loads(written[0].read_bytes())["input"]["kind"] == "stream"


def test_an_extra_field_s_ids_cannot_carry_text(tmp_path, capsys):
    """An extra field of records that hold nothing, each record's id two bytes
    of text: a walk that reports every id it meets reads the text back out, two
    bytes at a time. Only the ids ZIP's application note publishes are told."""
    built = _package(tmp_path)
    raw = CANARY.encode()
    smuggled = b"".join(raw[i:i + 2].ljust(2, b"\0") + b"\0\0" for i in range(0, len(raw), 2))
    buf = io.BytesIO()
    with zipfile.ZipFile(built) as given, zipfile.ZipFile(buf, "w") as zf:
        for info in given.infolist():
            info.extra = smuggled
            zf.writestr(info, given.read(info.filename))
    path = tmp_path / "smuggled.aasx"
    path.write_bytes(buf.getvalue())
    _code, _captured, written = _bundle(tmp_path, capsys, str(path))
    data = written[0].read_bytes()
    assert not _leaks(data), _leaks(data)[:3]


@pytest.mark.allow_crash
def test_a_rule_that_ran_out_of_room_is_not_asked_to_be_reported(tmp_path, capsys,
                                                               monkeypatch):
    """Running out of memory or stack on a large but legal document is a limit,
    and its remedy says it is not a defect in the file or in this tool; the
    sentence after the report does not ask for it to be reported. A rule that
    fails with a defect of its own is."""
    import dataclasses

    from aas_submodel_validate import (
        registry,
        rules,  # noqa: F401 - importing registers
    )
    path = tmp_path / "env.json"
    path.write_text(json.dumps(dn_env()), encoding="utf-8")
    original = registry._registry["DN-E01"]
    for error, asked in ((RecursionError("deep"), False), (KeyError("k"), True)):
        def breaks(_ctx, error=error):
            raise error
        monkeypatch.setitem(registry._registry, "DN-E01",
                            dataclasses.replace(original, fn=breaks))
        cli.main([str(path)])
        assert (cli.REFUSED in capsys.readouterr().err) is asked, type(error).__name__


@pytest.mark.parametrize("error, written", [
    (FileNotFoundError(2, "No such file or directory"), True),
    (BrokenPipeError(32, "Broken pipe"), False),
], ids=["this-tool-s-own-file", "a-closed-pipe"])
def test_which_os_errors_are_this_tool_s_defect(error, written, tmp_path, capsys,
                                                monkeypatch):
    """A path the caller gave never reaches here as an exception -- the loader
    makes it `X6`. An `OSError` that escapes the run is this tool's -- one of its
    own files it could not open -- except a pipe closed on its output, which is
    the reader of the output leaving, and writes nothing."""
    path = str(_document(tmp_path))

    def breaks(*_args, **_kwargs):
        raise error
    monkeypatch.setattr(cli.runner, "run", breaks)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(type(error)):
        cli.main([path])
    assert bool(list(tmp_path.glob("bug-report-*.json"))) is written
    capsys.readouterr()


def test_a_file_past_the_reader_s_bounds_is_not_read_again_past_them(tmp_path, capsys,
                                                                     monkeypatch):
    """The bundle reads the input again, and what it takes in is held to the
    bounds the run held it to: past the size bound it is not hashed, and a
    central directory past the directory bound is counted, not listed."""
    from aas_submodel_validate import container
    path = _package(tmp_path)
    size = path.stat().st_size
    monkeypatch.setattr(container, "MAX_TOTAL_PART_BYTES", size - 1)
    shape = bundling.fingerprint(str(path))
    assert shape["sha256"] is None and shape["size"] == size, shape
    monkeypatch.undo()
    with zipfile.ZipFile(path) as zf:
        members = len(zf.infolist())
    monkeypatch.setattr(container, "MAX_DIRECTORY_BYTES", 10)
    shape = bundling.fingerprint(str(path))
    assert shape["kind"] == "zip" and shape["sha256"] is not None, shape
    assert shape["members"]["count"] == members and shape["members"]["listed"] == 0, shape


# -- what the tests above could not see, held -----------------------------

def _partly_refused(tmp_path):
    """A package that is judged and still refused in part: its origin names a
    second aas-spec part that is not there (`X2`), beside one that is."""
    built = tmp_path / "built-partly.aasx"
    build_aasx(built, payload=json.dumps(dn_env()).encode("utf-8"))
    buf = io.BytesIO()
    with zipfile.ZipFile(built) as given, zipfile.ZipFile(buf, "w") as zf:
        for info in given.infolist():
            data = given.read(info.filename)
            if info.filename.endswith("aasx-origin.rels"):
                data = data.replace(b"</Relationships>", (
                    b'<Relationship Type="http://admin-shell.io/aasx/relationships/aas-spec" '
                    b'Target="/aasx/missing.json" Id="R1" /></Relationships>'))
            zf.writestr(info, data)
    path = tmp_path / "partly.aasx"
    path.write_bytes(buf.getvalue())
    return path


def _dead_stderr_run(tmp_path, *args):
    reader, writer = os.pipe()
    os.close(reader)
    try:
        done = subprocess.run([sys.executable, "-m", "aas_submodel_validate", *args],
                              stdout=subprocess.DEVNULL, stderr=writer, cwd=str(tmp_path),
                              timeout=120, env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    finally:
        os.close(writer)
    return done.returncode


def test_a_stderr_nobody_reads_moves_no_exit_code(tmp_path):
    """A stderr that is there and cannot be written -- a pipe whose reader has
    gone -- took the sentence after a refusal, or a bundle's lines, and turned
    them into exit 120. The code is the one the run would have left by."""
    good = tmp_path / "good.json"
    good.write_text(json.dumps(dn_env()), encoding="utf-8")
    assert cli.main([str(good), "-q"]) == 0
    partly = _partly_refused(tmp_path)
    assert cli.main([str(partly), "-q"]) == 1
    assert _dead_stderr_run(tmp_path, str(good), "--bug-report") == 0
    assert _dead_stderr_run(tmp_path, str(good), "--show-bundle") == 0
    assert _dead_stderr_run(tmp_path, str(partly)) == 1
    assert _dead_stderr_run(tmp_path, str(partly), "--bug-report") == 1


def test_the_report_comes_before_the_lines_after_it_in_a_merged_log(tmp_path):
    partly = _partly_refused(tmp_path)
    done = subprocess.run([sys.executable, "-m", "aas_submodel_validate", str(partly)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                          timeout=120, env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert done.stdout.rstrip().endswith(cli.REFUSED), done.stdout[-400:]
    assert done.stdout.index(cli.REFUSED) > done.stdout.index("X2")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symbolic links here")
def test_a_link_planted_under_the_bundle_s_name_is_replaced_not_written_through(tmp_path,
                                                                                capsys):
    import hashlib
    good = tmp_path / "good.json"
    good.write_text(json.dumps(dn_env()), encoding="utf-8")
    victim = tmp_path / "victim.txt"
    victim.write_text("precious", encoding="utf-8")
    out = tmp_path / "shared"
    out.mkdir()
    name = "bug-report-%s-%s-%s.json" % (bundling.TOOL, cli.__version__,
                                         hashlib.sha256(good.read_bytes()).hexdigest()[:8])
    (out / name).symlink_to(victim)
    assert cli.main([str(good), "-q", "--bug-report", "--bundle-out", str(out)]) == 0
    capsys.readouterr()
    assert victim.read_text(encoding="utf-8") == "precious"
    assert not (out / name).is_symlink()
    assert json.loads((out / name).read_bytes())["bundle"]["tool"] == bundling.TOOL
    assert [p.name for p in out.iterdir()] == [name], "a temporary file was left behind"


def _twin(tmp_path, marker):
    """One input per marker, the markers the same length: stored, not
    compressed, so every size is the same, and the marker in every place a
    sender writes -- including a member's extension."""
    assert len(marker) == len(CANARY)
    env = json.loads(json.dumps(_marked_environment()).replace(CANARY, marker))
    built = tmp_path / ("built-%s.aasx" % marker)
    name = "aasx/files/%s/%s-file.pdf" % (marker, marker)
    pdf = ("%%PDF-1.7\n(%s body)\n%%%%EOF\n" % marker).encode()
    build_aasx(built, payload=json.dumps(env).encode("utf-8"),
               files=[(name, pdf), ("aasx/files/notes.%s" % marker, marker.encode())])
    buf = io.BytesIO()
    with zipfile.ZipFile(built) as given, zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.comment = ("%s archive comment" % marker).encode()
        for info in given.infolist():
            data = given.read(info.filename)
            info.compress_type = zipfile.ZIP_STORED
            if info.filename == name:
                info.extra = (b"\xfe\xca" + len(marker).to_bytes(2, "little")
                              + marker.encode())
            zf.writestr(info, data)
    where = tmp_path / ("drop-%s" % marker)
    where.mkdir()
    path = where / ("%s.aasx" % marker)
    path.write_bytes(buf.getvalue())
    return path


def test_two_files_that_differ_only_in_what_their_senders_wrote_give_one_bundle(tmp_path,
                                                                                capsys):
    """Whatever the bundle carries that came from what a sender wrote -- the
    text itself, a hash of it, a number made of it, an extension -- differs
    between two files that differ only in that. Nothing but the input's own
    hash may."""
    other = "Jd4Walrus8Ck2Ft"
    bundles = []
    for marker in (CANARY, other):
        _code, _captured, written = _bundle(tmp_path / marker, capsys,
                                            str(_twin(tmp_path, marker)))
        bundles.append(json.loads(written[0].read_bytes()))
    for bundle in bundles:
        assert bundle["input"]["members"]["listed"] >= 6
        bundle["input"]["sha256"] = None
    assert bundles[0] == bundles[1]


def test_the_environment_the_user_and_the_host_stay_out(tmp_path, capsys, monkeypatch):
    import platform
    import socket
    for variable in ("USER", "LOGNAME", "USERNAME", "HOME", "SMTV_SOMETHING"):
        monkeypatch.setenv(variable, "%s-%s" % (variable, CANARY))
    monkeypatch.setattr(platform, "node", lambda: "host-%s" % CANARY)
    monkeypatch.setattr(socket, "gethostname", lambda: "host-%s" % CANARY)
    here = tmp_path / ("cwd-%s" % CANARY)
    here.mkdir()
    monkeypatch.chdir(here)
    path = here / "env.json"
    path.write_text(json.dumps(dn_env()), encoding="utf-8")
    assert cli.main([str(path), "-q", "--bug-report"]) == 0
    capsys.readouterr()
    [written] = list(here.glob("bug-report-*.json"))
    assert not _leaks(written.read_bytes()), _leaks(written.read_bytes())[:3]


def test_a_frame_outside_this_package_is_not_kept(tmp_path, capsys, monkeypatch):
    path = str(_document(tmp_path))
    namespace = {}
    exec("def Qz7Canary4Vx9Kp_raises(*a, **k):\n    raise KeyError('x')\n", namespace)
    monkeypatch.setattr(cli.runner, "run", namespace["Qz7Canary4Vx9Kp_raises"])
    monkeypatch.chdir(tmp_path)
    with pytest.raises(KeyError):
        cli.main([path])
    capsys.readouterr()
    [written] = list(tmp_path.glob("bug-report-*.json"))
    bundle = json.loads(written.read_bytes())
    assert not _leaks(written.read_bytes())
    assert all(frame["file"].startswith("aas_submodel_validate/")
               for frame in bundle["error"]["tracebackFrames"]), bundle["error"]
    assert bundle["run"]["exitCode"] == 1


def test_member_rows_are_trimmed_to_as_many_as_fit(tmp_path, capsys):
    """Rows of two published extra-field records each: five thousand of them
    are more than 256 KiB, and the bundle keeps as many as fit rather than
    halving until it is under."""
    buf = io.BytesIO()
    extra = (b"\x55\x54\x05\x00" + b"\x01" + b"\x00" * 4
             + b"\x75\x78\x0b\x00" + b"\x01\x04" + b"\x00" * 4 + b"\x04" + b"\x00" * 4)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for i in range(5001):
            info = zipfile.ZipInfo("member-%05d.txt" % i)
            info.extra = extra
            zf.writestr(info, b"x" * (i % 97))
    path = tmp_path / "wide.aasx"
    path.write_bytes(buf.getvalue())
    _code, _captured, written = _bundle(tmp_path, capsys, str(path))
    size = written[0].stat().st_size
    members = json.loads(written[0].read_bytes())["input"]["members"]
    assert size <= bundling.LIMIT, size
    assert members["count"] == 5001 and 3500 < members["listed"] < 5000, members["listed"]
    assert size > bundling.LIMIT - 200, "rows were left out that would have fitted"


def test_a_caller_template_whose_every_row_fires_stays_within_the_limit(tmp_path, capsys):
    """Ten thousand rows a caller's template may declare, and each can fire.
    The rules that fired least are left out, and their findings counted."""
    def ref(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}
    identifier = "urn:example:bundle:wide-template"
    elements = [{"modelType": "Property", "idShort": "P%d" % i, "valueType": "xs:string",
                 "semanticId": ref("%s/p%d" % (identifier, i)),
                 "qualifiers": [{"type": "SMT/Cardinality", "valueType": "xs:string",
                                 "value": "One"}]} for i in range(3000)]
    template = tmp_path / "wide-template.json"
    template.write_text(json.dumps({"submodels": [{
        "kind": "Template", "idShort": "Wide", "id": "urn:t", "semanticId": ref(identifier),
        "submodelElements": elements}]}), encoding="utf-8")
    instance = tmp_path / "instance.json"
    instance.write_text(json.dumps({"submodels": [{
        "idShort": "Wide", "id": "urn:i", "modelType": "Submodel",
        "semanticId": ref(identifier), "submodelElements": []}]}), encoding="utf-8")
    code, _captured, written = _bundle(tmp_path, capsys, str(instance), "--template",
                                       str(template), "-q")
    assert code == 1
    assert written[0].stat().st_size <= bundling.LIMIT
    bundle = json.loads(written[0].read_bytes())
    run = bundle["run"]
    assert run["notListed"] > 0 and len(run["findings"]) < 3000, len(run["findings"])
    assert run["notListed"] + sum(s["count"] for s in run["findings"].values()) >= 3000
    assert len(bundle["readable"]) < 2000


def test_two_processes_give_the_same_bytes(tmp_path):
    path = str(_package(tmp_path))
    names = []
    for seed in ("1", "2"):
        out = tmp_path / ("seed-" + seed)
        out.mkdir()
        subprocess.run([sys.executable, "-m", "aas_submodel_validate", path, "-q",
                        "--bug-report", "--bundle-out", str(out)], timeout=120,
                       capture_output=True,
                       env={**os.environ, "PYTHONPATH": str(ROOT / "src"),
                            "PYTHONHASHSEED": seed})
        [written] = list(out.iterdir())
        names.append((written.name, written.read_bytes()))
    assert names[0] == names[1]


def test_what_the_bundle_says_of_an_archive_is_what_the_archive_holds(tmp_path, capsys):
    import hashlib
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.txt", b"one")
        zf.writestr("B.txt", b"two")
        zf.writestr("b.txt", b"three")
        zf.writestr("inner.aasx", b"PK")
        zf.writestr("été.pdf", b"%PDF")
        with pytest.warns(UserWarning):
            zf.writestr("a.txt", b"again")
    path = tmp_path / "shaped.aasx"
    path.write_bytes(buf.getvalue())
    _code, _captured, written = _bundle(tmp_path, capsys, str(path))
    shape = json.loads(written[0].read_bytes())["input"]
    assert shape["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    rows = [dict(zip(shape["members"]["rowFields"], row)) for row in shape["members"]["rows"]]
    assert [row["sameNameAs"] for row in rows] == [None, None, None, None, None, 0]
    assert [row["sameFoldedNameAs"] for row in rows] == [None, None, 1, None, None, None]
    assert [row["utf8Flag"] for row in rows] == [False, False, False, False, True, False]
    assert shape["containersInside"] == 1 and shape["fileKinds"]["pdf"] == 1


def test_what_the_bundle_says_of_the_run_is_what_the_run_said(tmp_path, capsys):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(dn_env()), encoding="utf-8")
    partly = _partly_refused(tmp_path)
    # The exit code under -W is the one the process leaves by.
    code, _captured, written = _bundle(tmp_path / "w", capsys, str(partly), "-W", "-q")
    run = json.loads(written[0].read_bytes())["run"]
    assert run["exitCode"] == code == 1
    for rule, slot in run["findings"].items():
        assert sum(slot["whereKinds"].values()) == slot["count"], rule
    assert run["findings"]["X2"]["whereKinds"]["none"] == 0, run["findings"]["X2"]
    # --example is named, and no input place-holder stands for it.
    _code, _captured, written = _bundle(tmp_path / "e", capsys, "--example", "-q")
    argv = json.loads(written[0].read_bytes())["invocation"]["argv"]
    assert "--example" in argv and not [a for a in argv if a.startswith("<input")], argv


def test_the_bound_the_run_met_is_named(tmp_path, capsys, monkeypatch):
    from aas_submodel_validate import container
    monkeypatch.setattr(container, "MAX_PART_BYTES", 512)
    path = tmp_path / "big.json"
    path.write_bytes(b" " * 600)
    _code, _captured, written = _bundle(tmp_path, capsys, str(path))
    run = json.loads(written[0].read_bytes())["run"]
    assert run["budgets"]["hit"] == ["X5"], run


def test_show_bundle_writes_nothing_on_a_run_that_did_not_fail(tmp_path, capsys, monkeypatch):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(dn_env()), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert cli.main([str(good), "-q", "--show-bundle"]) == 0
    assert '"bundleSchema": 1' in capsys.readouterr().err
    assert not list(tmp_path.glob("bug-report-*.json"))


def test_an_interrupt_is_not_a_defect(tmp_path, capsys, monkeypatch):
    path = str(_document(tmp_path))

    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(cli.runner, "run", interrupted)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        cli.main([path])
    assert not list(tmp_path.glob("bug-report-*.json"))
    assert "defect" not in capsys.readouterr().err


def test_a_refused_template_is_not_a_refused_file(tmp_path, capsys):
    """A template this reader refuses is the caller's second file; the run
    judged nothing, and the sentence about reporting a file is not said."""
    template = tmp_path / "t.json"
    template.write_text("[1, 2]", encoding="utf-8")
    assert cli.main([str(_document(tmp_path)), "--template", str(template)]) == 2
    assert cli.REFUSED not in capsys.readouterr().err


def _over_the_bound(tmp_path, monkeypatch):
    from aas_submodel_validate import container
    monkeypatch.setattr(container, "MAX_PART_BYTES", 512)
    path = tmp_path / "big.json"
    path.write_bytes(b" " * 600)
    return path


def _unparsable(tmp_path, _monkeypatch):
    path = tmp_path / "broken.json"
    path.write_text("{", encoding="utf-8")
    return path


@pytest.mark.parametrize("make, rule", [
    (lambda tmp_path, _m: _partly_refused(tmp_path), "X2"),
    (_unparsable, "X3"),
    (_over_the_bound, "X5"),
], ids=["X2", "X3", "X5"])
def test_each_kind_of_refusal_is_told_how_to_report_it(make, rule, tmp_path, capsys,
                                                       monkeypatch):
    path = make(tmp_path, monkeypatch)
    report_code = cli.main([str(path), "-f", "json"])
    captured = capsys.readouterr()
    assert rule in {f["rule"] for f in json.loads(captured.out)["findings"]}
    assert captured.err.count(cli.REFUSED) == 1, (report_code, captured.err)


@pytest.mark.parametrize("flag", [["--bug-report"], ["--show-bundle"], ["--no-bundle"],
                                  ["--note", "x"], ["--bundle-out", "."]],
                         ids=lambda f: f[0])
def test_rules_refuses_every_bundle_switch(flag):
    with pytest.raises(SystemExit) as exited:
        cli.main(["--rules", *flag])
    assert exited.value.code == cli.EXIT_USAGE
