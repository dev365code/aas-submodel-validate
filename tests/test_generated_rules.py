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
from aas_submodel_validate.rules import hd_tables
from builders import break_row, hd_env, inject, strip_row, stub_of


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
    findings = {f.id: f for f in runner.run(path).findings}
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
    findings = {f.id: f for f in runner.run(path).findings}
    assert "xs:date" in findings[row["id"]].violation.message
