#!/usr/bin/env python3
"""What may not be inside a built wheel or sdist.

Two rules, and neither of them is a list of filenames.

**Only what the repository tracks.** A file the tree does not track is
one nobody decided belonged to the project, and a build that picks one
up has reached past the tree into the working directory. Asked of
`git ls-files`, which answers that question -- `git check-ignore`
answers a different one, and the gap between them is the whole risk:
`MANIFEST.in` grafts whole directories, so a note dropped into `docs/`
ships without ever being ignored *or* tracked. Nothing here names a file
it refuses; the list of what belongs is the index itself.

**Not the battery-passport indexes.** Those are a repository
publication, not a Python payload: fifteen thousand lines of JSON in an
install serve nobody, the gate that reads them skips cleanly when they
are absent, and their licences are attributed in the bundle's own README
rather than in this package's metadata.

Both are asked of what the archives actually contain, rather than of
what the packaging configuration says they should hold. Configuration
is a claim about a build; the archive is the build, and only one of the
two can be wrong without anybody noticing. Which files the build
relocated into its metadata directory is asked of the archive too: its
`METADATA` (or an sdist's `PKG-INFO`) lists them under `License-File:`,
resolved to real names. Reading `pyproject.toml` for the same answer was
tried and is what a spelling can break -- a `license-files` glob without
a bracket parsed as a literal pattern, matched nothing, and the gate
reported `LICENSE` as a file this repository does not track.

A wheel is a different namespace from the tree: its members live under
the import name, not under `src/`. Repository paths are recovered before
either rule is applied. The first version compared wheel members against
repository paths directly, so every anchored rule missed on a wheel and
the indexes rule could not match there at all -- measured, by planting
each of them and watching the gate stay green.

Run after `python -m build`. Exits 1 and names every offending member.
"""
from __future__ import annotations

import pathlib
import pathlib as _pathlib
import subprocess
import sys
import sys as _sys
import tarfile
import zipfile

# The package, from wherever this script is. `make` exports
# PYTHONPATH and the lint job installs the package first, but
# CI's wheel job installs nothing and an unpacked sdist has no
# install at all -- and `MANIFEST.in` grafts this directory for
# exactly that reader. Two scripts here already did this; the
# import added to all eight assumed the other six were as
# lucky.
_TOOLS_SRC = str(_pathlib.Path(__file__).resolve().parent.parent / "src")
if _TOOLS_SRC not in _sys.path:
    _sys.path.insert(0, _TOOLS_SRC)

from aas_submodel_validate._terminal import survive  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

#: Both spellings of this project's own name. setuptools normalised
#: sdist filenames to underscores in 69.3 (PEP 625) and writes hyphens
#: before that, and `requires = ["setuptools>=64"]` admits those -- so an
#: sdist built with an older one matched nothing and was skipped in
#: silence, with the summary line still counting what it had looked at.
#: Named here so a test can ask what the gate considers its own.
OURS = ("aas_submodel_validate-", "aas-submodel-validate-")

def ours(name: str) -> bool:
    """Whether a file in `dist/` is a distribution of this project.

    `dist/` also holds the dependency wheel the release downloads so the
    offline route resolves, and every file inside somebody else's wheel
    is untracked here -- true, and not this gate's business, and it
    would have arrived as hundreds of reports the first time those two
    steps were reordered.

    A function rather than an expression inside `main`, so a test can
    ask the gate this instead of restating it: the first version of that
    test rebuilt the condition, and a change that stopped `main` reading
    it at all left every test green.
    """
    return name.startswith(OURS) and (name.endswith(".whl")
                                      or name.endswith(".tar.gz"))


#: Tracked, published here, and deliberately not shipped.
NOT_A_PAYLOAD = "data/battery-passport/"

#: Where an installed package's files come from in the tree. A wheel
#: member `aas_submodel_validate/cli.py` is `src/aas_submodel_validate/
#: cli.py` here, and mapping the one spelling to the other is what makes
#: a rule written for the tree hold for a wheel at all.
IMPORT_ROOT = "aas_submodel_validate/"
SOURCE_ROOT = "src/"

#: Directories the build system owns. Matched as a whole path segment:
#: `endswith` on the raw path let `evil-PKG-INFO/notes.md` through.
METADATA_DIRS = (".egg-info", ".dist-info", ".data")

#: Files the packaging standards put at the top of a distribution, and
#: inside a metadata directory. Named, because a blanket exemption for
#: everything under `*.egg-info/` hides a file put there on purpose --
#: and `endswith` on a raw path let `evil-PKG-INFO/notes.md` through
#: besides.
METADATA_FILES = ("PKG-INFO", "setup.cfg")
METADATA_MEMBERS = ("PKG-INFO", "RECORD", "WHEEL", "METADATA", "SOURCES.txt",
                    "entry_points.txt", "top_level.txt", "requires.txt",
                    "dependency_links.txt", "not-zip-safe", "zip-safe",
                    "AUTHORS", "REQUESTED", "INSTALLER")


