"""0.3.0 announced, one release ahead, that a usage error would leave by 64.
This is that release, and this file is the promise.

The distinction being bought is narrow and worth stating: today argparse
and a refused input leave by the same code, so a pipeline branching on 2
cannot tell "your file could not be judged" from "you spelled the flag
wrong". After this, 2 means only the first.
"""
import ast
import json
import pathlib
import re
import sys

import pytest

from aas_submodel_validate.cli import EXIT_ERROR, EXIT_USAGE, main

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Ten shapes of "you called this wrong". Five come from argparse itself
#: and five from checks this file's own `main` makes -- measured by
#: recording the calling frame of `error` for each, not counted by eye,
#: which is how an earlier version of this comment said three and six and
#: added up to nine. Not every shape there is: the `--rules` check names
#: eight flags it would have to ignore and one of them is exercised here.
#: They were all 2 before, which is what made 2 unreadable.
WRONG_CALLS = (
    (["--nonesuch"], "an option that does not exist"),
    (["--format"], "an option whose argument is missing"),
    (["--format", "bogus", "x.json"], "a value outside the choices"),
    (["--profile", "02099-1", "x.json"], "a template number not on offer"),
    (["x.json", "second.json"], "a second path the parser cannot place"),
    ([], "no path and no --example and no --rules"),
    (["--example", "x.json"], "the bundled example and a path of your own"),
    (["--example", "--rules"], "two different requests at once"),
    (["--rules", "-q"], "a flag --rules would have to ignore"),
    (["--strict-meta", "--meta", "info", "x.json"], "two contradictory dials"),
)


@pytest.mark.parametrize("argv,shape", WRONG_CALLS,
                         ids=[" ".join(a) or "(nothing)" for a, _s in WRONG_CALLS])
def test_a_wrong_call_exits_64(argv, shape, capsys):
    with pytest.raises(SystemExit) as raised:
        main(argv)
    printed = capsys.readouterr()
    assert raised.value.code == EXIT_USAGE, (
        "%s left by %r; 0.3.0 announced 64 for this" % (shape, raised.value.code))
    # Discarding this was a hole: an `error` that did everything right on
    # stderr and also printed a JSON document on stdout passed the whole
    # suite, while `docs/report-schema.md` says a usage error writes no
    # report. A caller parsing stdout would then read a document about a
    # flag it mistyped. Measured.
    assert printed.out == "", (
        "%s wrote to stdout; a usage error parsed nothing and has no report "
        "to give: %r" % (shape, printed.out[:200]))
    assert printed.err, "%s left without saying what was wrong" % shape


#: Paths that are a path -- given, and not a mistake in the call. `""` is
#: what a shell produces from `smtv "$FILE"` with `FILE` unset, and it was
#: exit 2 at v0.3.0.
GIVEN_BUT_UNREADABLE = ("", " ")


@pytest.mark.parametrize("path", GIVEN_BUT_UNREADABLE,
                         ids=["empty string", "one space"])
def test_a_path_that_is_empty_is_still_a_path(path, capsys):
    """`smtv ""` is a path this reader cannot read, not a wrong call.

    Measured at v0.3.0: `smtv ""` exited 2, because the empty string is
    falsy and fell into the "a path is required" branch, which was 2 like
    everything else. Moving usage errors to 64 moved this with them -- so
    a shell expanding an unset variable would have started telling
    pipelines they had called the tool wrong.

    `" "` never took that branch and has always been 2, which is the
    answer both should give: something was given, and nothing behind it
    could be read.
    """
    assert main([path, "-q"]) == EXIT_ERROR, (
        "a path of %r left by something other than 2" % path)
    assert "smtv: " in capsys.readouterr().err


@pytest.mark.parametrize("argv,shape", (
    (["--rules", ""], "--rules with a path"),
    (["--example", ""], "--example with a path of your own"),
), ids=["--rules", "--example"])
def test_an_empty_path_is_not_dropped_in_silence(argv, shape, capsys):
    """The same falsiness, in the two checks that refuse a second request.

    Both read `args.path` for truth, so an empty string was not a path to
    them: `--rules ""` printed the listing and `--example ""` judged the
    bundled example, each dropping what the caller typed. The comment
    above the `--rules` check calls answering a different question in
    silence "the thing this tool refuses everywhere else", and this is
    that, reached through a shell rather than through a flag.
    """
    with pytest.raises(SystemExit) as raised:
        main(argv)
    capsys.readouterr()
    assert raised.value.code == EXIT_USAGE, \
        "%s answered a different question and left by 0" % shape


