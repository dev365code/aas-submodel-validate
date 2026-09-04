"""The one file this package can always judge.

`pip install` used to leave a reader with a validator and nothing to
validate: the front page's first command named a file only a clone has,
and the machine this project is for is often one where the clone is
blocked. So IDTA's own published example travels in the wheel, under the
same CC BY 4.0 licence and the same NOTICE entry as the templates beside
it.

Unmodified, defects and all -- it raises findings, and that is the point
of shipping this one rather than a clean file somebody wrote to pass.
A first verdict that says `ok` proves nothing about a validator.
"""
from __future__ import annotations

import contextlib
import importlib.resources
import pathlib

#: Beside the vendored templates, because it is the same kind of thing:
#: material IDTA published, carried so that what you install holds its
#: own provenance.
NAME = "idta-02004-2.0.aasx"


def example_name() -> str:
    """What to call the example in a report.

    `NAME`, and never the name of the file it was extracted to. Reading
    it off the path worked from an installed package, where nothing is
    extracted and the path is the real one, and printed
    `tmp7uh08xcmidta-02004-2.0.aasx` from the single file -- which is
    every reader who carried the archive in, and none of the tests,
    because they run from a source tree.
    """
    return NAME


class NotBundled(Exception):
    """The example did not travel with this installation."""


@contextlib.contextmanager
def bundled_example():
    """A real path to the example, for as long as the caller needs one.

    Asked of the package rather than computed from `__file__`. The first
    version did the arithmetic -- `Path(__file__).parent / "data" / ...`
    -- which is a filesystem path, and inside a zipapp `__file__` names a
    location *within* the archive that no `open()` can reach. So the one
    command the release note leads with died on the single file, with a
    message saying the data had not travelled while the bytes sat in the
    archive it was reading, and the reader it misinformed is by
    definition the one who cannot go and check.

    A context manager because the answer is not always a file that
    exists: from a zipapp the bytes are extracted for the duration and
    removed afterwards, which is what `as_file` is for. Callers get a
    path either way and never learn which case they were in.
    """
    resource = (importlib.resources.files(__package__)
                / "data" / "example" / NAME)
    if not resource.is_file():
        raise NotBundled(
            "this installation carries no %s; the package data did not "
            "travel with it" % NAME)
    with importlib.resources.as_file(resource) as path:
        yield pathlib.Path(path)
