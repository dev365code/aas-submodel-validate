"""The library is a way in, and it reaches the verdict the others reach.

Two ways in judged a file until now -- the command line and the single
file -- and a program that wanted the verdict ran the first and parsed what
it printed. That works, and it leaves every caller re-deriving the exit
code from a report this tool had already judged, by rules copied off the
help page. `validate` is the judgement those two make, called from Python,
and `exit_code` is the number they leave by.

It is not a second engine. The command line calls these two functions, so
most of what follows is a statement that every entrance still says one
thing: about every input in the corpus, under every flag that moves a
verdict, the bytes `smtv -f json` prints and the code it leaves by are the
bytes and the number the library gives. Bytes and an open file are judged
as the path they were read from. And the line the command line draws
between exit 2 and exit 64 -- your file could not be judged, you called
this wrong -- is drawn here between a report and a Python exception.
"""
from __future__ import annotations

import ast
import contextlib
import inspect
import io
import json
import os
import pathlib
import pkgutil
import re
import subprocess
import sys

import pytest
from aas_core3 import jsonization, xmlization

import aas_submodel_validate as api
from aas_submodel_validate import __version__, cli, container, tablegen
from aas_submodel_validate.rules import profiles
from aas_submodel_validate.rules.battery import settles_only
from builders import build_aasx

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verdict_diff  # noqa: E402

RELEASED = ROOT / "tests" / "released_api.txt"
README = (ROOT / "README.md").read_text(encoding="utf-8")
EXAMPLE = ROOT / "src" / "aas_submodel_validate" / "data" / "example" / "idta-02004-2.0.aasx"

#: What the command line is asked, and what asks the same of the library:
#: the flags that move the report are keywords of `validate`, and the two
#: that move only the exit code are keywords of `exit_code` -- the split
#: `docs/report-schema.md` draws when it says which options a report
#: records. Every profile key the parser accepts, the settle-only one too.
ASKED = ([((), {}, {}),
          (("--allow-unmatched",), {"allow_unmatched": True}, {}),
          (("--meta", "info"), {"meta": "info"}, {}),
          (("--meta", "error"), {"meta": "error"}, {}),
          (("--strict-meta",), {"meta": "error"}, {}),
          (("-W",), {}, {"warnings_as_errors": True}),
          (("--require-all-judged",), {}, {"require_all_judged": True})]
         + [(("--profile", key), {"profile": key}, {})
            for key in profiles.KEYS + settles_only()])


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    return verdict_diff.build_corpus(tmp_path_factory.mktemp("corpus"))


@pytest.fixture(scope="module")
def xml_inputs(corpus, tmp_path_factory):
    """What the XML reader is handed. The corpus holds no XML -- it is
    JSON and packages -- so every environment in it that the metamodel
    library reads is written out again as XML, with one bare submodel and
    three documents the reader refuses for three different reasons."""
    into = tmp_path_factory.mktemp("xml")
    made, bare = [], None
    for index, case in enumerate(corpus):
        path = pathlib.Path(case.path)
        if path.suffix.lower() != ".json" or case.template is not None:
            continue
        try:
            environment = jsonization.environment_from_jsonable(
                json.loads(path.read_bytes().decode("utf-8-sig")))
        except Exception:  # noqa: BLE001 - a corpus input meant to be broken
            continue
        twin = into / ("%02d-%s.xml" % (index, path.stem))
        twin.write_text(xmlization.to_str(environment), "utf-8")
        made.append(twin)
        if bare is None and environment.submodels:
            bare = environment.submodels[0]
    assert made and bare is not None, "no corpus environment to write as XML"
    (into / "bare-submodel.xml").write_text(xmlization.to_str(bare), "utf-8")
    (into / "not-xml.xml").write_bytes(b"<environment")
    (into / "declares-a-doctype.xml").write_bytes(
        b'<?xml version="1.0"?><!DOCTYPE environment>'
        b'<environment xmlns="https://admin-shell.io/aas/3/0"/>')
    (into / "another-edition.xml").write_bytes(
        b'<environment xmlns="https://admin-shell.io/aas/2/0"/>')
    return made + [into / name for name in ("bare-submodel.xml", "not-xml.xml",
                                            "declares-a-doctype.xml",
                                            "another-edition.xml")]


