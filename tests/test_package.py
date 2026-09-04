"""The package exists, imports, and says who it is."""
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

    The one that works is kept, spelled as a directory, so a new note
    does not need a new line naming it."""
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
    import subprocess
    listed = subprocess.run(["git", "ls-files", "docs/"], cwd=str(root),
                            capture_output=True, text=True)
    for name in listed.stdout.split():
        assert "include %s" % name in manifest, \
            "%s is published here and would not reach an sdist" % name
