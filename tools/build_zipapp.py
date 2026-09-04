#!/usr/bin/env python3
"""Build the single-file form: `dist/smtv.pyz`.

Why this exists. This tool is for networks that have no route to the
internet, and `pip install` is the first thing such a network takes
away: a wheel still needs pip, an index or a directory of wheels, often
a virtual environment and the rights to create one. A `.pyz` needs a
copy of the file and a Python.

    python smtv.pyz path/to/submodel.aasx

Everything is inside it -- this package and aas-core3.0 -- and nothing
is compiled, so the same file runs on Linux, macOS and Windows. It is
also an ordinary zip: whoever has to approve it can open it and read
every line, which matters more than convenience when the approval is
the hard part.

    python tools/build_zipapp.py                  # dist/smtv.pyz
    python tools/build_zipapp.py --check          # build it and run it

Needs the network once, to fetch the dependency being bundled.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "aas_submodel_validate"
OUTPUT = ROOT / "dist" / "smtv.pyz"

#: The archive carries no wheel metadata, so `Requires-Python` is not in
#: it -- and the reader who most needs that number is the one who carried
#: this file through a site's inbound review and cannot go and look it
#: up. An interpreter too old raised a syntax error from a file they had
#: no way to read first, and the trip back out to a networked machine is
#: measured in half-days.
#:
#: The guard runs before the import whose failure it explains, and uses
#: nothing newer than what it refuses.
MAIN = """import sys

if sys.version_info < (3, 9):
    sys.stderr.write(
        "smtv: this needs Python 3.9 or newer; this one is %d.%d (%s)\\n"
        % (sys.version_info[0], sys.version_info[1], sys.executable))
    sys.exit(2)

from aas_submodel_validate.cli import main

sys.exit(main())
"""

SHEBANG = b"#!/usr/bin/env python3\n"

#: A fixed date, so two builds of one tree are one file. Zip cannot store
#: anything before 1980, and a `SOURCE_DATE_EPOCH` outside the range it
#: can store is clamped rather than allowed to produce a stamp from the
#: year twelve million.
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ZIP_EARLIEST = (1980, 1, 1, 0, 0, 0)
ZIP_LATEST = (2107, 12, 31, 23, 59, 58)


def _timestamp():
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if not epoch:
        return FIXED_TIMESTAMP
    try:
        stamp = time.gmtime(int(epoch))[:6]
    except (ValueError, OSError, OverflowError):
        return FIXED_TIMESTAMP
    return min(max(stamp, ZIP_EARLIEST), ZIP_LATEST)


def python_floor(text: str = None) -> str:
    """The oldest Python pyproject says this runs on, as "X.Y"."""
    if text is None:
        text = (ROOT / "pyproject.toml").read_text("utf-8")
    found = re.search(r'^requires-python = ">=([0-9]+\.[0-9]+)"', text, re.M)
    assert found, ('pyproject.toml no longer declares requires-python as ">=X.Y"; '
                   "the archive would be resolved for whichever Python built it")
    return found.group(1)


def dependencies() -> list:
    """What pyproject asks for at runtime, verbatim."""
    text = (ROOT / "pyproject.toml").read_text("utf-8")
    block = re.search(r"^dependencies = \[(.*?)\]", text, re.M | re.S)
    assert block, "pyproject.toml declares no runtime dependencies block"
    return [line.strip().strip(",").strip('"')
            for line in block.group(1).splitlines() if line.strip()]


def pip_arguments(target: Path) -> list:
    """How the dependency is fetched: resolved for the oldest Python this
    runs on, not for the one doing the building. A dependency whose own
    requirements differ by Python version would otherwise put the
    builder's closure in a file that claims to run on all of them."""
    return [sys.executable, "-m", "pip", "install", "--quiet", "--no-compile",
            "--target", str(target), "--only-binary=:all:",
            "--python-version", python_floor(), *dependencies()]


