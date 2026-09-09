"""Every generated rule fires, and the golden fixture fires none.

The mutation per row is chosen by what the row demands: a required
element is removed; an optional one is injected twice (over its maximum);
a required child of an optional list gets its list injected empty. If
any row's id never appears, that rule is dead -- and a dead rule is
indistinguishable from a wrong one from the outside.
"""
from __future__ import annotations

import copy
import json

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.rules import (
    dbp_tables,
    engine,
    hd_tables,
    td_tables,
)
from builders import break_row, hd_env, inject, strip_row, stub_of
from verdicts import by_id


def _ids(tmp_path, env: dict):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return {finding.id for finding in runner.run(path).findings}


def test_the_golden_environment_is_clean(tmp_path):
    assert _ids(tmp_path, hd_env()) == set()


@pytest.mark.parametrize("row", hd_tables.ROWS, ids=[r["id"] for r in hd_tables.ROWS])
def test_every_generated_rule_fires(tmp_path, row):
    assert row["id"] in _ids(tmp_path, break_row(hd_env(), row, hd_tables))


#: The three ways a cardinality is said. Two copies of this vocabulary
#: exist and only one of them was checked: the generator writes the
#: remedy ("Provide exactly one 'Documents' element(s)...") and the
#: byte-compare gate holds it, while the walk writes the message from a
#: table of its own that nothing read.
#:
#: A key moved in that table does not crash and does not lose the
#: finding. It falls through to "a bounded number of", and the report
#: then says one thing and advises another about the same row:
#:
#:     error  HD-E01  the template expects a bounded number of 'Documents'
#:            fix: Provide exactly one 'Documents' element(s) with ...
CARDINALITY_WORDS = ("exactly one", "at most one", "one or more")


def _cardinality_phrase(text):
    said = [phrase for phrase in CARDINALITY_WORDS if phrase in (text or "")]
    return said[0] if len(said) == 1 else None


def test_the_walk_has_a_word_for_every_count_it_can_report():
    """The message's vocabulary against the shapes the tables actually
    carry, across all three of them -- the test below reads 02004 only,
    and a shape none of its rows has would reach the fallback with
    nothing to compare it to.

    Reportable means a count can fail: `(0, None)` is unbounded and not
    required, so `count < 0` never holds and there is no upper test. That
    shape exists (five rows of it, all in 02003) and is the reason the
    fallback is there at all; it is also why the fallback is unreachable,
    which is worth a gate rather than a comment. A fifth cardinality in a
    future template arrives here silently otherwise."""
    reportable = set()

    def walk(rows):
        for row in rows:
            low, high = row["card"]
            if low > 0 or high is not None:
                reportable.add((low, high))
            walk(row["children"])

    for tables in (hd_tables, td_tables, dbp_tables):
        walk(tables.TREE)
    assert reportable, "no table has a countable row any more"
    assert reportable == set(engine._KIND_WORDS)
    # And the shape that is not reportable is really in the tables, or
    # the sentence above is about nothing.
    unbounded = set()

    def walk_all(rows):
        for row in rows:
            unbounded.add(tuple(row["card"]))
            walk_all(row["children"])

    for tables in (hd_tables, td_tables, dbp_tables):
        walk_all(tables.TREE)
    assert (0, None) in unbounded


def test_a_cardinality_message_and_its_remedy_say_the_same_thing(tmp_path):
    """Every row, because the disagreement is per shape and the shapes
    are spread across the table.

    One test over the whole table rather than one per row: what a reader
    needs when this goes red is which rows disagree, not the first one
    alphabetically."""
    disagreeing, said, checked = [], set(), 0
    for row in hd_tables.ROWS:
        path = tmp_path / "env.json"
        path.write_bytes(json.dumps(break_row(hd_env(), row, hd_tables)).encode("utf-8"))
        for finding in runner.run(path).findings:
            if finding.id != row["id"] or "the template expects" not in \
                    finding.violation.message:
                continue
            checked += 1
            message = _cardinality_phrase(finding.violation.message)
            said.add(message)
            if message != _cardinality_phrase(finding.fix):
                disagreeing.append((row["id"], finding.violation.message, finding.fix))
            break
    assert checked == len(hd_tables.ROWS), \
        "only %d of %d rows reached a cardinality finding" % (checked, len(hd_tables.ROWS))
    assert said == set(CARDINALITY_WORDS), \
        "the table stopped exercising every shape: %s" % sorted(x for x in said if x)
    assert not disagreeing, (
        "the message and the remedy disagree about the cardinality: %r"
        % disagreeing[:5])


def test_a_kind_mismatch_names_both_kinds(tmp_path):
    env = copy.deepcopy(hd_env())
    row = hd_tables.BY_LABEL["Version"]
    strip_row(env, row, hd_tables)
    wrong = {"idShort": "Version", "modelType": "MultiLanguageProperty",
             "semanticId": {"type": "ExternalReference",
                            "keys": [{"type": "GlobalReference", "value": row["sid"]}]},
             "value": [{"language": "en", "text": "V1.2"}]}
    inject(env, hd_tables.BY_ID[row["parent"]], [wrong], hd_tables)
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    findings = by_id(runner.run(path))
    assert "must be a Property" in findings[row["id"]].violation.message


