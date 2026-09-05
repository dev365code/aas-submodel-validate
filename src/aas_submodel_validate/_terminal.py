"""Escape what the terminal cannot encode instead of raising.

What this project writes of its own is ASCII, so ordinary output reads
the same everywhere. What it repeats from elsewhere is not ours to
constrain -- a section sign in an IDTA citation, an idShort in any
script, a path a reader chose. Without this, writing one of those
raises, the interpreter prints a traceback, and the process leaves by 1.

For the CLI that is a lie about the verdict: 1 means *findings*, and a
clean file and a refused one both came back as it. For the scripts under
`tools/` it is a lie about a gate: `make check` runs five of them, and a
message a terminal cannot spell would fail a check that had found
nothing wrong. One helper, so the two cannot drift.

Not an exotic case: cp949 is the default code page on Korean Windows and
cp932 on Japanese, and neither has an em dash.
"""
from __future__ import annotations

import contextlib
import sys


def survive() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        # Not a text stream -- a test's own, a pipe somebody replaced.
        # Nothing to do, and nothing to break.
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(errors="backslashreplace")
