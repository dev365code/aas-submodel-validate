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

import pathlib

#: Beside the vendored templates, because it is the same kind of thing:
#: material IDTA published, carried so that what you install holds its
#: own provenance.
NAME = "idta-02004-2.0.aasx"


def bundled_example() -> pathlib.Path:
    """Where the example is, or a message saying why it is not.

    A wheel built without its package data installs a validator whose
    `--example` points at nothing, and the failure has to name the file
    rather than arrive as a stack trace from the loader.
    """
    path = pathlib.Path(__file__).resolve().parent / "data" / "example" / NAME
    if not path.is_file():
        raise FileNotFoundError(
            "this installation carries no %s; the package data did not "
            "travel with it" % NAME)
    return path
