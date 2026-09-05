"""Which copy of the package the suite is judging."""
from __future__ import annotations

import pathlib
import unicodedata

import aas_submodel_validate


def _comparable(path: pathlib.Path) -> pathlib.Path:
    """One normal form, so two spellings of a directory compare equal.

    macOS stores a decomposed filename and hands it back from
    `resolve()`; an editable install's import hook hands back the
    composed spelling. On a checkout whose path is ASCII the two are the
    same bytes and nothing here matters. On one that is not -- a
    contributor working in Korean, German or Japanese, which is who this
    project is built for -- they are different bytes for one directory,
    and this guard failed on a tree it should have passed, telling the
    contributor their suite was judging an installed copy when it was
    not. A guard that cries wolf on a correct setup gets switched off,
    and this is the guard that keeps a green from being meaningless.
    """
    return pathlib.Path(unicodedata.normalize("NFC", str(path)))


TREE = _comparable(pathlib.Path(__file__).resolve().parents[1])


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
    imported = _comparable(pathlib.Path(aas_submodel_validate.__file__).resolve())
    assert TREE in imported.parents, (
        "the suite imported %s, which is not in this tree (%s) -- it is "
        "judging an installed copy, so its verdict is about that copy. "
        "Run `make check`, or put src/ on PYTHONPATH." % (imported, TREE))