def stage(target: Path) -> None:
    subprocess.run(pip_arguments(target), check=True)
    shutil.copytree(SOURCE, target / SOURCE.name,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (target / "__main__.py").write_text(MAIN, "utf-8")
    for licence in ("LICENSE", "NOTICE", "THIRD_PARTY.md"):
        found = ROOT / licence
        if found.exists():
            shutil.copy2(found, target / found.name)


#: Directories a dependency's own wheel carries for its maintainers.
#: aas-core3.0 ships the scripts it builds itself with, and they arrived
#: in the artifact: dead code the entry point never reaches, the only
#: `subprocess` import in the whole archive -- the one line a scanner
#: stops on and a reviewer then has to ask about -- and a top-level
#: `dev_scripts` name on `sys.path` that this file has no business
#: claiming. Matched as a whole path segment, not as a prefix, so a
#: package legitimately named `dev_scripts_of_something` is not caught
#: and one nested under `aas_core3/` is.
NOT_OURS_TO_CARRY = ("dev_scripts",)


def belongs(name: str) -> bool:
    """Whether an archive member travels in the single file.

    A path filter, and the only one: `inspect` afterwards asks what has
    to be present, and the two together are what a reviewer opening the
    zip is entitled to.
    """
    return not any(part in NOT_OURS_TO_CARRY for part in name.split("/"))


def create_archive(source: Path, target: Path) -> None:
    """`zipapp.create_archive`, with the timestamps and the order pinned --
    which is what makes two builds of one tree the same bytes."""
    stamp = _timestamp()
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as handle:
        handle.write(SHEBANG)
        with zipfile.ZipFile(handle, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(p for p in source.rglob("*") if p.is_file()):
                name = path.relative_to(source).as_posix()
                if not belongs(name):
                    continue
                info = zipfile.ZipInfo(name, date_time=stamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())
    target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def inspect(pyz: Path) -> list:
    """What has to be inside it for the file to be worth carrying."""
    with zipfile.ZipFile(pyz) as archive:
        names = archive.namelist()
    problems = []
    for wanted in ("__main__.py", "aas_submodel_validate/cli.py",
                   "aas_submodel_validate/rules/battery_tables.py",
                   "aas_core3/verification.py"):
        if wanted not in names:
            problems.append("%s is not in the archive" % wanted)
    # The vendored template files are package data and the generated
    # tables are read off them; a .pyz without them answers nothing.
    if not any(name.endswith("template.json") for name in names):
        problems.append("no vendored template travelled with it")
    if any("__pycache__" in name for name in names):
        problems.append("compiled bytecode travelled with it")
    return problems


def smoke(pyz: Path) -> int:
    """Run it on a file the tree already carries, and read the exit code.

    Building a thing that imports is not the same as building a thing
    that answers -- a missing dependency shows up here and nowhere in
    the build.

    With the interpreter's own packages shut out. A zipapp does not
    isolate `sys.path`: site-packages sits behind it, and the release
    job installs this project and its dependency into the very
    interpreter that runs this check, so an archive missing half of
    `aas_core3` imported the installed copy and answered perfectly.
    Measured: eight of nine modules deleted from the archive, and the
    smoke test passed. `-S` and an empty `PYTHONPATH` leave the archive
    carrying the whole answer or not answering at all.
    """
    example = ROOT / "tests" / "corpus" / "idta" / "02004" / "example.json"
    environment = dict(os.environ, PYTHONPATH="", PYTHONNOUSERSITE="1")
    result = subprocess.run([sys.executable, "-S", str(pyz), "-f", "json",
                             str(example)],
                            capture_output=True, text=True, env=environment)
    if result.returncode not in (0, 1):
        print("the archive did not run: exit %d\n%s"
              % (result.returncode, result.stderr[:2000]), file=sys.stderr)
        return 1
    if '"schemaVersion": 1' not in result.stdout:
        print("the archive ran and did not print a report", file=sys.stderr)
        return 1
    print("smoke: the archive judged %s and exited %d"
          % (example.name, result.returncode))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", default=str(OUTPUT))
    parser.add_argument("--check", action="store_true",
                        help="build it, look inside it, and run it")
    args = parser.parse_args()
    output = Path(args.output)
    with tempfile.TemporaryDirectory() as staging:
        target = Path(staging)
        stage(target)
        create_archive(target, output)
    print("built %s (%d bytes)" % (output, output.stat().st_size))
    problems = inspect(output)
    for problem in problems:
        print("zipapp: %s" % problem, file=sys.stderr)
    if problems:
        return 1
    return smoke(output) if args.check else 0


if __name__ == "__main__":
    sys.exit(main())
