"""The corpus the release note is measured against must measure something.

`tools/verdict_diff.py` exists so that the sentence about what a
reader's pipeline will do differently is measured rather than recalled.
An instrument that reports confidently and measures nothing is worse
than no instrument, because the number it prints gets written into a
document that cannot be taken back.

That is not hypothetical. The first version of the corpus built its
File-value containers by handing an environment to a helper that takes
a semanticId string. Every one of them came back `X3: the document
could not be read` -- the same verdict from both versions, on every
input -- and the tool reported that sixteen shapes had not moved. They
had all moved. The release note would have carried that number.

So: the corpus is asked whether it is judgeable at all, and whether it
distinguishes anything. Neither question is about which verdicts moved
-- that is the tool's job and a person's to read -- and both are about
whether an answer of "nothing moved" would mean anything.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from pathlib import Path

import pytest

from aas_submodel_validate import runner, tablegen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verdict_diff  # noqa: E402


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    return verdict_diff.build_corpus(tmp_path_factory.mktemp("corpus"))


def test_every_input_in_the_corpus_says_something_that_could_change(corpus):
    """An input that says nothing is not a measurement.

    This asked whether every entry was *read* -- `complete` -- on the
    reasoning that a refused input "contributes a row that can never
    move however much the reader changes". That reasoning was true when
    it was written and this release is the one that disproves it: a
    refusal now carries a report, so what it says can change, and four
    of the seven rows that moved in 0.1.3 are refusals. Three of them
    moved *from* saying nothing.

    So the question is the one that was meant: does this entry say
    anything a later version could say differently. A run with no
    findings and nothing refused is a row that cannot move; a refusal
    with a finding on it is a row that just did.
    """
    empty = []
    for case in corpus:
        # With whatever the case is judged with. A case carrying a
        # template asked without it is a different question, and one
        # that would answer green here while the corpus measured
        # something nobody asked for.
        try:
            report = runner.run(str(case.path), template=case.template)
        except tablegen.TemplateRefused:
            # A table this reader will not read: exit 2 at the command
            # line, where every other refusal in this corpus is a report
            # with `complete` false. The asymmetry is the schema page's
            # to settle and not this file's; what matters here is that
            # "refused the table" is an answer a later version can give
            # differently, so it is not the silence this looks for.
            continue
        # A clean pass is a row with content: it moves the day a rule
        # wrongly starts firing on it, and several entries here are
        # exactly that. What cannot move is a refusal that says nothing,
        # which is what a refusal used to be.
        if not report.complete and not report.findings:
            empty.append((case.label, "refused and said nothing"))
    assert not empty, empty


def test_the_corpus_tells_inputs_apart(corpus):
    """And that it is not thirty-two spellings of one question.

    A corpus whose entries all produce the same verdict reports
    "nothing moved" for any change whatsoever. This does not say how
    many distinct verdicts there should be -- that number moves
    whenever a rule does -- only that there is more than one.
    """
    verdicts = set()
    for case in corpus:
        try:
            report = runner.run(str(case.path), template=case.template)
        except tablegen.TemplateRefused:
            verdicts.add(("the table was refused",))
            continue
        verdicts.add(tuple(sorted((f.id, str(f.severity))
                                  for f in report.findings)))
    assert len(verdicts) > 1, "every input in the corpus is judged the same"


def test_the_file_value_shapes_reach_the_rule_they_were_written_for(corpus):
    """The specific failure above, pinned by name.

    Those entries exist to move `HD-D7` and nothing else in the corpus
    asks about it. If the containers stop parsing -- or the path into
    the environment that carries the File value goes stale, which is
    the likelier way this rots -- they stop measuring silently, and the
    tool keeps printing a number.
    """
    drawn = set()
    for case in corpus:
        if not case.label.startswith("a File value"):
            continue
        drawn |= {f.id for f in runner.run(str(case.path)).findings}
    assert "HD-D7" in drawn, sorted(drawn)


def test_the_held_spelling_inputs_hold_the_part_their_value_names(corpus):
    """The corpus gained these because it could not see a change.

    Every `a File value of ...` container packs the same plain entry
    name, so which spelling `part` tries first cannot alter any of them.
    The tool duly reported nothing moved for a change that closes four
    recorded disagreements (docs/divergences.md #18). These put the odd
    spelling in the archive instead of only in the value, which is the
    only place the two orders can be told apart.

    What makes them a measurement rather than four more rows: three of
    them really do hold the file the value names, so `HD-D7` there is a
    false refusal and not a defect caught. The fourth holds the odd
    spelling in the *archive* and an ordinary value, and must stay
    refused -- matching it would mean the reader supplying characters
    the value does not have.
    """
    import zipfile

    from aas_submodel_validate.container import AasxPackage

    held = [case for case in corpus if case.label.startswith("the archive holds")]
    assert len(held) == len(verdict_diff.HELD_SPELLINGS) == 4, held

    for (entry, value, resolves), case in zip(verdict_diff.HELD_SPELLINGS, held):
        with zipfile.ZipFile(str(case.path)) as archive:
            assert entry in archive.namelist(), (case.label, archive.namelist())
        with AasxPackage(str(case.path)) as package:
            found = package.part(value)
        assert found == (entry if resolves else None), (case.label, found)
    assert [r for _e, _v, r in verdict_diff.HELD_SPELLINGS].count(False) == 1, (
        "the row that must stay refused is what stops an over-eager fix"
    )
def test_the_corpus_holds_a_passport_that_states_two_categories(corpus):
    """A shape the corpus could not see, and a release said so.

    `BAT-R8` withheld the rows that turn on a battery category from a
    file stating two of them -- a verdict change -- and the corpus
    comparison for that release read "none of the inputs is judged
    differently". Both sentences were true: every battery input here
    states exactly one category, so the measurement was silent about the
    only shape the change touched. A count of zero from a corpus that
    cannot hold the case is not evidence, and it reads exactly like one.

    Two categories, in one submodel. Two submodels each stating one
    would move a second thing -- how many Technical Data submodels a
    file has -- and then a difference could not be attributed.
    """
    seen = []
    for case in corpus:
        path = pathlib.Path(case.path)
        if not path.name.endswith(".json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError, RecursionError, OSError):
            #: The corpus carries inputs written to be unreadable -- one
            #: of them is legal JSON nested deeply enough to exhaust the
            #: parser and another is a path that names nothing, which are
            #: the cases `X3` and `X6` exist for. An input this walk
            #: cannot read states no category, which is the honest answer
            #: rather than a reason to narrow the walk to filenames.
            continue
        stated = _categories_stated(data)
        if len(stated) > 1:
            seen.append((path.name, stated))
    assert seen, (
        "every battery input states at most one category, so a verdict "
        "that turns on a file stating two cannot be measured here")


#: What the template calls a battery category. Read from the document by
#: identifier, never by `idShort` -- two of these live in one collection
#: and AAS requires their idShorts to differ, so a walk keyed on the name
#: would find one of the two and report the file states a single
#: category. That is also the rule this project judges by.
CATEGORY_ID = ("urn:samm:io.admin-shell.idta.batterypass."
               "technical_data:1.0.0#batteryCategory")


def _categories_stated(data):
    """Every distinct battery category value an environment states.

    Walks the document rather than asking the validator, so that what
    the corpus contains is established by something other than the code
    whose verdict the corpus exists to measure.
    """
    found = []

    def names_the_category(node):
        semantic = node.get("semanticId") or {}
        return any(key.get("value") == CATEGORY_ID
                   for key in (semantic.get("keys") or []))

    def walk(node):
        if isinstance(node, dict):
            if names_the_category(node):
                value = (node.get("value") or "")
                value = value.strip().lower() if isinstance(value, str) else ""
                if value and value not in found:
                    found.append(value)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(data)
    return tuple(found)


def test_the_comparison_says_what_it_does_not_cover(corpus):
    """A zero is only worth the cases behind it, and this corpus has
    none for `--template`.

    `_judge` runs the tool with `-f json` and no other flag, so every
    verdict a caller's own table decides is outside the comparison. The
    figure is still true and still useful — and quoted in a commit about
    that mode it reads as evidence it cannot be. `_judge`'s own
    docstring is where this project wrote the principle down: a zero
    from an instrument with no case for the change is the failure this
    tool exists to stop.

    The caveat is tied to the fact rather than left standing on its own.
    Add `--template` to the corpus and the sentence has to go, and this
    is what says so — a caveat nobody retires becomes a caveat nobody
    reads.

    The fact is read from the corpus and not from the source text. The
    first version of this cut `_judge`'s argv out of the file and looked
    for the flag in it, which meant the gate answered a question about
    spelling: build the list in a variable, or spread a case's flags
    into it, and the caveat stays required while the corpus already
    carries templates. Asking the corpus is asking the thing the
    sentence is about.
    """
    carried = [case.label for case in corpus if case.template is not None]
    source = (Path(verdict_diff.__file__)).read_text("utf-8")
    warns = "No case here is judged with --template" in source
    assert bool(carried) != warns, (
        "the corpus %s judged with --template (%d case(s)) and the summary "
        "%s say so" % ("is" if carried else "is not", len(carried),
                       "does" if warns else "does not"))


@pytest.fixture(scope="module")
def released_tree(tmp_path_factory):
    """The tree of the tag this comparison runs against by default, or a
    skip that says which of the three reasons applied.

    Taken out of git rather than installed, the way the tool takes it --
    0.08s measured, which is what makes asking the real released reader
    affordable here instead of a stand-in built to answer the way this
    test wants.

    The reasons are not hypothetical; the first version of this asserted
    instead of skipping and went red in two places at once. An unpacked
    sdist has no `.git` and `git tag` exits 128 there, and a checkout
    made at depth 1 has the history but none of the tags, which is what
    the matrix does. `make check` runs with `-rs`, so a skip here is
    printed with its reason rather than counted.

    The newest tag is not the same thing as the released version. On the
    job that publishes a release the tag being released is already there
    and is the newest of all, so "the released reader" became the tree
    under test, which has every option it has. Nothing before that job
    reproduced the state — the suite, the clean clone and the interpreter
    axes all ran on a tree with no tag of its own — and the release
    stopped at its own gate. So: the newest tag *below this tree's
    version*, and a tag whose name is not `vN.N.N` is not a release.

    Nor is every tag below the version a release. A tag is pushed before
    the job that publishes from it runs, and a job that stops leaves the
    tag behind in every clone that fetches tags; one version later it is
    the newest tag below the tree, and a reader nobody was ever given.
    So the tag must also be one the CHANGELOG dates
    (`_the_released_reader`, and the table under it).
    """
    import subprocess

    from aas_submodel_validate import __version__

    try:
        tag = subprocess.run(["git", "-C", str(ROOT), "tag", "--sort=-v:refname"],
                             capture_output=True, text=True)
    except OSError:
        pytest.skip("git is not available")
    if tag.returncode != 0:
        pytest.skip("not a git checkout (an unpacked sdist is not one)")
    latest = _the_released_reader(
        tag.stdout.split("\n"), __version__,
        (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    if latest is None:
        pytest.skip("this checkout carries no tag older than %s that the "
                    "CHANGELOG dates, so there is no earlier reader here to "
                    "ask; a clone made at depth 1 and the first release both "
                    "look like this" % __version__)
    into = tmp_path_factory.mktemp("released")
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", latest],
                             capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", str(into)], input=archive.stdout, check=True)
    return latest, into / "src"


def _the_released_reader(tags, version, changelog):
    """The newest `vN.N.N` tag below `version` that `changelog` dates.

    None when there is none. Apart from the fixture so that the choice
    is asserted by itself: every test handed the reader passes whichever
    one it gets, because both worlds are asserted there, so a wrong
    choice would not turn one of them red.
    """
    def numbers(name):
        matched = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", name.strip())
        return tuple(int(part) for part in matched.groups()) if matched else None

    ours = numbers("v" + version)
    dated = set(re.findall(r"^## (\d+\.\d+\.\d+) — \d{4}-\d{2}-\d{2}$",
                           changelog, re.MULTILINE))
    earlier = [name.strip() for name in tags
               if numbers(name) and (ours is None or numbers(name) < ours)
               and name.strip()[1:] in dated]
    return max(earlier, key=numbers) if earlier else None


@pytest.mark.parametrize("tags,version,headings,reader", [
    # A tag pushed, its release never made, and the tree one version on.
    # It is the newest tag below the version, and not a release.
    (["v1.3.0", "v1.2.1", "v1.2.0"], "1.3.1",
     ["1.3.1 — unreleased", "1.2.1 — 2026-01-02", "1.2.0 — 2026-01-01"],
     "v1.2.1"),
    # The job that publishes a release: the tree's own tag is there, and
    # dated, and is not the reader before it.
    (["v1.3.0", "v1.2.1"], "1.3.0",
     ["1.3.0 — 2026-01-03", "1.2.1 — 2026-01-02"], "v1.2.1"),
    # While one is prepared.
    (["v1.2.1"], "1.3.0", ["1.3.0 — unreleased", "1.2.1 — 2026-01-02"],
     "v1.2.1"),
    # Newest by number, not by spelling.
    (["v1.10.0", "v1.9.0"], "1.11.0",
     ["1.10.0 — 2026-01-02", "1.9.0 — 2026-01-01"], "v1.10.0"),
    # Names that are not releases of this package.
    (["v1.3.0-rc1", "sdk-v2.0.0", "nightly", "v1.2.1"], "1.3.0",
     ["1.3.0 — unreleased", "1.2.1 — 2026-01-02"], "v1.2.1"),
    # No reader: a clone with no tags, a first release, and tags the
    # CHANGELOG never dated.
    ([], "1.3.0", ["1.3.0 — unreleased", "1.2.1 — 2026-01-02"], None),
    (["v1.0.0"], "1.0.0", ["1.0.0 — 2026-01-01"], None),
    (["v1.2.1"], "1.3.0", ["1.3.0 — unreleased"], None),
])
def test_the_reader_asked_is_the_newest_release_the_changelog_dates(
        tags, version, headings, reader):
    changelog = "# Changelog\n\n" + "".join("## %s\n\nText.\n\n" % heading
                                           for heading in headings)
    assert _the_released_reader(tags, version, changelog) == reader


def _a_template_case(tmp_path):
    """An input and a table for it, the smallest pair that needs the flag."""
    identifier = "urn:example:verdict-diff:no-pack-answers-for-this"

    def ref(value):
        return {"type": "GlobalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    from builders import env_json

    template = tmp_path / "own-template.json"
    template.write_text(json.dumps({"submodels": [{
        "kind": "Template", "idShort": "SomethingNobodyVendored",
        "id": "urn:example:verdict-diff:template",
        "semanticId": ref(identifier),
        "submodelElements": [{
            "modelType": "Property", "idShort": "SerialNumber",
            "semanticId": ref(identifier + "/SerialNumber"),
            "valueType": "xs:string",
            "qualifiers": [{"type": "SMT/Cardinality", "valueType": "xs:string",
                            "value": "One"}]}]}]}), encoding="utf-8")
    document = tmp_path / "declares-it.json"
    document.write_bytes(env_json(identifier))
    return verdict_diff.Case("a template no pack has", document, template=template)


def test_a_case_the_old_version_cannot_be_asked_is_not_a_verdict_that_moved(
        released_tree, tmp_path):
    """`--template` is new, and new is not moved.

    The released reader answers a case carrying it with `unrecognized
    arguments` and exit 64 -- measured, not assumed. Compared as a
    verdict that is a difference, and every template case would land in
    the moved list the day the option shipped: true, useless, and it
    buries the one input whose verdict actually changed. The same
    mistake this file made over `rulesNotAsked`, which is why that one
    is counted apart too.
    """
    tag, old_src = released_tree
    case = _a_template_case(tmp_path)

    # Asked of that reader rather than assumed from its number. Which
    # release this runs against depends on where it runs, and a release
    # that has the option is not a defect -- it is the day this case
    # starts being compared like any other. Both worlds are asserted, so
    # neither goes unchecked.
    knows_it = verdict_diff._has_the_option(old_src, "--template")
    assert verdict_diff._comparable(ROOT / "src", case)
    assert verdict_diff._comparable(old_src, case) is knows_it, tag

    before = verdict_diff._judge(old_src, case)
    if not knows_it:
        # What the comparison would have had to work with, stated rather
        # than assumed: not a verdict, and not one that could be compared.
        assert before[2] == 64 and before[-1] == "no report", (tag, before)
        assert (verdict_diff._verdict_of(before)
                != verdict_diff._verdict_of(
                    verdict_diff._judge(ROOT / "src", case))), (
            "the two answers are identical, so this case proves nothing")
    else:
        assert before[2] != 64, (
            "%s lists --template in its help and then refuses it" % tag)
    # And a case with no flag on it is asked of both, which is every
    # other row in the corpus.
    assert verdict_diff._comparable(old_src, verdict_diff.Case("plain", case.path))


def test_a_probe_that_cannot_run_is_not_an_option_that_is_absent(tmp_path):
    """False here would empty the comparison and say nothing.

    Every template case is set aside on the strength of this answer, so
    a probe answering False when it simply could not run turns the whole
    axis off quietly -- and a quiet instrument reading zero is what this
    file exists to prevent. It stops instead.
    """
    holds_a_reader = tmp_path / "a-tree"
    package = holds_a_reader / "aas_submodel_validate"
    package.mkdir(parents=True)
    (package / "cli.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text("raise SystemExit(3)", encoding="utf-8")

    with pytest.raises(RuntimeError) as refused:
        verdict_diff._has_the_option(holds_a_reader, "--template")
    assert "which options it has" in str(refused.value)


def test_a_tree_with_no_reader_in_it_does_not_get_answered_by_the_machine(tmp_path):
    """The quieter half of the same failure, and this one is measured.

    `PYTHONPATH` comes before site-packages, so a tree holding the
    package answers for it -- and a tree that does not lets whatever is
    installed answer instead. This project *is* installed on the machine
    this was written on, so pointing the comparison at a tree with no
    reader in it produced a confident `--help`, a real verdict on every
    input, and both sides agreeing because both sides were the same
    reader. `--against` a tag from before the `src/` layout is the way
    somebody meets this, and it reads as "nothing moved".
    """
    empty = tmp_path / "no-package-here"
    empty.mkdir()
    with pytest.raises(RuntimeError) as refused:
        verdict_diff._has_the_option(empty, "--template")
    assert "holds no reader" in str(refused.value)


def test_the_count_leaves_out_what_the_old_version_was_never_asked(
        released_tree, tmp_path, capsys):
    """The denominator is a claim, and it is the one that gets quoted.

    "0 of 65 inputs are judged differently" over a corpus where four of
    the sixty-five were never put to the old reader is a true sentence
    that reads as a false one. So the cases nobody could ask are named
    above the count, and taken out of it.

    Measured through `compare` rather than read off the source, which is
    why it is a parameter: a test that had to build all sixty-one inputs
    and run two readers over each would be a test nobody runs.
    """
    tag, old_src = released_tree
    corpus = [verdict_diff.Case("the official example, untouched",
                                verdict_diff.EXAMPLE),
              _a_template_case(tmp_path)]

    # One if that reader predates the option, none if it has it. The
    # count is read from the reader rather than fixed here: on the job
    # that publishes a release, the release being published is a tag
    # like any other and this ran against a tree that has every option
    # the tree under test has.
    aside = 0 if verdict_diff._has_the_option(old_src, "--template") else 1

    counts = verdict_diff.compare(tag, old_src, corpus)
    printed = capsys.readouterr().out

    assert counts["unanswerable"] == aside, printed
    assert counts["compared"] == len(corpus) - aside
    assert ("%d of %d inputs are judged differently."
            % (counts["moved"], counts["compared"])) in printed
    if aside:
        assert ("%d of 2 are asked with an option %s does not have"
                % (aside, tag)) in printed
    else:
        assert "does not have" not in printed, printed
    # Set aside, not dropped: what the working tree makes of it is
    # printed, because a case that stopped being judgeable at all is
    # worth seeing even when there is nothing to compare it with.
    assert "a template no pack has" in printed


def test_every_case_that_carries_a_table_is_judged_with_it(corpus):
    """A case can name a table the reader never opens.

    Then the corpus looks like it covers the mode while judging those
    inputs with the packs, and the caveat that used to stand under the
    count has been retired on a promise. So each carrier is asked
    whether the table it names is the one the report says answered.
    """
    carriers = [case for case in corpus if case.template is not None]
    assert len(carriers) == 4, [case.label for case in carriers]

    for case in carriers:
        try:
            report = runner.run(str(case.path), template=case.template)
        except tablegen.TemplateRefused:
            # Refused, which is proof enough that it was read.
            continue
        assert report.template, case.label
        assert report.template["path"] == str(case.template), case.label


def test_the_table_a_case_carries_reaches_the_command_line(corpus):
    """And that the reader answers from it.

    `runner.run` above is the library entrance; this is the one the
    comparison actually uses, and a `_judge` that built its argv without
    the flag would leave every carrier judged by the packs while the
    report above said otherwise.

    The pairs are measured, and they are what makes these rows worth a
    pass each: the same missing element comes back under a `TPL-E` id
    with the table and a pack's id without it, so a change to which
    reader answers is visible here as a change of rule id.
    """
    expected = {
        "a submodel judged by a table no pack has": ("TPL-E01", "SMT-D1"),
        "a Digital Nameplate, judged by the vendored template handed in by hand":
            ("TPL-E02", "DN-E02"),
    }
    by_label = {case.label: case for case in corpus}
    assert set(expected) <= set(by_label), sorted(by_label)

    for label, (with_the_table, without_it) in expected.items():
        case = by_label[label]
        judged = verdict_diff._judge(ROOT / "src", case)
        plain = verdict_diff._judge(ROOT / "src", case._replace(template=None))
        assert {rule for rule, _severity, _subject in judged[0]} == {with_the_table}, (
            label, judged)
        assert {rule for rule, _severity, _subject in plain[0]} == {without_it}, (
            label, plain)
        assert verdict_diff._verdict_of(judged) != verdict_diff._verdict_of(plain)
