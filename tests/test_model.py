"""Findings carry their remedy, and severity follows the spec's own words."""
from aas_submodel_validate.model import Finding, Rule, Severity, Violation


def _rule(prio="MUST", fix="do the right thing"):
    return Rule(id="T1", kind="template", prio=prio, title="test rule",
                spec=None, fn=lambda ctx: (), fix=fix)


def test_severity_follows_the_specification_keyword():
    assert _rule("MUST").severity is Severity.ERROR
    assert _rule("SHALL").severity is Severity.ERROR
    assert _rule("SHOULD").severity is Severity.WARNING
    assert _rule("MAY").severity is Severity.INFO


def test_a_violations_own_fix_beats_the_rules_standing_advice():
    rule = _rule(fix="the general remedy")
    assert Finding(rule, Violation("m")).fix == "the general remedy"
    assert Finding(rule, Violation("m", fix="this specific one")).fix == "this specific one"


def test_findings_serialise_for_machines():
    entry = Finding(_rule(), Violation("wrong", subject="urn:x", detail="saw 2")).as_dict()
    assert entry["rule"] == "T1"
    assert entry["severity"] == "error"
    assert entry["subject"] == "urn:x"