def test_a_version_or_help_request_still_wins_over_a_wrong_call(capsys):
    """Measured, and **not** what this release changes.

    `--version` and `--help` are argparse actions that fire while the
    argv is still being read, so anything after them is never parsed and
    anything before them that was wrong is never reported:

        smtv --nonesuch --version   ->  0, prints the version
        smtv --format bogus --version -> 64, the value is checked first

    The code a caller gets therefore depends on where they put the flag.
    That is argparse's behaviour on every tool built with it and it is
    older than this release; it is pinned here so that the public
    sentences about 64 can say so honestly rather than claiming an
    absolute they do not have. Making `--version` and `--help` join the
    two-requests check is a change of its own, with its own reasons.
    """
    for argv in (["--nonesuch", "--version"], ["--rules", "--version"]):
        with pytest.raises(SystemExit) as raised:
            main(argv)
        capsys.readouterr()
        assert raised.value.code in (0, None), (
            "%s no longer leaves by 0; if that was deliberate, the "
            "paragraphs naming 64 have to lose their caveat" % argv)

    # And where the wrong value is read before the action, 64 wins.
    with pytest.raises(SystemExit) as raised:
        main(["--format", "bogus", "--version"])
    capsys.readouterr()
    assert raised.value.code == EXIT_USAGE


def test_a_wrong_call_still_says_what_was_wrong(capsys):
    """The code changes and the sentence does not.

    Rewriting argparse's message here rather than letting argparse print
    it would drift from argparse the moment either side changed, and
    would be silently untranslated where argparse is not."""
    with pytest.raises(SystemExit):
        main(["--nonesuch"])
    err = capsys.readouterr().err
    assert "usage:" in err and "--nonesuch" in err, err


def test_could_not_run_still_exits_2(tmp_path, capsys):
    """The other half of the promise, and the half that is easy to lose.

    Moving usage errors off 2 is only worth something if 2 keeps meaning
    what it meant, and the two nearest shapes are the ones that read most
    like a mistake in the call: a file named `.txt`, and a bare `-`. Both
    are "could not run" here, because a path was given and this reader
    could not read it -- and calling either 64 would tell a pipeline to
    stop looking at the file.

    An earlier version of this test asked only for a missing file and a
    refused one, and a mutation that sent `UnreadablePath` to 64 survived
    it: `runner.run` catches that exception and turns it into a report,
    so the `except` clause in `cli` was never entered and the code came
    from the `judged` branch below it. Measured with `trace`: of the five
    shapes here, none reaches that clause.
    """
    refused = tmp_path / "refused.json"
    refused.write_bytes(b"not json at all")
    wrong_suffix = tmp_path / "notes.txt"
    wrong_suffix.write_text("{}", encoding="utf-8")
    directory = tmp_path / "a-directory"
    directory.mkdir()

    for path, shape in (
            (tmp_path / "no-such-file.json", "a path with nothing behind it"),
            (refused, "a file opened and then refused"),
            (wrong_suffix, "a suffix this reader chooses no format for"),
            (directory, "a directory where a file was wanted"),
            ("-", "a bare - this reader will not read as standard input")):
        # Returned, not raised: none of these is a wrong call, so none of
        # them goes through the parser's error path.
        assert main([str(path), "-q"]) == EXIT_ERROR, \
            "%s stopped meaning 2" % shape
        assert capsys.readouterr().err.startswith("smtv: "), \
            "%s left without saying why" % shape


def test_the_two_codes_are_not_the_same_number():
    """Pinned as its own sentence because every assertion above would
    still pass if somebody set both constants to the same value."""
    assert EXIT_USAGE != EXIT_ERROR
    assert EXIT_USAGE == 64


