"""What the page behind the front-page picture says, held to what is true.

The shared gates (`test_capabilities_current.py`) keep the picture, its
data and the README in step, and hold a done item to a file that contains
the words it quotes. Three things they cannot see, each measured by
flipping it and watching every test stay green: a quote can be words from
a sentence that says the opposite, the page's own done/not-yet lines can
disagree with the data, and the outputs the page quotes can drift from the
tool. These are this repository's answers to the three.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "docs" / "capabilities.json").read_text("utf-8"))
PAGE = (ROOT / "docs" / "what-it-catches.md").read_text("utf-8")


def _axis(key):
    (axis,) = [axis for axis in DATA["axes"] if axis["key"] == key]
    return axis


def _section(label):
    match = re.search(r"(?ms)^## %s\n(.*?)(?=^## |\Z)" % re.escape(label), PAGE)
    assert match, "the page has no section headed %r" % label
    return match.group(1)


def test_the_templates_marked_done_are_the_ones_vendored():
    """Coverage is a list of names, and a name quoted from a sentence that
    says the template is *not* vendored satisfies the shared gate. So the
    done items are held to what is in the package instead."""
    vendored = {path.name for path in
                (ROOT / "src" / "aas_submodel_validate" / "data" / "smt").iterdir()
                if path.is_dir()}
    done = {re.search(r"IDTA (\d{5}(?:-\d)?)", item["text"]).group(1)
            for item in _axis("coverage")["items"] if item["done"]}
    assert done == vendored, (sorted(done), sorted(vendored))


def test_each_item_line_on_the_page_says_what_the_data_says():
    """The page lists every item as done or not yet, and the picture it is
    linked from draws the same items. A line flipped on one side only is
    a page contradicting its own picture."""
    for axis in DATA["axes"]:
        section = _section(axis["label"])
        lines = re.findall(r"(?m)^- (.+) — (done|not yet)$", section)
        expected = [(item["text"], "done" if item["done"] else "not yet")
                    for item in axis["items"]]
        assert lines == expected, (axis["label"], lines, expected)


def _fenced(section):
    return re.findall(r"(?ms)^```\n(.*?)\n```", section)


def test_the_outputs_the_page_quotes_are_what_the_tool_prints(capsys, monkeypatch):
    """The page says "Reproduce:" under each sample; this reproduces them,
    through the command a reader types and from the root, as written."""
    from aas_submodel_validate.cli import main

    monkeypatch.chdir(ROOT)
    coverage, explanation = _section("Coverage"), _section("Explanation")

    main(["--example"])
    example = capsys.readouterr().out
    quoted = _fenced(coverage)
    assert quoted[0] == example.rstrip("\n").splitlines()[-1], quoted[0]
    (block,) = _fenced(explanation)
    assert block in example, block

    main(["tests/corpus/idta/02003/sample-2.0.1.aasx"])
    assert quoted[1] == capsys.readouterr().out.rstrip("\n").splitlines()[-1], quoted[1]

    (upstream,) = _fenced(_section("Upstream"))
    checked = subprocess.run([sys.executable, str(ROOT / "tools" / "vendor_template.py"), "--check"],
                             capture_output=True, text=True, cwd=str(ROOT))
    assert upstream == checked.stdout.strip().splitlines()[-1], (upstream, checked.stdout)
