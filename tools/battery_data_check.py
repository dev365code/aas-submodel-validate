"""The battery-passport indexes agree with themselves, offline.

`data/battery-passport/` holds indexes derived from four canonical
sources this repository does not mirror -- the pins live in
`sources.sha256`, and anyone can re-fetch the originals and re-run the
extractors (`data/battery-passport/tools/REGENERATE.txt`). That
regeneration is the real gate and it needs the network, so it runs in a
scheduled job; a checkout has to settle for what the files can prove
about each other. Four things, none of which needs a byte of source:

- every index's own `counts.records` equals the number of records it
  carries, so a count quoted from the header is the count;
- record ids are unique within an index (the extractors assert this too
  -- the same gate in two places, on purpose);
- every provenance entry pins a 64-hex sha256, and the same file is in
  the ledger beside it under the same hash -- an index cannot claim a
  source the ledger does not carry;
- the extractor scripts still parse and import. Two of them need
  third-party readers (`openpyxl`, `pymupdf`) this project does not
  depend on; where those are absent the import is reported and skipped,
  and CI installs them so the full check runs somewhere on every push.
"""
from __future__ import annotations

import json
import py_compile
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "battery-passport"
INDEXES = ("requirements-annex-xiii.json", "requirements-ec-datapoints.json",
           "requirements-longlist.json", "requirements-idta.json")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
#: Third-party readers the extractors need and this project does not
#: depend on. Anything else failing to import is a defect, not a skip.
_OPTIONAL = ("openpyxl", "fitz", "pymupdf")


def _ledger() -> dict:
    pins = {}
    for line in (DATA / "sources.sha256").read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, name = line.partition("  ")
        pins[name.strip()] = digest.strip()
    return pins


def main() -> int:
    problems = []
    ledger = _ledger()

    for name in INDEXES:
        index = json.loads((DATA / name).read_text("utf-8"))
        records = index["records"]
        counted = index["counts"]["records"]
        if counted != len(records):
            problems.append("%s: counts.records says %d, file holds %d"
                            % (name, counted, len(records)))
        ids = [record["id"] for record in records]
        for duplicate in sorted({i for i in ids if ids.count(i) > 1}):
            problems.append("%s: id %r appears more than once" % (name, duplicate))
        for entry in index["provenance"]:
            digest, source = entry["sha256"], entry["file"]
            if not _HEX64.match(digest):
                problems.append("%s: provenance for %s pins %r, not a sha256"
                                % (name, source, digest))
            elif ledger.get(source) != digest:
                problems.append("%s: provenance pins %s at %s..., the ledger says %s"
                                % (name, source, digest[:12],
                                   (ledger.get(source) or "nothing")[:12]))

    skipped = []
    sys.path.insert(0, str(DATA / "tools"))
    for script in sorted((DATA / "tools").glob("*.py")):
        try:
            py_compile.compile(str(script), doraise=True)
        except py_compile.PyCompileError as error:
            problems.append("%s does not parse: %s" % (script.name, error.msg))
            continue
        try:
            __import__(script.stem)
        except ModuleNotFoundError as error:
            if error.name in _OPTIONAL:
                skipped.append("%s (needs %s)" % (script.name, error.name))
            else:
                problems.append("%s imports nothing named %r"
                                % (script.name, error.name))
        except Exception as error:  # noqa: BLE001 - any import failure is the finding
            problems.append("%s fails to import: %s: %s"
                            % (script.name, type(error).__name__, error))

    for problem in problems:
        print("battery-data: %s" % problem, file=sys.stderr)
    if skipped:
        print("battery-data: import skipped for %s -- CI runs them"
              % ", ".join(skipped))
    if not problems:
        print("battery-data: %d indexes agree with themselves and the ledger"
              % len(INDEXES))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
