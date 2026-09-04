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
