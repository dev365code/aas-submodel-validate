"""Every case on the what-it-catches page, run the way the page says to.

The page quotes the tool's own sentences. A quote is a claim about what
somebody will see, and a page of quotes nobody re-runs is a page that
becomes wrong one rule at a time -- silently, because prose has no
compiler. So each case here is materialised from the page itself: the
file it tells the reader to paste, the command it tells them to run, and
the line it promises they will see.

Nothing is typed into this file that the page does not carry. A case
added to the page is a case run here; a case whose wording drifts from
what the tool prints fails here rather than on a reader's screen.
"""
from __future__ import annotations

import io
import json
import re
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from aas_submodel_validate import cli

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "docs" / "what-it-catches.md").read_text("utf-8")

#: `printf 'body' > name` -- the one case whose input is not JSON.
_PRINTF = re.compile(r"^printf '(?P<body>[^']*)' > (?P<name>\S+)$", re.M)
_SMTV = re.compile(r"^smtv (?P<args>.+)$", re.M)


def _blocks(section: str, language: str) -> list:
    return re.findall(r"```%s\n(.*?)```" % language, section, re.S)


def _cases() -> list:
    """(title, pasted json or None, written files, argv, expected lines)."""
    out = []
    for section in PAGE.split("\n## ")[1:]:
        title = section.splitlines()[0].strip()
        shell = _blocks(section, "sh")
        if not shell:
            continue
        written = {m.group("name"): m.group("body")
                   for m in _PRINTF.finditer(shell[0])}
        command = _SMTV.search(shell[0])
        assert command, "%s: the shell block runs no `smtv` command" % title
        argv = command.group("args").split()
        pasted = _blocks(section, "json")
        assert len(pasted) <= 1, "%s: more than one file to paste" % title
        expected = re.findall(r"^> `(.+)`$", section, re.M)
        assert expected, "%s: the page promises no sentence" % title
        out.append((title, pasted[0] if pasted else None, written, argv,
                    expected))
    return out


CASES = _cases()


def test_the_page_carries_the_cases_its_own_table_counts():
    """The table at the top says how many cases follow."""
    stated = re.search(r"^(\w+) things this tool says", PAGE, re.M)
    assert stated, "the page no longer opens by counting its cases"
    numerals = {"four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
    rows = len(re.findall(r"^\| \d+ \|", PAGE, re.M))
    assert numerals.get(stated.group(1).lower()) == len(CASES) == rows, (
        "the page says %s, its table has %d rows, and %d cases follow"
        % (stated.group(1).lower(), rows, len(CASES)))


@pytest.mark.parametrize("title,pasted,written,argv,expected",
                         CASES, ids=[case[0].split(" · ")[0] for case in CASES])
def test_a_case_on_the_page_says_what_the_page_says_it_says(
        tmp_path, monkeypatch, title, pasted, written, argv, expected):
    named = [arg for arg in argv if not arg.startswith("-")]
    assert len(named) <= 1, "%s: more than one input named" % title
    if pasted is not None:
        assert named, "%s: a file to paste and no file named" % title
        json.loads(pasted)          # the page must not print invalid JSON
        (tmp_path / named[0]).write_text(pasted, encoding="utf-8")
    for name, body in written.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    if named:
        assert (tmp_path / named[0]).exists(), (
            "%s: the page names %s and neither pastes nor writes it"
            % (title, named[0]))

    monkeypatch.chdir(tmp_path)
    printed = io.StringIO()
    with redirect_stdout(printed):
        code = cli.main(list(argv))
    said = printed.getvalue()
    # The page writes the bare name a reader would type; a run from any
    # directory prints the path it was handed.
    for name in list(written) + named:
        said = said.replace(str(tmp_path / name), name)

    for line in expected:
        assert line in said, (
            "%s: the page promises\n  %s\nand the run printed\n%s\n"
            "(exit %d)" % (title, line, said, code))
