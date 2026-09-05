"""Which copy of the package the suite is judging."""
from __future__ import annotations

import pathlib

import aas_submodel_validate

TREE = pathlib.Path(__file__).resolve().parents[1]


def test_the_suite_ran_against_this_tree():
    """A green that means nothing is worse than a red.

    This is a src-layout project, so `aas_submodel_validate` is not
    importable from the repository root: `make check` exports
    PYTHONPATH, and anything that does not -- a bare `pytest`, an IDE's
    run button -- falls through to whatever is installed. On a machine
    that has ever run `pip install aas-submodel-validate` that is the
    released version, and the suite then passes or fails on code the
    author did not write and cannot edit. Both directions are wrong, and
    the passing direction is the dangerous one: a contributor sees green
    for a change that was never executed.

    Found by chasing a front-page test that failed alone and passed
    under `make check`. The page was right; the import was not."""
    imported = pathlib.Path(aas_submodel_validate.__file__).resolve()
    assert TREE in imported.parents, (
        "the suite imported %s, which is not in this tree (%s) -- it is "
        "judging an installed copy, so its verdict is about that copy. "
        "Run `make check`, or put src/ on PYTHONPATH." % (imported, TREE))
