"""What the page runs: the command's own entry point, on the file it was handed.

Nothing here decides anything about a submodel. The page saves the bytes it
was given under the name they came with, calls the function the console
script calls with the arguments somebody would type, and keeps exactly what
that function wrote to each stream and the code it ended with. The command's
report is the page's report; there is no second rendering of it to keep in
step with the first.

It runs inside the browser, on the Python the page carries --
`tools/build_browser.py` puts it there -- and on any other Python as well,
which is how the suite holds it to the command without a browser.
"""
from __future__ import annotations

import io
import os
import sys
import traceback
import zipfile

# The runtime loads its `lzma` package after `zipfile` has been imported --
# its own package loader reads wheels with it -- and `zipfile` decides at
# import whether it has `lzma`, keeping the answer in a name of its own. So
# every LZMA-compressed member of a package came back "Compression requires
# the (missing) lzma module", where the command decompresses it. The module
# is there by now; the name is told. On any other Python it already is.
if getattr(zipfile, "lzma", None) is None:
    import lzma

    zipfile.lzma = lzma

#: Where a file the page was handed is put: the runtime's own filesystem,
#: which lives in the tab's memory. Nothing written here reaches the
#: machine's disk.
ROOM = "/work"


def argv_for(name: str, as_json: bool) -> list:
    """What somebody at a console types to judge this file where it is.

    `--no-bundle`: a diagnostic bundle written into the tab's memory is a
    file nobody could open, so the page asks for none, and the command it is
    compared with is asked for none. A name that begins with `-` would be
    read as an option, so it is passed as `./name`, as it is at a shell.
    """
    path = "./" + name if name.startswith("-") else name
    return ["--no-bundle", *(["-f", "json"] if as_json else []), path]


def check(name: str, data, as_json: bool, room: str = ROOM):
    """Judge `data` as the file `name`; return (argv, stdout, stderr, exit code).

    The streams are bytes, as a process's are. The exit code is the one a
    process running the command would end with.
    """
    if name in ("", ".", "..") or "/" in name or "\0" in name:
        raise ValueError("not the name of a file: %r" % (name,))
    from aas_submodel_validate import cli

    argv = argv_for(name, as_json)
    os.makedirs(room, exist_ok=True)
    target = os.path.join(room, name)
    with open(target, "wb") as handle:
        handle.write(bytes(data))
    out, err = _console(), _console()
    streams, here = (sys.stdout, sys.stderr), os.getcwd()
    try:
        sys.stdout, sys.stderr = out, err
        os.chdir(room)
        code = _exit_status(cli.main, list(argv))
    finally:
        sys.stdout, sys.stderr = streams
        os.chdir(here)
        os.remove(target)
    out.flush()
    err.flush()
    return argv, out.buffer.getvalue(), err.buffer.getvalue(), code


def versions() -> dict:
    """What decides a verdict here, so that a comparison can check it compares
    like with like before it compares anything."""
    import aas_core3

    import aas_submodel_validate

    return {"python": "%d.%d.%d" % sys.version_info[:3],
            "aas_submodel_validate": aas_submodel_validate.__version__,
            "aas_core3": aas_core3.__version__}


def _console():
    """A UTF-8 console that ends a line the way this platform's console does.

    CPython's own streams write `\\n` everywhere but Windows, and leaving
    `newline` unset asks for exactly that. In the browser the runtime is a
    POSIX one, so the page writes `\\n`, as the command does on the machine
    it is compared with there.
    """
    return io.TextIOWrapper(io.BytesIO(), encoding="utf-8", write_through=True)


def _exit_status(run, argv) -> int:
    """`sys.exit(run(argv))`, as the interpreter finishes it.

    The console script hands `main`'s result to `sys.exit`, and argparse ends
    a run by raising `SystemExit` itself; a process turns both into a status,
    and a traceback into status 1 with the traceback on stderr. The page is
    not a process, so it does the same here.
    """
    try:
        code = run(argv)
    except SystemExit as stop:
        code = stop.code
        if code is not None and not isinstance(code, int):
            print(code, file=sys.stderr)
            return 1
    except BaseException:                # as the interpreter does: everything
        traceback.print_exc()
        return 1
    return 0 if code is None else code