def _smtv(*argv):
    """What `smtv` prints on stdout and the code it leaves by, run here."""
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed), contextlib.redirect_stderr(io.StringIO()):
        code = cli.main(list(argv))
    return printed.getvalue(), code


def _as_smtv_prints(report) -> str:
    return json.dumps(report.as_dict(), indent=2) + "\n"


# -- one verdict, whichever way in ------------------------------------------


def test_every_corpus_input_reads_the_same_from_the_library_as_from_smtv(corpus):
    """The gate this entrance stands on: no input, no flag, one byte apart.

    A refused template is the one case with no report on either side --
    the command line prints nothing and leaves by 2, the library raises --
    and it is compared as exactly that rather than skipped.
    """
    differ, left_by = [], set()
    for case in corpus:
        for flags, asked, exit_asked in ASKED:
            argv = [str(case.path), "-f", "json", *flags]
            kwargs = dict(asked)
            if case.template is not None:
                argv += ["--template", str(case.template)]
                kwargs["template"] = str(case.template)
            printed, code = _smtv(*argv)
            try:
                report = api.validate(str(case.path), **kwargs)
            except api.TemplateRefused:
                said, left = "", 2
            else:
                said, left = _as_smtv_prints(report), api.exit_code(report, **exit_asked)
            left_by.add(code)
            if (said, left) != (printed, code):
                differ.append("%s [%s]: smtv left by %d, the library by %d%s"
                              % (case.label, " ".join(flags) or "no flag", code, left,
                                 "" if said == printed else ", and the reports differ"))
    assert not differ, "\n".join(differ)
    # Not a comparison of three passes: each code this entrance can give
    # is among the ones compared.
    assert left_by == {0, 1, 2}, left_by


def test_a_separate_process_prints_what_the_library_returns(corpus):
    """The comparison above runs the command line inside this interpreter,
    beside the library it is compared with. A difference that only a fresh
    process has -- how the package is found, what `-m` imports first --
    would pass there, so three inputs go through `python -m` as well: a
    clean read, one with a template, and one nothing was judged in."""
    unjudged = next(case for case in corpus
                    if case.template is None and not api.validate(str(case.path)).judged)
    templated = next(case for case in corpus if case.template is not None)
    for case in (corpus[0], templated, unjudged):
        argv = [sys.executable, "-m", "aas_submodel_validate", str(case.path), "-f", "json"]
        kwargs = {}
        if case.template is not None:
            argv += ["--template", str(case.template)]
            kwargs["template"] = str(case.template)
        run = subprocess.run(argv, capture_output=True, text=True,
                             env={**os.environ, "PYTHONPATH": str(ROOT / "src"),
                                  "PYTHONIOENCODING": "utf-8"})
        try:
            report = api.validate(str(case.path), **kwargs)
        except api.TemplateRefused:
            assert (run.stdout, run.returncode) == ("", 2), case.label
            continue
        assert run.stdout == _as_smtv_prints(report), case.label
        assert run.returncode == api.exit_code(report), case.label


def test_bytes_and_an_open_file_are_judged_as_the_file_they_were_read_from(corpus, xml_inputs):
    """A browser page has bytes and no path; a caller holding a download has
    an open stream. Each is judged as the file it came from, given that
    file's name: the same report, key for key, refusals included."""
    inputs = ([(pathlib.Path(case.path), case.template) for case in corpus]
              + [(path, None) for path in xml_inputs])
    differ, compared = [], set()
    for path, template in inputs:
        if not path.is_file():
            # Nothing behind the name, or not a file: a question only a
            # path can ask, and bytes have no answer to it.
            continue
        kwargs = {} if template is None else {"template": str(template)}
        data, form = path.read_bytes(), path.suffix[1:].lower()
        try:
            want = api.validate(str(path), **kwargs).as_dict()
        except api.TemplateRefused:
            with pytest.raises(api.TemplateRefused):
                api.validate(data, format=form, name=str(path), **kwargs)
            continue
        given = {
            "bytes": api.validate(data, format=form, name=str(path), **kwargs),
            "a bytearray": api.validate(bytearray(data), format=form, name=str(path), **kwargs),
            "a memoryview": api.validate(memoryview(data), format=form, name=str(path), **kwargs),
        }
        with path.open("rb") as handle:
            given["an open file"] = api.validate(handle, **kwargs)
        differ += ["%s, as %s" % (path.name, how)
                   for how, report in given.items() if report.as_dict() != want]
        compared.add((form, want["summary"]["judged"]))
    assert not differ, "\n".join(differ)
    # Each reader, on an input it judged and on one it refused.
    assert compared == {(form, judged) for form in ("aasx", "json", "xml")
                        for judged in (True, False)}, sorted(compared)