def test_64_is_written_here_and_not_read_from_os():
    """`os.EX_USAGE` is 64 and does not exist on Windows.

    Reading it would raise `AttributeError` on one of the platforms this
    project tests on, and the failure would be an import-time crash in
    the CLI rather than a wrong exit code -- which is worse than the bug
    it would be trying to avoid."""
    source = (ROOT / "src" / "aas_submodel_validate" / "cli.py").read_text("utf-8")
    # Asked of the syntax tree, not of the letters. `EX_USAGE` is what
    # the number is called and belongs in prose -- the docstring, the
    # help page and the comment on the constant all say it. Two earlier
    # spellings of this test forbade the string and then the dotted
    # string, and both failed against a file whose only mention was the
    # explanation, which would have taught the next reader to delete the
    # explanation rather than keep the portability.
    tree = ast.parse(source)
    reads = [node for node in ast.walk(tree)
             if isinstance(node, ast.Attribute) and node.attr == "EX_USAGE"]
    assert not reads, (
        "cli.py reads EX_USAGE as an attribute at line %s; that name is "
        "absent from `os` on Windows, where this project tests"
        % [node.lineno for node in reads])

    # And the number really is a literal here, not imported from
    # somewhere that could be the same `os` one indirection away.
    written = [node for node in ast.walk(tree)
               if isinstance(node, ast.Assign)
               and any(getattr(target, "id", None) == "EXIT_USAGE"
                       for target in node.targets)]
    assert len(written) == 1, "EXIT_USAGE is assigned %d times" % len(written)
    value = written[0].value
    assert isinstance(value, ast.Constant) and value.value == 64, \
        "EXIT_USAGE is not the literal 64"


def test_help_and_version_still_leave_by_zero(capsys):
    """Neither is a mistake, and argparse routes both through the same
    `exit` that a usage error passes through."""
    for argv in (["--help"], ["--version"]):
        with pytest.raises(SystemExit) as raised:
            main(argv)
        capsys.readouterr()
        assert raised.value.code in (0, None), argv


#: Where a reader meets this contract: the documents, and the package they
#: install. Not `tests/` or `tools/`, which no caller reads -- but every
#: `.md` in the tree, because the hole this closes was a promise moved to
#: a page the gate did not happen to name.
READER_FACING_SUFFIXES = (".md",)
SKIPPED_DIRECTORIES = frozenset((
    ".git", "__pycache__", "dist", "build", ".ruff_cache", ".pytest_cache",
    ".venv", "offline", "data", "node_modules", ".claude"))
#: Words that say a code is a mistake in the call rather than in the file.
CALLED_WRONG = ("usage", "called", "mistake")


def _reader_facing():
    """Every document in the tree, plus the package a caller installs."""
    found = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or set(path.parts) & SKIPPED_DIRECTORIES:
            continue
        if path.suffix in READER_FACING_SUFFIXES:
            found.append(path)
    found += sorted((ROOT / "src").rglob("*.py"))
    # Asserted rather than assumed: a walk that collects nothing satisfies
    # every loop below it while asking nothing at all, which is the shape
    # this suite has fallen for elsewhere.
    assert len(found) >= 10, "the walk found %d files; it is broken" % len(found)
    return found


def _paragraph_containing(path, sentence):
    """The one paragraph, cut at the blank lines around it.

    A fixed-width window was the first spelling and it read whatever
    followed: deleting this paragraph's explanation of 64 pulled the code
    sample below it into the window, whose comment says "64 called
    wrong", and the assertion looking for a word like "called" was
    satisfied by the thing that had replaced the sentence it was
    checking. Measured.
    """
    lines = path.read_text("utf-8").splitlines()
    first = next(n for n, line in enumerate(lines) if sentence in line)
    last = first
    while last + 1 < len(lines) and lines[last + 1].strip():
        last += 1
    while first > 0 and lines[first - 1].strip():
        first -= 1
    return "\n".join(lines[first:last + 1])


def _normalised(text):
    """One line, single-spaced.

    Line-by-line matching was the first spelling and a reflow defeated it:
    the 0.3.0 promise put back into the README with its line breaks in
    different places passed the whole suite, because neither "next minor
    release" nor "will exit 64" survived intact on any one line. Markdown
    renders the two identically, so the reader would have met the old
    promise on the front page of the release that answered it.
    """
    return " ".join(text.split())


def _epilog_codes(help_text):
    """The `--help` exit-code table as {code: what it says it means}."""
    tail = help_text.split("exit codes:")[-1]
    rows, current = {}, None
    for line in tail.splitlines():
        begins = re.match(r"^\s*(\d+)\s\s+(.*)$", line)
        if begins:
            current = begins.group(1)
            rows[current] = begins.group(2)
        elif current and line.strip():
            rows[current] += " " + line.strip()
        elif current:
            break
    return rows


