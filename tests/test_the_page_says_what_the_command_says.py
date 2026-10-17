"""The page is a way in, and it reaches the verdict the others reach.

`dist/aas-submodel-validate.html` carries a Python built for the browser,
this engine and its one dependency, and runs the command's own entry point
inside the tab, on the file it is handed, with the arguments a person would
type. What the page shows is what that function wrote, so there is no
second rendering of a report to keep in step with the first.

A browser can be driven only where one is installed, so the counting, and
the comparison made inside a real browser, are `tools/browser_gates.py`'s,
run by CI's job for the page on the Python the page carries. What can be
held without a browser is held here: the page's Python against the command
on this interpreter, the comparison the gate makes and the counters it
trusts, the pins the build takes, and that one tree builds one page.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
from aas_core3 import jsonization, xmlization

from builders import hd_env

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "src" / "aas_submodel_validate" / "data" / "example" / "idta-02004-2.0.aasx"


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _page():
    """`browser/aas_page.py`, loaded from its file: it is the page's code and
    lives with the page."""
    return _module("aas_page", ROOT / "browser" / "aas_page.py")


def _command(argv, cwd):
    """The command from this tree at a UTF-8 console: both streams, as bytes,
    and the code it leaves by."""
    done = subprocess.run([sys.executable, "-m", "aas_submodel_validate", *argv],
                          cwd=str(cwd), capture_output=True, timeout=300,
                          env={**os.environ, "PYTHONPATH": str(ROOT / "src"),
                               "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
    return done.stdout, done.stderr, done.returncode


def _sources(tmp_path):
    """A judged package, a document refused, an XML environment, and a file
    whose name reads as an option."""
    made = tmp_path / "made"
    made.mkdir()
    (made / "broken.json").write_bytes(b"not json at all")
    environment = jsonization.environment_from_jsonable(hd_env())
    (made / "environment.xml").write_text(xmlization.to_str(environment), "utf-8")
    (made / "-W.aasx").write_bytes(EXAMPLE.read_bytes())
    return [EXAMPLE, made / "broken.json", made / "environment.xml", made / "-W.aasx"]


# -- what the page runs ------------------------------------------------------


@pytest.mark.parametrize("as_json", [False, True], ids=["text", "json"])
def test_the_page_runs_the_command_on_what_it_is_handed(tmp_path, as_json):
    page = _page()
    for source in _sources(tmp_path):
        argv, out, err, code = page.check(source.name, source.read_bytes(), as_json,
                                          room=str(tmp_path / "room"))
        assert argv == page.argv_for(source.name, as_json)
        assert (out, err, code) == _command(argv, source.parent), source.name


def test_a_name_that_reads_as_an_option_is_passed_as_a_file():
    page = _page()
    assert page.argv_for("-W.aasx", False)[-1] == "./-W.aasx"
    assert page.argv_for("plain.aasx", True) == ["--no-bundle", "-f", "json", "plain.aasx"]


@pytest.mark.parametrize("name", ["", ".", "..", "a/b.aasx", "a\0b.aasx"])
def test_what_is_not_a_file_name_is_refused_before_anything_is_written(tmp_path, name):
    room = tmp_path / "room"
    with pytest.raises(ValueError):
        _page().check(name, b"{}", False, room=str(room))
    assert not room.exists() or not any(room.iterdir())


def test_the_page_leaves_nothing_behind(tmp_path):
    room = tmp_path / "room"
    _page().check("environment.json", b"{}", False, room=str(room))
    assert not any(room.iterdir())


def test_the_page_reports_the_code_a_process_would_exit_with(tmp_path, monkeypatch):
    """`sys.exit(main(argv))` as the interpreter finishes it: argparse leaves
    by raising, a message given to SystemExit goes to stderr with 1, and a
    traceback is 1 with the traceback on stderr."""
    page = _page()
    from aas_submodel_validate import cli

    for raised, code, said in ((SystemExit(64), 64, b""), (SystemExit("stopped"), 1, b"stopped"),
                               (RuntimeError("broke"), 1, b"RuntimeError: broke")):
        def main(argv, raised=raised):
            raise raised
        monkeypatch.setattr(cli, "main", main)
        _, out, err, left = page.check("x.json", b"{}", False, room=str(tmp_path / "room"))
        assert left == code and said in err, (raised, left, err)


def test_the_versions_the_page_reports_are_what_decides_a_verdict():
    import aas_core3

    from aas_submodel_validate import __version__
    reported = _page().versions()
    assert reported == {"python": "%d.%d.%d" % sys.version_info[:3],
                        "aas_submodel_validate": __version__,
                        "aas_core3": aas_core3.__version__}
    json.dumps(reported)


# -- what the gate trusts ----------------------------------------------------


def _gates():
    return _module("browser_gates", ROOT / "tools" / "browser_gates.py")


def test_the_comparison_sees_a_difference_on_each_stream():
    gates = _gates()
    argv = ["--no-bundle", "x.aasx"]
    same = gates.Run(argv, b"report\n", b"note\n", 1)
    assert gates.differences(same, gates.Run(argv, b"report\n", b"note\n", 1)) == []
    for other, stream in ((gates.Run(argv, b"other\n", b"note\n", 1), "stdout"),
                          (gates.Run(argv, b"report\n", b"", 1), "stderr"),
                          (gates.Run(argv, b"report\n", b"note\n", 0), "exit code")):
        said = gates.differences(same, other)
        assert len(said) == 1 and said[0].startswith(stream), said


def test_two_runs_of_different_commands_are_not_compared():
    gates = _gates()
    said = gates.differences(gates.Run(["--no-bundle", "a"], b"", b"", 0),
                             gates.Run(["--no-bundle", "-f", "json", "a"], b"", b"", 0))
    assert len(said) == 1 and said[0].startswith("argv"), said


def test_a_counter_that_missed_the_control_is_blind_not_quiet():
    """A counter attached to the wrong thing reads zero, which is also what a
    page that sends nothing reads. So each counter is shown requests it has
    to see -- the page's own timing cannot see the worker's, nor the
    worker's the page's -- and one that misses them is named."""
    gates = _gates()
    assert gates.CONTROLS == {"browser": 2, "server": 2, "page timing": 1, "worker timing": 1}
    assert gates.blind(gates.CONTROLS, dict(gates.CONTROLS)) == []
    assert gates.blind(gates.CONTROLS, dict(gates.CONTROLS, **{"worker timing": 0})) == ["worker timing"]
    assert gates.blind(gates.CONTROLS, {}) == list(gates.CONTROLS)


class _Watched:
    """An open page as `judge` reads one, with what each counter saw."""

    def __init__(self, url, after_load=None, controls=None, downloads=()):
        self.url = url
        self.downloads = list(downloads)
        self.loaded = {}
        self._after = after_load or {}
        self._controls = controls

    def asked_while_loading(self):
        return [self.url]

    def since(self, mark):
        return {name: list(self._after.get(name, ())) for name in
                ("browser", "server", "page timing", "worker timing")}

    def controls(self, base):
        return (dict(_gates().CONTROLS) if self._controls is None else self._controls), {}


def _judged(gates, watched, todo, deep=True):
    problems = []
    if deep:
        todo = todo + [path.parent / name for path in todo[:1] for name in gates.DEEP]
    expected = {(path, as_json): gates.Run(["a"], b"", b"", 0)
                for path in todo for as_json in (False, True)}
    gates.judge(watched, "served", todo, expected, "http://127.0.0.1:1/", problems,
                run_page=lambda page, path: [gates.Run(["a"], b"", b"", 0)] * 2)
    return problems


def test_a_request_after_load_is_a_problem_named_by_the_counter_that_saw_it(tmp_path):
    gates = _gates()
    todo = [tmp_path / name for name in gates.DOORS]
    assert _judged(gates, _Watched("http://x/", {}), todo) == []
    problems = _judged(gates, _Watched("http://x/", {"worker timing": ["http://elsewhere/"]}), todo)
    assert any("request(s) after load" in line and "worker timing" in line for line in problems), problems


def test_a_blind_counter_fails_the_run_even_when_it_read_zero(tmp_path):
    gates = _gates()
    todo = [tmp_path / name for name in gates.DOORS]
    problems = _judged(gates, _Watched("http://x/", {}, controls=dict(gates.CONTROLS, server=0)), todo)
    assert any("server counter did not see the control" in line for line in problems), problems


def test_the_doors_have_to_be_among_the_files_checked(tmp_path):
    gates = _gates()
    todo = [tmp_path / name for name in gates.DOORS]
    assert len(gates.DOORS) >= 2
    for missing in gates.DOORS:
        problems = _judged(gates, _Watched("http://x/", {}), [p for p in todo if p.name != missing])
        assert any("reach the server" in line for line in problems), (missing, problems)


def test_the_documents_past_the_bound_have_to_be_among_the_files_checked(tmp_path):
    gates = _gates()
    todo = [tmp_path / name for name in gates.DOORS]
    problems = _judged(gates, _Watched("http://x/", {}), todo, deep=False)
    assert any("nested past the bound" in line for line in problems), problems


def test_a_document_nested_past_the_bound_is_refused_by_the_page_as_by_the_command(tmp_path):
    """The two documents the gate hands the browser, far past the bound:
    the page's Python refuses each as X5 and leaves by 2, the command's
    bytes exactly -- the browser's runtime, whose stack ran out on them
    first, is asked the same by the gate."""
    gates, page = _gates(), _page()
    for path in gates.deep(tmp_path / "deep"):
        for as_json in (False, True):
            argv, out, err, code = page.check(path.name, path.read_bytes(), as_json,
                                              room=str(tmp_path / "room"))
            assert (out, err, code) == _command(argv, path.parent), path.name
            assert code == 2 and b"X5" in out, (path.name, out[:200])


def test_the_gate_refuses_to_compare_across_interpreters():
    """Two patch releases of one minor version are two readers: a patch can
    change what the standard library's zipfile accepts. So the page's Python
    and the command's are compared to the patch, and each package exactly."""
    gates = _gates()
    page = {"python": "3.13.2", "aas_submodel_validate": "0.13.0", "aas_core3": "1.1.4"}
    assert gates.unlike(page, dict(page)) == []
    assert gates.unlike(page, dict(page, python="3.13.15")) == ["python"]
    assert gates.unlike(page, dict(page, aas_core3="1.1.5")) == ["aas_core3"]
    assert gates.unlike(page, dict(page, aas_submodel_validate="0.12.0")) == ["aas_submodel_validate"]