def test_bytes_nobody_named_are_called_so_in_the_report():
    data = EXAMPLE.read_bytes()
    assert api.validate(data, format="aasx").as_dict()["path"] == "<bytes>"
    assert api.validate(io.BytesIO(data), format="aasx").as_dict()["path"] == "<bytes>"
    # And the name, when there is one, is all that changes.
    named = api.validate(data, format="aasx", name="from-the-supplier.aasx").as_dict()
    unnamed = api.validate(data, format="aasx").as_dict()
    assert named.pop("path") == "from-the-supplier.aasx"
    unnamed.pop("path")
    assert named == unnamed


def test_an_open_file_is_typed_by_the_name_it_was_opened_under(tmp_path):
    """No format given, the file's own name decides -- the way a path's
    extension does at the command line, and with the same answer when the
    extension is not one this reader reads."""
    unknown = tmp_path / "environment.txt"
    unknown.write_bytes(b"{}")
    with unknown.open("rb") as handle:
        report = api.validate(handle)
    assert report.as_dict() == api.validate(str(unknown)).as_dict()
    assert not report.judged and api.exit_code(report) == 2


def test_bytes_over_the_bound_are_refused_as_the_same_file_on_disk_is(tmp_path, monkeypatch):
    """The bounds a path is read under are the bounds bytes are read under.
    Lowered here so that nothing has to weigh 64 MiB to show it."""
    monkeypatch.setattr(container, "MAX_PART_BYTES", 1024)
    document = json.dumps({"submodels": [], "padding": "x" * 2048}).encode("utf-8")
    bare = tmp_path / "large.json"
    bare.write_bytes(document)
    packaged = build_aasx(tmp_path / "large.aasx", payload=document)
    for path in (bare, pathlib.Path(packaged)):
        want = api.validate(str(path)).as_dict()
        assert "X5" in {finding["rule"] for finding in want["findings"]}, path.name
        got = api.validate(path.read_bytes(), format=path.suffix[1:], name=str(path))
        assert got.as_dict() == want, path.name
        assert api.exit_code(got) == 2


def test_each_keyword_reaches_the_engine_and_is_recorded_as_asked(tmp_path):
    """The comparison with the command line cannot see a keyword the library
    drops on its way to the engine: the command line calls the library and
    would drop the flag the same way, one byte in step. So each keyword is
    held to the record the report keeps of what was asked, and to what the
    flag is documented to do."""
    report = api.validate(str(EXAMPLE), meta="info", allow_unmatched=True, profile="02004")
    assert report.as_dict()["options"] == {"profile": "02004", "meta": "info",
                                           "strictMeta": False, "allowUnmatched": True}
    # `--allow-unmatched` turns "no template matched" into a note.
    unknown = json.dumps({"submodels": [{"modelType": "Submodel", "id": "urn:example:unknown",
                                         "idShort": "Unknown"}]}).encode("utf-8")
    refused = {f["rule"] for f in api.validate(unknown, format="json").as_dict()["findings"]}
    allowed = api.validate(unknown, format="json", allow_unmatched=True)
    assert "SMT-D1" in refused
    assert "SMT-D1" not in {f["rule"] for f in allowed.as_dict()["findings"]}
    assert any("(allowed)" in note for note in allowed.notes)
    # `--template` is recorded where the report says whose table judged.
    template = api.validate(str(EXAMPLE), template=str(_a_template(tmp_path)))
    assert template.as_dict()["provenance"]["template"]["published"] is False


