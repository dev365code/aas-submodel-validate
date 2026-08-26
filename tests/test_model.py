"""Findings carry their remedy, and severity follows the spec's own words.

And the report has a shape somebody else's program reads. `schemaVersion`
is a promise to that program, and it was a promise nothing kept: every
key in the document could be renamed, and the version itself could be
renamed or bumped, with the suite green.
"""
import json

import pytest

from aas_submodel_validate.model import Finding, Report, Rule, Severity, Violation


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


#: The shape `schemaVersion: 1` names, written out rather than read off
#: the code. A contract derived from the thing it constrains constrains
#: nothing: `set(report.as_dict())` agrees with whatever is emitted,
#: including a typo.
#:
#: Adding a key is compatible and leaves the version where it is -- a
#: consumer that does not know the key reads what it read before.
#: Renaming or removing one is not. Both changes pass through this list,
#: which is the whole point: somebody has to say so.
REPORT_KEYS = {"schemaVersion", "path", "ok", "summary", "notes", "findings"}
SUMMARY_KEYS = {"errors", "warnings", "info", "rulesChecked", "complete"}
FINDING_KEYS = {"rule", "kind", "severity", "priority", "message", "subject",
                "detail", "fix", "title", "spec"}


def _report():
    report = Report(path="machine-docs.json")
    report.findings = [Finding(_rule(), Violation("wrong", subject="urn:x",
                                                  detail="saw 2", fix="mend it"))]
    report.checked = 123
    report.notes = ["something worth saying once"]
    return report


def test_the_report_has_the_shape_version_one_names():
    document = _report().as_dict()
    assert set(document) == REPORT_KEYS
    assert set(document["summary"]) == SUMMARY_KEYS
    assert set(document["findings"][0]) == FINDING_KEYS


def test_the_version_says_which_shape_it_is():
    """A version nobody asserts is a number that moves without meaning
    anything -- and this one could be bumped, or renamed away, with
    everything green."""
    assert _report().as_dict()["schemaVersion"] == 1


def test_the_report_says_what_the_types_promise():
    """Key names alone let a boolean become a string. A consumer reading
    `ok` branches on it."""
    document = _report().as_dict()
    assert isinstance(document["ok"], bool)
    assert isinstance(document["path"], str)
    assert isinstance(document["notes"], list)
    assert isinstance(document["findings"], list)
    assert isinstance(document["summary"]["complete"], bool)
    for counter in ("errors", "warnings", "info", "rulesChecked"):
        assert isinstance(document["summary"][counter], int), counter


def test_the_report_survives_the_trip_through_json():
    """The point of the shape is that it leaves this process. A value the
    encoder refuses is a report nobody receives."""
    document = _report().as_dict()
    assert json.loads(json.dumps(document)) == document


@pytest.mark.parametrize("prio,severity", (
    ("MUST", "error"), ("SHALL", "error"), ("SHOULD", "warning"), ("MAY", "info")))
def test_a_findings_severity_and_priority_are_both_published(prio, severity):
    """Two fields, not one: the severity is this project's reading and the
    priority is the specification's word for it. A consumer that wants to
    re-derive the first from the second needs both, and dropping either
    leaves it guessing."""
    entry = Finding(_rule(prio), Violation("m")).as_dict()
    assert entry["severity"] == severity
    assert entry["priority"] == prio