def test_the_help_page_pairs_each_code_with_its_meaning(capsys):
    """Somebody wiring this into a build reads `--help`, not a CHANGELOG.

    Asked as a pairing, not as a presence. The first spelling asked only
    that "64", "exit codes" and a usage word each appeared somewhere in
    the same tail -- so swapping the 2 and 64 blocks outright, leaving
    the page stating the exact opposite of what the tool does, passed
    every test in the suite. Measured.
    """
    with pytest.raises(SystemExit):
        main(["--help"])
    rows = _epilog_codes(capsys.readouterr().out)
    assert set(rows) == {"0", "1", "2", str(EXIT_USAGE)}, sorted(rows)

    could_not_run = rows["2"].lower()
    assert "could not run" in could_not_run
    assert not any(word in could_not_run for word in CALLED_WRONG), \
        "the page calls 2 a mistake in the call: %r" % rows["2"]

    wrong_call = rows[str(EXIT_USAGE)].lower()
    assert any(word in wrong_call for word in CALLED_WRONG), \
        "the page names %d without saying it is a wrong call" % EXIT_USAGE
    assert "could not run" not in wrong_call, \
        "the page gives %d the meaning 2 has: %r" % (EXIT_USAGE,
                                                     rows[str(EXIT_USAGE)])


#: The release that owed this and paid it. Written down rather than read
#: as "the newest entry": 0.3.0 promised 64 for the next minor release and
#: 0.4.0 is that release, so the paragraph belongs there forever. Asked of
#: the newest entry instead, this gate started failing the moment a 0.4.1
#: draft was opened for something else -- a gate that goes red for an
#: unrelated entry teaches the next person to delete the gate.
PAID_IN = "0.4.0"
#: The entry that made the promise, and the only one allowed to keep its
#: future tense: it is a record of what 0.3.0 said, not a claim about now.
PROMISED_IN = "0.3.0"


def _entries():
    """Each CHANGELOG entry as {version: its text}."""
    _, _, rest = (ROOT / "CHANGELOG.md").read_text("utf-8").partition("\n## ")
    found = {}
    for chunk in rest.split("\n## "):
        found[chunk.split(" ", 1)[0].split("\n", 1)[0]] = chunk
    assert PAID_IN in found and PROMISED_IN in found, sorted(found)
    return found


#: Present tense, and the number this release actually uses.
DELIVERED = re.compile(r"\bexits? %d\b" % EXIT_USAGE)
#: Ways of saying it has not happened. A paragraph carrying one of these
#: is not an announcement that the promise was kept.
DEFERRING = re.compile(
    r"\b(deferred|postponed|still not|not yet|will exit|next minor release)\b",
    re.IGNORECASE)


def test_the_release_that_owes_64_says_it_paid():
    """A promise made in a CHANGELOG is discharged in a CHANGELOG.

    Asked for direction, not for vocabulary. The first spelling checked
    that some line in the newest entry carried the number, the word
    "usage" and the word "exit" -- and a paragraph reading "Exit 64 is
    still not here ... a wrong flag still exits 2, not 64 (EX_USAGE)"
    satisfies every one of those while telling the reader the opposite of
    what shipped. Measured: that paragraph passed this file.
    """
    entry = _normalised(_entries()[PAID_IN])
    # Sentence by sentence, and only the ones about this number. Asked of
    # the whole entry, the deferral words matched "IDTA 02007 ... is still
    # not vendored", which is a true sentence about something else -- a
    # gate that goes red for an unrelated paragraph teaches the next
    # person to delete the gate.
    about_64 = [sentence for sentence in re.split(r"(?<=\.) ", entry)
                if re.search(r"\b%d\b" % EXIT_USAGE, sentence)
                and "MiB" not in sentence]
    assert about_64, (
        "the %s entry says nothing about %d; every entry here carries "
        "`64 MiB` twice, so the bare number proves nothing"
        % (PAID_IN, EXIT_USAGE))
    assert any(DELIVERED.search(sentence) for sentence in about_64), (
        "the entry names %d but never says the tool exits by it: %r"
        % (EXIT_USAGE, about_64))
    deferring = [sentence for sentence in about_64 if DEFERRING.search(sentence)]
    assert not deferring, (
        "the entry says the change has not happened: %r" % deferring)
    assert "EX_USAGE" in entry, "the entry does not name the code it uses"