def _a_template(tmp_path):
    """The smallest template this reader builds a table from: one submodel
    of kind Template with one identified element."""
    path = tmp_path / "template.json"
    path.write_text(json.dumps({"submodels": [{
        "modelType": "Submodel", "kind": "Template", "id": "urn:example:template",
        "idShort": "Example",
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference", "value": "urn:example:template"}]},
        "submodelElements": [{
            "modelType": "Property", "idShort": "Thing", "valueType": "xs:string",
            "semanticId": {"type": "ExternalReference",
                           "keys": [{"type": "GlobalReference", "value": "urn:example:thing"}]}}],
    }]}), "utf-8")
    return path


# -- the line between a report and an exception -----------------------------


def test_what_cannot_be_judged_comes_back_as_a_report_that_leaves_by_2(tmp_path):
    """Exit 2 at the command line, and a report beside it saying what was
    refused. Here too: never an exception, because nothing about the call
    was wrong -- the file was."""
    reports = {
        "a path with nothing behind it": api.validate(str(tmp_path / "absent.json")),
        "a directory": api.validate(str(tmp_path)),
        "bytes that are not JSON": api.validate(b"{", format="json"),
        "bytes that are not an archive": api.validate(b"PK, and then nothing", format="aasx"),
        "bytes that are not XML": api.validate(b"<environment", format="xml"),
    }
    for how, report in reports.items():
        assert not report.judged, how
        assert report.as_dict()["findings"], "%s: nothing says what was refused" % how
        assert api.exit_code(report) == 2, how
        # Whatever else was asked: 1 is the code for a verdict.
        assert api.exit_code(report, warnings_as_errors=True,
                             require_all_judged=True) == 2, how


def test_a_refused_template_raises_the_class_smtv_leaves_by_2_on(tmp_path):
    assert api.TemplateRefused is tablegen.TemplateRefused
    # Not a kind of TypeError or ValueError: those are the exceptions for a
    # call made wrong, and a template that is not one is not that.
    assert not issubclass(api.TemplateRefused, (TypeError, ValueError))
    not_a_template = tmp_path / "not-a-template.json"
    not_a_template.write_text("[]", "utf-8")
    with pytest.raises(api.TemplateRefused):
        api.validate(str(EXAMPLE), template=str(not_a_template))
    assert _smtv(str(EXAMPLE), "-f", "json", "--template", str(not_a_template)) == ("", 2)


#: A call made wrong, and the exception it raises: TypeError for the kind
#: of thing passed, ValueError for a value outside the choices. The command
#: line answers each of these with 64 before it reads a byte.
MISTAKES = [
    ("bytes with no format", lambda: api.validate(b"{}"), ValueError),
    ("a format there is no reader for", lambda: api.validate(b"{}", format="pdf"), ValueError),
    ("a format in capitals", lambda: api.validate(b"{}", format="JSON"), ValueError),
    ("a format beside a path", lambda: api.validate(str(EXAMPLE), format="aasx"), ValueError),
    ("a name beside a path", lambda: api.validate(str(EXAMPLE), name="other.aasx"), ValueError),
    ("an open file with no name and no format",
     lambda: api.validate(io.BytesIO(b"{}")), ValueError),
    ("a meta level there is none of", lambda: api.validate(str(EXAMPLE), meta="loud"), ValueError),
    ("meta as a flag rather than a level", lambda: api.validate(str(EXAMPLE), meta=True), ValueError),
    ("a profile there is none of", lambda: api.validate(str(EXAMPLE), profile="02099"), ValueError),
    ("a number for an input", lambda: api.validate(4), TypeError),
    ("nothing for an input", lambda: api.validate(None), TypeError),
    ("a file opened as text", lambda: api.validate(io.StringIO("{}"), format="json"), TypeError),
    ("a name that is not a string", lambda: api.validate(b"{}", format="json", name=4), TypeError),
    ("allow_unmatched as a word", lambda: api.validate(str(EXAMPLE), allow_unmatched="yes"),
     TypeError),
    ("a template that is not a path", lambda: api.validate(str(EXAMPLE), template=4), TypeError),
    ("a keyword there is none of", lambda: api.validate(str(EXAMPLE), strict_meta=True),
     TypeError),
    ("an option passed by position", lambda: api.validate(str(EXAMPLE), "aasx"), TypeError),
    ("exit_code of something that is not a report", lambda: api.exit_code({"ok": True}),
     TypeError),
    ("warnings_as_errors as a number",
     lambda: api.exit_code(api.validate(str(EXAMPLE)), warnings_as_errors=1), TypeError),
    ("list_rules at a level there is none of", lambda: api.list_rules(meta="loud"), ValueError),
]


