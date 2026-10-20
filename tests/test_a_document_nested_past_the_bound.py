"""How deep a document may nest is this reader's bound, not the machine's.

A document nested deeper than the parser can follow used to be refused
where the interpreter's stack ran out: CPython's JSON parser follows 9,998
levels, the browser's build of the same Python runs out of stack near
2,000, and so the same file was a report at one entrance and a crash at
another. A bound the reader sets does not depend on where it runs. Every
JSON and XML document -- a bare one and a part in a package -- is scanned
for how deep it nests before it is parsed, by one linear pass that does
not recurse, and one past the bound is refused as X5 refuses a document
past the 64 MiB bound: refused, not judged, with exit 2.

The bound is measured, not chosen: ten times the deepest nesting in
anything this repository judges -- the corpus the release notes measure
and the twelve vendored templates -- rounded up to the hundred, held at
1,000 or below, and with more than half the browser's measured depth to
spare.
"""
from __future__ import annotations

import json
import math
import sys
import time
import zipfile
from pathlib import Path

import pytest

from aas_submodel_validate import container, loader, runner
from builders import build_aasx

ROOT = Path(__file__).resolve().parents[1]
N = container.MAX_NESTING

#: The deepest the browser page's runtime was measured to follow before its
#: stack ran out: JSON arrays 2,000 deep were judged as the command judges
#: them and 2,500 were not; XML 1,200 deep was, and 3,000 was not.
BROWSER_FOLLOWS = {"json": 2000, "xml": 1200}


def _ids(report):
    return [finding.id for finding in report.findings]


def _json(depth: int) -> bytes:
    return ("[" * depth + "]" * depth).encode("ascii")


def _xml(depth: int) -> bytes:
    """An environment element with `depth - 1` elements nested inside it."""
    inner = depth - 1
    return ('<environment xmlns="https://admin-shell.io/aas/3/0">' + "<a>" * inner
            + "</a>" * inner + "</environment>").encode("ascii")


