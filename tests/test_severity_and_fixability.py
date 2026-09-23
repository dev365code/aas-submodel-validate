"""What a finding costs to fix, and where to stand to see it.

Two attributes beside the severity a rule already carries. They answer
different questions and neither answers the other's: severity is how
loudly a defect is reported, fixability is what it would take to repair
it, and a file can hold a loud defect nobody can repair (a missing
original) beside a quiet one that is repaired by rewriting a string.
Keeping them one number is what makes a tool promise repairs it cannot
perform.

`path` is the third: the route from the input to the kind of place this
rule's findings name. `subject` is one string doing three jobs -- an
idShort path, an identifier, or a part name -- and a consumer cannot
tell which without knowing the rule. This says which, per rule, in a
closed vocabulary.
"""
from __future__ import annotations

import json

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.model import PATH_STEPS, Rule, Violation
from aas_submodel_validate.registry import all_rules


def test_every_rule_says_where_its_findings_point():
    """`subject` is documented as "an idShort path, an identifier, or a
    part name", and nothing says which for a given rule. A consumer
    that wants to navigate to the thing a finding names has to know the
    rule already, which is the knowledge the report exists to supply."""
    missing = [rule.id for rule in all_rules() if not rule.path]
    assert not missing, missing
    unknown = {step for rule in all_rules() for step in rule.path
               if step not in PATH_STEPS}
    assert not unknown, "steps outside the vocabulary: %s" % sorted(unknown)


def test_a_grade_without_a_reason_is_refused():
    """A number nobody can check is worse than no number: it reads as a
    measurement. The reason is a sentence about this code, and it is
    required at the boundary rather than audited later, beside the
    duplicate id and the missing remedy."""
    with pytest.raises(ValueError) as refused:
        Rule(id="T-1", kind="template", prio="MUST", title="t", spec=None,
             fn=lambda ctx: (), fix="do it", path=("document",), fixability=2)
    assert "reason" in str(refused.value).lower(), refused.value


def test_a_grade_outside_the_scale_is_refused():
    for grade in (0, 6, -1):
        with pytest.raises(ValueError):
            Rule(id="T-%d" % grade, kind="template", prio="MUST", title="t",
                 spec=None, fn=lambda ctx: (), fix="do it",
                 path=("document",), fixability=grade,
                 fixability_why="because")


def test_a_finding_takes_the_grade_of_its_own_violation():
    """One rule can produce defects of different fixability, and the
    code knows which it produced. A rule-level number would be wrong
    for all but one of them."""
    rule = Rule(id="T-9", kind="template", prio="MUST", title="t", spec=None,
                fn=lambda ctx: (), fix="do it", path=("document",),
                fixability=5, fixability_why="the value is not in the input")
    from aas_submodel_validate.model import Finding

    stock = Finding(rule=rule, violation=Violation("gone"))
    graded = Finding(rule=rule, violation=Violation("spelt wrong", fixability=2))
    assert stock.fixability == 5
    assert graded.fixability == 2


def test_the_report_carries_both_and_stays_schema_one(tmp_path):
    """Additive: the version does not move, every field a reader had is
    still there, and the two new ones are beside them."""
    from builders import env_json

    path = tmp_path / "unmatched.json"
    path.write_bytes(env_json("urn:nobody:claims:this"))
    document = json.loads(json.dumps(runner.run(str(path)).as_dict()))

    assert document["schemaVersion"] == 1
    assert document["findings"], "this input is supposed to draw one"
    for finding in document["findings"]:
        assert finding["fixability"] in (1, 2, 3, 4, 5), finding
        assert finding["path"], finding
        for was_there in ("rule", "severity", "priority", "message", "subject",
                          "fix", "title", "spec"):
            assert was_there in finding, was_there


def test_every_registered_rule_says_where_its_findings_point():
    """A route is optional to the decorator, so a rule written for a test can
    leave it out; every rule this package registers declares one. Two rules
    added after the route was introduced -- the shared File rule, installed
    for two packs -- had none, and nothing noticed."""
    import aas_submodel_validate.runner  # noqa: F401  (registers the packs)
    from aas_submodel_validate.registry import all_rules

    missing = sorted(rule.id for rule in all_rules() if not rule.path)
    assert not missing, missing
