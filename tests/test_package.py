"""The package exists, imports, and says who it is."""
import pytest

import aas_submodel_validate


def test_version_is_a_sane_string():
    major, minor, patch = aas_submodel_validate.__version__.split(".")
    assert all(part.isdigit() for part in (major, minor, patch))


def test_the_two_places_that_say_the_version_say_the_same_one():
    """The build reads one of these and the tool reads the other.

    They drifted, and the release gate could not see it: it compares the
    tag against `__version__` and calls that "three places say the
    version -- the package, the tag and the CHANGELOG". The fourth,
    which decides what the artifact is actually *called*, was read by
    nobody. A tag pushed in that state passes every check, builds a
    wheel named for the older version, and the publisher offers it to an
    index that already has one under that name.
    """
    import pathlib
    import re

    from aas_submodel_validate import __version__

    root = pathlib.Path(__file__).resolve().parents[1]
    declared = re.search(r'(?m)^version = "([^"]+)"',
                         (root / "pyproject.toml").read_text(encoding="utf-8"))
    assert declared, "pyproject.toml no longer declares a version"
    assert declared.group(1) == __version__, (
        "pyproject.toml says %s and the package says %s; the wheel would "
        "be named for the first and report itself as the second"
        % (declared.group(1), __version__))


def test_no_distribution_rule_names_a_file_this_project_does_not_ship():
    """A rule that excludes something says the something exists.

    `MANIFEST.in` travels inside the sdist, and `.gitignore` is on the
    front page of the repository. Two of the three exclusions here did
    no work -- setuptools does not collect a root `.md` it was not told
    about, and there is no `graft .claude` for a `prune` to undo -- so
    all they published was the names. Measured by deleting all three and
    building: only the one under `graft docs` changed what shipped.

    Deleting all three and keeping `graft docs` opened a real leak in
    place of a disclosure, so `docs/` is named file by file instead: a
    new document does not travel until somebody adds it, and nothing
    here spells out what must not."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    manifest = (root / "MANIFEST.in").read_text(encoding="utf-8")
    for word in ("CLAUDE", "AGENTS", ".claude", "findings", "audits"):
        assert word not in manifest, (
            "MANIFEST.in names %r, and this file ships inside the sdist" % word)

    # Named file by file, not grafted: the first attempt at the above
    # deleted the exclusions and left `graft docs`, which meant a working
    # note dropped in that directory shipped. Planted one and it did.
    assert "graft docs" not in manifest, \
        "docs/ is grafted again, so anything left in it ships"
    # Asked of the directory, not of git. The first version shelled out
    # to `git ls-files`, which is empty in an unpacked sdist -- where
    # `MANIFEST.in`'s own first paragraph promises this suite runs -- so
    # the check passed there having asked nothing, and raised
    # FileNotFoundError anywhere git is not installed, which is most
    # distribution build environments.
    # Read from the directory, minus what `.gitignore` keeps out of it.
    # Asking git instead was empty in an unpacked sdist and raised where
    # git is absent; asking the directory alone failed `make check` the
    # moment somebody put a working note in `docs/` -- and told them the
    # note was "published here and would not reach an sdist", whose
    # remedy is to add it to the manifest, which is the leak this list
    # exists to prevent.
    # An sdist has no `.gitignore` -- and no working notes either, since
    # they are what it excludes -- so an empty set is the right answer
    # there rather than a skip. The assertion below still runs: this
    # subtraction narrows what is asked, it is not the asking.
    exclusions = root / ".gitignore"
    local = {line.strip().lstrip("/").split("/", 1)[-1]
             for line in (exclusions.read_text(encoding="utf-8").splitlines()
                          if exclusions.is_file() else [])
             if line.startswith("/docs/")}
    published = sorted(p.name for p in (root / "docs").iterdir()
                       if p.is_file() and not p.name.startswith(".")
                       and p.name not in local)
    assert published, "docs/ holds nothing"
    for name in published:
        assert "include docs/%s" % name in manifest, \
            "docs/%s would not reach an sdist; name it in MANIFEST.in, or " \
            "keep it out of docs/ if it is not meant to travel" % name


def test_nothing_local_is_tracked():
    """The exclusions are in `.gitignore` because that is the only file a
    clone carries.

    They were moved to `.git/info/exclude` once, on the reasoning that a
    rule excluding something says the something exists. It does -- and
    that file is not cloned, so every fresh checkout was one `git add -A`
    away from committing the things it named. Measured in a clone: all
    five appeared in `git status` and staged. Publishing the names is the
    cheaper of the two.

    This asks the other half: that none of them is tracked now."""
    import pathlib
    import subprocess
    root = pathlib.Path(__file__).resolve().parents[1]
    try:
        listed = subprocess.run(["git", "ls-files"], cwd=str(root),
                                capture_output=True, text=True)
    except OSError:                    # git is not installed
        pytest.skip("git is not available")
    if listed.returncode != 0:
        pytest.skip("not a git checkout")
    tracked = set(listed.stdout.split())
    # A `git ls-files` that succeeds says nothing about whether this
    # tree has a `.gitignore`: unpack an sdist inside somebody else's
    # working copy and it succeeds, and the read below raised. The
    # sibling check learned this one commit earlier and this half did
    # not -- the same file, the same shape -- and then a third place in
    # `test_registry.py` met it again. `builders.tracked_files` is the
    # one body now; this check keeps its own `.gitignore` question,
    # which is about this repository rather than about git.
    exclusions = root / ".gitignore"
    if not exclusions.is_file():
        pytest.skip("not a checkout of this repository")
    ignored = [line.strip().lstrip("/").rstrip("/")
               for line in exclusions.read_text(encoding="utf-8").splitlines()
               if line.startswith("/")]
    assert ignored, ".gitignore names no local-only path"
    for name in ignored:
        offenders = [t for t in tracked if t == name or t.startswith(name + "/")]
        assert not offenders, "%s is local-only and tracked" % offenders



def test_a_table_can_be_built_from_the_package_alone():
    """The reason the row builder is in `src/` and not in `tools/`.

    `tools/` is not installed and must not be: a wheel carrying it would
    put two more top-level names into everybody's site-packages, which
    `tools/check_distributions.py` refuses in writing. So while the
    builder lived there, an installed copy of this package could not
    build a table from a template, and neither could the single-file
    build, which copies exactly this directory and nothing else.

    A mode that reads a template a caller supplies has to answer the same
    from every entrance, and an entrance that cannot reach the builder is
    an entrance that answers differently. This asks the package on its
    own -- no repository, no `tools` on the path.
    """
    import os
    import pathlib
    import subprocess
    import sys

    # In a process where `tools` is not on the path at all. Asserting
    # that `tools` is absent from `sys.modules` was the first spelling
    # and it asked about the session rather than about the package: the
    # whole suite imports `tools` elsewhere, so it failed for a reason
    # that has nothing to do with whether the package stands alone.
    root = pathlib.Path(__file__).resolve().parents[1]
    asking = (
        "import json, pathlib, sys\n"
        "from aas_submodel_validate import tablegen\n"
        "import importlib.util as u\n"
        "assert u.find_spec('tools') is None, 'tools is reachable; ask again'\n"
        "here = pathlib.Path(tablegen.__file__).parent\n"
        "t = here / 'data' / 'smt' / '02003' / '2.0.1' / 'template.json'\n"
        "assert t.is_file(), 'the vendored template does not travel'\n"
        "b = tablegen.build(json.loads(t.read_text('utf-8-sig')),\n"
        "                   {'prefix': 'TD-E', 'citation': 'c',\n"
        "                    'skip_sids': frozenset(), 'item_names': {},\n"
        "                    'example_types': ('ExampleValue',)})\n"
        "print(len(b['tree']), b['submodel_sid'])\n")
    done = subprocess.run([sys.executable, "-c", asking], capture_output=True,
                          text=True, cwd=str(root / "src"),
                          env={k: v for k, v in os.environ.items()
                               if k not in ("PYTHONPATH",)})
    assert done.returncode == 0, done.stdout + done.stderr
    rows, sid = done.stdout.split()
    assert int(rows) > 0, "no rows came out"
    assert sid == "0173-1#01-AHX837#002", sid


def test_the_single_file_carries_the_row_builder():
    """The entrance most likely to be forgotten, because it is built by a
    script rather than by packaging metadata."""
    import pathlib
    import subprocess
    import sys
    import tempfile
    import zipfile

    root = pathlib.Path(__file__).resolve().parents[1]
    if not (root / "tools" / "build_zipapp.py").is_file():   # pragma: no cover
        pytest.skip("not a checkout")
    built = pathlib.Path(tempfile.mkdtemp()) / "smtv.pyz"
    done = subprocess.run([sys.executable, str(root / "tools" / "build_zipapp.py"),
                           "-o", str(built)],
                          capture_output=True, text=True, cwd=str(root))
    assert done.returncode == 0, done.stdout + done.stderr
    with zipfile.ZipFile(built) as archive:
        assert any(name.endswith("/tablegen.py") or name == "tablegen.py"
                   for name in archive.namelist()), \
            "the single file cannot build a table"