def _run(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return runner.run(str(path))


def _packaged(tmp_path, name, data, payload_name):
    path = tmp_path / name
    build_aasx(path, payload=data, payload_name=payload_name)
    return runner.run(str(path))


@pytest.mark.parametrize("form, make", [("json", _json), ("xml", _xml)])
def test_a_document_nested_to_the_bound_is_read_and_one_level_more_is_refused(tmp_path, form, make):
    at = _run(tmp_path, "at." + form, make(N))
    assert "X5" not in _ids(at), [f.violation.message for f in at.findings]
    past = _run(tmp_path, "past." + form, make(N + 1))
    assert "X5" in _ids(past) and not past.judged
    (refusal,) = [f for f in past.findings if f.id == "X5"]
    assert refusal.violation.message.endswith(
        "nests deeper than the %d levels this reader follows" % N), refusal.violation.message


@pytest.mark.parametrize("form, make", [("json", _json), ("xml", _xml)])
def test_a_part_in_a_package_is_bounded_as_the_same_document_bare(tmp_path, form, make):
    part = "aasx/env." + form
    at = _packaged(tmp_path, "at.aasx", make(N), part)
    assert "X5" not in _ids(at)
    past = _packaged(tmp_path, "past.aasx", make(N + 1), part)
    (refusal,) = [f for f in past.findings if f.id == "X5"]
    assert refusal.violation.subject == part
    assert refusal.violation.message == "%s nests deeper than the %d levels this reader follows" % (part, N)


def test_brackets_inside_a_string_are_text_and_not_nesting(tmp_path):
    deep_text = "[" * (N * 3) + "{" * (N * 3) + '\\"' + "]" * 7
    document = {"submodels": [], "note": deep_text, "other": "\\\\" + "[" * (N * 2)}
    report = _run(tmp_path, "strings.json", json.dumps(document).encode("utf-8"))
    assert "X5" not in _ids(report), [f.violation.message for f in report.findings]


def test_markup_that_is_not_an_element_is_not_nesting(tmp_path):
    """A comment, a CDATA section and an attribute value may hold angle
    brackets; none of them opens an element."""
    filler = ("<!-- " + "<a>" * N + " -->" + "<![CDATA[" + "<a>" * N + "]]>")
    data = ('<environment xmlns="https://admin-shell.io/aas/3/0" x="%s">%s</environment>'
            % ("&lt;a&gt;" * 3, filler)).encode("ascii")
    report = _run(tmp_path, "markup.xml", data)
    assert "X5" not in _ids(report), [f.violation.message for f in report.findings]


@pytest.mark.parametrize("form, make, depth", [("json", _json, 1_000_000), ("xml", _xml, 200_000)])
def test_the_scan_neither_recurses_nor_takes_long(tmp_path, form, make, depth):
    """Far past any stack: refused as past the bound -- not as a stack that
    ran out, which is the machine's answer -- and quickly."""
    started = time.perf_counter()
    report = _run(tmp_path, "far." + form, make(depth))
    assert time.perf_counter() - started < 20
    (refusal,) = [f for f in report.findings if f.id == "X5"]
    assert "RecursionError" not in (refusal.violation.detail or "")
    assert not [f for f in report.findings if f.id == "X3"]


def test_the_bound_is_ten_times_the_deepest_file_judged_here(tmp_path):
    sys.path.insert(0, str(ROOT / "tools"))
    import verdict_diff

    deepest = 0
    sources = [Path(case.path) for case in verdict_diff.build_corpus(tmp_path)]
    sources += sorted((ROOT / "src" / "aas_submodel_validate" / "data" / "smt").rglob("template.json"))
    for path in sources:
        if not path.is_file():
            continue
        for form, data in _documents(path):
            depth = loader.nesting(data, form)
            if depth > container.MAX_NESTING:
                continue          # the corpus's own case for this bound
            deepest = max(deepest, depth)
    assert deepest > 0
    assert N == math.ceil(10 * deepest / 100) * 100 <= 1000, (N, deepest)
    assert all(follows >= 2 * N for follows in BROWSER_FOLLOWS.values())
    # And the page that states the bound states the measurement behind it.
    scope = " ".join((ROOT / "docs" / "scope.md").read_text("utf-8").split())
    assert "nests deeper than %d levels" % N in scope
    assert "ten times the deepest" in scope and "(%d levels)" % deepest in scope


def _documents(path):
    """(form, bytes) for each JSON or XML document a file is or holds."""
    if path.suffix in (".json", ".xml"):
        yield path.suffix[1:], path.read_bytes()
    elif path.suffix == ".aasx":
        try:
            archive = zipfile.ZipFile(path)
        except zipfile.BadZipFile:
            return
        with archive:
            for name in archive.namelist():
                if name.endswith((".json", ".xml")) and not name.startswith("[Content_Types]"):
                    try:
                        yield name.rsplit(".", 1)[1], archive.read(name)
                    except Exception:  # noqa: BLE001 - a corpus part meant to be unreadable
                        continue


def _read_character_by_character(text: str) -> int:
    """The JSON depth as a reader walking one character at a time sees it:
    a quote opens and closes a string, a backslash inside one takes the
    character after it, and only brackets outside strings count."""
    depth = deepest = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            deepest = max(deepest, depth)
        elif char in "]}":
            depth -= 1
    return deepest


def test_the_scan_reads_json_as_a_character_by_character_reader_would(tmp_path):
    """The scan reads whole strings and whole runs of other characters at a
    time, so that asking costs about what parsing costs; what it answers is
    held to the slow reading above, on the corpus and on strings of nothing
    but the characters that decide the answer, as text and as bytes."""
    import random

    sys.path.insert(0, str(ROOT / "tools"))
    import verdict_diff

    texts = [Path(case.path).read_bytes().decode("utf-8-sig", "replace")
             for case in verdict_diff.build_corpus(tmp_path)
             if Path(case.path).suffix == ".json" and Path(case.path).is_file()]
    chooser = random.Random(2770)
    texts += ["".join(chooser.choice('[]{}"\\ a') for _ in range(chooser.randint(0, 90)))
              for _ in range(3000)]
    texts += ['["\\', '"[[[', "]", "]][[[", '{"a": "x\\"[[["}', '{"a":"\\\\"}[[']
    for text in texts:
        expected = _read_character_by_character(text)
        assert loader.nesting(text, "json") == expected, text[:80]
        assert loader.nesting(text.encode("utf-8"), "json") == expected, text[:80]
