"""Every claim on the front of a document here is re-derivable, or it rots.

The console sample is regenerated here and compared byte-for-byte; the
rule counts are counted, not trusted. A README that says 56 while the
registry says 57 is the kind of small lie that outlives its excuse.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

from aas_submodel_validate import (
    rules,  # noqa: F401 - importing registers
    runner,
)
from aas_submodel_validate.registry import all_rules
from aas_submodel_validate.report import render
from aas_submodel_validate.rules import dbp_tables, hd_tables, td_tables
from builders import build_aasx, env_json

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text("utf-8")


def _command_blocks() -> list:
    """Every fenced block on the page that shows commands to type.

    Both spellings: `sh` for a block of bare commands, `console` for one
    that shows a prompt and its output. Reading only the first would
    have let a redesign move every command into the other fence and
    quietly blind the three gates below -- they look for repository
    paths, for spellings of the tool nobody taught them, and for a first
    verdict that needs no clone.

    A `$ ` prompt is stripped and output lines are dropped, so what each
    gate sees is the same shape either fence produces.
    """
    blocks = []
    for fence in ("sh", "console"):
        for body in re.findall("```%s\n(.*?)```" % fence, README, re.S):
            if fence == "sh":
                blocks.append(body)
                continue
            typed = [line[2:] for line in body.splitlines()
                     if line.startswith("$ ")]
            blocks.append("\n".join(typed) + "\n" if typed else "")
    return [block for block in blocks if block.strip()]
CHANGELOG = (ROOT / "CHANGELOG.md").read_text("utf-8")


def test_the_rule_counts_are_the_registrys():
    generated = len(hd_tables.ROWS) + len(td_tables.ROWS) + len(dbp_tables.ROWS)
    assert len(all_rules()) == 125
    assert (len(hd_tables.ROWS), len(td_tables.ROWS), len(dbp_tables.ROWS)) == (38, 26, 22)
    assert "125 rules" in README
    assert "%d generated" % generated in README
    # Each template's own row count is on the front page too, in the
    # table: a total alone would let one template's rows vanish into
    # another's without the number moving.
    assert "| 38 |" in README
    assert "| 26 |" in README
    assert "| 22 |" in README


def _x_rules_drawn_by(paths):
    drawn = set()
    for path in paths:
        drawn |= {f.id for f in runner.run(path).findings if f.id.startswith("X")}
    return drawn


def _bare_documents(tmp_path):
    """Documents with no container around them, of every shape this reader
    reads and several it does not.

    Broken input alone is not a measurement. A rule that answers for bare
    files might do it on a *well-formed* one, or on one that carries a
    File element, or on bytes that happen to be a ZIP -- and a corpus of
    three broken files would go on reporting the same answer while the
    front page went stale. Each of these was chosen for something a
    packaging rule might key on."""
    written = []
    for name, data in (
            ("bad.json", b"{ not json"),
            ("bad.xml", b"<nope"),
            ("valid.json", env_json("urn:x")),
            ("valid.xml", b'<?xml version="1.0"?>'
                          b'<environment xmlns="https://admin-shell.io/aas/3/0">'
                          b"<submodels /></environment>"),
            ("submodel.json", b'{"modelType": "Submodel", "id": "urn:x"}'),
            ("empty.json", b""),
            # Bytes that are an archive, under a name that is not.
            ("zip.json", b"PK\x03\x04" + b"\x00" * 60),
    ):
        path = tmp_path / name
        path.write_bytes(data)
        written.append(path)
    return written


def _packaged_documents(tmp_path):
    """The positive control. Without it, "X1 never answers for a bare
    file" cannot be told from "this measurement cannot see X1 at all"."""
    broken_zip = tmp_path / "notazip.aasx"
    broken_zip.write_bytes(b"not a zip at all")
    return [
        broken_zip,
        build_aasx(tmp_path / "nochain.aasx", root_rels=False),
        build_aasx(tmp_path / "suppl.aasx", suppl_targets=("aasx/files/absent.png",)),
    ]


def _x_rules_a_bare_document_can_draw(tmp_path, monkeypatch):
    """Measured, not read off the code."""
    from aas_submodel_validate import container

    drawn = _x_rules_drawn_by(_bare_documents(tmp_path))
    monkeypatch.setattr(container, "MAX_PART_BYTES", 512)
    over = tmp_path / "big.json"
    over.write_bytes(b" " * 600)
    return drawn | _x_rules_drawn_by([over])


