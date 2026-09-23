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

import pytest
from tools import extract_smt_rules as generator

from aas_submodel_validate import tablegen

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
    tablegen._qualify_repeats(tree)
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
    tablegen._qualify_repeats(tree)
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


def test_a_template_far_above_the_row_bound_is_refused_before_anything_walks_it(tmp_path):
    """What the bound bought, and what it retired.

    The duplicate-label backstop in `build` was quadratic and ran on the
    refusal path -- the path a file somebody else wrote takes most.
    Measured end to end before the bound: 4,000 elements refused in
    0.11s, 8,000 in 0.55s, 16,000 in 2.5s, 32,000 in 9.4s, on files of a
    few megabytes and well inside the 64 MiB this reader advertises.

    Both were repaired: the counting is linear now, and `build` refuses
    above `MAX_TEMPLATE_ROWS` before anything walks the tree twice. The
    second makes the first unreachable at scale, which is why this test
    no longer measures the backstop at 32,000 rows -- it cannot get
    there. What it measures is that the bound is checked early enough to
    be worth having: a template far above it is refused in the time it
    takes to read, not in the time it would have taken to process.

    The two tests above still measure the functions, because the bound
    is a number somebody can raise and the shape of the cost is what
    makes raising it safe.
    """
    pack = _pack(tmp_path, ROWS)
    start = time.perf_counter()
    # `SystemExit`, because this caller is the build tool. The core
    # raises `TemplateRefused` so that a reader handed a file by
    # somebody else can leave by the code that means "could not judge
    # this input"; a build tool owes a sentence and a 1. `generate`
    # caught only `DuplicateLabel` for that, which is a subclass -- so
    # this refusal, its sibling, came out as twelve frames of traceback
    # naming no pack.
    with pytest.raises(SystemExit) as refused:
        generator.generate(pack)
    took = time.perf_counter() - start
    assert "rows" in str(refused.value), refused.value
    assert str(tablegen.MAX_TEMPLATE_ROWS) in str(refused.value), (
        "the refusal does not say what the bound is: %s" % refused.value)
    assert pack["output"].name in str(refused.value), (
        "the refusal does not say which pack it is about: %s" % refused.value)
    assert took < CEILING_SECONDS, (
        "refusing %d elements on the row bound took %.2fs" % (ROWS, took))


def test_the_bound_lets_every_vendored_template_through():
    """A bound that refuses something this project ships would be a bound
    nobody could have measured. The widest vendored template has
    thirty-eight rows against a bound of ten thousand."""
    import json

    widest = 0
    for pack in generator.PACKS:
        document = json.loads(pack["template"].read_text("utf-8-sig"))
        built = tablegen.build(document, pack)
        widest = max(widest, len(built["tree"]))
    assert widest, "no pack produced rows"
    assert widest < tablegen.MAX_TEMPLATE_ROWS, (
        "the widest vendored template has %d top-level rows and the bound is %d"
        % (widest, tablegen.MAX_TEMPLATE_ROWS))
