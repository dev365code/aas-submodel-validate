"""One broken rule must not hide the others."""
from aas_submodel_validate.model import Rule, Severity, Violation
from aas_submodel_validate.runner import COULD_NOT_RUN, execute


def _rule(rule_id, fn):
    return Rule(id=rule_id, kind="template", prio="MUST", title=rule_id,
                spec=None, fn=fn, fix="mend it")


def test_a_rule_that_raises_becomes_a_finding_not_a_crash():
    def healthy(ctx):
        yield Violation("a real finding")

    def broken(ctx):
        raise KeyError("oops")

    findings = execute([_rule("A", healthy), _rule("B", broken)], ctx=None)
    assert [f.id for f in findings] == ["A", "B"]
    crash = findings[1]
    assert crash.severity is Severity.ERROR
    assert "KeyError" in (crash.violation.detail or "")
    # The exact sentence, not a substring of it: the coverage
    # collector filters on this string, and a near-match there
    # silently counts a crash as the rule working.
    assert crash.violation.message == COULD_NOT_RUN
