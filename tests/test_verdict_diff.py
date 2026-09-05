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


def test_every_input_in_the_corpus_can_be_read(corpus):
    """A refused input is not a measurement.

    `complete` is the report's own answer to "did everything I was
    handed get read". An entry that comes back false is one both
    versions refuse for the same reason, and it contributes a row that
    can never move however much the reader changes.
    """
    unreadable = []
    for label, target in corpus:
        report = runner.run(str(target))
        if not report.complete:
            unreadable.append((label, [f.id for f in report.findings]))
    assert not unreadable, unreadable


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
