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