@pytest.mark.parametrize("call, raised", [(call, raised) for _, call, raised in MISTAKES],
                         ids=[name for name, _, _ in MISTAKES])
def test_a_call_made_wrong_raises_rather_than_reports(call, raised):
    with pytest.raises(raised):
        call()


def test_a_profile_there_is_none_of_is_refused_where_the_engine_would_ignore_it():
    """The engine does not check the key: `runner.run(profile=...)` with a
    key no pair publishes judged as though none were given, and only the
    parser's `choices` stood between that and the command line. The
    library has no parser in front of it, so it checks."""
    assert _smtv_refuses("--profile", "02099")
    with pytest.raises(ValueError):
        api.validate(str(EXAMPLE), profile="02099")
    for key in profiles.KEYS + settles_only():
        api.validate(str(EXAMPLE), profile=key)


def _smtv_refuses(*flags) -> bool:
    with contextlib.redirect_stderr(io.StringIO()), pytest.raises(SystemExit) as left:
        cli.main([str(EXAMPLE), *flags])
    return left.value.code == cli.EXIT_USAGE


def test_require_all_judged_fails_an_input_with_nothing_to_judge():
    report = api.validate(b'{"submodels": []}', format="json", allow_unmatched=True)
    assert report.judged
    assert api.exit_code(report) == _smtv_code(b'{"submodels": []}', "--allow-unmatched")
    assert api.exit_code(report, require_all_judged=True) == _smtv_code(
        b'{"submodels": []}', "--allow-unmatched", "--require-all-judged") == 1


def _smtv_code(document: bytes, *flags) -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as into:
        path = pathlib.Path(into) / "environment.json"
        path.write_bytes(document)
        return _smtv(str(path), "-q", *flags)[1]


# -- the rest of what smtv answers ------------------------------------------


@pytest.mark.parametrize("meta", [None, "error", "warning", "info"])
def test_list_rules_is_the_listing_smtv_rules_prints(meta):
    printed, code = _smtv("--rules", *(() if meta is None else ("--meta", meta)))
    listed = api.list_rules(**({} if meta is None else {"meta": meta}))
    assert code == 0
    assert all(set(rule) == {"id", "kind", "severity", "title"} for rule in listed)
    assert all(isinstance(value, str) for rule in listed for value in rule.values())
    assert printed == "".join("%-8s %-9s %-10s %s\n" % (rule["id"], rule["kind"],
                                                       rule["severity"], rule["title"])
                              for rule in listed)


def test_example_path_is_the_file_smtv_example_judges():
    """A real path, so that `validate(example_path())` works as written. The
    command line names the example by its file name, having been given no
    path; the library reports the path it was handed. Nothing else moves."""
    path = api.example_path()
    assert isinstance(path, pathlib.Path) and path.is_file()
    printed, code = _smtv("--example", "-f", "json")
    shown, judged = json.loads(printed), api.validate(path)
    got = judged.as_dict()
    assert shown.pop("path") == "idta-02004-2.0.aasx"
    assert got.pop("path") == str(path)
    assert got == shown
    assert api.exit_code(judged) == code


# -- the surface, held ------------------------------------------------------

#: Every flag `smtv` defines, by what it asks. The first two map onto the
#: library's keywords; the third says why a flag has no keyword.
REPORT_FLAGS = {"--meta": "meta", "--strict-meta": "meta", "--allow-unmatched": "allow_unmatched",
                "--profile": "profile", "--template": "template"}
EXIT_FLAGS = {"--warnings-as-errors": "warnings_as_errors",
              "--require-all-judged": "require_all_judged"}
