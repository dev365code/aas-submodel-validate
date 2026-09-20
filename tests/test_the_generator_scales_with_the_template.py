"""The generator's cost must follow the template's size, not its square.

`_qualify_repeats` asked `labels.count(label)` once per label, over the
same list, before the early return that most templates take. Measured on
this machine: 2,000 rows in 0.023s, 8,000 in 0.51s, 16,000 in 2.2s,
32,000 in 9.2s -- four times the rows for twenty times the work, which is
what a quadratic looks like from outside.

No vendored template is anywhere near that, so nothing a user runs today
reaches it: the generator runs at build time over files this project
chose. What makes it worth fixing rather than noting is that the arriving
`--template` mode hands the generator a file somebody else chose, and the
reader's byte bound does not bound this. A 46 MiB template is inside the
64 MiB this reader advertises and was measured at twenty-four minutes.
"""
from __future__ import annotations

import time

from tools import extract_smt_rules as generator

#: Big enough that a quadratic cannot hide in the noise and small enough
#: that a linear one is not worth timing twice. At this size the old code
#: took about nine seconds here.
ROWS = 32_000
#: Six times the measured quadratic would have to get *faster* to pass,
#: and a linear implementation beats it by three orders of magnitude, so
#: this separates the two on any machine rather than describing this one.
CEILING_SECONDS = 1.5


def _flat(rows):
    """A tree of `rows` siblings, every label its own."""
    return [{"label": "Row%d" % index, "children": []} for index in range(rows)]


def _collided(rows):
    """The same rows under two scopes, so every label is claimed twice
    and the immediate parent is what tells the copies apart.

    Written this way after the first attempt put the colliding pairs at
    the top level, where there is no ancestor to qualify by -- nothing
    can tell those apart and `_qualify_repeats` correctly leaves them,
    so the test was asserting a thing the function does not promise.
    """
    half = rows // 2
    return [{"label": "ScopeA",
             "children": [{"label": "Row%d" % i, "children": []}
                          for i in range(half)]},
            {"label": "ScopeB",
             "children": [{"label": "Row%d" % i, "children": []}
                          for i in range(half)]}]


def test_a_wide_template_does_not_cost_the_square_of_its_width():
    """The early-return path, which is every template vendored here."""
    tree = _flat(ROWS)
    start = time.perf_counter()
    generator._qualify_repeats(tree)
    took = time.perf_counter() - start
    assert took < CEILING_SECONDS, (
        "%d rows with no repeated label took %.2fs; the work is meant to "
        "follow the number of rows, not its square" % (ROWS, took))


def test_the_same_holds_when_there_is_work_to_do():
    """And the path that does not return early, because a fix that only
    made the no-op case fast would leave the expensive one quadratic --
    and the expensive one is the one a wide template takes."""
    tree = _collided(ROWS)
    start = time.perf_counter()
    generator._qualify_repeats(tree)
    took = time.perf_counter() - start
    assert took < CEILING_SECONDS, (
        "%d rows claimed by two scopes took %.2fs" % (ROWS, took))
    # And it did the work rather than being fast by doing none: every
    # label is now distinct, qualified by the scope that claims it.
    qualified = [child["label"] for scope in tree for child in scope["children"]]
    assert len(set(qualified)) == len(qualified) == ROWS, (
        "%d rows collapsed to %d distinct labels"
        % (len(qualified), len(set(qualified))))
    assert "ScopeA" in qualified[0], qualified[0]
