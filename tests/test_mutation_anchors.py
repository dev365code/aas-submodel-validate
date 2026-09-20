"""Every mutation-table anchor matches its target file exactly once.

A review fix that edits an anchored line drifts its anchor silently: the
mutation still "passes" because it never applies, so the row proves
nothing. `mutation_table --run` catches this only when the whole table is
exercised (and stops at the first drift); this catches every drift in
`make check`, in milliseconds, without applying a single mutation.

The check is `count == 1`, so it goes red both when an anchor has gone
(0 matches, the drift that prompted this) and when an edit made it
ambiguous (2+ matches, where the mutation would strike the wrong line).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import mutation_table as m  # noqa: E402


@pytest.mark.parametrize("row", m.TABLE, ids=[row[0] for row in m.TABLE])
def test_every_anchor_matches_its_target_file_exactly_once(row):
    identifier, relative_path, anchor = row[0], row[1], row[2]
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    count = text.count(anchor)
    assert count == 1, (
        "%s: its anchor appears %d times in %s (want exactly one). The table "
        "has drifted from the code; regenerate the row or fix the anchor."
        % (identifier, count, relative_path))


@pytest.mark.parametrize("row", m.TABLE, ids=[row[0] for row in m.TABLE])
def test_every_check_a_row_names_still_collects_something(row):
    """A row's anchor is checked and the tests it names were not.

    Measured: a row kept pointing at
    `test_refusing_a_template_is_not_the_square_of_its_width` after that
    test was renamed one commit later. `pytest` exits 4 on a selection
    that collects nothing, so the harness reports the row broken rather
    than booking a false kill -- but only when somebody runs the
    harness, and `make check` could not see it at all.

    Collection only, which is milliseconds: whether the mutant dies is
    the harness's question, and whether there is anything to run is this
    one.
    """
    identifier, checks = row[0], row[4]
    # The three forms the harness reads, and only one of them is a pytest
    # selection: `step:<workflow>:<name>` lifts a workflow step out and
    # runs it, `tools/<script>` runs a gate that is a script, and
    # anything else is handed to pytest. Taking the prefixes from the
    # harness rather than listing them here would be better and is not
    # possible without importing its private dispatch; the two are
    # asserted to still be the prefixes it branches on.
    source = (ROOT / "tools" / "mutation_table.py").read_text(encoding="utf-8")
    for prefix in ("step:", "tools/"):
        assert 'startswith("%s")' % prefix in source, (
            "the harness no longer branches on %r, so this filter is wrong"
            % prefix)
    selections = [check for check in checks
                  if not check.startswith(("tools/", "step:"))]
    if not selections:
        return                      # a row whose checks are all scripts
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "-p", "no:cacheprovider", *selections],
        capture_output=True, text=True, cwd=str(ROOT),
        env=dict(os.environ, PYTHONPATH="src:tests"))
    assert done.returncode == 0, (
        "%s names %s, which collects nothing:\n%s"
        % (identifier, selections, (done.stdout + done.stderr)[-800:]))