def _licence_files(text: str) -> tuple:
    """The names the build says it relocated, from an archive's own
    metadata.

    `License-File:` is written by the build after resolving whatever
    `license-files` said -- a glob arrives here as the names it matched.
    So this answers for every spelling, which is the thing reading the
    configuration could not do.

    Headers only. A metadata file is headers, one blank line, then the
    project description -- which for this project is its README -- and
    reading the whole file took a `License-File:` line written in prose
    as a declaration. Measured: a line like that in the README made the
    gate accept a planted file of that name.
    """
    # Normalised first: a metadata file written on Windows separates its
    # headers from the description with `\r\n\r\n`, so splitting on
    # `\n\n` found no boundary and read the description again.
    plain = text.replace("\r\n", "\n").replace("\r", "\n")
    headers = plain.split("\n\n", 1)[0]
    return tuple(line.split(":", 1)[1].strip()
                 for line in headers.splitlines()
                 if line.startswith("License-File:"))


def _in_metadata_dir(path: str) -> bool:
    """Whether any *directory* on this path is one the build writes.

    The last segment is a file, and a file is not a directory however it
    is spelled: this read the suffix off every segment, so `evil.data`
    matched, `rest` came back empty, and the caller answered "the build
    system wrote this" about a planted payload. What makes a metadata
    directory a directory is that something is inside it.
    """
    return any(part.endswith(METADATA_DIRS) for part in path.split("/")[:-1])


def is_build_metadata(path: str) -> bool:
    """A file the build system writes, and only those.

    Inside a metadata directory the name has to be one the packaging
    standards define -- `licenses/` is theirs too, so its contents pass.
    Everything else inside is reported: a note dropped into an
    `.egg-info/` is still a note.
    """
    parts = path.split("/")
    if _in_metadata_dir(path):
        for index, part in enumerate(parts):
            if part.endswith(METADATA_DIRS):
                rest = parts[index + 1:]
                if not rest:
                    return True
                if rest[0] == "licenses":
                    # Not exempt -- relocated. The build copies these
                    # from the top of the tree, so the tracked-files rule
                    # is exactly the right question and just has to be
                    # asked of where they came from. Exempting the whole
                    # directory answered "is it a licence file?" when the
                    # question is "did this repository put it there?":
                    # setuptools' default `license-files` glob picks up
                    # anything matching NOTICE*, LICEN[CS]E*, COPYING* or
                    # AUTHORS* at the root, so an untracked working note
                    # named NOTICE.internal.md shipped in the wheel while
                    # this printed its green line. Planted, and it did.
                    return False
                return len(rest) == 1 and rest[0] in METADATA_MEMBERS
    return len(parts) == 1 and parts[0] in METADATA_FILES


def members(artifact: pathlib.Path):
    """(name in the archive, path in the repository), files only.

    Directories are dropped rather than compared: a tar carries them as
    members of their own and `git ls-files` lists no directory, so every
    one of them read as untracked -- twenty-one false reports on a clean
    build, which is the shape that teaches a reader to ignore the gate.
    """
    if artifact.name.endswith(".tar.gz"):
        with tarfile.open(artifact) as archive:
            # Not `isfile()`. Directories are dropped because tar carries
            # them and `git ls-files` lists none, and that reasoning
            # covers directories -- it was written as "files only", so a
            # symbolic link, which is neither, went past unseen. A link
            # is a payload: unpacked, `passwd_leak -> /etc/passwd` is a
            # path out of the tree, and this gate reported nothing.
            members_ = archive.getmembers()
            names = [m.name for m in members_ if not m.isdir()]
            # A directory is dropped because `git ls-files` lists none,
            # and that reasoning is about a directory the archive puts
            # its own files in. It says nothing about one whose name
            # climbs out of the tree, and `ROOT/../../../tmp/pwned`
            # unpacks wherever that points. The name is the payload.
            escaping = [m.name for m in members_
                        if m.isdir() and ".." in m.name.split("/")]
            names += escaping
        # An sdist puts everything under one directory named for the
        # distribution; below that it is the repository's own layout.
        # Which directory is checked rather than assumed: dropping
        # whatever the first component happens to be let a member under
        # a second root borrow a tracked path and pass.
        root = artifact.name[:-len(".tar.gz")]
        return [(name,
                 name.split("/", 1)[-1]
                 if name.split("/", 1)[0] == root else name)
                for name in names]
    with zipfile.ZipFile(artifact) as archive:
        names = [n for n in archive.namelist() if not n.endswith("/")]
        # What the build says it relocated, read from the build.
        metadata = [n for n in names if n.endswith(".dist-info/METADATA")]
        declared = _licence_files(
            archive.read(metadata[0]).decode("utf-8", "replace")) if metadata else ()
    # One decider. Mapping used to exempt a metadata directory here as
    # well, so a file planted inside one never reached the function whose
    # job is to say whether it belongs -- and a note in a `.dist-info/`
    # went out green while the same note in an `.egg-info/` was caught.
    return [(name, _repository_path(name, declared)) for name in names]


