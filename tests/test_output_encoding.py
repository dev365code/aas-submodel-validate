"""What the terminal can encode, and what happens when it cannot.

The summary line every run prints carried an em dash. On a terminal
whose encoding has no em dash the write raises, Python prints a
traceback, and the process leaves by 1 -- so a clean file and a refused
file both came back as "there are findings", which is the one
distinction this tool works hardest to keep. That is not an exotic
setup: cp949 is the default code page on Korean Windows and cp932 on
Japanese, and this project advertises Windows and aims at machines
inside plants.

Two defences, and they are for different things. What this tool writes
of its own -- the separators in the summary -- is ASCII, so the normal
output reads the same everywhere. What it repeats from somewhere else
-- a section sign in an IDTA citation, an idShort in any script, a path
-- cannot be constrained, so the streams are reconfigured to escape
what they cannot encode rather than raise. The run survives and the
exit code stays honest.

Run in a subprocess on purpose: the encoding of a stream is a property
of the process that owns it, and a test that swapped `sys.stdout` for
something of its own would be measuring its own fixture.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Encodings a reader plausibly has, and what each of them cannot take.
#: cp1252 and cp936 are here as the control: they encode everything this
#: tool writes, which is why a suite that only ever ran on them --
#: including this project's own CI, all of it UTF-8 -- saw nothing.
CODE_PAGES = ["cp949", "cp932", "cp437", "cp850", "iso8859-1", "ascii",
              "cp1252", "cp936", "utf-8"]


def test_the_code_pages_this_is_for_are_still_in_the_list():
    """The two this repair exists for. A list in a test file is a line
    somebody can shorten, and deleting cp949 and cp932 leaves every
    assertion here passing while the reason for all of them is gone --
    they are the defaults on Korean and Japanese Windows, which is where
    the em dash killed a run. cp1252 and cp936 are the control: they
    encode everything, which is why a suite that only ever ran on UTF-8
    saw none of it."""
    for required in ("cp949", "cp932", "cp1252", "utf-8"):
        assert required in CODE_PAGES, (
            "%s left the list; it is either the case this was written "
            "for or the control that shows why it was not caught"
            % required)


def _run(arguments, encoding):
    environment = dict(os.environ,
                       PYTHONIOENCODING=encoding,
                       PYTHONPATH=str(ROOT / "src"))
    return subprocess.run([sys.executable, "-m", "aas_submodel_validate",
                           *arguments],
                          capture_output=True, env=environment, cwd=str(ROOT))


@pytest.mark.parametrize("encoding", CODE_PAGES)
def test_a_verdict_survives_a_terminal_that_cannot_spell_it(encoding):
    """The exit code is the contract -- 0 judged and clean, 1 findings,
    2 could not run -- and an encoding error made a clean run say 1."""
    done = _run(["--example"], encoding)
    assert b"Traceback" not in done.stderr, (
        "%s: the run died writing its own output:\n%s"
        % (encoding, done.stderr.decode("utf-8", "replace")[-800:]))
    assert done.returncode == 0, (
        "%s: a clean verdict left by %d; the exit code is the whole "
        "contract for a pipeline that reads nothing else"
        % (encoding, done.returncode))


@pytest.mark.parametrize("encoding", CODE_PAGES)
def test_a_refusal_survives_it_too(encoding, tmp_path):
    """The other half of the same contract, and the one that mattered
    more: a file this reader will not read leaves by 2, and an encoding
    error turned that into 1 -- which is what a judged file that failed
    looks like."""
    refused = tmp_path / "refused.json"
    refused.write_bytes(b"{ not json at all")
    done = _run([str(refused)], encoding)
    assert b"Traceback" not in done.stderr, (
        "%s: the run died writing its own output:\n%s"
        % (encoding, done.stderr.decode("utf-8", "replace")[-800:]))
    assert done.returncode == 2, (
        "%s: a refused input left by %d, which is the code for a verdict"
        % (encoding, done.returncode))


#: The one character this project writes that is not ASCII, and the
#: CHANGELOG says the same in the same words. `IDTA 02004-2-0 §2.4` is
#: how the standard spells that clause and how a reader has to spell it
#: back, so it stays; the escape hatch above carries it onto a terminal
#: that cannot take it, where it shows as `\xa7` -- ugly, and legible
#: enough to cite from. cp949 and cp932, the two this repair was for,
#: encode it fine. Everything else has an ASCII spelling and
#: has to use it.
ALLOWED = {"\u00a7"}


def test_what_this_tool_writes_of_its_own_is_ascii():
    """Every line, not the last one.

    The first version of this read `splitlines()[-1]` -- the summary --
    on the reasoning that the summary was where the crash was. Putting
    the em dash back into the `--example` banner, one of the four
    places the same commit repaired, left the suite green. So did an em
    dash in a rule's title, which travels in `--rules` and in every
    JSON finding. And the companion gate was a list of three characters,
    which an en dash walks past -- and an en dash is refused by cp949,
    cp932, cp437, cp850 and latin-1, the same five that started this.

    A list of what is forbidden is a list somebody has to keep. What is
    allowed is one character long."""
    done = _run(["--example"], "utf-8")
    assert done.returncode == 0, done.stderr
    for line in done.stdout.decode("utf-8").splitlines():
        found = sorted({character for character in line
                        if ord(character) > 127} - ALLOWED)
        assert not found, (
            "this line carries %s, which the common default code pages "
            "cannot encode: %r" % (found, line))


def test_no_rule_carries_a_character_the_common_code_pages_lack():
    """The sentences a rule is built from -- its title, the clause it
    cites, the remedy it offers. The title never reaches the text
    report, so a gate that reads the screen cannot see it, and it is on
    every finding in the JSON and on every line of `--rules`."""
    from aas_submodel_validate import runner
    from aas_submodel_validate.registry import all_rules

    for rule in list(all_rules()) + [runner._meta_rule(False)]:
        for label, sentence in (("title", rule.title), ("spec", rule.spec),
                                ("fix", rule.fix)):
            found = sorted({character for character in (sentence or "")
                            if ord(character) > 127} - ALLOWED)
            assert not found, (
                "%s's %s carries %s: %r" % (rule.id, label, found, sentence))


def test_no_finding_writes_a_character_the_common_code_pages_lack(tmp_path,
                                                                  monkeypatch):
    """The repair for the summary line was four separators in the
    renderer, and one had got into a rule: the note about a submodel
    named for a template it does not declare joined its two halves with
    an em dash. Fixing the place the crash was found is not fixing the
    class, so this reads what the rules actually print.

    Run from a directory of its own with ASCII names, because a path is
    the reader's and this is about what the tool contributes."""
    import json

    from aas_submodel_validate import runner
    from aas_submodel_validate.example import bundled_example
    from aas_submodel_validate.report import render
    from builders import env_json, hd_env
    from test_battery_rules import _env, _technical_data

    monkeypatch.chdir(tmp_path)
    (tmp_path / "battery.json").write_text(
        json.dumps(_env(_technical_data(fade=False))), encoding="utf-8")
    (tmp_path / "unmatched.json").write_bytes(env_json("urn:somecompany:docs"))
    (tmp_path / "clean.json").write_text(json.dumps(hd_env()), encoding="utf-8")
    (tmp_path / "refused.json").write_bytes(b"{ not json at all")
    (tmp_path / "empty.json").write_text('{"submodels": []}', encoding="utf-8")

    written = [
        render(runner.run("battery.json", allow_unmatched=True, strict_meta="info")),
        render(runner.run("unmatched.json")),
        render(runner.run("clean.json")),
        render(runner.run("refused.json")),
        render(runner.run("empty.json", allow_unmatched=True)),
    ]
    with bundled_example() as example:
        # Named, not pathed: this repository sits under a directory with
        # Korean in its name, and macOS hands that back as decomposed
        # jamo. That is the reader's path and the escape hatch's job.
        written.append(render(runner.run(str(example), strict_meta="info"),
                              show_meta=True).replace(str(example), "example.aasx"))

    for text in written:
        found = sorted({character for character in text
                        if ord(character) > 127} - ALLOWED)
        assert not found, (
            "the tool writes %s of its own accord, and the common "
            "default code pages cannot encode it" % found)