def test_every_corpus_input_and_every_official_sample_is_compared(tmp_path):
    """The population is the corpus the release notes measure -- every case
    that is a file; a path with nothing behind it cannot be handed to a page
    -- and every official sample this repository carries, each once."""
    gates = _gates()
    sys.path.insert(0, str(ROOT / "tools"))
    import verdict_diff

    into = tmp_path / "inputs"
    asked = gates.inputs(into)
    corpus = [Path(case.path) for case in verdict_diff.build_corpus(into)]
    samples = sorted(path for path in (ROOT / "tests" / "corpus" / "idta").rglob("*")
                     if path.suffix in (".aasx", ".json", ".xml"))
    assert samples, "no official sample to compare"
    assert asked == list(dict.fromkeys([path for path in corpus if path.is_file()] + samples))
    assert len(asked) >= 90


def test_the_doors_are_shut_to_the_command_and_it_is_asked_through_each(tmp_path):
    """Each door asks the reader to reach a server this test started: an
    external entity, a schema location, a relationship whose target is that
    server. The command is run on every one, and the server has to have
    been asked for nothing -- the same question the gate asks of the page."""
    gates = _gates()
    server = gates.Server(tmp_path / "page.html")
    try:
        made = gates.doors(tmp_path, server.base)
        assert sorted(path.name for path in made) == sorted(gates.DOORS)
        entity, schema, package = made
        # Each door is open: it names the server, the way a reader that
        # followed it would have to ask it.
        text = entity.read_text("utf-8")
        assert 'SYSTEM "%sdoor/entity"' % server.base in text and "&pull;" in text
        assert 'xsi:schemaLocation="https://admin-shell.io/aas/3/0 %sdoor/schema.xsd"' \
            % server.base in schema.read_text("utf-8")
        with zipfile.ZipFile(package) as archive:
            declared = b"".join(archive.read(name) for name in archive.namelist()
                                if name.endswith(".rels"))
        assert ('Target="%sdoor/relationship"' % server.base).encode() in declared
        assert b'TargetMode="External"' in declared
        for path in made:
            out, err, code = _command(["--no-bundle", path.name], path.parent)
            assert code in (0, 1, 2), (path.name, code, err)
        assert server.count() == 0, server.since(0)
    finally:
        server.close()