def test_the_readme_names_the_rules_that_are_about_packaging(tmp_path, monkeypatch):
    """The front page said five of the X rules were about the AASX/OPC
    package, then four. Both counted X3, which answers for a bare .json
    that will not parse, and the second also stopped counting X5 on the
    commit that gave X5 bare files to answer for.

    The sentence is derived here rather than compared to a remembered
    one: whichever ids a document with no container can draw are not the
    packaging rules, and the README says so in those words."""
    every_x = sorted(rule.id for rule in all_rules() if re.fullmatch(r"X\d+", rule.id))
    bare = _x_rules_a_bare_document_can_draw(tmp_path, monkeypatch)
    packaging = [rule_id for rule_id in every_x if rule_id not in bare]
    # The control, and the reason the sentence means anything: every id
    # the README calls a packaging rule is one this measurement has seen
    # fire, from a container. "Never drawn bare" is only interesting
    # about a rule the instrument can draw at all.
    packaged = _x_rules_drawn_by(_packaged_documents(tmp_path))
    assert set(packaging) <= packaged, (
        "the front page names %s as packaging rules and this measurement "
        "never saw them fire at all" % sorted(set(packaging) - packaged))
    # Whitespace-normalised: the README wraps at seventy-two columns and a
    # sentence straddles the break wherever it happens to fall. What is
    # pinned is what it says.
    assert "%s and %s are about the AASX/OPC package" % (
        ", ".join(packaging[:-1]), packaging[-1]) in " ".join(README.split())


def test_the_generator_counts_the_rows_it_warns_about():
    """The generator's docstring warns that a hand-copied row count goes
    stale, and was one: it said sixty-four from when two tables existed and
    went on saying it through a third. The warning is worth keeping and the
    number belongs where the others are."""
    generated = len(hd_tables.ROWS) + len(td_tables.ROWS) + len(dbp_tables.ROWS)
    source = (ROOT / "tools" / "extract_smt_rules.py").read_text("utf-8")
    assert "hand-copying %d rows" % generated in source


def test_the_console_sample_is_what_the_tool_prints(tmp_path, monkeypatch):
    (tmp_path / "machine-docs.json").write_bytes(env_json("urn:somecompany:docs"))
    monkeypatch.chdir(tmp_path)
    sample = render(runner.run("machine-docs.json"))
    assert "```text\n%s\n```" % sample in README, \
        "the README's console sample went stale; regenerate it"


