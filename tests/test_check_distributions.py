"""The packaging gate, asked about layouts it will meet.

It had no tests at all, and it is the only thing standing between a
working copy and what goes on an index -- a sibling of every rule here
is a thing that has actually shipped somewhere.

The two placements of a licence file are the case that matters: which
one a build produces depends on the version of setuptools that ran, and
this project declares support for a floor that produces the older one.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _gate():
    spec = importlib.util.spec_from_file_location(
        "_check_distributions", ROOT / "tools" / "check_distributions.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DIST_INFO = "aas_submodel_validate-0.1.1.dist-info"

#: What a build of this project writes into its own metadata.
DECLARED = ("LICENSE", "NOTICE", "THIRD_PARTY.md")


@pytest.mark.parametrize("member", [
    # setuptools >= 77 puts them in a subdirectory; older ones do not,
    # and `requires = ["setuptools>=64"]` says both are supported. The
    # gate knew only the newer layout, and answered "this repository does
    # not track it" about a file the repository tracks -- rejecting a
    # correct build, which is the failure this project fears most.
    DIST_INFO + "/licenses/THIRD_PARTY.md",
    DIST_INFO + "/THIRD_PARTY.md",
    DIST_INFO + "/licenses/LICENSE",
    DIST_INFO + "/LICENSE",
    DIST_INFO + "/licenses/NOTICE",
    DIST_INFO + "/NOTICE",
])
def test_a_declared_licence_file_is_recognised_in_either_placement(member):
    gate = _gate()
    recovered = gate._repository_path(member, DECLARED)
    assert (ROOT / recovered).is_file(), \
        "%s was mapped to %r, which is not in this tree" % (member, recovered)
    assert not gate.is_build_metadata(recovered)


#: How every spelling of `license-files` reaches this gate. The build
#: resolves the setting and writes the names it actually used, so a glob
#: arrives here as filenames.
METADATA_SPELLINGS = (
    "License-File: LICENSE\nLicense-File: NOTICE\nLicense-File: THIRD_PARTY.md\n",
    "Metadata-Version: 2.4\nName: x\nLicense-File: LICENSE\n"
    "License-File: NOTICE\nLicense-File: THIRD_PARTY.md\nDescription\n",
)


@pytest.mark.parametrize("metadata", METADATA_SPELLINGS)
def test_the_declared_files_are_read_from_the_build_not_the_configuration(metadata):
    """Reading `pyproject.toml` for this could not answer for a glob.

    A regular expression over `license-files = [...]` stops at the first
    `]`, so `LICEN[CS]E*` returned nothing -- the permissive answer, and
    harmless. `LICENSE*` has no bracket: it parsed cleanly as the literal
    string `LICENSE*`, matched no member, and the gate reported
    `<dist-info>/licenses/LICENSE` as a file this repository does not
    track. A correct build refused, which is the failure this file
    exists not to cause, on the branch that builds this project.

    The build has already resolved the setting by the time an archive
    exists, and writes the names it used. Asking the archive answers for
    every spelling, and is what the module says it does."""
    gate = _gate()
    declared = gate._licence_files(metadata)
    assert declared == ("LICENSE", "NOTICE", "THIRD_PARTY.md")
    for member in (DIST_INFO + "/licenses/LICENSE", DIST_INFO + "/LICENSE"):
        assert gate._repository_path(member, declared) == "LICENSE"


def test_a_build_that_declares_nothing_is_not_refused():
    """No `License-File:` at all is "no opinion", not "none of them".

    Very old metadata carries no such header, and answering "nothing was
    relocated" there would report every licence file in the archive as
    untracked."""
    gate = _gate()
    assert gate._licence_files("Metadata-Version: 2.1\nName: x\n") == ()
    assert gate._repository_path(DIST_INFO + "/LICENSE", ()) == "LICENSE"
    assert gate._repository_path(DIST_INFO + "/licenses/LICENSE", ()) == "LICENSE"


def test_the_configuration_still_names_them_explicitly():
    """Not what the gate reads, and still worth asking: setuptools'
    default glob sweeps `NOTICE*` and `LICEN[CS]E*` from the top of the
    tree, so an untracked working note gets copied into the wheel. An
    explicit list is what stops that."""
    gate = _gate()
    declared = gate.declared_licence_files()
    assert "THIRD_PARTY.md" in declared, \
        "the configuration no longer names the attribution files"


@pytest.mark.parametrize("member", [
    DIST_INFO + "/NOTICE.internal.md",
    DIST_INFO + "/licenses/NOTICE.internal.md",
    DIST_INFO + "/licenses/notes.md",
    # Named like something this repository tracks, which is what made
    # the second version of the mapping let them past: it relocated
    # anything to the tree root, and the tree has a README, a Makefile
    # and a pyproject. None of them has any business in a metadata
    # directory.
    DIST_INFO + "/README.md",
    DIST_INFO + "/Makefile",
    DIST_INFO + "/pyproject.toml",
    DIST_INFO + "/CHANGELOG.md",
    DIST_INFO + "/.gitignore",
])
def test_something_that_only_looks_like_one_is_still_asked_about(member):
    """setuptools' default glob collects `NOTICE*` from the top of the
    tree, so an untracked working note called `NOTICE.internal.md` gets
    copied in. Exempting the directory answered "is this a licence
    file?" when the question is "did this repository put it there?"."""
    gate = _gate()
    recovered = gate._repository_path(member, DECLARED)
    assert not gate.is_build_metadata(recovered)
    # The member itself, unmoved. Only a declared licence file is
    # relocated, in either placement, so the tracked-files rule is asked
    # about this exactly where the archive holds it.
    #
    # Written first as "either it is not a file in the tree, or it is a
    # declared licence file" -- an `or` with an escape hatch, and a wrong
    # answer walked through it: a bug made this return `THIRD_PARTY.md`
    # for every one of these, which is a file *and* a declared licence
    # file, so the assertion held while the mapping answered nonsense.
    # Asked of the correspondence now.
    assert recovered == member, (
        "%s was relocated to %r, and nothing but a declared licence file "
        "moves" % (member, recovered))


@pytest.mark.parametrize("member", [
    DIST_INFO + "/METADATA",
    DIST_INFO + "/RECORD",
    DIST_INFO + "/WHEEL",
    "aas_submodel_validate.egg-info/SOURCES.txt",
    "PKG-INFO",
])
def test_what_the_build_system_writes_is_still_exempt(member):
    assert _gate().is_build_metadata(member)


def test_a_note_planted_inside_a_metadata_directory_is_not_exempt():
    assert not _gate().is_build_metadata(DIST_INFO + "/notes.md")