def test_a_reader_who_typed_a_dash_is_told_what_that_means(capsys):
    """`-` is how half the tools on a machine mean "read standard
    input", and this one does not read standard input. It answered "no
    such file: -", which is true and teaches nothing: a reader cannot
    tell a tool that has no such feature from one that lost the file."""
    from aas_submodel_validate.cli import main

    assert main(["-"]) == 2
    said = capsys.readouterr().err
    assert "standard input" in said, (
        "the message does not say this tool has no such thing: %r" % said)


def test_the_json_report_is_ascii_whatever_is_in_the_file():
    """The CHANGELOG says a reader parsing JSON never saw the em dash
    to begin with, which is a claim about the encoder and not about the
    strings: `json.dumps` escapes above ASCII, so a section sign leaves
    as `\\u00a7` and an idShort in Hangul leaves as escapes too. Worth
    pinning rather than assuming -- `ensure_ascii` is a default, and a
    default is a thing somebody can pass over."""
    # Read on a UTF-8 stream, deliberately. Asking for this on an
    # ASCII one measures the escape hatch and not the encoder: the
    # stream would escape whatever the encoder emitted and the answer
    # would be ASCII no matter what -- which is what the first version
    # of this did, and turning `ensure_ascii` off left it green.
    done = _run(["--example", "-f", "json", "--show-meta"], "utf-8")
    assert done.returncode == 0, done.stderr
    body = done.stdout.decode("utf-8")
    assert '"schemaVersion"' in body, body[:200]
    outside = sorted({character for character in body if ord(character) > 127})
    assert not outside, (
        "the JSON report carries %s; it is read by machines on hosts "
        "whose encoding nobody chose" % outside)


