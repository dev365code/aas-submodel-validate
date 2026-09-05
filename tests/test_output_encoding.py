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


#: The one character this project writes that is not ASCII. `IDTA
#: 02004-2-0 §2.4` is how the standard spells that clause and how a
#: reader has to spell it back; the escape hatch above carries it onto
#: a terminal that cannot. Everything else has an ASCII spelling and
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
