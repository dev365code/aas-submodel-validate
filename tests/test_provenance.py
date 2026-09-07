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
        # As the file is addressed inside a distribution, not as this
        # tree spells it: `src/` is a layout of the repository and of
        # nothing that ships, so an entry naming it cannot be matched to
        # a file by anyone holding an install.
        packaged = rel[len("src/"):] if rel.startswith("src/") else rel
        assert packaged in notice, \
            "NOTICE does not name %s, which ships" % packaged
        # THIRD_PARTY.md travels in all three distributions now, so it
        # is addressed the same way for the same reason.
        assert packaged in third_party, \
            "THIRD_PARTY.md does not list %s" % packaged


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


def test_the_digest_bound_the_schema_publishes_is_the_one_in_the_code():
    """A number in the schema that no test derives is a number that
    drifts.

    The prose said `null` for anything "larger than this reader takes
    in at all", which reads as the 64 MiB document bound -- and the
    digest uses the 256 MiB container bound, so a 100 MiB document is
    refused, judged nothing, and comes back with a complete digest. The
    document was describing a stricter tool than the one it ships with.
    """
    import pathlib
    import re

    from aas_submodel_validate import container

    schema = (pathlib.Path(__file__).resolve().parents[1]
              / "docs" / "report-schema.md").read_text(encoding="utf-8")
    row = [line for line in schema.splitlines() if "`inputSha256`" in line]
    assert row, "the schema no longer documents inputSha256"
    stated = re.search(r"\((\d+) MiB", row[0])
    assert stated, "the digest bound is not stated with its number"
    assert int(stated.group(1)) * 1024 * 1024 == container.MAX_TOTAL_PART_BYTES


def test_the_attribution_names_paths_that_exist_where_it_is_read():
    """A notice a reader cannot follow attributes nothing.

    NOTICE listed the CC BY 4.0 files as `src/aas_submodel_validate/...`,
    which is where this tree keeps them and is not where any
    distribution does -- a wheel, an sdist's installed form and the
    single file all carry them under the import name. Somebody holding
    an install could not match an entry to a file, which is the one
    thing the entry is for.

    Found by what a path looks like rather than by where it sits on the
    line. The first version read every bullet as a path, so a bullet of
    prose broke it and, worse, a path named in a sentence went
    unchecked -- and the attribution that had to be added for the
    generated battery table names its file in a sentence.
    """
    import pathlib
    import re as _re
    root = pathlib.Path(__file__).resolve().parents[1]
    notice = (root / "NOTICE").read_text(encoding="utf-8")
    #: A path into the installed package, wherever it appears. The
    #: import name is the anchor: that is what a reader holding a wheel
    #: has, and naming `src/...` was the fault this test was written for.
    paths = _re.compile(r"(?:src/)?aas_submodel_validate/[\w./-]+")
    named = sorted(set(paths.findall(notice)))
    assert named, "NOTICE names no packaged file"
    for path in named:
        assert not path.startswith("src/"), (
            "NOTICE names %r, which is a path in this tree and not in "
            "anything it ships in" % path)
        assert (root / "src" / path).is_file(), \
            "NOTICE names %r and no such file is packaged" % path


def test_a_shipped_module_carrying_a_sources_own_words_is_attributed():
    """The attribution followed the vendored *files* and missed a
    generated one.

    `data/battery-passport/` is in the repository and in no
    distribution, and `THIRD_PARTY.md` said so -- correctly, and then
    stopped. The rule table generated from it is a Python module: it
    ships in the wheel, the source distribution and smtv.pyz, and it
    carries each row's element description verbatim from the IDTA 02035
    templates (CC BY 4.0), the legal references verbatim from the
    BatteryPass-Ready longlist (CC BY 4.0), and the qualifying phrase of
    a conditional provision verbatim from the consolidated regulation.
    So somebody holding a wheel held CC BY material with no attribution
    beside it.

    Derived, not asserted: the verbatim-ness is measured against the
    indexes here, so a table that stops copying stops needing the
    paragraph, and one that starts copying somewhere new fails until
    somebody says where it came from.
    """
    import json
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    data = root / "data" / "battery-passport"
    if not data.is_dir():
        pytest.skip("the indexes are not in this tree (an sdist ships "
                    "the table, not the indexes it came from)")
    from aas_submodel_validate.rules import battery_tables

    def index(name):
        return json.loads((data / name).read_text("utf-8"))["records"]

    idta = {r["id"]: r for r in index("requirements-idta.json")}
    rows = (battery_tables.LAW_REQUIRES_TEMPLATE_OPTIONAL
            + battery_tables.CONDITIONAL_ON_CATEGORY)
    copied = [r for r in rows
              if idta.get(r["element"], {}).get("text") == r["text"] and r["text"]]
    assert copied, "no row copies a source's words any more; check this test"

    notice = (root / "NOTICE").read_text("utf-8")
    assert "aas_submodel_validate/rules/battery_tables.py" in notice, (
        "%d of %d rows carry an IDTA description verbatim into a module "
        "that ships, and NOTICE does not name the file"
        % (len(copied), len(rows)))
    # What CC BY 4.0 section 3(a) asks for, beside the file: the
    # licence and its URI, and a statement that the material was
    # modified. A path on its own is a citation, not an attribution.
    #
    # Asked of the passage that names the file, not of the document.
    # Over the whole of NOTICE this passed with the licence URI deleted
    # from here, because another section carries one -- the assertion
    # was measuring that the document mentions CC BY somewhere, which it
    # would do if this paragraph were removed entirely.
    start = notice.index("aas_submodel_validate/rules/battery_tables.py")
    passage = notice[start:notice.index("Copyright for that material:", start)]
    # Each of these is a thing one of the three sources asks for and
    # nothing else in the passage supplies. `BatteryPass-Ready` alone was
    # here and a mutation that unnamed the document survived it: the
    # word occurs again in the rightsholder's name a line below, so the
    # assertion was satisfied by a different sentence. The Consortium's
    # own recommended citation cannot be satisfied by accident.
    for owed in ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/",
                 "How the material was modified",
                 "BatteryPass-Ready Consortium (2026). Battery",
                 "Data Attribute Longlist v1.3",
                 "CELEX 02023R1542-20250731",
                 "IDTA 02035-1, 02035-4 and 02035-5"):
        assert owed in passage, (
            "the passage attributing the generated table does not carry %r"
            % owed)
    # And the claim next door has to stay true of the directory while
    # being untrue of the table: the sentence that misled is the one
    # that stopped at the directory.
    third_party = (root / "THIRD_PARTY.md").read_text("utf-8")
    assert "battery_tables.py" in third_party, \
        "THIRD_PARTY still says the material is in no distribution and stops"