def test_the_newest_changelog_entry_is_a_draft_or_a_dated_release():
    """Exactly two shapes, and the release workflow accepts the same two.

    They used to disagree, and the disagreement was a deadlock nobody
    could see from either side: the workflow refused an undated heading,
    this test refused a dated one, and `make check` runs inside the
    workflow. There was no state of this file in which a release could
    be built. Measured, by dating the heading and watching the release
    job's own `make check` step go red.

    So the shape is asserted here in the same two forms the workflow
    matches, and the number check below applies to a draft only -- once
    a version is dated its entry is history and must not be edited."""
    _, _, entries = CHANGELOG.partition("\n## ")     # past the file's title
    unreleased, _, _ = entries.partition("\n## ")     # the newest entry alone
    heading = unreleased.splitlines()[0]
    draft = "unreleased" in heading.lower()
    dated = re.match(r"^\d+\.\d+\.\d+ — \d{4}-\d\d-\d\d$", heading)
    assert draft or dated, (
        "the newest entry reads %r; the release workflow accepts a draft "
        "(`— unreleased`) or a dated release (`— YYYY-MM-DD`) and nothing "
        "else, and this file is the other half of that gate" % heading)
    if not draft:
        return                                        # history, not a draft
    generated = len(hd_tables.ROWS) + len(td_tables.ROWS) + len(dbp_tables.ROWS)
    assert "%d rules" % len(all_rules()) in unreleased
    assert "%d are" % generated in unreleased or "%d generated" % generated in unreleased
    # The bounds are on this page too, and were the only prose numbers on
    # it with nothing watching them: SECURITY.md derives its copy and this
    # one would have gone quietly stale beside it.
    from aas_submodel_validate import container
    assert ("one document at %d MiB, a container's parts at %d MiB each and %d MiB"
            % (container.MAX_PART_BYTES // 1024 ** 2,
               container.MAX_PART_BYTES // 1024 ** 2,
               container.MAX_TOTAL_PART_BYTES // 1024 ** 2)) in " ".join(unreleased.split())


def test_every_file_the_readme_tells_a_stranger_to_run_exists():
    """The third line of the quickstart named a file that exists nowhere
    in this repository, and it is the first thing a reader types.

    Nothing was watching, because the console sample beside it is
    generated from a fixture rather than from the command the README
    prints. So: every path-shaped argument in a fenced `sh` block is
    resolved against the tree, unless it is plainly a stand-in for the
    reader's own file."""
    blocks = _command_blocks()
    assert blocks, "the README has no shell examples any more"
    # What an earlier line in the same block writes into the reader's
    # directory: a fetched example, a built archive. Those are not in
    # the tree and are not supposed to be.
    written = {Path(word).name
               for line in "\n".join(blocks).splitlines()
               if line.split()[:1] == ["curl"]
               for word in line.split() if word.startswith("http")}
    checked = 0
    for line in "\n".join(blocks).splitlines():
        for word in line.split():
            if word.startswith("your-") or "/" not in word and "." not in word:
                continue
            if word.startswith(("http", "-", "&&", "#")) or word.endswith(":"):
                continue
            if "." not in Path(word).name:
                continue                       # a directory, not a file argument
            if word.startswith("dist/") or Path(word).name in written:
                continue                       # written by a line above it
            checked += 1
            assert (ROOT / word).exists(), \
                "the README tells a reader to run %r and it is not here" % word
    assert checked, "no runnable path was checked; the pattern stopped matching"


def test_the_first_verdict_needs_nothing_but_the_install():
    """The reader gets a verdict from the install alone.

    Two earlier answers were worse. The wheel carried no example and the
    quickstart named a path only a clone has, so `pip install` followed
    by the next line printed "no such file" -- measured against the
    description the package index serves, not against this tree. Fetching one fixed that reader and not the one this
    project is for, whose machine has no route to github.com; the file
    arrived over the network the whole pitch says is unnecessary.

    So it ships, and the block asks for it by name rather than by path.
    Pinned here the same way the templates are: a recorded hash beside
    it, and an entry in the attribution file, because it is IDTA's
    document and not this project's."""
    blocks = _command_blocks()
    published = [b for b in blocks if "install aas-submodel-validate" in b]
    assert published, "the README no longer shows how to use the published package"
    assert any("--example" in b for b in published), (
        "the published-package block gives the reader no verdict without a "
        "file of their own")

    example = ROOT / "src/aas_submodel_validate/data/example/idta-02004-2.0.aasx"
    assert example.is_file(), "the example the block promises does not ship"
    recorded = (example.parent / "sha256sums.txt").read_text(encoding="utf-8")
    assert hashlib.sha256(example.read_bytes()).hexdigest() in recorded, \
        "the bundled example does not match its recorded hash"
    attribution = (ROOT / "THIRD_PARTY.md").read_text(encoding="utf-8")
    assert example.name in attribution, \
        "a CC BY 4.0 file ships without an attribution entry"

    # A raw URL may still appear for something else; a branch moves and a
    # tag does not.
    for ref, path in re.findall(
            r"https://github\.com/[\w-]+/[\w-]+/raw/([^/\s]+)/(\S+)", README):
        assert re.match(r"^v\d+\.\d+\.\d+$", ref), \
            "%r is fetched from %r, which moves" % (path, ref)
        assert (ROOT / path).exists(), \
            "the README fetches %r and this tree does not have it" % path


#: Every way this page tells a reader to invoke the tool. Two of them
#: were listed while a third was taught in prose -- `python3 -m
#: aas_submodel_validate`, offered for when the console script is not on
#: the PATH -- so a repository path written that way walked past the
#: gate whose whole job is to catch a repository path. Named here, and
#: pinned below against what the page actually teaches, because a list
#: of spellings goes stale the moment a new one is offered.
INVOCATIONS = (("smtv",), ("aas-submodel-validate",),
               ("python3", "-m", "aas_submodel_validate"),
               ("python", "-m", "aas_submodel_validate"),
               ("python3", "dist/smtv.pyz"), ("python", "dist/smtv.pyz"),
               ("python3", "smtv.pyz"), ("python", "smtv.pyz"))


def _arguments_to_the_tool(words):
    """What a command line hands the tool, or None if it is not one."""
    for invocation in INVOCATIONS:
        if tuple(words[:len(invocation)]) == invocation:
            return words[len(invocation):]
    return None


#: Commands in a shell block that are not this tool: installing it,
#: fetching something, moving around. Anything on the page that is
#: neither one of these nor an invocation is a spelling nobody taught
#: the gate, and the gate has to say so rather than skip the line.
NOT_THE_TOOL = ("pip", "pip3", "python3 -m pip", "python -m pip",
                "python3 -m venv", "python -m venv",
                "python3 tools/", "python tools/",
                "curl", "git", "cd", "export", "shasum", "gh", "make")


def test_the_gate_knows_every_way_this_page_starts_the_tool():
    """A spelling the page teaches and the gate does not know is a hole
    in the gate, and the page teaches new ones.

    The first version of this compared the page's invocations against
    the gate's list and then asserted that each one it had found in the
    list was in the list. It could not fail. Planted `uvx
    aas-submodel-validate tests/corpus/...` in the published-package
    block -- a repository path, in the block whose whole purpose is to
    have none -- and every test in this file stayed green.

    So it reads the other way now: every command in every shell block
    has to be one of two known kinds, and a first word that is neither
    fails here rather than being skipped by the gate that matters."""
    unknown = []
    for block in _command_blocks():
        for line in block.splitlines():
            words = line.split("#", 1)[0].split()
            if not words:
                continue
            if _arguments_to_the_tool(words) is not None:
                continue
            command = " ".join(words)
            if any(command == other or command.startswith(other + " ")
                   or (other.endswith("/") and command.startswith(other))
                   for other in NOT_THE_TOOL):
                continue
            unknown.append(line.strip())
    assert not unknown, (
        "these lines start with something this file does not recognise, so "
        "the gates that read shell blocks skip them silently: %s" % unknown)


def test_the_published_package_path_stands_without_the_repository():
    """This file is two documents. It is the front page of a repository,
    and it is the description PyPI renders for the package -- and on
    PyPI the repository does not exist.

    So the block a reader follows after `pip install aas-submodel-validate`
    may not name a file that only a clone has. Every input it hands the
    tool must be one an earlier line in the same block fetched, or a
    plainly-named stand-in for the reader's own.

    Measured on the released 0.1.0: the description PyPI showed opened
    with `git clone`, because the fix landed after the tag and a project
    description is frozen at the release that carried it. That is the
    trap this exists for -- a README correction is invisible on PyPI
    until the next release, so the path has to be right *before* the tag,
    not after."""
    blocks = _command_blocks()
    # `pip` or `pip3` or `python3 -m pip`; the block is identified by
    # what it installs, not by the spelling of the installer -- which is
    # itself one of the things the block now has to warn about.
    published = [b for b in blocks if "install aas-submodel-validate" in b]
    assert published, "the README no longer shows how to use the published package"
    for block in published:
        fetched, offences = set(), []
        for line in block.splitlines():
            # A trailing `# comment` is prose, not arguments. Without
            # this the words of "# IDTA's own published example" were
            # each read as a file the tool was handed.
            words = line.split("#", 1)[0].split()
            if words[:1] == ["curl"]:
                fetched |= {Path(w).name for w in words if w.startswith("http")}
                continue
            arguments = _arguments_to_the_tool(words)
            if arguments is None:
                continue
            for word in arguments:
                if word.startswith("-") or word.startswith("your-"):
                    continue
                # Exactly, not by basename: `curl -O` writes the file
                # into the current directory under that bare name, so
                # `tests/corpus/.../example.aasx` is a different thing
                # from `example.aasx` and only the second one is there.
                # Matching basenames let the repo path through.
                if word in fetched:
                    continue
                offences.append(word)
        assert not offences, (
            "the published-package path hands the tool %s, which only a "
            "clone of this repository has; on PyPI this block is the whole "
            "page and there is no clone" % offences)


def test_every_link_on_the_front_page_resolves_off_the_repository():
    """The same two-documents problem, in the links this time.

    A relative link works on the repository's front page and is dead on
    the package index, which renders this file as the project
    description and rewrites nothing. Five of them shipped in 0.1.0 --
    the scope document, the divergences, the report schema, support and
    contributing -- so a reader arriving from `pip install` could reach
    none of what the page pointed them at.

    In-page anchors are fine: they resolve wherever the page is."""
    links = re.findall(r"\]\(([^)]+)\)", README)
    assert links, "the front page has no links at all"
    dead = [target for target in links
            if not target.startswith(("http://", "https://", "#"))]
    assert not dead, (
        "these link targets are relative, and this file is also the "
        "package description, where there is no repository to resolve "
        "them against: %s" % dead)


def test_every_label_the_text_report_prints_is_explained():
    """The person at a terminal has one document, and it is this page.

    `docs/report-schema.md` says in its first sentence that it describes
    the JSON, so a label that appears only in the text output is
    explained nowhere at all -- which is where `per` and the fold line
    both landed the day they were added. Derived from the renderer, not
    listed, because a hand-kept list is how the next label goes
    undocumented."""
    source = (ROOT / "src" / "aas_submodel_validate" / "report.py").read_text("utf-8")
    labels = set(re.findall(r'"        (\w+)[: ]', source))
    assert labels, "the renderer prints no labelled lines any more"
    for label in sorted(labels):
        assert "| `%s` |" % label in README, \
            "the text report prints a %r line and this page never says what it is" % label


def test_every_picture_on_the_page_is_the_one_committed():
    """A picture is served through GitHub's image proxy, which caches by
    URL. Change the file and leave the URL alone and every reader keeps
    the picture that was cached -- so the page goes on showing a verdict
    the tool stopped printing, and nothing anywhere goes red.

    That is not hypothetical: the terminal shot was regenerated when the
    battery finding learned to cite the row's own clause, and the page
    went on pointing at the version that cited the wrong annex. Three
    tests already ask whether the committed picture is true; none of
    them asked whether the page points at the committed picture.

    So the query string is the file's hash, and this asserts it. The
    branch in the URL moves, deliberately -- the pictures are checked
    against a live run on every push, so what `main` holds is true of
    `main` -- and the hash is what makes a changed picture reach a
    reader who has already seen the old one."""
    # Every picture, found by the tag rather than by the host, because
    # the two gates on this page that could have caught a picture served
    # from somewhere else both read something a picture is not written
    # in: this one read the proxy host, and the relative-link gate reads
    # markdown `](...)`. An `<img src="docs/assets/verdict.svg">` -- dead
    # on the package index, which is the entire reason that gate exists
    # -- passed both.
    project = (ROOT / "pyproject.toml").read_text("utf-8")
    home = re.search(r'(?m)^Homepage = "https://github\.com/([^/"]+)/([^/"]+)"',
                     project)
    assert home, "pyproject.toml names no GitHub Homepage to check against"
    ours = "raw.githubusercontent.com/%s/%s/" % home.groups()

    sources = re.findall(r'<img\s[^>]*?src="([^"]+)"', README)
    assert sources, "the front page shows no pictures at all"
    references = []
    for source in sources:
        assert source.startswith("https://" + ours), (
            "%s is not served from this repository's raw host (%s). A "
            "relative path is dead on the package index; another "
            "owner's host is not this project's picture." % (source, ours))
        rest = source.split(ours, 1)[1]
        branch, _, tail = rest.partition("/")
        path, _, query = tail.partition("?")
        references.append(
            (branch, path, query[2:] if query.startswith("v=") else ""))
    for branch, path, cachebuster in references:
        picture = ROOT / path
        assert picture.is_file(), (
            "the page points at %s, which this repository does not have"
            % path)
        digest = hashlib.sha256(picture.read_bytes()).hexdigest()[:8]
        assert cachebuster, (
            "%s is referenced off %s with no ?v= -- change the file and "
            "every reader who has seen it keeps the old one" % (path, branch))
        assert cachebuster == digest, (
            "%s has changed since the page was written: the URL says ?v=%s "
            "and the committed file hashes to %s. Readers behind the image "
            "proxy would keep the old picture." % (path, cachebuster, digest))


def test_the_anatomy_block_is_what_the_tool_prints(tmp_path, monkeypatch):
    """The finding this whole page is built around, quoted.

    The picture of this verdict is checked against a live run on every
    build and the block beneath it was checked against nothing, so when
    the rule learned to cite its own row's clause the picture followed
    and the text did not: for one commit the front page showed an `at`
    line naming a path the walk never takes, a `saw` line saying the
    provision "requires" what an industry reading requires, and a `per`
    line citing the one annex nothing in the finding chose.

    Same discipline as the picture, then. Every line quoted here has to
    be a line the tool prints, with the flags the block itself types.
    The block is an excerpt -- the run goes on to the notes and the
    summary -- and the elision is marked, because a reader who cannot
    see where output was cut cannot tell a short verdict from a
    shortened one."""
    from test_battery_rules import _env, _technical_data

    block = [body for body in re.findall("```console\n(.*?)```", README, re.S)
             if "BAT-R8" in body]
    assert len(block) == 1, "expected exactly one BAT-R8 block on the page"
    lines = block[0].splitlines()
    typed = [line[2:] for line in lines if line.startswith("$ ")]
    assert typed, "the block quotes output with no command above it"
    flags = [word for command in typed for word in command.split()
             if word.startswith("--")]

    (tmp_path / "your-battery-passport.json").write_text(
        json.dumps(_env(_technical_data(fade=False))), "utf-8")
    monkeypatch.chdir(tmp_path)
    printed = {" ".join(row.split()) for row in render(runner.run(
        "your-battery-passport.json",
        allow_unmatched="--allow-unmatched" in flags,
        strict_meta=("info" if "--meta" in flags else False))).splitlines()}

    # Whole lines, not substrings of the joined output. Compared against
    # one run-shaped string, a quote could stop early -- dropping the
    # part of a clause that says which annex, or the part of a remedy
    # that says what not to do -- and pass, and a quote could run across
    # a line boundary and stitch two true lines into a sentence the tool
    # never printed. The elision mark says a line is missing; nothing
    # said a line was shortened.
    quoted = [line for line in lines
              if line and not line.startswith("$ ") and line.strip() != "…"]
    assert quoted, "the block types a command and quotes no output"
    for line in quoted:
        assert " ".join(line.split()) in printed, (
            "the page quotes %r and the tool prints no such line. A "
            "quote that stops early is a quote that says something "
            "else." % line)
    assert any(line.strip() == "…" for line in lines), (
        "this block is an excerpt -- the run continues past it -- and "
        "nothing on the page says so")


#: Flags on this page that are somebody else's, and whose. Anything not
#: here has to be one of ours, and anything here has to still be on the
#: page and still not be ours -- so the exemption cannot outlive its
#: sentence or quietly cover a real flag.
NOT_OURS = {
    "--from": "uvx, in the no-install tip",
    "--no-index": "pip, in the offline install route",
    "--find-links": "pip, in the offline install route",
    "--fix": "named in order to say this tool does not have it",
    "-m": "python, in `python3 -m pip` and `python3 -m aas_submodel_validate`",
}


def test_every_flag_this_page_names_is_a_flag_the_tool_has():
    """A flag in a sentence is as copyable as a flag in a code block.

    The gate above this one reads the commands the page types, so a
    made-up option inside a fenced block fails. Prose was unguarded, and
    a sentence explaining that a regulatory finding does not fail a
    build offered `--fail-on warning` to make it do so -- a flag this
    tool has never had. The reader who tries it gets `unrecognized
    arguments` and no idea which half of the sentence to believe.

    Read out of the source rather than out of `--help`, because the
    parser is built inside `main` and because `--help` is answered by
    whichever copy of the package was imported."""
    source = (ROOT / "src" / "aas_submodel_validate" / "cli.py").read_text("utf-8")
    real = {"--help"}
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"):
            real.update(argument.value for argument in node.args
                        if isinstance(argument, ast.Constant)
                        and isinstance(argument.value, str)
                        and argument.value.startswith("-"))
    assert len(real) > 5, "no options were read out of cli.py at all"
    # Short spellings too. The sentence that made this gate necessary
    # offered a flag the tool does not have, and the repair moved it to
    # `-W` -- into the half of the option space the first version of
    # this gate could not see. The page teaches `-W`, `-f` and `-q`, and
    # nothing was watching any of them.
    named = set(re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]+)", README))
    named |= set(re.findall(r"(?<![\w-])(-[A-Za-z])(?![\w-])", README))
    borrowed = sorted(set(NOT_OURS) & real)
    assert not borrowed, (
        "%s is listed as another command's flag and this tool has it"
        % borrowed)
    stale = sorted(flag for flag in NOT_OURS if flag not in named)
    assert not stale, (
        "%s is excused here and no longer appears on the page" % stale)
    unknown = sorted(named - real - set(NOT_OURS))
    assert not unknown, (
        "this page names options the tool does not have: %s. It has: %s. "
        "If one of them belongs to another command the page tells a "
        "reader to run, say so in NOT_OURS." % (unknown, sorted(real)))
