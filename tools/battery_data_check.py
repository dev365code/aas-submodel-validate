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


def _check_join(known, provenance, problems) -> None:
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

    declared = join.get("indexes", {})
    # Over the four this checker knows, not over what the join declares.
    # Iterating the join's own keys meant a join that simply omits an
    # index -- the shape a half-finished regeneration leaves -- passed,
    # and the summary line said all four agreed.
    for filename in INDEXES:
        name = filename[len("requirements-"):-len(".json")]
        name = "idta-smt" if name == "idta" else name
        index = declared.get(name)
        if index is None:
            problems.append("%s: declares no %s" % (JOIN, name))
            continue
        if index.get("records") != len(known[filename]):
            problems.append("%s: says %s holds %s records, it holds %d"
                            % (JOIN, filename, index.get("records"), len(known[filename])))
        # And the pins. `requirements-join.md` prints these digests in a
        # source table a reader is invited to check, and nothing compared
        # them to anything: re-pin a source, update the index and the
        # ledger, forget the join, and the published page kept quoting
        # the old digest with every gate green. That is the exact
        # sequence this repository ran a day earlier.
        theirs = {p["file"]: p["sha256"] for p in provenance[filename]}
        for entry in index.get("provenance", []):
            source, digest = entry.get("file"), entry.get("sha256")
            if theirs.get(source) != digest:
                problems.append("%s: pins %s at %s..., %s says %s..."
                                % (JOIN, source, str(digest)[:12], filename,
                                   str(theirs.get(source))[:12]))
        for source in theirs:
            if source not in {e.get("file") for e in index.get("provenance", [])}:
                problems.append("%s: %s pins %s and the join does not carry it"
                                % (JOIN, filename, source))
    for name in declared:
        if name not in {"idta-smt"} | {f[len("requirements-"):-len(".json")] for f in INDEXES}:
            problems.append("%s: names an index this checker does not know: %s" % (JOIN, name))

    # Every record id the join hands a reader has to exist. A stale id in
    # a published table is a reader following a reference to nothing.
    # All six lists, not the two in the coverage table: the other four are
    # equally published and were walked by nothing.
    ELEMENTS = "requirements-idta.json"
    for point in join.get("annex_coverage", []):
        where = point.get("annex_point")
        reached = point.get("reached_by_a_broader_citation", {})
        for field, filename in _JOIN_REFERS_TO.items():
            for record_id in list(point.get(field, [])) + list(reached.get(field, [])):
                if record_id not in known[filename]:
                    problems.append("%s: %s cites %s, which no index carries"
                                    % (JOIN, where, record_id))
    for match in join.get("name_matches", []):
        if match.get("element") not in known[ELEMENTS]:
            problems.append("%s: name_matches names %s, which no index carries"
                            % (JOIN, match.get("element")))
        for field, filename in _JOIN_REFERS_TO.items():
            for record_id in match.get(field, []):
                if record_id not in known[filename]:
                    problems.append("%s: %s matches %s, which no index carries"
                                    % (JOIN, match.get("element"), record_id))
    for element in join.get("template_elements_matched_by_nothing", []):
        if element not in known[ELEMENTS]:
            problems.append("%s: unmatched list names %s, which no index carries"
                            % (JOIN, element))
    for entry in join.get("readings_that_differ_by_name", []):
        if entry.get("element") not in known[ELEMENTS]:
            problems.append("%s: readings_that_differ_by_name names %s, which no index carries"
                            % (JOIN, entry.get("element")))
    every_record = known["requirements-ec-datapoints.json"] | known["requirements-longlist.json"]
    for entry in join.get("readings_that_differ_by_citation", []):
        for ids in entry.get("readings", {}).values():
            for record_id in ids:
                if record_id not in every_record:
                    problems.append("%s: %s lists %s, which no index carries"
                                    % (JOIN, entry.get("citation"), record_id))
    for entry in join.get("citations_without_a_matching_annex_point", []):
        if entry.get("cited_by") not in every_record:
            problems.append("%s: an unresolved citation is credited to %s, which no index carries"
                            % (JOIN, entry.get("cited_by")))

    # A count is a promise about a list in the same file.
    counts = join.get("counts")
    if not isinstance(counts, dict):
        problems.append("%s: carries no counts" % JOIN)
        counts = {}
    for count, field in (
        ("annex_points", "annex_coverage"),
        ("template_elements_matched_by_name", "name_matches"),
        ("template_elements_matched_by_nothing", "template_elements_matched_by_nothing"),
        ("name_matches_where_the_readings_differ", "readings_that_differ_by_name"),
        ("citations_where_the_readings_differ", "readings_that_differ_by_citation"),
        ("citations_unresolved_in_consolidated_text", "citations_without_a_matching_annex_point"),
    ):
        stated, listed = counts.get(count), join.get(field)
        if listed is None:
            problems.append("%s: counts %s and carries no %s" % (JOIN, count, field))
        elif stated != len(listed):
            problems.append("%s: counts.%s says %s, %s holds %d"
                            % (JOIN, count, stated, field, len(listed)))

    # And the counts computed from the lists rather than from the
    # generator. Five of them were paired with nothing at all, so a join
    # could say no annex point lacks a restatement, or that every
    # longlist row matched, and both gates passed.
    coverage = join.get("annex_coverage", [])

    def _broader(point):
        reached = point.get("reached_by_a_broader_citation", {})
        return bool(reached.get("ec_datapoints") or reached.get("longlist_rows"))

    for count, measured in (
        ("annex_points_with_a_guidance_data_point",
         sum(1 for a in coverage if a.get("ec_datapoints"))),
        ("annex_points_with_a_longlist_row",
         sum(1 for a in coverage if a.get("longlist_rows"))),
        ("annex_points_with_neither",
         sum(1 for a in coverage if not a.get("ec_datapoints") and not a.get("longlist_rows"))),
        ("annex_points_named_only_through_their_parent",
         sum(1 for a in coverage if a.get("cited_only_through_its_parent"))),
        ("annex_points_a_broader_citation_reaches_without_naming",
         sum(1 for a in coverage if _broader(a))),
        ("longlist_rows_matched_by_name",
         len({i for m in join.get("name_matches", []) for i in m.get("longlist_rows", [])})),
        ("guidance_data_points_matched_by_name",
         len({i for m in join.get("name_matches", []) for i in m.get("ec_datapoints", [])})),
    ):
        if counts.get(count) != measured:
            problems.append("%s: counts.%s says %s, the lists give %d"
                            % (JOIN, count, counts.get(count), measured))


def main() -> int:
    survive()
    if not DATA.is_dir():
        print("battery-data: no data/battery-passport in this tree "
              "(an sdist ships the checker, not the data); nothing to check")
        return 0
    problems = []
    ledger = _ledger(problems)
    known = {}
    provenance = {}

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
        provenance[name] = index["provenance"]
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

    _check_join(known, provenance, problems)

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