# -- the gate that says the vendored bytes are the recorded bytes -------------

def _vendor_checker(tmp_path, monkeypatch):
    """`tools/vendor_template.py`'s checker, over a copy of the trees.

    Pointed at a copy so each fault can be handed to it. Every branch of
    this gate could be disabled and the whole suite stayed green --
    measured: `if False` on the hash comparison, on the missing-file
    check and on the stray-file check, three mutants and nothing caught
    one. It is the gate that says the vendored IDTA material is the bytes
    this project recorded, which is the whole of the provenance story
    the front page tells.
    """
    import importlib.util
    import pathlib
    import shutil

    root = pathlib.Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "vendor_template", root / "tools" / "vendor_template.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for rel in module.FILES:
        source = root / rel
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        sums = source.parent / "sha256sums.txt"
        if sums.is_file():
            shutil.copy2(sums, target.parent / "sha256sums.txt")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module, tmp_path


def test_the_vendored_gate_passes_material_it_should_pass(tmp_path, monkeypatch,
                                                          capsys):
    """The control. Without it every assertion below is satisfied by a
    checker that refuses everything."""
    module, _ = _vendor_checker(tmp_path, monkeypatch)
    assert module.check() == 0, capsys.readouterr().err


def test_a_vendored_file_whose_bytes_moved_is_refused(tmp_path, monkeypatch,
                                                      capsys):
    """One byte, in each vendored file in turn.

    Each on its own, because a loop that corrupts them all is satisfied
    by a gate that notices any one of them -- and what is claimed is that
    the recorded hash is checked for every file it names."""
    module, root = _vendor_checker(tmp_path, monkeypatch)
    for rel in sorted(module.FILES):
        target = root / rel
        kept = target.read_bytes()
        target.write_bytes(kept + b"\n")
        try:
            assert module.check() == 1, "%s: a changed byte was accepted" % rel
            assert "hash mismatch" in capsys.readouterr().err, rel
        finally:
            target.write_bytes(kept)
    assert module.check() == 0, capsys.readouterr().err


def test_a_vendored_file_that_is_gone_is_refused(tmp_path, monkeypatch, capsys):
    """Absent is not the same as changed, and the gate answers for both.
    A file deleted between a refresh and a release ships nothing where
    the package promises something."""
    module, root = _vendor_checker(tmp_path, monkeypatch)
    for rel in sorted(module.FILES):
        target = root / rel
        kept = target.read_bytes()
        target.unlink()
        try:
            assert module.check() == 1, "%s: a missing file was accepted" % rel
            assert "missing" in capsys.readouterr().err, rel
        finally:
            target.write_bytes(kept)


def test_material_that_ships_with_no_recorded_hash_is_refused(tmp_path,
                                                              monkeypatch,
                                                              capsys):
    """The third branch, and the one a reader would never think to ask
    about: bytes that travel in the package with nothing recording what
    they are. A hash check over a list is only as complete as the list."""
    module, root = _vendor_checker(tmp_path, monkeypatch)
    beside = root / sorted(module.FILES)[0]
    stray = beside.parent / "extra.json"
    stray.write_text('{"not": "declared"}', "utf-8")
    try:
        assert module.check() == 1, "an undeclared vendored file was accepted"
        said = capsys.readouterr().err
        assert "not declared" in said, said
        assert "extra.json" in said, said
    finally:
        stray.unlink()
    assert module.check() == 0, capsys.readouterr().err
