"""The last full run of the mutation table, kept beside the table it ran.

`tools/mutation_table.py --run` makes the mistake each gate says it stops
and checks a test fails, and CI runs it on every commit; what a run found
otherwise lives in a terminal or a CI log. `docs/mutation-record.json` is
written by the run itself -- only after a run in which every row died,
and only from a clean checkout, naming the commit it copied. It is held
here to the table: a row added or dropped without a run makes the two
disagree, and so does a record of a run that was anything but clean.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "mutation-record.json"
if not (ROOT / "tools" / "mutation_table.py").exists():
    pytest.skip("no tools/ here (installed package, not a checkout)",
                allow_module_level=True)
sys.path.insert(0, str(ROOT / "tools"))

import mutation_table  # noqa: E402


def _record():
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_the_record_ran_every_row_of_the_table_and_no_other():
    rows = [row[0] for row in mutation_table.TABLE]
    assert _record()["rows"] == rows, (
        "the table has changed since the record was taken; run "
        "`python3 tools/mutation_table.py --run --record docs/mutation-record.json` "
        "on a clean checkout and commit what it writes")


def test_the_record_is_of_a_run_in_which_everything_but_the_canary_died():
    record = _record()
    canary = mutation_table.CANARY[0]
    assert record["survived"] == [canary], record["survived"]
    assert record["killed"] == [row for row in record["rows"] if row != canary], \
        sorted(set(record["rows"]) - set(record["killed"]) - {canary})


def test_the_record_names_the_commit_and_the_python_it_measured():
    record = _record()
    assert re.fullmatch(r"[0-9a-f]{40}", record["commit"]), record["commit"]
    assert re.fullmatch(r"3\.\d+\.\d+", record["python"]), record["python"]