NOT_A_KEYWORD = {
    "path": "the input, which is validate's first argument",
    "--format": "how a report is shown; Report.as_dict() is the JSON",
    "--quiet": "what is shown",
    "--show-meta": "what is shown",
    "--example": "example_path()",
    "--rules": "list_rules()",
    "--bug-report": "the diagnostic bundle, which an entrance writes",
    "--note": "the diagnostic bundle",
    "--bundle-out": "the diagnostic bundle",
    "--show-bundle": "the diagnostic bundle",
    "--no-bundle": "the diagnostic bundle",
    "--version": "__version__",
}


def _flags_smtv_defines() -> set:
    """Each `add_argument` in `cli.py`, by its long name -- read from the
    parser's own definitions, so a flag added there is a flag seen here."""
    tree = ast.parse(pathlib.Path(cli.__file__).read_text(encoding="utf-8"))
    flags = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"):
            names = [a.value for a in node.args
                     if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            flags.add(([n for n in names if n.startswith("--")] or names)[0])
    return flags


def test_every_flag_smtv_takes_is_a_keyword_of_the_library_or_says_why_not():
    flags = _flags_smtv_defines()
    accounted = set(REPORT_FLAGS) | set(EXIT_FLAGS) | set(NOT_A_KEYWORD)
    assert flags == accounted, ("flags with no line here: %s; lines with no flag: %s"
                                % (sorted(flags - accounted), sorted(accounted - flags)))
    asked = set(inspect.signature(api.validate).parameters) - {"source", "format", "name"}
    assert asked == set(REPORT_FLAGS.values())
    assert set(inspect.signature(api.exit_code).parameters) - {"report"} == set(EXIT_FLAGS.values())


def test_the_command_line_judges_through_the_library():
    """One road. A command line that called the engine itself could drift
    from the library without a single verdict in the corpus moving, until
    the day one did."""
    tree = ast.parse(pathlib.Path(cli.__file__).read_text(encoding="utf-8"))
    called = {ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    assert "runner.run" not in called
    assert {"api.validate", "api.exit_code"} <= called, sorted(c for c in called if "api" in c)


def _released():
    return [line for line in RELEASED.read_text("utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def _written(function, *, method: bool = False) -> str:
    """A signature as `released_api.txt` writes one: names, defaults and
    where the keywords start, and no annotations."""
    parameters = list(inspect.signature(function).parameters.values())
    if method:
        parameters = parameters[1:]
    words, starred = [], False
    for parameter in parameters:
        if parameter.kind is parameter.KEYWORD_ONLY and not starred:
            words.append("*")
            starred = True
        words.append(parameter.name if parameter.default is parameter.empty
                     else "%s=%r" % (parameter.name, parameter.default))
    return "(%s)" % ", ".join(words)


def test_the_root_exports_what_released_api_txt_lists_and_nothing_else():
    lines = _released()
    assert lines, "the released list is empty; this test is checking nothing"
    owners = []
    for line in lines:
        owner = re.match(r"[A-Za-z_]\w*", line).group(0)
        if owner not in owners:
            owners.append(owner)
    assert sorted(api.__all__) == sorted(owners), (
        "the root exports %s and the released list names %s"
        % (sorted(api.__all__), sorted(owners)))
    report = api.validate(str(EXAMPLE))
    for line in lines:
        found = re.fullmatch(r"([A-Za-z_]\w*)(?:\.(\w+))?(\(.*\))?", line)
        assert found, "a line this test cannot read: %r" % line
        owner, member, call = found.groups()
        if member is None and call is not None:
            assert _written(getattr(api, owner)) == call, line
        elif member is None:
            exposed = getattr(api, owner)
            assert inspect.isclass(exposed) and issubclass(exposed, Exception), line
        elif call is not None:
            assert _written(getattr(getattr(api, owner), member), method=True) == call, line
            assert isinstance(getattr(report, member)(), dict), line
        else:
            assert isinstance(getattr(report, member), bool), line


def test_the_released_api_list_says_which_release_it_was_written_for():
    header = RELEASED.read_text("utf-8").split("\n", 1)[0]
    found = re.search(r"written for v(\d+)\.(\d+)\.(\d+)\.$", header)
    assert header.startswith("#") and found, header
    assert tuple(map(int, found.groups())) <= tuple(map(int, __version__.split("."))), header


def test_no_root_name_is_also_the_name_of_a_module_beneath_it():
    """`from aas_submodel_validate import x` asks the root for an attribute
    first and the import system second. A public name that is also a module
    beneath the root is one of two objects, depending on whether something
    imported that module first -- the reason the rule listing is
    `list_rules` and not `rules`, which is a package here."""
    beneath = {module.name for module in pkgutil.iter_modules(api.__path__)}
    assert not beneath & set(api.__all__), sorted(beneath & set(api.__all__))


def test_importing_the_package_does_not_import_the_engine():
    """Python runs the root's `__init__` before any module beneath it, and
    the single-file builder imports one of those in an environment that
    holds only this source tree -- it is the tool that fetches the one
    dependency. With the library's names imported in `__init__`, that took
    aas-core3.0 with it, and the builder died in CI before it could fetch
    anything. The names are imported when they are first asked for, and
    the version is readable with nothing installed."""
    script = "\n".join([
        "import sys",
        "import aas_submodel_validate, aas_submodel_validate._terminal",
        "print(aas_submodel_validate.__version__)",
        "print(sorted(name for name in sys.modules if name.split('.')[0] == 'aas_core3'"
        " or name in ('aas_submodel_validate.api', 'aas_submodel_validate.runner')))",
    ])
    run = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert run.returncode == 0, run.stderr
    assert run.stdout.split("\n")[:2] == [__version__, "[]"], run.stdout


@pytest.mark.parametrize("first", ["import aas_submodel_validate.rules.profiles",
                                   "from aas_submodel_validate import list_rules"])
def test_each_root_name_is_one_object_whatever_was_imported_first(first):
    """The same question asked of a fresh interpreter, in both orders: the
    module beneath the root first, and the root's own name first."""
    script = "\n".join([
        first,
        "import aas_submodel_validate.rules.profiles",
        "import json, types, aas_submodel_validate as root",
        "names = {name: '%s.%s' % (getattr(root, name).__module__, getattr(root, name).__qualname__)"
        " for name in root.__all__}",
        "names['rules is a package'] = isinstance(root.rules, types.ModuleType)",
        "print(json.dumps(names, sort_keys=True))",
    ])
    run = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert run.returncode == 0, run.stderr
    seen = json.loads(run.stdout)
    assert seen.pop("rules is a package") is True
    assert seen == {name: "%s.%s" % (getattr(api, name).__module__, getattr(api, name).__qualname__)
                    for name in api.__all__}


# -- the front page ---------------------------------------------------------


def _front_page_library_example() -> str:
    after = README.split("From Python the same judgement is a call.", 1)[1]
    code = re.search(r"(?s)```python\n(.*?)```", after)
    assert code, "the README no longer shows the library example"
    return code.group(1)


def _run_the_front_page_example(path, capsys):
    """The example, as written, on `path`: what it prints and what it
    leaves by."""
    code = _front_page_library_example()
    assert code.count('"submodel.aasx"') == 1, code
    code = code.replace('"submodel.aasx"', repr(str(path)))
    with pytest.raises(SystemExit) as left:
        exec(compile(code, "README.md", "exec"), {"__name__": "readme"})
    return capsys.readouterr().out, left.value.code


def test_the_front_page_library_example_runs_as_written(tmp_path, capsys):
    """The code a Python integrator copies whole, on a file it judges, a
    document it refuses and a path with nothing behind it -- leaving by the
    code `smtv` leaves by on each."""
    broken = tmp_path / "broken.json"
    broken.write_bytes(b"not json at all")
    absent = tmp_path / "nothing-here.aasx"
    for path, first in ((EXAMPLE, None), (broken, "X3 error"), (absent, "X6 error")):
        printed, left = _run_the_front_page_example(path, capsys)
        assert left == _smtv(str(path), "-q")[1], path.name
        if first is None:
            assert "HD-D10 warning" in printed, printed
        else:
            assert printed.startswith(first), printed
            assert left == 2


def test_the_front_page_names_everything_the_root_exports():
    _, _, stable = README.partition("What is stable, what is not")
    section = stable.split("</details>", 1)[0]
    missing = [name for name in api.__all__ if "`%s" % name not in section]
    assert not missing, missing
