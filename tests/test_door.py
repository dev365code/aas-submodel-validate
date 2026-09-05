"""The picture of a verdict has to be that verdict.

A terminal shot is the one asset that can go quietly false: the tool
changes a sentence, the SVG keeps the old one, and the front page shows
output no version ever produced. Every string drawn in
`docs/assets/verdict.svg` is checked here against a live run, and the
generator is checked against what is committed.
"""
from __future__ import annotations

import json
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
    path = tmp_path / "battery-passport.json"
    path.write_text(json.dumps(_env(_technical_data(fade=False))), encoding="utf-8")
    flags = [word for _dy, runs in _generator().VERDICT_LINES
             for _x, _colour, text, _bold in runs if text.startswith("smtv ")
             for word in text.split()[1:] if word.startswith("--")]
    report = runner.run(path, allow_unmatched="--allow-unmatched" in flags,
                        strict_meta=("info" if "--meta" in flags else False))
    return " ".join(render(report, show_meta="--show-meta" in flags).split())


def test_every_sentence_in_the_picture_is_one_the_tool_prints(tmp_path):
    """Drawn from an installed run, and pinned here so it cannot drift
    apart from one. The picture wraps where the drawing needs it and a
    terminal wraps where the window ends, so the comparison is of the
    text, not of the lines."""
    said = _the_verdict(tmp_path)
    lines = _generator().VERDICT_LINES
    typed = {index for index, (_dy, runs) in enumerate(lines)
             if any(text == "$ " for _x, _colour, text, _bold in runs)}
    elision = _generator().ELISION
    labels = {"at", "saw", "per", "fix", "note", "warning ", "BAT-R8"}
    drawn = [text for index, (_dy, runs) in enumerate(lines)
             if index not in typed
             for _x, _colour, text, _bold in runs if text not in labels]
    prose = [text for text in drawn if text != elision]
    assert prose, "the picture draws no sentence at all"
    for text in prose:
        assert " ".join(text.split()) in said, (
            "the picture shows %r and the tool does not say it" % text)
    # The one string in the picture that is not the tool's: the mark
    # that says lines were left out. The picture is a crop -- the folded
    # metamodel line and one note are not in it -- and every sentence in
    # it being true does not make the picture true if it reads as the
    # whole run. The front page's text block is held to this; the
    # picture above it was not.
    assert elision in drawn, (
        "the picture is a crop of the run and draws no elision mark")


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
