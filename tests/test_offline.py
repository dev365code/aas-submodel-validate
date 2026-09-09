"""The front page says "Offline, always. No network call in any code path."

That is the sentence an air-gapped reader chooses this tool on, and until
now nothing checked it. A promise in prose goes false in silence: the
paragraph beside it on the same page used to say a new rule meant a minor
version, and three releases had already said otherwise.

Two questions, because neither answers the other. What the shipped code
*could* reach is a property of every path, including the ones no test
exercises, and is read from the source. What it *does* reach is a
property of the paths that run, and is measured by taking the network
away and asking for a verdict anyway.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "aas_submodel_validate"

#: Modules that can open a connection. `urllib.parse` is deliberately not
#: among them and `urllib.request` deliberately is: the container reads
#: percent escapes out of part names, which is string work that happens to
#: live under the same package name. A rule that matched on `urllib`
#: would fail on the correct file, which is the shape this suite has been
#: caught by before.
REACHES_THE_NETWORK = {
    "socket", "ssl", "ftplib", "smtplib", "poplib", "imaplib", "telnetlib",
    "http", "urllib.request", "urllib.error", "xmlrpc", "asyncio",
    "requests", "httpx", "aiohttp", "urllib3",
}


def _imported(path: Path):
    """Every module a file imports, as dotted names."""
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def _reaches(name: str) -> bool:
    """Whether this import can open a connection.

    Compared by dotted prefix so `http.client` counts through `http`,
    and `urllib.parse` does not count through `urllib` -- only the
    submodules named above do.
    """
    parts = name.split(".")
    return any(".".join(parts[:n]) in REACHES_THE_NETWORK
               for n in range(1, len(parts) + 1))


def test_nothing_the_package_ships_can_open_a_connection():
    """Read from the source, so it covers the paths no test runs."""
    sources = sorted(PACKAGE.rglob("*.py"))
    assert sources, "no package sources found; this test is looking nowhere"
    guilty = sorted({"%s: %s" % (p.relative_to(ROOT), name)
                     for p in sources for name in _imported(p)
                     if _reaches(name)})
    assert not guilty, (
        "the front page says no code path calls the network, and these "
        "import something that can:\n  " + "\n  ".join(guilty))


def test_a_verdict_still_comes_out_with_the_network_taken_away():
    """Read by running it, so it covers what the source cannot say.

    The static reading above cannot see a connection opened inside a
    dependency, and the promise on the page is about what happens when
    somebody runs this, not about this package's imports. So the socket
    is removed and a verdict is asked for anyway.
    """
    guard = (
        "import socket\n"
        "def _refuse(*a, **k):\n"
        "    raise AssertionError('this code path opened a socket')\n"
        "socket.socket = _refuse\n"
        "socket.create_connection = _refuse\n"
        "if hasattr(socket, 'socketpair'):\n"
        "    socket.socketpair = _refuse\n"
        "import sys\n"
        "sys.argv = ['smtv', '--example']\n"
        "from aas_submodel_validate.cli import main\n"
        "raise SystemExit(main())\n")
    done = subprocess.run(
        [sys.executable, "-c", guard], cwd=str(ROOT), capture_output=True,
        text=True, env={"PYTHONPATH": str(ROOT / "src"), "PATH": ""})
    assert done.returncode == 0, (
        "judging the bundled example with the socket removed did not "
        "reach a verdict:\n%s%s" % (done.stdout[-2000:], done.stderr[-2000:]))
    assert "judged 1 of 1 submodel" in done.stdout, done.stdout[-2000:]


def test_the_guard_would_notice_a_connection():
    """The test above passes if nothing opens a socket. It would also
    pass if the guard were not installed, so the guard is asked to fire
    on a program that does open one."""
    prove = (
        "import socket\n"
        "def _refuse(*a, **k):\n"
        "    raise AssertionError('this code path opened a socket')\n"
        "socket.socket = _refuse\n"
        "socket.socket()\n")
    done = subprocess.run([sys.executable, "-c", prove], capture_output=True,
                          text=True, env={"PATH": ""})
    assert done.returncode != 0 and "opened a socket" in done.stderr, done.stderr


def test_the_page_still_makes_the_promise_these_check():
    """If the sentence goes, these tests are guarding nothing and should
    go with it -- rather than sitting here asserting a claim the project
    no longer makes."""
    page = (ROOT / "README.md").read_text("utf-8")
    assert "No network call in any code path" in page, (
        "the front page no longer promises this; delete these tests or "
        "restore the sentence, but do not leave them guarding nothing")
