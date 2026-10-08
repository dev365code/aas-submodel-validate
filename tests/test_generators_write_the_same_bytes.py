"""Committed output keeps its bytes under either platform's text defaults.

Run the real generators in an archived tree, with only the vendor's HTTP
responses and the suite's observed rule set replayed from pinned files.
The child process changes default text writes to CRLF and unspecified
encodings to cp1252; explicit UTF-8 and LF must survive those defaults.
"""
from __future__ import annotations

import builtins
import hashlib
import io
import json
import os
import re
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATORS = (
    ("extract_smt_rules.py", ()),
    ("golden_report.py", ()),
    ("vendor_template.py", ("--refresh",)),
    ("extract_battery_rules.py", ()),
    ("gen_door.py", ()),
    ("capabilities_svg.py", ("docs/capabilities.json",)),
    ("gen_official_samples.py", ()),
    ("rule_coverage.py", ("--write",)),
)


@pytest.fixture(scope="module")
def archived_tree(tmp_path_factory):
    tree = tmp_path_factory.mktemp("generator-bytes")
    try:
        archive = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT,
                                 capture_output=True)
    except OSError:
        pytest.skip("git is not available")
    if archive.returncode:
        pytest.skip("not a git checkout (an unpacked sdist is not one)")
    subprocess.run(["tar", "-x", "-C", str(tree)], input=archive.stdout, check=True)
    # Exercise source edits before they have a commit, too. Everything the
    # generators read or overwrite remains the archive's committed input.
    for tool, _flags in GENERATORS:
        (tree / "tools" / tool).write_bytes((ROOT / "tools" / tool).read_bytes())
    (tree / ".rule-coverage.json").write_bytes(
        (tree / "docs" / "rule-coverage.json").read_bytes())
    from tools import vendor_template
    for rel in vendor_template.FILES:
        replay = tree / ".vendor-replay" / (rel + ".bin")
        replay.parent.mkdir(parents=True, exist_ok=True)
        replay.write_bytes((tree / rel).read_bytes())
    return tree


def _run_generator(tree, tool, flags, windows):
    """Child entry point: no platform monkeypatch escapes into pytest."""
    os.chdir(tree)
    sys.path[:0] = [str(tree / "src"), str(tree / "tools")]
    original_open = builtins.open
    writes = set()

    def opener(original):
        def open_file(file, mode="r", buffering=-1, encoding=None, errors=None,
                      newline=None, closefd=True, opener=None):
            if "b" not in mode:
                if any(c in mode for c in "wax+"):
                    if not isinstance(file, int):
                        writes.add(str(Path(file).resolve()))
                    if windows and newline is None:
                        newline = "\r\n"
                if windows and encoding is None:
                    encoding = "cp1252"
            return original(file, mode, buffering, encoding, errors,
                            newline, closefd, opener)
        return open_file

    builtins.open = opener(original_open)
    io.open = opener(io.open)
    if windows:
        original_write_text = Path.write_text

        def write_text(path, data, encoding=None, errors=None, **kwargs):
            # Path.write_text gained newline in 3.10; this also exercises
            # the 3.9 implementation without passing it a newer argument.
            newline = kwargs.get("newline", "\r\n")
            if newline is None:
                newline = "\r\n"
            with open(path, "w", encoding=encoding or "cp1252",
                      errors=errors, newline=newline) as stream:
                return stream.write(data)

        Path.write_text = write_text
        # A positive control prevents a no-op simulation from passing.
        probe = tree / "platform-probe.txt"
        probe.write_text("a\nb\n©")
        assert probe.read_bytes() == b"a\r\nb\r\n\xa9"
        with open(probe, "w") as stream:
            stream.write("a\nb\n©")
        assert probe.read_bytes() == b"a\r\nb\r\n\xa9"
        probe.unlink()
        assert Path.write_text is not original_write_text
    if tool == "vendor_template.py":
        import urllib.request

        import vendor_template
        payloads = {vendor_template._url(source):
                    (tree / ".vendor-replay" / (rel + ".bin")).read_bytes()
                    for rel, source in vendor_template.FILES.items()}
        urllib.request.urlopen = lambda url: io.BytesIO(payloads[url])
    sys.argv = [str(tree / "tools" / tool), *flags]
    try:
        runpy.run_path(sys.argv[0], run_name="__main__")
    finally:
        with original_open(tree / ".generator-writes.json", "wb") as stream:
            stream.write(json.dumps(sorted(writes)).encode("utf-8"))


