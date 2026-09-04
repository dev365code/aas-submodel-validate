#!/usr/bin/env python3
"""What may not be inside a built wheel or sdist.

Two rules, and neither of them is a list of filenames.

**Nothing the repository does not track**, except what the build system
writes into a distribution itself. A file that is ignored here is one
somebody decided does not belong to the project, and a build that picks
one up has reached past the tree into the working directory. Asked of
`git check-ignore` rather than of a list, so this file names nothing it
refuses -- the list already exists, in one place, and a second copy of it
would be a second place to keep right.

**Not the battery-passport indexes.** Those are a repository
publication, not a Python payload: fifteen thousand lines of JSON in an
install serve nobody, the gate that reads them skips cleanly when they
are absent, and their licences are attributed in the bundle's own README
rather than in this package's metadata. Shipping them would put a
redistribution question inside a wheel to answer nothing.

Both are asked of what the archives actually contain, not of what the
packaging configuration says they should -- a sibling project shipped
its working notes in five sdists while its configuration said otherwise.

Run after `python -m build`. Exits 1 and names every offending member.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tarfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

#: Tracked, published here, and deliberately not shipped.
NOT_A_PAYLOAD = "data/battery-passport/"

#: What the build system writes into a distribution itself. These are
#: ignored in the tree -- they are outputs -- and belong in an sdist all
#: the same: the packaging standards name them, and a source archive
#: without its metadata is not a source archive. Named by what they are
#: rather than left to the ignore rule, because "ignored" answers a
#: question about the working tree and this one is about the artifact.
BUILD_METADATA = (".egg-info", ".dist-info", "PKG-INFO")


def _is_build_metadata(inner: str) -> bool:
    """By path segment, not by substring. The directory arrives as its own
    member without a trailing slash, so a check for `".egg-info/" in path`
    passes over every file inside it and reports the directory."""
    return any(part.endswith(BUILD_METADATA) for part in inner.split("/"))


def members(artifact: pathlib.Path) -> list:
    """(name in the archive, path relative to the repository)."""
    if artifact.name.endswith(".tar.gz"):
        with tarfile.open(artifact) as archive:
            names = archive.getnames()
        # An sdist puts everything under one top directory named for the
        # distribution; strip it so a repository path matches either kind.
        return [(name, name.split("/", 1)[-1]) for name in names]
    with zipfile.ZipFile(artifact) as archive:
        return [(name, name) for name in archive.namelist()]


def ignored(paths) -> set:
    """The subset git would refuse to track. One call, not one per file:
    `check-ignore` reads them from stdin and answers only for the ones it
    matched, so a tree without git or without a match answers nothing and
    this returns the empty set rather than guessing."""
    paths = [p for p in paths if p and not p.endswith("/")]
    if not paths:
        return set()
    result = subprocess.run(["git", "check-ignore", "--stdin"],
                            cwd=ROOT, input="\n".join(paths),
                            capture_output=True, text=True)
    if result.returncode not in (0, 1):      # 1 is "nothing matched"
        print("distribution: git could not be asked what is ignored (%s); "
              "the tracked-files rule did not run"
              % (result.stderr.strip() or "no git here"), file=sys.stderr)
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def main() -> int:
    if not DIST.is_dir():
        print("no dist/ -- build the distributions first", file=sys.stderr)
        return 1
    artifacts = sorted(p for p in DIST.iterdir()
                       if p.suffix == ".whl" or p.name.endswith(".tar.gz"))
    if not artifacts:
        print("no distributions in dist/ -- build them first", file=sys.stderr)
        return 1

    problems = []
    for artifact in artifacts:
        contents = members(artifact)
        untracked = ignored(inner for _name, inner in contents)
        for name, inner in contents:
            if inner.startswith(NOT_A_PAYLOAD) or inner == NOT_A_PAYLOAD.rstrip("/"):
                problems.append("%s carries %s -- the requirements indexes are a "
                                "repository publication, not a Python payload"
                                % (artifact.name, name))
            elif _is_build_metadata(inner):
                continue
            elif inner in untracked:
                problems.append("%s carries %s -- this repository does not track it"
                                % (artifact.name, name))
    for problem in problems:
        print("distribution: %s" % problem, file=sys.stderr)
    if problems:
        return 1
    print("distributions: %d checked, neither carries what it must not"
          % len(artifacts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
