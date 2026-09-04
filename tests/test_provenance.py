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


#: Vendored material that travels in the distribution rather than staying
#: in the checkout. The corpus does not ship -- the wheel gate asserts its
#: absence -- so only these carry an attribution obligation.
SHIPPED = [rel for rel in vendor_template.FILES if rel.startswith("src/")]


def test_the_notice_names_every_vendored_file_that_ships():
    """CC BY 4.0 attribution is an obligation on the *distribution*, and
    the distribution is whatever `package-data` globbed -- a path glob,
    which picks up a new template without anyone deciding it should.
    pyproject's comment states the obligation in one direction only
    ("NOTICE says the distribution contains it, so it must"); this is the
    other one."""
    notice = (ROOT / "NOTICE").read_text("utf-8")
    third_party = (ROOT / "THIRD_PARTY.md").read_text("utf-8")
    for rel in SHIPPED:
        assert rel in notice, "NOTICE does not name %s, which ships" % rel
        assert rel in third_party, "THIRD_PARTY.md does not list %s" % rel


def test_the_wheel_gate_requires_every_vendored_file_that_ships():
    """The wheel job exists so that "NOTICE lies about what it ships"
    cannot happen -- its own words. Its `required` list is written by
    hand, so it holds only as long as somebody remembers to extend it,
    which is the failure it was built to catch."""
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")
    for rel in SHIPPED:
        installed = rel[len("src/"):]
        sums = installed.rsplit("/", 1)[0] + "/sha256sums.txt"
        for name in (installed, sums):
            assert '"%s"' % name in workflow, \
                "the wheel gate does not require %s" % name


def test_no_recorded_hash_names_a_file_that_is_not_there():
    """A record that vouches for something absent is worse than none.

    `check()` looks each file up in its directory's record, so a record
    naming a file the directory no longer holds is invisible to it, and
    `--refresh` rewrites the file sorted and keeps the orphan. Left one
    behind when the example moved into the package: anyone running
    `shasum -a 256 -c sha256sums.txt` in that directory got a FAILED
    line and exit 1 from a provenance record that is otherwise this
    project's whole argument for what it vendored."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    orphans = []
    for record in root.rglob("sha256sums.txt"):
        for line in record.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            name = line.split(None, 1)[1].strip()
            if not (record.parent / name).is_file():
                orphans.append("%s names %s" % (record.relative_to(root), name))
    assert not orphans, orphans