def test_nothing_public_still_says_64_is_coming():
    """The gate that makes this kind of silence impossible to repeat.

    Four public places carried the announcement in the future tense. A
    release that ships the behaviour and leaves them saying "will" is
    telling its readers the opposite of what the tool does, and no test
    of the code could see it -- the behaviour would be right and every
    sentence about it wrong.

    Asked of every document in the tree rather than of three names. The
    first spelling listed `README.md`, `docs/report-schema.md` and
    `cli.py`; deleting the paragraph from the first and appending the old
    promise to `docs/scope.md` passed the whole suite. Measured.

    The 0.3.0 entry keeps its future tense -- it is a record of what
    0.3.0 said, not a statement about today -- so the CHANGELOG is asked
    only about its newest entry.
    """
    promising = re.compile(
        r"(next minor release|will exit 64|64 [^.]{0,40}instead of 2)",
        re.IGNORECASE)
    for path in _reader_facing():
        if path.name == "CHANGELOG.md":
            # Every entry but the one that made the promise. Restricting
            # this to the newest entry would let a stale promise sit in
            # any entry written after 0.3.0 and before today.
            for version, entry in _entries().items():
                if version == PROMISED_IN:
                    continue
                found = promising.search(_normalised(entry))
                assert not found, (
                    "the %s entry still promises %d for a later release: %r"
                    % (version, EXIT_USAGE, found.group(0)))
            continue
        found = promising.search(_normalised(path.read_text("utf-8")))
        assert not found, "%s still promises %d for a later release: %r" % (
            path.relative_to(ROOT), EXIT_USAGE, found.group(0))

    # And the announcement is still on the record where it was made, so
    # this test cannot be satisfied by deleting the history instead.
    assert "will exit 64" in _entries()[PROMISED_IN], \
        "%s's announcement was edited away rather than answered" % PROMISED_IN


def test_the_front_page_contract_paragraph_names_64_and_what_it_means():
    """The paragraph headed "The contract is the report and the exit
    codes" is where the promise was made on the front page, and it is
    where a reader goes to find out whether it was kept.

    Nothing required it to mention 64 at all: deleting its last sentence,
    leaving "Exit codes are 0, 1 and 2 and mean what the page above
    says", passed every test in this file. Measured.
    """
    paragraph = _normalised(_paragraph_containing(
        ROOT / "README.md", "The contract is the report and the exit codes."))
    assert str(EXIT_USAGE) in paragraph, \
        "the contract paragraph still lists three exit codes"
    assert "EX_USAGE" in paragraph, \
        "the paragraph names %d without naming the code: %r" % (EXIT_USAGE,
                                                                paragraph)
    assert any(word in paragraph.lower() for word in CALLED_WRONG), \
        "the paragraph names %d without saying it is a wrong call" % EXIT_USAGE
    assert "could not judge" in paragraph or "could not run" in paragraph, \
        "the paragraph does not say what 2 is left with"


def test_the_page_that_describes_the_report_says_which_runs_write_none():
    """`docs/report-schema.md` is one of the four places that carried the
    announcement, and a promise is discharged where it was made.

    Nothing required it to say anything: deleting the sentence outright
    left the page silent about 64 and every test green. Measured. A
    reader of that page is the reader most likely to be parsing stdout,
    which is the one thing a usage error does not write.
    """
    page = _normalised((ROOT / "docs" / "report-schema.md").read_text("utf-8"))
    assert str(EXIT_USAGE) in page, \
        "the page that says what is written says nothing about %d" % EXIT_USAGE
    naming = [sentence for sentence in re.split(r"(?<=\.) ", page)
              if re.search(r"\b%d\b" % EXIT_USAGE, sentence)]
    assert any("no report" in sentence or "writes none" in sentence
               for sentence in naming), (
        "the page names %d without saying it writes no report: %r"
        % (EXIT_USAGE, naming))


