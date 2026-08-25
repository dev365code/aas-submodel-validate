"""What the distribution carries, and what it says it carries.

Two claims travel with every vendored byte. One is a SHA-256 that says
the bytes are upstream's; the other is a sentence in NOTICE that says
this distribution contains them, which CC BY 4.0 requires and which
nothing regenerates. Both are written by hand into files no gate reads.

The hash gate reads a *list*, not the tree: `--check` walks FILES, so a
vendored file that no entry names is invisible to it -- and still ships,
because `package-data` globs on path. That is the shape these tests are
for. The first vendored file added since the gate was written is the
first chance to walk into it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "tools" / "vendor_template.py").exists():
    pytest.skip("no tools/ here (installed package, not a checkout)",
                allow_module_level=True)
sys.path.insert(0, str(ROOT / "tools"))

import vendor_template  # noqa: E402


def _declared(tmp_path, rel: str) -> Path:
    """A vendored file with its digest recorded, as `--refresh` leaves it."""
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"{}\n")
    vendor_template._record(path)
    return path


def test_a_vendored_file_no_entry_names_is_reported(tmp_path, monkeypatch, capsys):
    """The plausible slip: the bytes are committed, the FILES entry is
    forgotten. Every gate stays green -- the generator reads the pack's
    path directly, the hash gate reads FILES -- and an unverified CC BY
    file ships in the wheel."""
    rel = "src/aas_submodel_validate/data/smt/02004/2.0.1/template.json"
    _declared(tmp_path, rel)
    stray = tmp_path / "src/aas_submodel_validate/data/smt/02035-2/1.0/template.json"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"{}\n")

    monkeypatch.setattr(vendor_template, "ROOT", tmp_path)
    monkeypatch.setattr(vendor_template, "FILES", {rel: "upstream/whatever"})
    assert vendor_template.check() == 1
    assert "02035-2" in capsys.readouterr().err


def test_the_files_this_project_writes_itself_are_not_strays(tmp_path, monkeypatch, capsys):
    """`sha256sums.txt` is the gate's own record and the corpus README is
    ours. A sweep that called them unaccounted-for would be a gate nobody
    could leave green, which is a gate people switch off."""
    rel = "tests/corpus/idta/02004/example.json"
    _declared(tmp_path, rel)
    (tmp_path / "tests/corpus/idta/README.md").write_bytes(b"# corpus\n")

    monkeypatch.setattr(vendor_template, "ROOT", tmp_path)
    monkeypatch.setattr(vendor_template, "FILES", {rel: "upstream/whatever"})
    assert vendor_template.check() == 0
    assert "not declared" not in capsys.readouterr().err


def test_this_tree_has_no_vendored_file_that_files_does_not_name():
    """The live invariant, on the real tree."""
    assert vendor_template.undeclared() == []
