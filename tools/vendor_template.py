#!/usr/bin/env python3
"""Vendor the official IDTA material this project validates against.

Everything comes from admin-shell-io/submodel-templates (CC BY 4.0) at
one pinned commit, and every vendored byte is recorded in a sha256sums
file beside it. `--check` verifies the recorded hashes offline on every
CI run, and sweeps the vendored trees for anything no entry names --
the hash gate reads a list, and a file missing from that list is a file
it silently approves; `--refresh` re-fetches from the pin (the one operation that
needs the network). The pin moves only by editing COMMIT here, on
purpose, in a commit that says why.
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib as _pathlib
import sys
import sys as _sys
import urllib.parse
import urllib.request
from pathlib import Path

# The package, from wherever this script is. `make` exports
# PYTHONPATH and the lint job installs the package first, but
# CI's wheel job installs nothing and an unpacked sdist has no
# install at all -- and `MANIFEST.in` grafts this directory for
# exactly that reader. Two scripts here already did this; the
# import added to all eight assumed the other six were as
# lucky.
_TOOLS_SRC = str(_pathlib.Path(__file__).resolve().parent.parent / "src")
if _TOOLS_SRC not in _sys.path:
    _sys.path.insert(0, _TOOLS_SRC)

from aas_submodel_validate._terminal import survive  # noqa: E402

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
    # 02035-2 is the Digital Battery Passport's part 2 and a *second*
    # Handover Documentation template: the same submodel semanticId as
    # 02004, different requirements. Upstream publishes it twice in this
    # directory and the "_without_examplevalues" twin is not what its name
    # says -- it keeps all twelve ExampleValue qualifiers and differs by one
    # Property value and a final newline (docs/divergences.md #25). This is
    # the published file.
    "src/aas_submodel_validate/data/smt/02035-2/1.0/template.json":
        "published/Digital Battery Passport/2_Handover Documentation/1/0/"
        "IDTA 02035-2_DBP-Part-2_HandoverDocumentation.json",
    "tests/corpus/idta/02004/example.json":
        "published/Handover Documentation/2/0/"
        "IDTA 02004-2-0_Example_HandoverDocumentation.json",
    "src/aas_submodel_validate/data/example/idta-02004-2.0.aasx":
        "published/Handover Documentation/2/0/"
        "IDTA 02004-2-0_Example_HandoverDocumentation.aasx",
    # Upstream publishes a 2.0.1 "template sample" for metamodel 3.1 -- a
    # template (kind Template) whatever its name says, in the 3/1 XML
    # namespace. This reader parses 3.0 and refuses it (X3); it is kept as
    # the witness of that refusal (the corpus README says why).
    "tests/corpus/idta/02004/template-sample-2.0.1-for-aas-3.1.aasx":
        "published/Handover Documentation/2/0/1/"
        "IDTA 02004-2-0-1_Template_sample_HandoverDocumentation_forAASMetamodelV3.1.aasx",
    # 02003 publishes its sample twice: once beside the 2.0 template and
    # again, repaired, beside the 2.0.1 one. Both are kept -- the pair is
    # the evidence for what upstream itself considered wrong.
    "tests/corpus/idta/02003/sample-2.0.json":
        "published/Technical_Data/2/0/IDTA 02003_Sample_TechnicalData.json",
    "tests/corpus/idta/02003/sample-2.0.aasx":
        "published/Technical_Data/2/0/IDTA 02003_Sample_TechnicalData.aasx",
    "tests/corpus/idta/02003/sample-2.0.1.aasx":
        "published/Technical_Data/2/0/1/IDTA 02003_Sample_TechnicalData.aasx",
    # And a third time, beside the second, for metamodel 3.1: refused (X3),
    # kept as a witness, like the 02004 one above.
    "tests/corpus/idta/02003/sample-2.0.1-for-aas-3.1.aasx":
        "published/Technical_Data/2/0/1/"
        "IDTA 02003_Sample_TechnicalData_forAASMetamodelV3.1.aasx",
    # 02006 2.0's sample, which upstream has moved under deprecated/: an AAS
    # 2.0 package, whose relationship types this reader does not follow
    # (X2). Kept as a witness of that.
    "tests/corpus/idta/02006/sample-2.0.aasx":
        "deprecated/Digital nameplate/2/0/"
        "IDTA 02006-2-0_Sample Digital Nameplate.aasx",
    "src/aas_submodel_validate/data/smt/02006/3.0/template.json":
        "published/Digital nameplate/3/0/"
        "IDTA 02006-3-0_Template_Digital Nameplate.json",
    "src/aas_submodel_validate/data/smt/02023/1.0/template.json":
        "published/Carbon Footprint/1/0/"
        "IDTA 02023 _Template_CarbonFootprint.json",
    # 02002 is published at 1.0 and again at 1.0.1, and 1.0.1 is the one
    # this project reads: 1.0 gives `IPCommunication` the submodel's own
    # identifier, which 1.0.1 repairs (docs/divergences.md). Upstream
    # publishes the 1.0.1 JSON twice, under this name and under a
    # "_forAASMetamodelV3.1" one, and the two are byte-identical -- one
    # sha256 under two names, unlike 02035-2's twin above, whose name
    # promised a difference it did not keep (#25). There is no choice to
    # make; this entry records which name the bytes were taken from.
    "src/aas_submodel_validate/data/smt/02002/1.0.1/template.json":
        "published/Contact Information/1/0/1/"
        "IDTA 02002-1-0-1_Template_ContactInformation.json",
    # 02011's `Node` holds a `Node` of its own identifier, to any depth, and
    # the template writes that out one level down and stops
    # (docs/divergences.md #48). 1.1.1 is the newest edition at the pin.
    "src/aas_submodel_validate/data/smt/02011/1.1.1/template.json":
        "published/Hierarchical Structures enabling Bills of Material/1/1/1/"
        "IDTA 02011-1-1-1_Template_HSEBoM.json",
    # 02007 is published at 1.0 and at 1.0.1; 1.0.1 is the newest at the
    # pin. Like 02002's, its JSON is published twice, under this name and
    # under a "_forAASMetamodelV3.1" one, and the two are byte-identical.
    # Its `Contact` collection is 02002's `ContactInformation` copied in,
    # and it carries 02002's defects with it (docs/divergences.md #51).
    "src/aas_submodel_validate/data/smt/02007/1.0.1/template.json":
        "published/Software Nameplate/1/0/1/"
        "IDTA 02007-1-0-1_Template_Software Nameplate.json",
    # 02035-5 is the Digital Battery Passport's part 5, Product Condition,
    # published at 1.0, 1.0.1 and 1.0.2; 1.0.2 is the newest at the pin,
    # and the edition the battery-data layer already reads. Its directory
    # holds no README and names the JSON by its version. Every identifier
    # is a SAMM URN whose version moved with each release (1.0.0, 1.0.1,
    # 1.0.2 -- the specification's Annex B says so of 1.0.2).
    "src/aas_submodel_validate/data/smt/02035-5/1.0.2/template.json":
        "published/Digital Battery Passport/5_Product Condition/1/0/2/"
        "IDTA 02035-5_DBP-Part-5_ProductCondition_V1.0.2.json",
}


#: Directories that hold nothing but vendored material. `--check` walks
#: FILES, so a file no entry names is invisible to it -- and still ships,
#: because `pyproject.toml`'s package-data globs on path, not on this
#: list. Sweeping these trees is how the two stay the same set.
VENDORED_TREES = ("src/aas_submodel_validate/data/smt",
                  "src/aas_submodel_validate/data/example",
                  "tests/corpus/idta")

#: What those trees hold that is ours rather than upstream's: the gate's
#: own record, and the note that says where the corpus came from.
OURS = ("sha256sums.txt", "README.md")


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


def undeclared() -> list:
    """Files under VENDORED_TREES that no FILES entry names.

    Not an error the moment it happens -- a file arrives before its entry
    in the seconds between two edits -- but an error by the time a gate
    is asked whether the vendored material is verified, because for this
    one it never answered.
    """
    declared = {ROOT / rel for rel in FILES}
    found = []
    for tree in VENDORED_TREES:
        root = ROOT / tree
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.name not in OURS and path not in declared:
                found.append(path.relative_to(ROOT).as_posix())
    return found


def check() -> int:
    bad = 0
    for stray in undeclared():
        print("vendored but not declared in FILES: %s (its bytes ship and "
              "nothing records their hash)" % stray, file=sys.stderr)
        bad = 1
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
        print("vendored material matches its recorded hashes, and the trees "
              "hold nothing else (%d files, pin %s)" % (len(FILES), COMMIT[:12]))
    return bad


def main() -> int:
    survive()
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--refresh", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    return refresh() if args.refresh else check()


if __name__ == "__main__":
    sys.exit(main())
