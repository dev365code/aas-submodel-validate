"""The release carries the page, and it is the page CI opened.

The front page offers a page that runs the check in a browser with nothing
installed, and a reader who wanted it had to build it in a clone with a
network -- the one door a release did not hand over. A release now builds
it beside the single file, on the Python CI built it on, vouches for it in
the one checksum file, signs it with the rest, and refuses to go out if the
bytes differ from the page CI opened in a browser and compared with the
command. Read out of the workflows, because a release is the one run nobody
gets to try twice.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
PAGE = "aas-submodel-validate.html"


def _job(text: str, name: str) -> str:
    """One job's text, from its key to the next job's."""
    found = re.search(r"(?m)^  %s:\n" % re.escape(name), text)
    assert found, "no job %r" % name
    rest = text[found.end():]
    following = re.search(r"(?m)^  [a-z][a-z0-9-]*:\n", rest)
    return rest[:following.start()] if following else rest


def test_ci_keeps_the_page_it_opened():
    job = _job(CI, "the-page-this-repo-offers")
    assert "actions/upload-artifact@" in job
    assert re.search(r"(?m)^\s+name: the-page$", job)
    assert re.search(r"(?m)^\s+path: dist/%s$" % re.escape(PAGE), job)


def test_the_release_builds_the_page_into_what_it_sums_and_compares_it_with_ci():
    build = _job(RELEASE, "build")
    line = "python tools/build_browser.py -o dist/%s" % PAGE
    assert line in build, "the release does not build the page into dist/"
    built = build.index(line)
    assert built < build.index("shasum -a 256 * > SHA256SUMS"), (
        "the page is built after the checksums, so nothing vouches for it")
    assert re.search(r'python-version: "3\.13\.2"', build[:built]), (
        "the page is built on another Python than the one CI built it on")
    assert re.search(r"gh run download \S+ -n the-page", build[built:])
    assert "cmp dist/%s " % PAGE in build[built:]


def test_the_gate_counts_the_page_among_what_the_release_publishes():
    build = _job(RELEASE, "build")
    assert '"$records" != "5"' in build
    assert '"$count" != "6"' in build
    assert "'%s'" % PAGE in build


def test_the_round_trip_expects_every_file_the_release_path_sends():
    """CI's release path uploads what a release would publish, and a second
    job downloads it and counts it. That job kept the count from before the
    page, so the commit that added the page went red there and nowhere a
    check runs before a push. The two counts are one number."""
    sent = re.search(r'"\$count" != "(\d+)"', _job(CI, "release-path"))
    came_back = re.search(r'"\$count" != "(\d+)"', _job(CI, "round-trip"))
    assert sent and came_back, "a count is no longer where this reads it"
    assert came_back.group(1) == sent.group(1) == "6"


def test_the_page_is_signed_and_named_in_the_notes():
    assert "dist/%s" % PAGE in _job(RELEASE, "attest")
    notes = _job(RELEASE, "github-release")
    assert "`%s`" % PAGE in notes
    assert "which of the six files" in notes


def test_the_front_page_hands_the_page_over_from_the_release():
    assert "releases/latest/download/%s" % PAGE in README
