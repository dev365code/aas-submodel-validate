"""A rule id, once published, is a citation somebody else made.

`README.md` says no rule id has been renamed or reused. That sentence sits
beside one which said a new rule meant a minor version, and three releases
had already said otherwise before anybody noticed -- a promise in prose
goes false in silence, because nothing reads prose.

So the ids the last release published are written down, and this asserts
they are all still here. Adding a rule is allowed and does not touch that
file; removing or renaming one is what this catches, in the release where
it happens rather than in the ticket where a reader cites `HD-D7` and is
told there is no such rule.
"""
from __future__ import annotations

from pathlib import Path

import aas_submodel_validate.rules  # noqa: F401 - importing registers them
from aas_submodel_validate.registry import all_rules

RELEASED = Path(__file__).resolve().parent / "released_rule_ids.txt"


def _released():
    return {line.strip() for line in RELEASED.read_text("utf-8").splitlines()
            if line.strip() and not line.startswith("#")}


def test_every_rule_id_the_last_release_published_still_exists():
    released = _released()
    assert released, "the released list is empty; this test is checking nothing"
    gone = sorted(released - {rule.id for rule in all_rules()})
    assert not gone, (
        "these rule ids were published and are no longer here, so a report "
        "citing one names a rule this build does not have: %s. Renaming a "
        "published id is the thing the front page says does not happen; if "
        "it has to happen, the sentence changes too." % ", ".join(gone))


def test_the_released_list_says_where_it_came_from():
    """A golden file nobody can date is one nobody can update correctly."""
    header = RELEASED.read_text("utf-8").split("\n", 1)[0]
    assert header.startswith("#") and "v0.1." in header, header
