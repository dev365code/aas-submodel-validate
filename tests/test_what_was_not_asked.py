"""A run that could not put half its questions has to say so.

`docs/divergences.md` #23: a generated rule lives inside a scope, and a
scope is entered only when an element matches the row that opens it. An
element whose `semanticId` matches no row is not entered, so every rule
beneath it leaves the run -- and the report said nothing, because
nothing was wrong with what *was* checked.

`tools/scope_silence.py` measures how much that is worth: a typo inside
a path segment of one identifier silences 24 of the 69 measurable rows
and produces a report **byte-identical** to the conformant one. Two such
documents were indistinguishable, which is the same sentence every other
field on `Report` was added to answer.

This is not a claim about the file. The template states a minimum, not a
whitelist (#19), so an element matching no row is not by itself a
defect. What is reportable is that this run did not look inside it.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from aas_submodel_validate import runner
from aas_submodel_validate.rules import td_tables
from builders import build_aasx, td_env

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import scope_silence  # noqa: E402


def _judge(tmp_path, environment, tag):
    path = build_aasx(tmp_path / (tag + ".aasx"),
                      payload=json.dumps(environment).encode("utf-8"),
                      files=(("aasx/files/manual.pdf", b"%PDF-1.4"),))
    return runner.run(str(path))


def _drifted(label, mode="middle"):
    sid = td_tables.BY_LABEL[label]["sid"]
    environment = copy.deepcopy(td_env())
    changed = []
    scope_silence._wear(environment, sid, mode, changed)
    assert changed, "the fixture does not carry %s" % label
    return environment


def test_a_conformant_file_is_asked_everything(tmp_path):
    """The denominator. If this is not empty on a clean file the field
    below is noise, and a reader learns to skip it."""
    assert _judge(tmp_path, td_env(), "clean").not_asked == []


def test_an_unrecognised_scope_says_which_rules_it_took_with_it(tmp_path):
    """`ProductClassifications` opens a subtree. Misspell one segment of
    its identifier and the walk does not enter it -- the same findings,
    the same exit code, and seven rules never put."""
    report = _judge(tmp_path, _drifted("ProductClassifications"), "typo")
    clean = _judge(tmp_path, td_env(), "clean2")

    assert {f.id for f in report.findings} == {f.id for f in clean.findings}, (
        "this test is worthless if the findings already differ")
    assert report.not_asked, "the two reports are still indistinguishable"
    assert "TD-E12" in report.not_asked, report.not_asked
    assert "TD-E11" not in report.not_asked, (
        "the row that failed to match was reached; it is its children that were not")


def test_the_count_matches_what_the_instrument_measures(tmp_path):
    """The field and `tools/scope_silence.py` have to be measuring the
    same thing, or one of them is describing a run nobody had."""
    for label in ("ProductClassifications", "TechnicalPropertyAreas", "ProductImages"):
        report = _judge(tmp_path, _drifted(label), "m-" + label)
        assert report.not_asked, label
        for rule_id in report.not_asked:
            assert rule_id.startswith(("TD-", "HD-", "DBP2-")), rule_id


def test_a_pack_whose_submodel_is_absent_is_not_reported_as_unasked(tmp_path):
    """A Handover file is not a Technical Data file, and listing every
    Technical Data rule against it would bury the signal in the noise
    the first version of this made."""
    from builders import hd_env

    report = _judge(tmp_path, hd_env(), "hd-only")
    assert not [r for r in report.not_asked if r.startswith("TD-")], report.not_asked


def test_the_json_report_carries_it(tmp_path):
    """A consumer comparing two stored reports is the reader this exists
    for; the field has to survive serialisation."""
    report = _judge(tmp_path, _drifted("ProductClassifications"), "json")
    document = report.as_dict()
    assert document["summary"]["rulesNotAsked"] == report.not_asked
    assert document["summary"]["rulesNotAsked"], document["summary"]
    # Round-trips: the CLI prints this with `json.dumps`.
    assert json.loads(json.dumps(document))["summary"]["rulesNotAsked"] == report.not_asked


def test_the_person_at_the_terminal_is_told_too(tmp_path):
    """The JSON key is for a pipeline. The screen is where somebody
    decides whether to ship, and until now it printed the same line for
    a file that was asked everything and one that was not."""
    from aas_submodel_validate.report import render

    clean = render(_judge(tmp_path, td_env(), "clean3"))
    typo = render(_judge(tmp_path, _drifted("ProductClassifications"), "typo3"))
    assert clean != typo, "the screen still cannot tell them apart"
    assert "not asked" not in clean
    assert "rules not asked" in typo
    assert "did not look inside it" in typo


def test_one_unasked_rule_is_not_called_rules(tmp_path):
    """Plural agreement, because this line is read by people and a tool
    that writes '1 rules' reads as one nobody proofread."""
    from aas_submodel_validate.report import render

    report = _judge(tmp_path, _drifted("ProductClassifications"), "plural")
    report.not_asked = report.not_asked[:1]
    assert "1 rule not asked" in render(report)
    report.not_asked = report.not_asked * 2
    assert "2 rules not asked" in render(report)


def _find_by_sid(node, sid):
    if isinstance(node, dict):
        for key in (node.get("semanticId") or {}).get("keys") or []:
            if key.get("value") == sid:
                return node
        for value in node.values():
            found = _find_by_sid(value, sid)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_by_sid(value, sid)
            if found is not None:
                return found
    return None


def test_the_same_rule_lost_twice_is_reported_once(tmp_path):
    """A list with two items, both carrying the same unrecognised child:
    the scope is walked once per item, so the same three rows are
    stranded twice. A reader counting the list would read that as twice
    the loss, and `24 rules not asked` is a number people will quote."""
    from aas_submodel_validate.rules import hd_tables
    from builders import hd_env

    environment = copy.deepcopy(hd_env())
    documents = _find_by_sid(environment, hd_tables.BY_LABEL["Documents"]["sid"])
    assert len(documents["value"]) == 1, "the fixture shape moved"
    documents["value"].append(copy.deepcopy(documents["value"][0]))

    changed = []
    scope_silence._wear(environment, hd_tables.BY_LABEL["DocumentId"]["sid"],
                        "middle", changed)
    assert len(changed) == 2, changed

    not_asked = _judge(tmp_path, environment, "twice").not_asked
    assert not_asked == sorted(set(not_asked), key=not_asked.index)
    assert len(not_asked) == len(set(not_asked)) == 3, not_asked