def test_a_value_type_mismatch_is_reported(tmp_path):
    env = copy.deepcopy(hd_env())
    row = hd_tables.BY_LABEL["StatusSetDate"]
    strip_row(env, row, hd_tables)
    wrong = stub_of(row)
    wrong["valueType"] = "xs:string"
    wrong["value"] = "2020-02-06"
    inject(env, hd_tables.BY_ID[row["parent"]], [wrong], hd_tables)
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    findings = by_id(runner.run(path))
    assert "xs:date" in findings[row["id"]].violation.message


# -- a required element that carries nothing ---------------------------------

def _without_value(env, label):
    """The same environment with one property's `value` key removed."""
    import copy
    env = copy.deepcopy(env)

    def walk(node):
        if isinstance(node, dict):
            if node.get("idShort") == label and node.get("modelType") == "Property":
                node.pop("value", None)
                return True
            return any(walk(v) for v in node.values())
        if isinstance(node, list):
            return any(walk(v) for v in node)
        return False

    assert walk(env), "no property named %r in this fixture" % label
    return env


def test_a_required_property_that_carries_no_value_is_reported(tmp_path):
    """The template says exactly one `DocumentDomainId` and the file has
    one, holding nothing.

    Every content rule guards on `value is not None` -- correctly, since
    cardinality is the generated rules' question and not theirs -- and
    the generated rule counted the element and stopped. So the count was
    satisfied in form: a Technical Data file with the value deleted from
    all nine of its required properties drew no finding at all and left
    by 0. An empty shell passing is the false pass this project treats
    as worst, and it was on the tool's own promise -- "the template
    requires this element" answered yes about an element carrying
    nothing.
    """
    path = tmp_path / "env.json"
    path.write_text(json.dumps(_without_value(hd_env(), "DocumentDomainId")),
                    "utf-8")
    report = runner.run(path)
    said = [f for f in report.findings if "DocumentDomainId" in (f.violation.message or "")]
    assert said, sorted({f.id for f in report.findings})
    assert not report.ok, "an element required by the template carries nothing"
    assert "carries no value" in said[0].violation.message, said[0].violation.message
    # Its own remedy. The row's standing advice is "provide one", which
    # here tells the reader to add a second empty one.
    assert "add another" in (said[0].fix or "").lower(), said[0].fix


def test_an_optional_property_with_no_value_is_left_alone(tmp_path):
    """The rule is about what the template requires. An element it
    permits to be absent is permitted to be there and empty; saying
    otherwise would be this tool inventing a requirement."""
    from aas_submodel_validate.rules import hd_tables
    optional = [r for r in hd_tables.ROWS
                if r["kind"] == "Property" and (r["card"] or [0])[0] == 0]
    assert optional, "the fixture pack has no optional property to test with"
    path = tmp_path / "env.json"
    base = hd_env()
    for row in optional:
        try:
            base = _without_value(base, row["label"])
        except AssertionError:
            continue          # not in this fixture
    path.write_text(json.dumps(base), "utf-8")
    report = runner.run(path)
    assert report.ok, [f.violation.message for f in report.findings]


def test_the_published_examples_carry_a_value_everywhere_it_is_required():
    """The over-refusal check, run rather than assumed.

    A rule that moves the exit code has to be measured against what the
    standards body actually publishes, and this one is: across IDTA's own
    02004 example and the three 02003 samples, every property carries a
    value -- 102 of them, none absent. So the rule costs nothing on
    published material, which is what makes MUST defensible."""
    from pathlib import Path as _Path
    root = _Path(__file__).resolve().parents[1]
    seen = 0
    for name in sorted((root / "tests" / "corpus" / "idta").rglob("*.json")) + \
            sorted((root / "tests" / "corpus" / "idta").rglob("*.aasx")):
        report = runner.run(name)
        for finding in report.findings:
            assert "carries no value" not in (finding.violation.message or ""), \
                "%s: %s" % (name.name, finding.violation.message)
        seen += 1
    assert seen >= 4, seen


def test_an_empty_string_is_a_value_and_this_rule_does_not_judge_it(tmp_path):
    """The line the presence rule draws, pinned because it is a decision.

    `value: ""` is the empty string, which *is* a value of type
    `xs:string`, and calling it nothing is a reading about content where
    this rule is about presence -- the metamodel draws the same line and
    so does the file, one shape carrying the key and one not. Recorded
    in `docs/divergences.md` #40 and, until this test, recorded and
    nothing more: a mutation that swept the empty string in passed the
    whole suite.

    Where an empty value really is wrong the tool already says so
    elsewhere -- the relayed channel for a typed property, `TD-D1` for a
    dated one -- and what is left unjudged is an empty `xs:string`,
    deliberately.
    """
    import copy
    base = copy.deepcopy(hd_env())

    def blank(node):
        if isinstance(node, dict):
            if node.get("idShort") == "DocumentDomainId" \
                    and node.get("modelType") == "Property":
                node["value"] = ""
                return True
            return any(blank(v) for v in node.values())
        if isinstance(node, list):
            return any(blank(v) for v in node)
        return False

    assert blank(base)
    path = tmp_path / "env.json"
    path.write_text(json.dumps(base), "utf-8")
    report = runner.run(path)
    assert not [f for f in report.findings
                if "carries no value" in (f.violation.message or "")], \
        "the presence rule judged an empty string; #40 says it does not"
    # And the control: the same property with the key gone is reported,
    # so this test cannot pass by the rule being broken altogether.
    gone = tmp_path / "gone.json"
    gone.write_text(json.dumps(_without_value(hd_env(), "DocumentDomainId")), "utf-8")
    assert [f for f in runner.run(gone).findings
            if "carries no value" in (f.violation.message or "")]