def _run(tree, tool, flags, windows=True):
    code = ("import pathlib, runpy, sys; "
            "runpy.run_path(sys.argv[1])['_run_generator']("
            "pathlib.Path(sys.argv[2]), sys.argv[3], sys.argv[5:], sys.argv[4] == '1')")
    return subprocess.run([sys.executable, "-c", code, __file__, str(tree), tool,
                           "1" if windows else "0", *flags],
                          cwd=tree, capture_output=True)


@pytest.mark.parametrize("tool,flags", GENERATORS, ids=[g[0] for g in GENERATORS])
def test_windows_text_defaults_do_not_change_committed_bytes(archived_tree, tool, flags):
    tree = archived_tree
    before = {p: p.read_bytes() for p in tree.rglob("*")
              if p.is_file() and "__pycache__" not in p.parts
              and p.name != ".generator-writes.json"}
    result = _run(tree, tool, flags)
    assert result.returncode == 0, result.stdout + result.stderr
    changed = [str(p.relative_to(tree)) for p, data in before.items()
               if p.read_bytes() != data]
    # Restore even a failing writer so the next case has the same inputs.
    for p, data in before.items():
        if p.read_bytes() != data:
            p.write_bytes(data)
    assert changed == [], changed


@pytest.mark.parametrize("tool,flags", GENERATORS, ids=[g[0] for g in GENERATORS])
def test_check_refuses_crlf_even_when_the_text_is_the_same(archived_tree, tool, flags):
    tree = archived_tree
    # Observe the actual writer to find its outputs, rather than maintain
    # another list that could omit a new table or a second SVG.
    result = _run(tree, tool, flags, windows=False)
    assert result.returncode == 0, result.stdout + result.stderr
    outputs = [Path(p) for p in json.loads((tree / ".generator-writes.json").read_bytes())
               if Path(p).is_file()]
    if tool == "capabilities_svg.py" and tree / "README.md" not in outputs:
        outputs.append(tree / "README.md")
    assert outputs, "the generator wrote no text output"
    check_flags = ("docs/capabilities.json", "--check") if tool == "capabilities_svg.py" else ("--check",)
    clean = _run(tree, tool, check_flags)
    assert clean.returncode == 0, clean.stdout + clean.stderr
    # Each output has its own negative control: a gate must see drift in
    # the second picture or a later pack as well as the first one.
    for p in outputs:
        data = p.read_bytes()
        p.write_bytes(data.replace(b"\n", b"\r\n"))
        try:
            result = _run(tree, tool, check_flags)
            assert result.returncode == 1, (str(p.relative_to(tree)), result.stdout, result.stderr)
        finally:
            p.write_bytes(data)


def test_picture_stamps_are_hashes_of_the_written_bytes(archived_tree):
    tree = archived_tree
    for tool, flags in (("gen_door.py", ()),
                        ("capabilities_svg.py", ("docs/capabilities.json",))):
        result = _run(tree, tool, flags)
        assert result.returncode == 0, result.stdout + result.stderr
    page = (tree / "README.md").read_bytes()
    for path in ("docs/assets/door.svg", "docs/assets/verdict.svg", "docs/capabilities.svg"):
        stamp = re.search(re.escape(Path(path).name.encode()) + rb"\?v=([0-9a-f]+)", page)
        assert stamp is not None, path
        digest = hashlib.sha256((tree / path).read_bytes()).hexdigest().encode()
        assert stamp[1] == digest[:len(stamp[1])], path
