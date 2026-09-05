"""The picture of a verdict has to be that verdict.

A terminal shot is the one asset that can go quietly false: the tool
changes a sentence, the SVG keeps the old one, and the front page shows
output no version ever produced. Every string drawn in
`docs/assets/verdict.svg` is checked here against a live run, and the
generator is checked against what is committed.
"""
from __future__ import annotations

import json
import os
import pathlib
import types

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.report import render
from test_battery_rules import _env, _technical_data

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _generator():
    """The generator as it is on disk, not as it was last compiled.

    macOS ships a Python whose bytecode cache lives outside the tree
    (`sys.pycache_prefix`), so a stale `.pyc` survives deleting every
    `__pycache__` here -- and an edited generator went on producing the
    old picture for a whole debugging session, with the source and the
    committed asset both correct the entire time.
    """
    source = (ROOT / "tools" / "gen_door.py").read_text(encoding="utf-8")
    module = types.ModuleType("_gen_door")
    module.__file__ = str(ROOT / "tools" / "gen_door.py")
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def _the_verdict(tmp_path) -> str:
    """The run the picture types, with the flags the picture types.

    Written first as a plain run, then as one with `allow_unmatched` set
    on the report afterwards -- which relabels a finding without
    re-deciding it -- and both disagreed with the drawing. The flags are
    read out of the command in the picture so the two cannot part.
    """
    (tmp_path / "battery-passport.json").write_text(
        json.dumps(_env(_technical_data(fade=False))), encoding="utf-8")
    flags = [word for _dy, runs in _generator().VERDICT_LINES
             for _x, _colour, text, _bold in runs if text.startswith("smtv ")
             for word in text.split()[1:] if word.startswith("--")]
    # Run from inside the directory, so the summary names the file the
    # picture types rather than a temporary path no reader will ever see.
    here = os.getcwd()
    try:
        os.chdir(tmp_path)
        report = runner.run("battery-passport.json",
                            allow_unmatched="--allow-unmatched" in flags,
                            strict_meta=("info" if "--meta" in flags else False))
        return render(report, show_meta="--show-meta" in flags)
    finally:
        os.chdir(here)


def _quoted_lines(lines, elision):
    """The picture's drawn runs, regrouped into the output lines they
    quote.

    A terminal line is one line and the drawing wraps it wherever the
    picture is wide enough, so a run is not a line and comparing runs
    to output is comparing the wrong things. Runs are joined back into
    the line they came from -- a new one starts wherever a label or a
    prompt does -- and the label is kept, because `fix` and `fix:` are
    not the same word and a picture that drops the colon is quoting
    something the tool does not print.
    """
    groups = []
    for _dy, runs in lines:
        texts = [text for _x, _colour, text, _bold in runs]
        if elision in texts:
            groups.append(elision)
            continue
        opens = any(x < 168 for x, _colour, _text, _bold in runs)
        body = " ".join(" ".join(text.split()) for text in texts if text.strip())
        if opens or not groups or groups[-1] == elision:
            groups.append(body)
        else:
            groups[-1] = (groups[-1] + " " + body).strip()
    return groups


def test_every_sentence_in_the_picture_is_one_the_tool_prints(tmp_path):
    """Drawn from an installed run, and pinned here so it cannot drift
    apart from one. The picture wraps where the drawing needs it and a
    terminal wraps where the window ends, so the runs are joined back
    into the lines they came from and the comparison is of those."""
    said = _the_verdict(tmp_path)
    printed = [" ".join(row.split()) for row in said.splitlines()]
    generator = _generator()
    elision = generator.ELISION
    groups = _quoted_lines(generator.VERDICT_LINES, elision)
    quotes = [text for text in groups
              if text != elision and not text.startswith("$ ")]
    assert quotes, "the picture draws no sentence at all"
    # Whole lines, or a prefix that says it is one. Compared against the
    # run joined into a single string -- which is what this did -- a
    # quote could stop anywhere and pass, and one that stopped just
    # before "not about where the template puts it" reversed the
    # sentence and stayed green. The front page's text block was held to
    # this and the picture above it, which is what a reader sees first,
    # was not.
    # In the order the tool prints them, and with every gap marked. The
    # front page's text block was given both checks when reversing its
    # lines was found to pass; the picture above it, which is what a
    # reader sees first, kept neither -- so the remedy and the clause
    # could be drawn the other way round, regenerate cleanly and stay
    # green through every gate.
    # Both ends, which the first version of this could not see: `at >= 0`
    # skipped the check on the first quote, so dropping the opening line
    # -- the finding itself -- regenerated clean and passed everything,
    # and `gap` was never read after the loop, so a mark at the bottom
    # with nothing below it passed too.
    at, gap = -1, False
    for text in groups:
        if text == elision:
            gap = True
            continue
        if text.startswith("$ "):
            continue
        if text.endswith(elision):
            stem = text[:-len(elision)].rstrip()
            where = [i for i, row in enumerate(printed) if row.startswith(stem)]
            missing = ("the picture quotes %r and no line the tool prints "
                       "begins that way" % stem)
        else:
            where = [i for i, row in enumerate(printed) if row == text]
            missing = ("the picture shows %r and the tool prints no such "
                       "line. A quote that stops early is a quote that says "
                       "something else -- mark it with %s if it is a crop."
                       % (text, elision))
        assert where, missing
        later = [index for index in where if index > at]
        assert later, (
            "the picture draws %r after a line the tool prints later, or "
            "draws it twice where the tool prints it once; a verdict is "
            "read downwards and this one is not" % text)
        # Every gap marked, which the comment above promised and the
        # first version did not do: leaving a line out of the middle of
        # the picture without an elision was green, and so was putting
        # the mark somewhere no line was missing. The front page's text
        # block has had both halves since the day reversing its lines
        # was found to pass.
        skipped = later[0] - at - 1
        if gap:
            assert skipped, (
                "there is an elision mark before %r and the tool prints "
                "nothing between it and the line above it" % text)
        else:
            assert not skipped, (
                "the picture goes straight from %s to %r and the tool "
                "prints %d line(s) between them, with nothing to say so"
                % ("the top" if at < 0 else "the line above", text, skipped))
        gap = False
        at = later[0]
    # The one string in the picture that is not the tool's: the mark
    # that says lines were left out. The picture is a crop -- the folded
    # metamodel line and one note are not in it -- and every sentence in
    # it being true does not make the picture true if it reads as the
    # whole run. The front page's text block is held to this; the
    # picture above it was not.
    # And the tail. A mark below the last quote says lines follow it;
    # one that is the last thing in the picture when the summary was
    # already quoted says nothing follows, which is a different claim.
    trailing = len(printed) - 1 - at
    if gap:
        assert trailing > 0, (
            "the picture ends with an elision mark and has already "
            "quoted the run's last line")
    else:
        assert trailing == 0, (
            "the picture stops %d line(s) before the run does, with "
            "nothing to say so" % trailing)
    assert elision in groups, (
        "the picture is a crop of the run -- lines are missing between "
        "the remedy and the note -- and draws no elision mark")
    assert len(quotes) < len(printed), (
        "the picture claims to quote as many lines as the run printed, "
        "so either it is not a crop or one of these is wrong")


