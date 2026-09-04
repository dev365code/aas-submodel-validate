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
    published = sorted(p.name for p in (root / "docs").iterdir()
                       if p.is_file() and not p.name.startswith("."))
    assert published, "docs/ holds nothing"
    for name in published:
        assert "include docs/%s" % name in manifest, \
            "docs/%s is published here and would not reach an sdist" % name


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
    listed = subprocess.run(["git", "ls-files"], cwd=str(root),
                            capture_output=True, text=True)
    if listed.returncode != 0:
        pytest.skip("not a git checkout")
    tracked = set(listed.stdout.split())
    ignored = [line.strip().lstrip("/").rstrip("/")
               for line in (root / ".gitignore").read_text(encoding="utf-8").splitlines()
               if line.startswith("/")]
    assert ignored, ".gitignore names no local-only path"
    for name in ignored:
        offenders = [t for t in tracked if t == name or t.startswith(name + "/")]
        assert not offenders, "%s is local-only and tracked" % offenders