# -- what the page is built from ---------------------------------------------

HEX = re.compile(r"[0-9a-f]{64}")
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _builder():
    return _module("build_browser", ROOT / "tools" / "build_browser.py")


def test_the_runtime_is_the_one_this_repository_names():
    runtime = _builder().RUNTIME
    assert runtime["name"] == "Pyodide" and HEX.fullmatch(runtime["sha256"])
    assert runtime["url"].endswith("/pyodide-core-%s.tar.bz2" % runtime["version"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", runtime["python"]), "the Python to the patch"


def test_what_the_runtime_ships_apart_is_carried_as_its_lock_file_pins_it():
    """The engine imports `lzma` at its top -- a part of a package compressed
    with LZMA is read like any other -- and the runtime keeps that module out
    of its standard library, as a package of its own. Carried, then, at the
    digest the runtime's own lock file gives it; left out, the page would
    not start, and made optional, it would judge such a package differently
    from the command."""
    build = _builder()
    (entry,) = build.RUNTIME_PACKAGES
    assert entry["name"] == "lzma" and HEX.fullmatch(entry["sha256"])
    assert entry["url"].endswith("/" + entry["file"])
    assert "/v%s/" % build.RUNTIME["version"] in entry["url"]
    container = (ROOT / "src" / "aas_submodel_validate" / "container.py").read_text("utf-8")
    assert re.search(r"(?m)^import lzma$", container), "nothing imports it; it need not travel"


def test_every_wheel_the_page_carries_is_pinned_exactly():
    """The commit decides the bytes: a version, a file and its digest, and
    no resolver between the pin and the page."""
    build = _builder()
    (wheel,) = build.WHEELS
    assert wheel["name"] == "aas-core3.0" and HEX.fullmatch(wheel["sha256"])
    assert wheel["url"].endswith("/aas_core3_0-%s-py3-none-any.whl" % wheel["version"])
    declared = re.search(r'"aas-core3\.0>=([\d.]+),<(\d+)"',
                         (ROOT / "pyproject.toml").read_text("utf-8"))
    floor, ceiling = declared.groups()
    pinned = tuple(int(n) for n in wheel["version"].split("."))
    assert tuple(int(n) for n in floor.split(".")) <= pinned < (int(ceiling),)


#: What the runtime has compiled into it, by the names its notices go by:
#: Pyodide and the hiwire it builds in; CPython and what CPython
#: incorporates, HACL* among it; libffi, bzip2 and musl, and the Emscripten
#: that built the rest; and liblzma, inside the lzma package the engine
#: needs.
COMPILED_IN = ("Pyodide", "hiwire", "CPython", "CPython incorporates", "HACL*", "libffi",
               "bzip2", "Emscripten", "musl", "liblzma")


def test_the_page_carries_the_notice_of_everything_compiled_into_its_runtime():
    notices = {entry["notice"] for entry in _builder().RUNTIME_LICENCES}
    missing = [name for name in COMPILED_IN if name not in notices]
    assert not missing, "the page prints no notice for %s" % missing


def test_every_notice_the_page_prints_is_pinned_at_a_revision():
    """Fetched at a tag or a commit and held to a digest, as the runtime is:
    a branch would print whatever the file says on the day of the build."""
    for entry in _builder().RUNTIME_LICENCES:
        assert HEX.fullmatch(entry["sha256"]), entry["notice"]
        assert "/%s/" % entry["revision"] in entry["url"], (entry["notice"], entry["url"])
        assert entry["revision"] in entry["source"], (entry["notice"], entry["source"])


def test_third_party_names_each_notice_the_page_prints_at_its_revision():
    text = (ROOT / "THIRD_PARTY.md").read_text("utf-8")
    build = _builder()
    for entry in build.RUNTIME_LICENCES:
        assert entry["notice"] in text and "`%s`" % entry["revision"] in text, entry["notice"]
    for pinned in (build.RUNTIME["sha256"], build.RUNTIME_PACKAGES[0]["sha256"],
                   build.WHEELS[0]["sha256"]):
        assert pinned in text, pinned


def test_a_notice_kept_in_a_source_file_is_cut_to_the_notice():
    source = b"/* MIT License\n *\n * Permission is hereby granted ... */\n\nint f(void) { return 0; }\n"
    cut = _builder().notice_text(source, ("/* MIT License", "*/"))
    assert cut.startswith("/* MIT License") and cut.endswith("*/") and "int f" not in cut


def test_each_place_in_the_page_is_filled_exactly_once():
    build = _builder()
    fills = dict.fromkeys(build.MARKS, "x")
    page = "".join(build.MARKS)
    assert build.assemble(page, fills) == "x" * len(build.MARKS)
    with pytest.raises(SystemExit):
        build.assemble(page + build.MARKS[0], fills)
    with pytest.raises(SystemExit):
        build.assemble(page.replace(build.MARKS[-1], ""), fills)
    with pytest.raises(SystemExit):
        build.assemble(page, dict(fills, **{build.MARKS[0]: build.MARKS[1]}))


def test_nothing_put_in_a_script_block_can_end_it():
    build = _builder()
    assert build.script_safe("let a = 1 < 2;", "it") == "let a = 1 < 2;"
    for text in ("</script>", "</SCRIPT", "<!-- x"):
        with pytest.raises(SystemExit):
            build.script_safe(text, "it")


def test_the_page_is_built_from_files_that_are_here():
    build = _builder()
    template = (ROOT / "browser" / "page.html").read_text("utf-8")
    assert all(template.count(mark) == 1 for mark in build.MARKS)
    assert (ROOT / "browser" / "worker.js").is_file()
    assert (ROOT / "browser" / "aas_page.py").is_file()


def _fakes(build, monkeypatch):
    """Every download the build makes, answered with bytes made here and
    pinned at their own digests, so that nothing is fetched."""
    def tarball():
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w:bz2") as tar:
            for name in build.RUNTIME_FILES:
                data = (json.dumps({"packages": {"lzma": {
                    "file_name": build.RUNTIME_PACKAGES[0]["file"],
                    "sha256": hashlib.sha256(b"lzma wheel").hexdigest()}}}).encode()
                        if name == "pyodide-lock.json" else ("fake %s" % name).encode())
                info = tarfile.TarInfo("pyodide/" + name)
                info.size, info.mtime = len(data), 0
                tar.addfile(info, io.BytesIO(data))
        return raw.getvalue()

    def wheel():
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as z:
            z.writestr("aas_core3/__init__.py", "__version__ = 'fake'\n")
            z.writestr("aas_core3_0-fake.dist-info/licenses/LICENSE", "MIT fake\n")
            z.writestr("aas_core3_0-fake.dist-info/licenses/AUTHORS", "someone\n")
            z.writestr("dev_scripts/build.py", "import subprocess\n")
        return raw.getvalue()

    answers = {build.RUNTIME["url"]: tarball(),
               build.RUNTIME_PACKAGES[0]["url"]: b"lzma wheel",
               build.WHEELS[0]["url"]: wheel()}
    answers.update({entry["url"]: ("/* MIT License notice of %s */ code" % entry["notice"]).encode()
                    for entry in build.RUNTIME_LICENCES})
    monkeypatch.setattr(build, "RUNTIME", dict(build.RUNTIME, sha256=hashlib.sha256(
        answers[build.RUNTIME["url"]]).hexdigest()))
    monkeypatch.setattr(build, "RUNTIME_PACKAGES", tuple(
        dict(entry, sha256=hashlib.sha256(answers[entry["url"]]).hexdigest())
        for entry in build.RUNTIME_PACKAGES))
    monkeypatch.setattr(build, "WHEELS", tuple(
        dict(entry, sha256=hashlib.sha256(answers[entry["url"]]).hexdigest())
        for entry in build.WHEELS))
    monkeypatch.setattr(build, "RUNTIME_LICENCES", tuple(
        dict(entry, sha256=hashlib.sha256(answers[entry["url"]]).hexdigest())
        for entry in build.RUNTIME_LICENCES))
    monkeypatch.setattr(build, "download", lambda url: answers[url])


def test_one_tree_builds_one_page(tmp_path, monkeypatch):
    """Two builds of one tree from the same pinned bytes are the same bytes:
    the archive's members in name order with one timestamp, the compression
    with no clock in it."""
    build = _builder()
    _fakes(build, monkeypatch)
    first = build.build(tmp_path / "one.html")
    second = build.build(tmp_path / "two.html")
    assert first == second and (tmp_path / "one.html").read_bytes() == first
    assert b"MIT fake" in first, "the wheel's own licence is not in the page"
    for entry in build.RUNTIME_LICENCES:
        assert ("notice of %s" % entry["notice"]).encode() in first, entry["notice"]


def test_a_download_that_is_not_the_pinned_bytes_is_refused(tmp_path, monkeypatch):
    build = _builder()
    _fakes(build, monkeypatch)
    real = build.download
    monkeypatch.setattr(build, "download", lambda url: real(url) + (
        b"!" if url == build.WHEELS[0]["url"] else b""))
    with pytest.raises(SystemExit) as refused:
        build.build(tmp_path / "page.html")
    assert "sha256" in str(refused.value)
    assert not (tmp_path / "page.html").exists()


def test_the_runtime_package_has_to_be_the_one_its_lock_file_names(tmp_path, monkeypatch):
    """The lzma package is pinned here and named in the runtime's lock file;
    the two have to agree, or the page carries a package its runtime would
    not have loaded."""
    build = _builder()
    _fakes(build, monkeypatch)
    monkeypatch.setattr(build, "RUNTIME_PACKAGES", tuple(
        dict(entry, file="lzma-other.whl") for entry in build.RUNTIME_PACKAGES))
    with pytest.raises(SystemExit) as refused:
        build.build(tmp_path / "page.html")
    assert "lock" in str(refused.value)


def test_what_the_page_carries_leaves_the_maintainers_scripts_behind(tmp_path, monkeypatch):
    build = _builder()
    _fakes(build, monkeypatch)
    page = build.build(tmp_path / "page.html").decode("utf-8")
    archive = re.search(r'data-asset="app.zip">([^<]+)<', page).group(1)
    names = zipfile.ZipFile(io.BytesIO(gzip.decompress(base64.b64decode(archive)))).namelist()
    assert "aas_page.py" in names and "aas_core3/__init__.py" in names
    assert not [name for name in names if name.startswith("dev_scripts/")], names
    assert "aas_submodel_validate/cli.py" in names


def test_the_job_runs_the_page_on_the_python_it_carries():
    """Two patch releases are two readers, so the job that compares the
    page with the command runs the command on the patch the page carries,
    with the wheel the page carries and the browser the gate was written
    against -- and builds the page twice, comparing the two."""
    build, gates = _builder(), _gates()
    text = WORKFLOW.read_text("utf-8")
    job = text[text.index("  the-page-this-repo-offers:"):]
    job = job[:job.index("\n  # ", 1)] if "\n  # " in job[1:] else job
    assert 'python-version: "%s"' % build.RUNTIME["python"] in job
    assert '"aas-core3.0==%s"' % build.WHEELS[0]["version"] in job
    assert '"playwright==%s"' % gates.PLAYWRIGHT in job
    assert job.count("tools/build_browser.py") >= 2 and "cmp " in job
    assert "tools/browser_gates.py" in job

