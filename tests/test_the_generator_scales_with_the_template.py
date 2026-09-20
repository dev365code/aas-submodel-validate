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


def _template(elements):
    """A template whose every idShort is used twice, which is the shape
    the duplicate-label backstop exists to refuse."""
    written = []
    for index in range(elements // 2):
        for _ in range(2):
            written.append({
                "modelType": "Property", "idShort": "P%d" % index,
                "valueType": "xs:string",
                "semanticId": {"type": "GlobalReference",
                               "keys": [{"type": "GlobalReference",
                                         "value": "urn:x:%d" % index}]}})
    return {"submodels": [{
        "kind": "Template", "idShort": "T",
        "semanticId": {"type": "GlobalReference",
                       "keys": [{"type": "GlobalReference",
                                 "value": "urn:x:top"}]},
        "submodelElements": written}]}


def _pack(tmp_path, elements):
    import json
    path = tmp_path / "template.json"
    path.write_text(json.dumps(_template(elements)), encoding="utf-8")
    return {"template": path, "output": tmp_path / "x_tables.py", "prefix": "X-E",
            "source": "a synthetic template", "citation": "none",
            "skip_sids": frozenset(), "item_names": {}, "example_types": ()}


def test_refusing_a_template_is_not_the_square_of_its_width(tmp_path):
    """The path a bad template takes, which is the one a mode that
    accepts a caller's file will take most.

    The fix that made `_qualify_repeats` linear left the same shape one
    function later: the duplicate-label backstop in `generate` asks
    `labels.count(label)` inside a comprehension over `labels`, and it
    runs only when there *are* duplicates -- so the common path got fast
    and the refusal stayed quadratic. Measured end to end before this
    change: 4,000 elements in 0.11s, 8,000 in 0.55s, 16,000 in 2.5s,
    32,000 in 9.4s. Every one of those files is a few megabytes, well
    inside the 64 MiB this reader advertises.

    The commit that fixed the first half said the generator's cost
    follows the template rather than its square. That was true of the
    path every vendored template takes and not true here.
    """
    pack = _pack(tmp_path, ROWS)
    start = time.perf_counter()
    try:
        generator.generate(pack)
    except SystemExit as refused:
        took = time.perf_counter() - start
        assert "share a label" in str(refused.code), refused.code
    else:
        raise AssertionError("a template with every label doubled was accepted")
    assert took < CEILING_SECONDS, (
        "refusing %d elements took %.2fs; the refusal reads the labels as "
        "many times as there are labels" % (ROWS, took))
