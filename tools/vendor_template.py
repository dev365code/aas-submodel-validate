#!/usr/bin/env python3
"""Vendor the official IDTA material this project validates against.

Everything comes from admin-shell-io/submodel-templates (CC BY 4.0) at
one pinned commit, and every vendored byte is recorded in a sha256sums
file beside it. `--check` verifies the recorded hashes offline on every
CI run; `--refresh` re-fetches from the pin (the one operation that
needs the network). The pin moves only by editing COMMIT here, on
purpose, in a commit that says why.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REPO = "admin-shell-io/submodel-templates"
COMMIT = "11ef3353124626e2dba4cb50767024df9a39928a"

#: destination (repo-relative) -> source (repo-relative in the upstream repo)
#:
#: Written out in full rather than joined to a shared prefix: the upstream
#: paths do not share one. They disagree about hyphens and underscores
#: ("IDTA 02004-2-0-1_Template..." against "IDTA 02003_2-0-1_Template..."),
#: about where the version sits in the tree, and one of them holds two
#: spaces in a directory name. A prefix that fits both would hide exactly
#: the detail somebody has to check against upstream.
FILES = {
    "src/aas_submodel_validate/data/smt/02004/2.0.1/template.json":
        "published/Handover Documentation/2/0/1/"
        "IDTA 02004-2-0-1_Template_HandoverDocumentation.json",
    "src/aas_submodel_validate/data/smt/02003/2.0.1/template.json":
        "published/Technical_Data/2/0/1/"
        "IDTA 02003_2-0-1_Template_TechnicalData.json",
    "tests/corpus/idta/example.json":
        "published/Handover Documentation/2/0/"
        "IDTA 02004-2-0_Example_HandoverDocumentation.json",
    "tests/corpus/idta/example.aasx":
        "published/Handover Documentation/2/0/"
        "IDTA 02004-2-0_Example_HandoverDocumentation.aasx",
}


def _url(source: str) -> str:
    return ("https://raw.githubusercontent.com/%s/%s/%s"
            % (REPO, COMMIT, urllib.parse.quote(source)))


def _sums_path(destination: Path) -> Path:
    return destination.parent / "sha256sums.txt"


def _record(destination: Path) -> None:
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    sums = _sums_path(destination)
    lines = [line for line in (sums.read_text("utf-8").splitlines() if sums.exists() else [])
             if not line.endswith("  " + destination.name)]
    lines.append("%s  %s" % (digest, destination.name))
    sums.write_text("\n".join(sorted(lines)) + "\n", "utf-8")


def refresh() -> int:
    for rel, source in FILES.items():
        destination = ROOT / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(_url(source)) as response:  # noqa: S310 - pinned https
            destination.write_bytes(response.read())
        _record(destination)
        print("vendored %s  (%d bytes)" % (rel, destination.stat().st_size))
    return 0


def check() -> int:
    bad = 0
    for rel in FILES:
        destination = ROOT / rel
        if not destination.exists():
            print("missing: %s (run tools/vendor_template.py --refresh)" % rel, file=sys.stderr)
            bad = 1
            continue
        recorded = {name: digest for line in _sums_path(destination).read_text("utf-8").splitlines()
                    for digest, _, name in [line.partition("  ")]}
        actual = hashlib.sha256(destination.read_bytes()).hexdigest()
        if recorded.get(destination.name) != actual:
            print("hash mismatch: %s" % rel, file=sys.stderr)
            bad = 1
    if not bad:
        print("vendored material matches its recorded hashes (%d files, pin %s)"
              % (len(FILES), COMMIT[:12]))
    return bad


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--refresh", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    return refresh() if args.refresh else check()


if __name__ == "__main__":
    sys.exit(main())