def test_the_front_page_tells_a_build_the_code_it_will_meet():
    """The README's table of doors is where a pipeline author looks
    first, and it listed three codes.

    Asked as a pairing. `"64" in row` was the first spelling, and the row
    `... 2 could not run; one document at 64 MiB` satisfies it -- as does
    a row with the meanings of 2 and 64 swapped. Both measured.
    """
    page = (ROOT / "README.md").read_text("utf-8")
    # Keyed on the enumeration, not on one row. Aimed at the door table
    # alone, this gate was blind to the line under "Putting it in a
    # build" -- the literal command a reader copies -- which went on
    # naming three codes after the table had been fixed. Measured.
    listings = [line for line in page.splitlines()
                if "could not run" in line and "0 pass" in line]
    assert listings, "nothing on the front page enumerates the exit codes"
    for line in listings:
        cell = line.rsplit("—", 1)[-1]
        meanings = {}
        for piece in re.split(r"[,;#]", cell):
            named = re.match(r"\s*(\d+)\s+(.+?)\s*$", piece)
            if named:
                meanings[named.group(1)] = named.group(2).lower()
        assert set(meanings) == {"0", "1", "2", str(EXIT_USAGE)}, (
            "this line names %s; a place that lists the codes lists every "
            "one a pipeline can meet: %r" % (sorted(meanings), line.strip()))
        assert "could not run" in meanings["2"]
        assert any(word in meanings[str(EXIT_USAGE)]
                   for word in CALLED_WRONG + ("incorrectly", "wrong")), \
            "%d is given no meaning a reader can act on: %r" % (
                EXIT_USAGE, meanings[str(EXIT_USAGE)])


def test_the_front_pages_own_snippet_survives_a_wrong_call():
    """The snippet under "the supported way to call this from another
    program" is the code a pipeline author copies, and it branched on
    `== 2`.

    With 64 arriving it fell through to `json.loads("")` and died of a
    `JSONDecodeError` -- the release that exists to stop a caller
    conflating "could not judge your file" with "you spelled the flag
    wrong" would have shipped a front page turning the second into a
    traceback. `docs/report-schema.md` warns against exactly that shape
    four sentences into the page.

    Run rather than read: the snippet is executed against a stub that
    returns each code this tool can leave by.
    """
    import types

    page = (ROOT / "README.md").read_text("utf-8")
    after = page.split("the supported way to call this")[1]
    snippet = after.split("```python")[1].split("```")[0]
    assert "json.loads" in snippet, "the snippet moved; this test aims at nothing"

    for code, writes_a_report in ((0, True), (1, True),
                                  (EXIT_ERROR, False), (EXIT_USAGE, False)):
        finished = types.SimpleNamespace(
            returncode=code,
            stdout='{"findings": []}' if writes_a_report else "",
            stderr="" if writes_a_report else "smtv: something")
        stub = types.ModuleType("subprocess")
        stub.run = lambda *a, _answer=finished, **k: _answer
        # Through `sys.modules`, not through the globals: the snippet's
        # first line is `import json, subprocess`, which rebinds the name
        # to the real module and ran the real `smtv` -- the first spelling
        # of this test failed with FileNotFoundError and told me nothing
        # about the README.
        saved = sys.modules.get("subprocess")
        sys.modules["subprocess"] = stub
        try:
            exec(compile(snippet, "<README>", "exec"),
                 {"__name__": "readme", "print": lambda *a, **k: None})
        except SystemExit:
            assert not writes_a_report, \
                "the snippet refuses exit %d, which does write a report" % code
        except Exception as broke:          # noqa: BLE001 - that is the finding
            raise AssertionError(
                "the README's own snippet dies on exit %d: %s: %s"
                % (code, type(broke).__name__, broke)) from None
        else:
            assert writes_a_report, \
                "the snippet parses stdout on exit %d, which writes none" % code
        finally:
            if saved is None:
                del sys.modules["subprocess"]
            else:
                sys.modules["subprocess"] = saved


def test_the_json_report_is_unchanged_by_this(tmp_path, capsys):
    """A usage error never reaches the reporter, so no report gains a
    field and `schemaVersion` does not move. Pinned because "exit codes
    are part of the contract" is the sentence right above the schema
    version in the README."""
    from aas_submodel_validate import __version__
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"assetAdministrationShells": [], "submodels": []}),
                    encoding="utf-8")
    main(["-f", "json", str(path)])
    document = json.loads(capsys.readouterr().out)
    assert document["schemaVersion"] == 1
    assert document["toolVersion"] == __version__
