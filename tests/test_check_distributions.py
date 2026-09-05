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

def _the_setting(configuration: str) -> str:
    """The `license-files` assignment, however it is written.

    Not a parse of the value -- only enough to find the lines the
    setting occupies, so a question about what it names can be asked of
    the text. A regular expression over the value broke on a glob; the
    first occurrence of the word is in the comment above it.
    """
    lines = configuration.splitlines()
    start = [i for i, line in enumerate(lines)
             if line.lstrip().startswith("license-files")]
    if not start:
        return ""
    setting = []
    for line in lines[start[0]:]:
        setting.append(line)
        if "]" in line:
            break
    return "\n".join(setting)


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
    "License-File: NOTICE\nLicense-File: THIRD_PARTY.md\nSummary: x\n",
    # Headers, a blank line, then the description -- which for this
    # project is the README. A line in prose that looks like a header
    # was read as one, so a sentence in the README could make the gate
    # accept a planted file of that name.
    "Metadata-Version: 2.4\nName: x\nLicense-File: LICENSE\n"
    "License-File: NOTICE\nLicense-File: THIRD_PARTY.md\n"
    "\n# aas-submodel-validate\n\nLicense-File: docs/scope.md\n",
    # The same file as written on Windows. `\r\n\r\n` is not `\n\n`,
    # so the boundary was not found and the description was read again.
    ("Metadata-Version: 2.4\r\nName: x\r\nLicense-File: LICENSE\r\n"
     "License-File: NOTICE\r\nLicense-File: THIRD_PARTY.md\r\n"
     "\r\n# aas-submodel-validate\r\n\r\nLicense-File: docs/scope.md\r\n"),
    # And the third line ending, so the split is total rather than
    # nearly so.
    ("Metadata-Version: 2.4\rName: x\rLicense-File: LICENSE\r"
     "License-File: NOTICE\rLicense-File: THIRD_PARTY.md\r"
     "\r# aas-submodel-validate\r\rLicense-File: docs/scope.md\r"),
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
    explicit list is what stops that.

    Asked of the text, not of a parse of it. This used to call the
    gate's own regular expression, which cannot read a single-quoted
    list or an indented key -- so changing the spelling of a setting
    that still names all three failed the suite saying the
    configuration no longer names them."""
    block = _the_setting((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert block, "nothing overrides setuptools' default licence glob"
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY.md"):
        assert name in block, \
            "%s is attributed and license-files does not name it" % name


@pytest.mark.parametrize("configuration,names", [
    ('license-files = ["LICENSE", "NOTICE"]', True),
    ("license-files = ['LICENSE', 'NOTICE']", True),
    ('license-files = [\n  "LICENSE",\n  "NOTICE",\n]', True),
    ('license-files=["LICENSE","NOTICE"]', True),
    # A top-level TOML key may be indented and is still the setting.
    # Refusing it called a correct configuration red, with the diagnosis
    # "nothing overrides setuptools' default licence glob" -- and the
    # paragraph above names an indented key as a thing this must read.
    # Nothing measured that: the shipped file is not indented, so
    # reverting the fix left the suite green.
    ('  license-files = ["LICENSE", "NOTICE"]', True),
    # The comment above the setting mentions it too, and taking the
    # first occurrence of the word read that instead.
    ('# see `license-files` below\nlicense-files = ["LICENSE", "NOTICE"]', True),
    ("# license-files is not set here, on purpose\nname = 'x'", False),
    ("name = 'x'", False),
])
def test_the_setting_is_found_however_it_is_spelled(configuration, names):
    block = _the_setting(configuration)
    assert bool(block) is names, block
    if names:
        assert "LICENSE" in block and "NOTICE" in block


@pytest.mark.parametrize("member", [
    DIST_INFO + "/NOTICE.internal.md",
    DIST_INFO + "/licenses/NOTICE.internal.md",
    DIST_INFO + "/licenses/notes.md",
    # The names that made the hole, in the placement that has it. These
    # five were listed for the flat branch only -- and the flat branch
    # is what setuptools wrote before 77, while `licenses/` is what
    # builds this project. So the case the fix was named for was the one
    # case not covered: putting the hole back left all 837 green while a
    # planted `licenses/README.md` walked through a real wheel.
    DIST_INFO + "/licenses/README.md",
    DIST_INFO + "/licenses/Makefile",
    DIST_INFO + "/licenses/pyproject.toml",
    DIST_INFO + "/licenses/CHANGELOG.md",
    DIST_INFO + "/licenses/.gitignore",
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


@pytest.mark.parametrize("filename,mine", [
    ("aas_submodel_validate-0.1.1-py3-none-any.whl", True),
    ("aas_submodel_validate-0.1.1.tar.gz", True),
    # setuptools normalised sdist filenames in 69.3, and this project's
    # build requirement admits the versions that write hyphens. Knowing
    # one spelling meant an sdist built with an older one matched
    # nothing and was skipped without a word; the change that fixed it
    # had no test, and reverting it left the whole suite green.
    ("aas-submodel-validate-0.1.1.tar.gz", True),
    # Somebody else's. The release downloads the dependency wheel into
    # the same directory so the offline route resolves, and every file
    # inside another project's wheel is untracked here -- true, and not
    # this gate's business.
    ("aas_core3_0-1.1.4-py3-none-any.whl", False),
    ("aas-core3.0-1.1.4.tar.gz", False),
    # Not a distribution at all. `dist/` holds these during a release.
    ("SHA256SUMS", False),
    ("smtv.pyz", False),
])
def test_the_gate_looks_at_this_projects_artifacts_and_no_others(filename, mine):
    assert _gate().ours(filename) is mine, filename


def test_the_run_itself_examines_an_sdist_named_the_older_way(tmp_path,
                                                              monkeypatch,
                                                              capsys):
    """Asked of `main`, and of what it said.

    The first version checked `ours()` and passed while `main` used a
    condition of its own, so a change that stopped it reading the
    constant left every test green. The second asked `main` for an exit
    code of 1 -- which "no distributions in dist/" also returns, so the
    same mutant walked through a second time. What has to be true is
    that the run *found the file and named it*.
    """
    import tarfile
    gate = _gate()
    monkeypatch.setattr(gate, "DIST", tmp_path)
    # The rule this exercises needs an index to compare against, and an
    # unpacked sdist has none. Pinned rather than skipped: `tracked` is
    # what decides, so it is told the answer and the selection is what
    # gets measured. Written first without this, it failed in exactly
    # the place `MANIFEST.in` promises the suite runs -- which is the
    # third time in a day a test here has assumed a checkout.
    monkeypatch.setattr(gate, "tracked", lambda: {"pyproject.toml"})

    stray = tmp_path / "note.md"
    stray.write_text("not tracked by this repository\n", encoding="utf-8")
    for name in ("aas-submodel-validate-0.1.1.tar.gz",
                 "aas_submodel_validate-0.1.1.tar.gz"):
        archive_path = tmp_path / name
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(stray, arcname=name.split(".tar.gz")[0] + "/note.md")
        capsys.readouterr()
        assert gate.main() == 1
        said = capsys.readouterr().err
        assert "note.md" in said, \
            "%s went unexamined; the run said %r" % (name, said)
        archive_path.unlink()

    # Somebody else's, in the same directory during a release: not this
    # gate's business, and there is then nothing of ours to look at.
    with tarfile.open(tmp_path / "aas_core3_0-1.1.4.tar.gz", "w:gz") as archive:
        archive.add(stray, arcname="aas_core3_0-1.1.4/note.md")
    capsys.readouterr()
    assert gate.main() == 1
    assert "no distributions" in capsys.readouterr().err


def test_an_empty_index_is_not_an_answer(tmp_path, monkeypatch, capsys):
    """A repository tracking nothing cannot have produced a
    distribution, so an empty `git ls-files` is `git init` inside an
    unpacked sdist rather than a reply.

    Taking it as one marks every member untracked and reports the whole
    archive. The paragraph above `tracked` said exactly that would
    happen and guarded only the two cases where git itself fails."""
    import subprocess
    gate = _gate()
    try:
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=False)
    except OSError:                              # git is not installed
        pytest.skip("git is not available")
    if not (tmp_path / ".git").is_dir():
        pytest.skip("git is not available")
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    assert gate.tracked() is None
    assert "nothing was concluded" in capsys.readouterr().err


def test_a_note_planted_inside_a_metadata_directory_is_not_exempt():
    assert not _gate().is_build_metadata(DIST_INFO + "/notes.md")


def test_a_metadata_suffix_on_a_file_does_not_exempt_it():
    """`.dist-info`, `.egg-info` and `.data` name directories the build
    system writes, and the check that recognises them read the suffix
    off any path segment -- including the last one, which is a file. A
    file called `evil.data` anywhere in a distribution answered "yes,
    the build wrote me", and the tracked-files rule let it past: an
    untracked payload in a wheel, reported as nothing.

    What makes a metadata directory a directory is that something is
    inside it."""
    gate = _gate()
    for planted in ("aas_submodel_validate/evil.data",
                    "aas_submodel_validate/notes.egg-info",
                    "anything.dist-info",
                    "aas_submodel_validate/data/smt/x.dist-info"):
        assert not gate.is_build_metadata(planted), (
            "%s is a file wearing a directory's suffix and the gate "
            "excused it" % planted)
    # The control: the same names with something inside them are what
    # the suffix is for, and they stay exempt.
    for real in ("aas_submodel_validate-0.1.1.dist-info/RECORD",
                 "aas_submodel_validate-0.1.1.dist-info/METADATA",
                 "aas_submodel_validate.egg-info/PKG-INFO",
                 "aas_submodel_validate.egg-info/SOURCES.txt"):
        assert gate.is_build_metadata(real), (
            "%s is what the build system writes and the gate stopped "
            "recognising it" % real)
    # Not a control, an observation kept where somebody will see it: a
    # `.data/` payload is reported rather than exempted, before this
    # change and after. Nothing in this project puts one there, and if
    # something ever does, the tracked-files rule is the right question
    # to ask of it.
    assert not gate.is_build_metadata(
        "aas_submodel_validate-0.1.1.data/scripts/smtv")


def _sdist_with(tmp_path, extra):
    """An sdist-shaped tar whose members `extra` adds to, by hand."""
    import io
    import tarfile

    made = tmp_path / "aas_submodel_validate-0.1.1.tar.gz"
    with tarfile.open(made, "w:gz") as archive:
        info = tarfile.TarInfo("aas_submodel_validate-0.1.1/PKG-INFO")
        body = b"Metadata-Version: 2.4\nName: aas-submodel-validate\n"
        info.size = len(body)
        archive.addfile(info, io.BytesIO(body))
        for member in extra:
            archive.addfile(member, io.BytesIO(b"")
                            if member.isfile() else None)
    return made


def test_a_symlink_is_a_member_too(tmp_path):
    """`members()` kept only what `isfile()` accepted, on the reasoning
    that directories are carried by tar and listed by no `git ls-files`.
    A symbolic link is neither a file nor a directory, so it was dropped
    silently -- and a link is a payload: unpacked, `passwd_leak ->
    /etc/passwd` is a path out of the tree that this gate reported as
    nothing at all."""
    import tarfile

    link = tarfile.TarInfo("aas_submodel_validate-0.1.1/passwd_leak")
    link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
    gate = _gate()
    names = [name for name, _repository in gate.members(_sdist_with(tmp_path, [link]))]
    assert any(name.endswith("passwd_leak") for name in names), (
        "a symbolic link rode along and the gate never saw it: %s" % names)


def test_the_directory_an_sdist_unpacks_into_has_to_be_its_own(tmp_path):
    """A member's repository path is taken by dropping the first path
    component, because an sdist puts everything under one directory
    named for the distribution. Nothing checked that it *was* that
    directory, so `WHATEVER/docs/scope.md` mapped to a tracked file and
    passed -- one archive, two roots, and the second one unreported."""
    import tarfile

    stray = tarfile.TarInfo("WHATEVER/docs/scope.md")
    stray.size = 0
    gate = _gate()
    pairs = dict(gate.members(_sdist_with(tmp_path, [stray])))
    assert pairs["WHATEVER/docs/scope.md"] != "docs/scope.md", (
        "a member under a directory that is not this distribution's was "
        "read as if it were, so a tracked path vouched for it")