def test_the_commands_in_the_picture_are_ones_this_project_offers(tmp_path,
                                                                  capsys):
    """The two prompt lines are commands a reader will copy. A picture
    that shows a flag the tool does not have teaches a wrong thing that
    no gate about the README would ever see."""
    from aas_submodel_validate.cli import main
    typed = [text for _dy, runs in _generator().VERDICT_LINES
             for _x, _colour, text, _bold in runs
             if not text.startswith("$ ") and text.startswith("smtv ")]
    assert typed, "the picture shows no command"
    for command in typed:
        words = command.split()[1:]
        argv = []
        for word in words:
            if word.startswith("--"):
                argv.append(word)
            elif argv and argv[-1].startswith("--") and not word.endswith(".json"):
                argv.append(word)          # the flag's value, kept with it
        assert argv, command
        path = tmp_path / "e.json"
        path.write_text(json.dumps(_env(_technical_data(fade=False))), "utf-8")
        assert main(["-q", *argv, str(path)]) in (0, 1), \
            "the picture types %r and the tool refuses it" % command
        capsys.readouterr()


def test_the_committed_pictures_match_their_generator():
    """`--check` is what CI runs; this is the same question, so a stale
    asset fails where it is cheap rather than on a release."""
    assert _generator().main(["--check"]) == 0, \
        "docs/assets is out of date; run tools/gen_door.py"


@pytest.mark.parametrize("name", ["door.svg", "verdict.svg"])
def test_the_banner_carries_no_number_that_can_go_stale(name):
    """A count in a picture is a count nothing regenerates. The banner
    carries none by design; the verdict shot carries the ones the tool
    printed, and the test above is what keeps those true."""
    import html
    import re
    svg = (ROOT / "docs" / "assets" / name).read_text(encoding="utf-8")
    # Entities are markup: `&#160;` is a space a reader sees as a space,
    # and reading it raw made the first version of this call the banner's
    # spacing a stale number.
    text = html.unescape(" ".join(re.findall(r">([^<>]+)<", svg)))
    if name == "door.svg":
        assert not re.search(r"\d", text), \
            "the banner shows %r, and nothing regenerates it" % text.strip()


def test_every_picture_ships_in_the_source_distribution():
    """`MANIFEST.in` names what `docs/` ships, file by file, on purpose --
    and it was written before there were pictures. So the two SVGs were
    committed, the suite that checks them was committed, and neither the
    packaging list nor anything else noticed that an sdist carried the
    checker without the thing it checks. Unpacked and run the way
    `MANIFEST.in` promises, four tests failed on files that were not
    there.

    Not caught locally, because setuptools carries `SOURCES.txt`
    forward from a previous build: on a machine that had ever built this
    sdist the pictures were in it, and on a clean checkout -- which is
    every checkout CI makes -- they were not.

    Asserted against the generator rather than against a listing of the
    directory, so a third picture cannot be added without this saying
    where it has to be named."""
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    for name in _generator().PICTURES:
        assert "docs/assets/%s" % name in manifest, (
            "docs/assets/%s is drawn by the generator and MANIFEST.in "
            "does not name it, so an sdist ships the tests that read it "
            "and not the file" % name)