def test_no_string_in_the_source_carries_one_either():
    """Every string literal this package can print, read out of the
    source rather than out of a run.

    The gates above read what one command wrote and what the registry
    holds, and between them they missed nine places a character can
    reach a terminal: the `--rules` format, argparse's description,
    epilog and per-flag help, `parser.error`, three `smtv:` lines on
    stderr, the loader's exception text, and the message of any rule
    the fixtures do not happen to fire. Each was found by planting an
    em dash and watching the suite stay green.

    Planting them one at a time is how that list got to nine and why it
    is not ten. A run only proves the paths it took; the source is all
    of them, and it is one `ast.walk` away."""
    import ast

    #: Bytes this package matches on rather than prints. A byte order
    #: mark is what a real .rels file starts with, and recognising one
    #: means holding one.
    NOT_PRINTED = {"\ufeff"}

    offenders = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text("utf-8"), str(path))
        # Docstrings are for whoever opens the file, not for a
        # terminal, and this project writes long ones. Collected by
        # identity so a string that happens to equal a docstring is
        # still read.
        prose = set()
        for holder in ast.walk(tree):
            if isinstance(holder, (ast.Module, ast.ClassDef,
                                   ast.FunctionDef, ast.AsyncFunctionDef)):
                first = (holder.body or [None])[0]
                if (isinstance(first, ast.Expr)
                        and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    prose.add(id(first.value))
        for node in ast.walk(tree):
            if (not isinstance(node, ast.Constant)
                    or not isinstance(node.value, str)
                    or id(node) in prose):
                continue
            found = sorted({character for character in node.value
                            if ord(character) > 127} - ALLOWED - NOT_PRINTED)
            if found:
                offenders.append("%s:%d %s in %r"
                                 % (path.name, node.lineno, found,
                                    node.value[:60]))
    assert not offenders, (
        "these strings can reach a terminal and the common default code "
        "pages cannot encode them:\n  %s" % "\n  ".join(offenders))


#: The scripts `make check` runs. A message one of them cannot encode is
#: a traceback and an exit 1 from a gate that found nothing wrong -- the
#: same lie the CLI told, one directory over, and the AST scan above
#: does not reach here because these also write SVG and other files
#: whose contents are not terminal output.
GATE_SCRIPTS = ["rule_coverage.py --check", "extract_smt_rules.py --check",
                "vendor_template.py --check", "extract_battery_rules.py --check",
                "battery_data_check.py", "gen_door.py --check"]


@pytest.mark.parametrize("script", GATE_SCRIPTS)
@pytest.mark.parametrize("encoding", ["cp949", "cp932", "ascii", "utf-8"])
def test_a_gate_does_not_die_of_its_own_output(script, encoding):
    """Each of these prints a sentence when it passes. If a terminal
    cannot encode that sentence the write raises, and `make check` fails
    on a tree with nothing wrong in it -- reporting a defect that is the
    reader's code page."""
    name, _, flag = script.partition(" ")
    environment = dict(os.environ, PYTHONIOENCODING=encoding,
                       PYTHONPATH=str(ROOT / "src"))
    done = subprocess.run(
        [sys.executable, str(ROOT / "tools" / name)] + ([flag] if flag else []),
        capture_output=True, env=environment, cwd=str(ROOT))
    assert b"UnicodeEncodeError" not in done.stderr, (
        "%s died writing its own output under %s:\n%s"
        % (name, encoding, done.stderr.decode("utf-8", "replace")[-400:]))
    assert done.returncode == 0, (
        "%s failed under %s with %s"
        % (name, encoding, done.stderr.decode("utf-8", "replace")[-400:]))
