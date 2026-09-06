"""The battery-passport indexes agree with themselves, offline.

`data/battery-passport/` holds indexes derived from four canonical
sources this repository does not mirror -- the pins live in
`sources.sha256`, and anyone can re-fetch the originals and re-run the
extractors (`data/battery-passport/tools/REGENERATE.txt`). That
regeneration is the real gate and it needs the network, so it is for
whoever has one -- no job runs it today, and this sentence will say so
until one does. A checkout settles for what the files can prove about
each other. Four things, none of which needs a byte of source:

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
  and both the CI job and the release job install them, so the full
  check runs wherever it matters. Measured: without them this reports
  two skips and still exits 0 -- which is the right behaviour for a
  contributor's laptop and the wrong one for a release, so the release
  installs them rather than relying on this.

An sdist carries this file and not the data directory it checks --
shipping fifteen thousand lines of indexes in a Python source archive
serves nobody -- so outside a repository checkout the gate reports that
there is nothing here to check and passes, rather than failing `make
check` over content the tree never had.
"""
from __future__ import annotations

import json
import pathlib as _pathlib
import py_compile
import re
import sys
import sys as _sys
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

DATA = Path(__file__).resolve().parents[1] / "data" / "battery-passport"
INDEXES = ("requirements-annex-xiii.json", "requirements-ec-datapoints.json",
           "requirements-longlist.json", "requirements-idta.json")
#: The join is derived from the four above and is published beside them,
#: in JSON and as a table people read. Nothing checked it: this gate
#: counted four files in a directory that generates six, and the two it
#: skipped are the two a reader opens first. A join can go stale on its
#: own -- an index regenerated without it, a record id that no longer
#: exists -- and neither shows up in any check of the four.
JOIN = "requirements-join.json"
#: Which index each list of record ids in the join is drawn from.
_JOIN_REFERS_TO = {
    "ec_datapoints": "requirements-ec-datapoints.json",
    "longlist_rows": "requirements-longlist.json",
}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
#: Third-party readers the extractors need and this project does not
#: depend on. Anything else failing to import is a defect, not a skip.
_OPTIONAL = ("openpyxl", "fitz", "pymupdf")


def _ledger(problems) -> dict:
    """Every pin in the ledger, and a problem for every line that is not
    one. All lines, not just the referenced ones: ten of the twenty-five
    pins are for sources no index cites directly, and a malformed pin
    among them was invisible -- the ledger's own promise is that each
    line verifies a fetch, referenced or not."""
    pins = {}
    for line in (DATA / "sources.sha256").read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, sep, name = line.partition("  ")
        if not sep or not _HEX64.match(digest.strip()) or not name.strip():
            problems.append("sources.sha256: not a pin: %r" % line[:60])
            continue
        pins[name.strip()] = digest.strip()
    return pins


def _check_join(known, problems) -> None:
    """The join, against the four indexes it was built from.

    A different question from the one `tests/test_battery_public_claims.py`
    asks. That file checks what the README and the divergence list *say*;
    this checks whether the derived file still matches its inputs. The
    case that separates them: regenerate an index and not the join, and
    the join stays perfectly self-consistent -- every count matching
    every list, every claim about itself true -- while describing a file
    that no longer exists. Nothing but a comparison against the inputs
    can see that.
    """
    path = DATA / JOIN
    if not path.is_file():
        problems.append("%s is missing" % JOIN)
        return
    join = json.loads(path.read_text("utf-8"))

    for name, index in join.get("indexes", {}).items():
        filename = "requirements-%s.json" % name.replace("idta-smt", "idta")
        if filename not in known:
            problems.append("%s: names an index this checker does not know: %s" % (JOIN, name))
        elif index.get("records") != len(known[filename]):
            problems.append("%s: says %s holds %s records, it holds %d"
                            % (JOIN, filename, index.get("records"), len(known[filename])))

    # Every record id the join hands a reader has to exist. A stale id in
    # a published table is a reader following a reference to nothing.
    for point in join.get("annex_coverage", []):
        buckets = [(k, point.get(k, [])) for k in _JOIN_REFERS_TO]
        reached = point.get("reached_by_a_broader_citation", {})
        buckets += [(k, reached.get(k, [])) for k in _JOIN_REFERS_TO]
        for field, ids in buckets:
            for record_id in ids:
                if record_id not in known[_JOIN_REFERS_TO[field]]:
                    problems.append("%s: %s cites %s, which no index carries"
                                    % (JOIN, point.get("annex_point"), record_id))

    # A count is a promise about a list in the same file.
    for count, field in (
        ("annex_points", "annex_coverage"),
        ("template_elements_matched_by_name", "name_matches"),
        ("template_elements_matched_by_nothing", "template_elements_matched_by_nothing"),
        ("name_matches_where_the_readings_differ", "readings_that_differ_by_name"),
        ("citations_where_the_readings_differ", "readings_that_differ_by_citation"),
        ("citations_unresolved_in_consolidated_text", "citations_without_a_matching_annex_point"),
    ):
        stated, listed = join["counts"].get(count), join.get(field)
        if listed is None:
            problems.append("%s: counts %s and carries no %s" % (JOIN, count, field))
        elif stated != len(listed):
            problems.append("%s: counts.%s says %s, %s holds %d"
                            % (JOIN, count, stated, field, len(listed)))


def main() -> int:
    survive()
    if not DATA.is_dir():
        print("battery-data: no data/battery-passport in this tree "
              "(an sdist ships the checker, not the data); nothing to check")
        return 0
    problems = []
    ledger = _ledger(problems)
    known = {}

    for name in INDEXES:
        index = json.loads((DATA / name).read_text("utf-8"))
        records = index["records"]
        counted = index["counts"]["records"]
        if counted != len(records):
            problems.append("%s: counts.records says %d, file holds %d"
                            % (name, counted, len(records)))
        # `.get`, because a record without an id is this checker's finding
        # to report, not its crash to raise -- the first version raised a
        # KeyError here, which turns a defect in the data into a defect
        # in the gate.
        ids = [record.get("id") for record in records]
        known[name] = {i for i in ids if i}
        for position, record_id in enumerate(ids):
            if not record_id:
                problems.append("%s: records[%d] carries no id" % (name, position))
        for duplicate in sorted({i for i in ids if i and ids.count(i) > 1}):
            problems.append("%s: id %r appears more than once" % (name, duplicate))
        for entry in index["provenance"]:
            digest, source = entry.get("sha256", ""), entry.get("file")
            if not source:
                problems.append("%s: a provenance entry names no file" % name)
            elif not _HEX64.match(digest):
                problems.append("%s: provenance for %s pins %r, not a sha256"
                                % (name, source, digest))
            elif ledger.get(source) != digest:
                problems.append("%s: provenance pins %s at %s..., the ledger says %s"
                                % (name, source, digest[:12],
                                   (ledger.get(source) or "nothing")[:12]))

    _check_join(known, problems)

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
        print("battery-data: %d indexes agree with themselves and the ledger, "
              "and the join agrees with all four"
              % len(INDEXES))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
