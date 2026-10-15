"""The counts divergences #38 and #40 give, counted from this tree.

Both rows justify a reading by measuring published material -- how many
references stack keys and how often judging the official example meets
one, how many official properties carry no value and how many rows the
rule reaches -- and both kept the numbers of the files vendored when they
were written. The template pin moved, nine packs arrived, and the counts
went on describing an earlier tree; #40's property count did not describe
even the tree it was written in. They are counted here from the files
this tree holds, and the rows are held to the counts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "aas_submodel_validate" / "data"
EXAMPLE = DATA / "example" / "idta-02004-2.0.aasx"
TEMPLATES = sorted((DATA / "smt").glob("*/*/template.json"))
SAMPLES_02003 = [ROOT / "tests" / "corpus" / "idta" / "02003" / name
                 for name in ("sample-2.0.aasx", "sample-2.0.1.aasx", "sample-2.0.json")]
WORDS = {3: "three", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen",
         14: "fourteen", 15: "fifteen"}


def _row(number):
    """Row `number`'s two cells, each on one line as the table writes it."""
    for line in (ROOT / "docs" / "divergences.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("| %d | " % number):
            cells = line.strip().strip("|").split(" | ")
            assert len(cells) == 3, cells
            return cells[1], cells[2]
    raise AssertionError("divergences.md has no row #%d" % number)


def _environments(path):
    from aas_submodel_validate.loader import load
    loaded = load(path)
    try:
        return list(loaded.environments)
    finally:
        if loaded.container:
            loaded.container.close()


def _references(paths):
    """Every Reference in `paths`, with the attribute that holds it."""
    from aas_core3 import types
    for path in paths:
        for environment in _environments(path):
            for holder in [environment, *environment.descend()]:
                for name, value in vars(holder).items():
                    for reference in (value if isinstance(value, list) else [value]):
                        if isinstance(reference, types.Reference):
                            yield name.lstrip("_"), reference


def test_row_38_counts_the_references_of_the_files_it_names():
    left, _ = _row(38)
    held = list(_references([EXAMPLE, SAMPLES_02003[0], *TEMPLATES]))
    stacked = [(role, ref) for role, ref in held if len(ref.keys) > 1]
    mains = [ref for role, ref in held if role == "semantic_id"]
    other = [role for role, _ in stacked if role not in ("supplemental_semantic_ids", "semantic_id")]
    assert "Counted across %s official files" % WORDS[2 + len(TEMPLATES)] in left, left
    assert "the %s vendored templates" % WORDS[len(TEMPLATES)] in left, left
    assert "**%d of the %s references stack more than one key**" % (
        len(stacked), format(len(held), ",")) in left, left
    assert ("Of those, %d are not `supplementalSemanticIds`: %d are a `valueId`, %d a `value` and %d a `unitId`"
            % (len(other), other.count("value_id"), other.count("value"), other.count("unit_id"))) in left, left
    assert len(other) == other.count("value_id") + other.count("value") + other.count("unit_id"), other
    assert "The other %d are supplementals" % sum(
        role == "supplemental_semantic_ids" for role, _ in stacked) in left, left
    assert not [ref for ref in mains if len(ref.keys) > 1], "a main semanticId stacks keys now"
    assert "**%d of them across those files and not one with a second key**" % len(mains) in left, left


def _report_with(collector=None):
    """The example's JSON report, judged with `collector` standing in for
    the code of `semantics.candidate_values` -- in every module that
    imported it by name, since they all hold the one function."""
    from aas_submodel_validate import runner, semantics
    original = semantics.candidate_values.__code__
    if collector is not None:
        semantics.candidate_values.__code__ = collector.__code__
    try:
        return json.dumps(runner.run(str(EXAMPLE)).as_dict(), sort_keys=True)
    finally:
        semantics.candidate_values.__code__ = original


def test_row_38_measures_the_collector_on_the_official_example():
    from aas_submodel_validate import runner, semantics
    _, right = _row(38)
    code, calls, stacked = semantics.candidate_values.__code__, [0], [0]

    def count(frame, event, arg):
        if event == "call" and frame.f_code is code:
            calls[0] += 1
            reference = frame.f_locals.get("reference")
            stacked[0] += reference is not None and len(reference.keys) > 1
    sys.setprofile(count)
    try:
        runner.run(str(EXAMPLE))
    finally:
        sys.setprofile(None)
    assert ("judging the official example calls the collector %s times and %d of those are multi-key"
            % (format(calls[0], ","), stacked[0])) in right, right

    def first_key_only(reference):
        return frozenset(key_values(reference)[:1])  # noqa: F821 -- semantics.py's own name

    assert "the example's report comes back byte for byte the same" in right, right
    assert _report_with(first_key_only) == _report_with(), \
        "the first key alone changes the example's report now; row 38 says it does not"


def test_row_40_counts_the_official_properties_and_the_rows_it_reaches():
    from aas_core3 import types

    from aas_submodel_validate.rules import dbp_tables, hd_tables, td_tables
    _, right = _row(40)
    properties = [element for path in [EXAMPLE, *SAMPLES_02003]
                  for environment in _environments(path)
                  for element in environment.descend() if isinstance(element, types.Property)]
    assert not [p for p in properties if p.value is None], "an official property carries no value"
    assert ("across IDTA's own 02004 example and the %s 02003 samples this reader reads, all %d "
            "properties carry a value and none is absent"
            % (WORDS[len(SAMPLES_02003)], len(properties))) in right, right

    def reached(rows):
        return sum(row["kind"] == "Property" and row["card"][0] >= 1 for row in rows)
    tables = [path.stem for path in (ROOT / "src" / "aas_submodel_validate" / "rules").glob("*_tables.py")
              if path.stem != "battery_tables"]
    import importlib
    total = sum(reached(importlib.import_module("aas_submodel_validate.rules." + name).ROWS)
                for name in tables)
    assert len(tables) == len(TEMPLATES), (tables, TEMPLATES)
    assert ("It reaches %d required `Property` rows across the %s packs, %d of them in 02004, %d in "
            "02003 and %d in 02035-2" % (total, WORDS[len(tables)], reached(hd_tables.ROWS),
                                         reached(td_tables.ROWS), reached(dbp_tables.ROWS))) in right, right