def _repository_path(name: str, declared: tuple = ()) -> str:
    """Where a wheel member came from in the tree.

    Two relocations, not one. Package members live under the import name
    and come from `src/`. Licence files live under
    `<dist-info>/licenses/` and come from wherever the tree keeps them,
    which for the ones setuptools collects by default is the top.
    """
    if name.startswith(IMPORT_ROOT):
        return SOURCE_ROOT + name
    parts = name.split("/")
    for index, part in enumerate(parts):
        if not part.endswith(METADATA_DIRS):
            continue
        rest = parts[index + 1:]
        # setuptools >= 77 puts them under `licenses/`; before that they
        # sit directly in the metadata directory, and this project's
        # build requirement admits both. Only the declared ones are
        # relocated back in the flat case -- everything else in there is
        # the build system's and is asked about as such.
        if rest[:1] == ["licenses"]:
            inner = "/".join(rest[1:])
            # The same question the flat case asks. This branch used to
            # relocate anything under `licenses/` by name, so
            # `<dist-info>/licenses/README.md` recovered as the tree's
            # own README and passed -- and setuptools >= 77, which is
            # what builds this project, puts licence files exactly here.
            # One branch was given teeth and the other was not.
            if not declared or inner in declared:
                return inner
            for candidate in declared:
                if pathlib.PurePosixPath(candidate).name == inner:
                    return candidate
            return name
        if len(rest) == 1 and rest[0] not in METADATA_MEMBERS:
            # Where the build took it from. Before setuptools 77 the
            # licence files sit here rather than under `licenses/`, and
            # this project's build requirement admits that version, so
            # the tracked-files rule has to be asked of the tree root
            # for those -- and only for those.
            #
            # Both earlier versions of this were wrong in opposite
            # directions. Naming `LICENSE` and `NOTICE` in a list here
            # rejected `THIRD_PARTY.md` the day it was added: a correct
            # build refused. Relocating anything by name let
            # `<dist-info>/README.md` through, because the tree has a
            # README -- the gate's teeth pulled, measured against eight
            # such names.
            #
            # So: the declared list decides, and when it cannot be read
            # the fallback is the permissive one, because refusing a
            # correct build is the worse of the two failures and a
            # configuration this cannot parse is a configuration nobody
            # is hiding a payload in.
            if not declared:
                return rest[0]
            for candidate in declared:
                if pathlib.PurePosixPath(candidate).name == rest[0]:
                    return candidate
    return name


def tracked():
    """Every path the repository tracks, or None when git cannot say.

    None rather than an empty set: empty would mark every member
    untracked and fail everything, and a gate that cannot ask has to say
    so rather than answer.
    """
    try:
        result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                                capture_output=True, text=True)
    except OSError as error:                     # git is not installed
        print("distribution: git could not be run (%s)" % error, file=sys.stderr)
        return None
    if result.returncode != 0:
        print("distribution: git could not list the index (%s)"
              % (result.stderr.strip() or "not a repository"), file=sys.stderr)
        return None
    listed = {name for name in result.stdout.split("\0") if name}
    if not listed:
        # A repository that tracks nothing cannot have produced a
        # distribution honestly, so this is `git init` inside an
        # unpacked sdist rather than an answer -- and taking it as one
        # marks every member untracked and reports the whole archive.
        # The paragraph above said that would happen and guarded only
        # the two cases where git itself fails.
        print("distribution: the index is empty, so nothing here came from "
              "this repository; nothing was concluded", file=sys.stderr)
        return None
    return listed


def main() -> int:
    survive()
    if not DIST.is_dir():
        print("no dist/ -- build the distributions first", file=sys.stderr)
        return 1
    artifacts = sorted(p for p in DIST.iterdir() if ours(p.name))
    if not artifacts:
        print("no distributions in dist/ -- build them first", file=sys.stderr)
        return 1

    index = tracked()
    if index is None:
        # One of the two rules cannot run, and the summary line below is
        # read as "both passed". Refusing is the only honest answer: an
        # unpacked sdist outside a tree is exactly where this used to
        # print a green line having checked half of what it claimed.
        print("distribution: the tracked-files rule needs the repository this "
              "was built from; nothing was concluded", file=sys.stderr)
        return 1

    problems = []
    for artifact in artifacts:
        for name, inner in members(artifact):
            if name.endswith("/"):
                continue
            if inner.startswith(NOT_A_PAYLOAD) or inner == NOT_A_PAYLOAD.rstrip("/"):
                problems.append("%s carries %s -- the requirements indexes are a "
                                "repository publication, not a Python payload"
                                % (artifact.name, name))
            elif is_build_metadata(inner):
                continue
            elif inner not in index:
                problems.append("%s carries %s -- this repository does not track it"
                                % (artifact.name, name))
    for problem in problems:
        print("distribution: %s" % problem, file=sys.stderr)
    if problems:
        return 1
    print("distributions: %d checked, none carries what it must not"
          % len(artifacts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
