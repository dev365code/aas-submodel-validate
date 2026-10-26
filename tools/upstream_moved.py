#!/usr/bin/env python3
"""Whether the folders the vendored templates come from have moved upstream.

Every vendored file comes from one commit of admin-shell-io/submodel-templates,
named in `tools/vendor_template.py`, and that pin moves only when somebody
edits it. This asks upstream where its default branch is now and, for each
folder a vendored file comes from -- a template's folder, every edition in
it -- whether the folder is still the tree it was at the pin. Git names a
tree by its content, so one comparison per folder answers whether anything
in it changed, a new edition included, without reading the history between.

    python3 tools/upstream_moved.py              0 when nothing vendored moved
    python3 tools/upstream_moved.py --pin SHA    the same question about another commit

Exit 1 names each folder that moved and what changed in it: a decision to
make about the pin, not a defect in this project. Exit 2 is a question
upstream did not answer -- no response, an error, a listing it may have cut
short -- reported as that rather than as either answer, and 64 is a wrong
call. It needs the network, so it is not part of `make check`:
`.github/workflows/upstream.yml` runs it every Monday, and on a push that
changes the pin or this check.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# The pin and the files from `vendor_template.py` beside this file, and the
# console guard from the package beside that, wherever this runs from: the
# workflow that runs it installs nothing.
_HERE = Path(__file__).resolve().parent
for _where in (str(_HERE), str(_HERE.parent / "src")):
    if _where not in sys.path:
        sys.path.insert(0, _where)

from aas_submodel_validate._terminal import survive  # noqa: E402
from vendor_template import COMMIT, FILES, REPO  # noqa: E402

ROOT_URL = "https://api.github.com/repos/" + REPO

#: How many entries the contents API lists before it stops. A listing that
#: long may be missing the folder asked about, which would read as "gone".
LISTED = 1000

#: How many changed paths a moved folder lists before it says how many more.
SHOWN = 12


class Unanswered(Exception):
    """Upstream gave no answer this can read."""


def request(path: str) -> urllib.request.Request:
    """The request for one REST path. Authenticated only when GH_TOKEN is set
    -- in the workflow, its own read-only token, for the rate limit."""
    made = urllib.request.Request(ROOT_URL + ("/" + path if path else ""), headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "aas-submodel-validate upstream check"})
    token = os.environ.get("GH_TOKEN")
    if token:
        made.add_header("Authorization", "Bearer " + token)
    return made


def api(path: str):
    """One REST call, parsed; any way of not getting an answer is `Unanswered`."""
    try:
        with urllib.request.urlopen(request(path), timeout=30) as response:  # noqa: S310 - fixed https host
            return json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise Unanswered("%s: %s" % (path or "the repository", error)) from None


def watched(files=FILES) -> list:
    """The folders the vendored files come from: each upstream path up to the
    first part that is a version number, so a template's folder holds every
    edition of it -- the one the pin chose and any published after it."""
    folders = set()
    for source in files.values():
        parts = source.split("/")
        cut = next((n for n, part in enumerate(parts) if part.isdigit()), 0)
        if cut < 2:
            raise ValueError("%r has no folder before its edition" % source)
        folders.add("/".join(parts[:cut]))
    return sorted(folders)


def head():
    """Upstream's default branch, and the commit it is at."""
    try:
        branch = api("")["default_branch"]
        return branch, api("commits/" + urllib.parse.quote(branch, safe=""))["sha"]
    except (KeyError, TypeError):
        raise Unanswered("the repository's default branch is not in its answer") from None


def trees(ref: str, folders) -> dict:
    """Each folder's tree at `ref`, read from the folder above it: one listing
    names every child's tree, so the folders cost a few calls, not one each."""
    found = {}
    for parent in sorted({folder.rsplit("/", 1)[0] for folder in folders}):
        listing = api("contents/%s?ref=%s" % (urllib.parse.quote(parent), ref))
        if not isinstance(listing, list):
            raise Unanswered("%s at %s is not a folder listing" % (parent, ref[:12]))
        if len(listing) >= LISTED:
            raise Unanswered("the listing of %s at %s may be cut short (%d entries)"
                             % (parent, ref[:12], len(listing)))
        for entry in listing:
            if isinstance(entry, dict) and entry.get("type") == "dir":
                found[entry.get("path")] = entry.get("sha")
    return found


def files(tree: str) -> dict:
    """Every file under a tree, by path, with the blob it is."""
    answer = api("git/trees/%s?recursive=1" % tree)
    if not isinstance(answer, dict) or answer.get("truncated") is not False:
        raise Unanswered("the tree %s is too large to list in one answer" % tree[:12])
    return {entry["path"]: entry["sha"] for entry in answer.get("tree", ())
            if entry.get("type") == "blob"}


def changes(old: str, new: str) -> list:
    """What differs between two trees of one folder, path by path."""
    before, after = files(old), files(new)
    return (["added   " + path for path in sorted(set(after) - set(before))]
            + ["removed " + path for path in sorted(set(before) - set(after))]
            + ["changed " + path for path in sorted(set(before) & set(after))
               if before[path] != after[path]])


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(64, "%s: error: %s\n" % (self.prog, message))


def main(argv=None) -> int:
    survive()
    parser = _Parser(description=__doc__.splitlines()[0])
    parser.add_argument("--pin", default=COMMIT,
                        help="the commit to compare upstream with (default: the pin "
                             "tools/vendor_template.py names)")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.pin):
        parser.error("--pin takes a commit's full 40-character name")
    folders = watched()
    try:
        branch, now = head()
        if now == args.pin:
            print("upstream %s is at the pin %s: nothing has moved" % (branch, args.pin[:12]))
            return 0
        then, current = trees(args.pin, folders), trees(now, folders)
        missing = [folder for folder in folders if folder not in then]
        if missing:
            raise Unanswered("%s at the pin %s holds no %s, which the vendored files "
                             "are taken from" % (REPO, args.pin[:12], ", ".join(missing)))
        moved = [folder for folder in folders if current.get(folder) != then[folder]]
        found = [(folder, changes(then[folder], current[folder]) if folder in current
                  else ["the folder is gone"]) for folder in moved]
    except Unanswered as error:
        print("upstream did not answer: %s" % error)
        return 2
    if not moved:
        print("upstream %s moved from %s to %s, and none of the %d folders the vendored "
              "files come from did" % (branch, args.pin[:12], now[:12], len(folders)))
        return 0
    print("upstream %s is at %s, and %d of the %d folders the vendored files come from "
          "moved since %s:" % (branch, now[:12], len(moved), len(folders), args.pin[:12]))
    for folder, lines in found:
        print("  %s" % folder)
        for line in lines[:SHOWN]:
            print("    %s" % line)
        if len(lines) > SHOWN:
            print("    ... and %d more" % (len(lines) - SHOWN))
    print("Moving the pin is a decision, made in one commit that says why: edit COMMIT in "
          "tools/vendor_template.py, run it with --refresh (which writes every sha256sums.txt "
          "again), change the commit THIRD_PARTY.md names, write again what is generated "
          "from the templates -- make check names each generated file that no longer "
          "matches, docs/official-samples.md among them -- and name in the CHANGELOG every "
          "verdict the move changed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
