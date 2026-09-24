#!/usr/bin/env python3
"""The whole report for one package, kept as a file a diff can be read from.

    python3 tools/golden_report.py            # write it
    python3 tools/golden_report.py --check    # it still says what the tool says

`tests/test_report_schema_doc.py` holds the report's shape against its
page: every key the report emits is described there, and nothing else
is. It does not catch a value quietly becoming another -- a severity
respelled, a grade moving, a remedy losing a clause, a record leaving
`scopeNotExamined` -- because no test reads a whole report at once.

So one whole report is a file, `docs/golden-report.json`: what `-f json`
says about a package this script builds from `tests/builders.py`, and
builds the same way on every machine -- fixed timestamps, one host
system, stored rather than compressed -- so the report's `inputSha256`
is a fact about the fixture and not about the zlib that wrote it. The
document inside is metamodel-clean on purpose. Every finding in the
report is this project's own, so the file moves when this project's
output does, and not on the day the upstream metamodel library words a
message it relays differently.

One field is a marker rather than pinned: `toolVersion`, which every
release moves and the release job holds against the package, the build
configuration, the tag and the changelog.
"""
from __future__ import annotations

import argparse
import json
import pathlib as _pathlib
import subprocess
import sys
import sys as _sys
import tempfile
import zipfile
from pathlib import Path

# The package, from wherever this script is, as the other tools find it.
_TOOLS_SRC = str(_pathlib.Path(__file__).resolve().parent.parent / "src")
if _TOOLS_SRC not in _sys.path:
    _sys.path.insert(0, _TOOLS_SRC)

from aas_submodel_validate._terminal import survive  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# The fixture is the suite's own: `tests/builders.py` ships in the sdist
# beside this script, as `verdict_diff.py` already relies on.
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))
GOLDEN = ROOT / "docs" / "golden-report.json"
PACKAGE = "golden.aasx"

#: Replaced rather than pinned, with the reason a reader needs.
MOVING = {
    ("toolVersion",): "<the release that ran it; moves with every release>",
}

#: The one timestamp every entry carries. ZIP cannot say 1970, and a
#: timestamp taken from the clock made the archive's bytes, and so its
#: digest in the report, a fact about the minute it was built.
_WHEN = (1980, 1, 1, 0, 0, 0)


def _environment() -> dict:
    """The 02004 golden fixture with three defects of this project's own
    to report, one of each shape a reader meets most: a File value naming
    a part the package holds under another folder, a mandatory element
    left out, and a list whose identifier is one version suffix off."""
    from builders import hd_env

    environment = hd_env()
    document = environment["submodels"][0]["submodelElements"][0]["value"][0]
    lists = {element["idShort"]: element for element in document["value"]}
    version = lists["DocumentVersions"]["value"][0]
    version["value"] = [element for element in version["value"]
                        if element.get("idShort") != "Version"]
    files = next(element for element in version["value"]
                 if element.get("idShort") == "DigitalFiles")
    files["value"][0]["value"] = "/aasx/documents/manual.pdf"
    lists["DocumentClassifications"]["semanticId"]["keys"][0]["value"] = \
        "0173-1#02-ABI502#004"
    return environment


def build(directory: Path) -> Path:
    """The package, written the same way on every machine."""
    from builders import CONTENT_TYPES, ORIGIN_REL, SPEC_REL, SUPPL_REL, rels

    payload = json.dumps(_environment(), indent=1, sort_keys=True).encode("utf-8")
    parts = [
        ("[Content_Types].xml", CONTENT_TYPES),
        ("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")])),
        ("aasx/aasx-origin", b""),
        ("aasx/_rels/aasx-origin.rels", rels([(SPEC_REL, "/aasx/env.json")])),
        ("aasx/env.json", payload),
        ("aasx/files/manual.pdf", b"%PDF-1.4\n% the golden report's manual\n%%EOF\n"),
        ("aasx/_rels/env.json.rels", rels([(SUPPL_REL, "/aasx/files/manual.pdf")])),
    ]
    path = directory / PACKAGE
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
        for name, data in parts:
            info = zipfile.ZipInfo(name, date_time=_WHEN)
            # The host system is written into every entry, and it is the
            # machine's by default: a Windows runner built other bytes.
            info.create_system = 3
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, data)
    return path


def report() -> dict:
    """What `-f json` says about the package, from this tree."""
    # This tree's package, put first on the path by the child itself and
    # asked where it came from. Handed over in PYTHONPATH it was split on
    # the path separator, so a checkout whose path holds one ran whatever
    # release was installed instead -- and said nothing.
    here = str(ROOT / "src")
    child = ("import os, sys; sys.path.insert(0, sys.argv[1]); "
             "import aas_submodel_validate as package; "
             "got = os.path.realpath(package.__file__); "
             "assert got.startswith(os.path.realpath(sys.argv[1]) + os.sep), "
             "'this tree was not the package imported: ' + got; "
             "from aas_submodel_validate.cli import main; sys.exit(main(sys.argv[2:]))")
    with tempfile.TemporaryDirectory() as scratch:
        build(Path(scratch))
        done = subprocess.run([sys.executable, "-c", child, here, "-f", "json", PACKAGE],
                              cwd=scratch, capture_output=True)
    # 0 is a clean package and 1 one with findings; anything else, and
    # whatever is on stdout is not a report. Said as a sentence, because a
    # gate that ends in a traceback is a gate whose failure nobody reads.
    stdout = done.stdout.decode("utf-8", "replace")
    if done.returncode not in (0, 1) or not stdout.strip():
        stderr = done.stderr.decode("utf-8", "replace").strip()
        raise SystemExit("the validator gave no report for %s (exit %d): %s"
                         % (PACKAGE, done.returncode,
                            stderr.splitlines()[-1] if stderr else "nothing on stderr either"))
    try:
        document = json.loads(stdout)
    except ValueError as exc:
        raise SystemExit("the validator's output for %s is not JSON: %s"
                         % (PACKAGE, exc)) from exc
    for path, marker in MOVING.items():
        node = document
        for step in path[:-1]:
            node = node.get(step) if isinstance(node, dict) else None
        if isinstance(node, dict) and path[-1] in node:
            node[path[-1]] = marker
    return document


def rendered(document: dict) -> str:
    return json.dumps(document, indent=1, sort_keys=True) + "\n"


def main(argv=None) -> int:
    survive()
    parser = argparse.ArgumentParser(description="the whole report for one package")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    fresh = rendered(report())
    if not args.check:
        GOLDEN.write_text(fresh, encoding="utf-8")
        print("%s: written" % GOLDEN.relative_to(ROOT))
        return 0
    if not GOLDEN.exists():
        print("%s does not exist; run tools/golden_report.py"
              % GOLDEN.relative_to(ROOT), file=sys.stderr)
        return 1
    stored = GOLDEN.read_text(encoding="utf-8")
    if stored == fresh:
        print("the stored report is the one this tree produces")
        return 0

    import difflib
    diff = list(difflib.unified_diff(stored.splitlines(True), fresh.splitlines(True),
                                     fromfile="docs/golden-report.json",
                                     tofile="what this tree says", n=2))
    sys.stderr.writelines(diff[:60])
    if len(diff) > 60:
        print("... %d more lines" % (len(diff) - 60), file=sys.stderr)
    print("the report for %s is not what is stored. If the change is meant, "
          "`python3 tools/golden_report.py` writes it, and the diff above is "
          "what a consumer's parser sees move." % PACKAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
