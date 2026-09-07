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

import sys
from pathlib import Path

import pytest

from aas_submodel_validate import runner

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
    for label, target in corpus:
        report = runner.run(str(target))
        # A clean pass is a row with content: it moves the day a rule
        # wrongly starts firing on it, and several entries here are
        # exactly that. What cannot move is a refusal that says nothing,
        # which is what a refusal used to be.
        if not report.complete and not report.findings:
            empty.append((label, "refused and said nothing"))
    assert not empty, empty


def test_the_corpus_tells_inputs_apart(corpus):
    """And that it is not thirty-two spellings of one question.

    A corpus whose entries all produce the same verdict reports
    "nothing moved" for any change whatsoever. This does not say how
    many distinct verdicts there should be -- that number moves
    whenever a rule does -- only that there is more than one.
    """
    verdicts = {
        tuple(sorted((f.id, str(f.severity)) for f in runner.run(str(target)).findings))
        for _label, target in corpus}
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
    for label, target in corpus:
        if not label.startswith("a File value"):
            continue
        drawn |= {f.id for f in runner.run(str(target)).findings}
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

    held = [(label, target) for label, target in corpus if label.startswith("the archive holds")]
    assert len(held) == len(verdict_diff.HELD_SPELLINGS) == 4, held

    for (entry, value, resolves), (label, target) in zip(verdict_diff.HELD_SPELLINGS, held):
        with zipfile.ZipFile(str(target)) as archive:
            assert entry in archive.namelist(), (label, archive.namelist())
        with AasxPackage(str(target)) as package:
            found = package.part(value)
        assert found == (entry if resolves else None), (label, found)
    assert [r for _e, _v, r in verdict_diff.HELD_SPELLINGS].count(False) == 1, (
        "the row that must stay refused is what stops an over-eager fix"
    )
