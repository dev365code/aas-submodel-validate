"""One broken rule must not hide the others."""
import pytest

from aas_submodel_validate.model import (
    PRIO_SEVERITY,
    Report,
    Rule,
    Severity,
    Violation,
)
from aas_submodel_validate.runner import COULD_NOT_RUN, CRASH_REMEDY, RESOURCE_REMEDY, execute


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


@pytest.mark.parametrize("exc", [MemoryError("no memory"), RecursionError("too deep")],
                         ids=["memory", "stack"])
def test_a_rule_that_runs_out_of_memory_or_stack_is_not_called_a_validator_defect(exc):
    """A rule that raises is reported, and its remedy is `CRASH_REMEDY`:
    a defect in the validator, please report it. That is true of a `KeyError`
    and false of `MemoryError` -- the input is within the size bound, but a
    parse and its checks cost a multiple of the bytes, so running out is the
    machine's limit, not a bug to file. Told to report it, an author files a
    bug about their own large-but-legal document."""
    def hungry(ctx):
        raise exc
        yield  # pragma: no cover - makes it a generator like a real rule

    (finding,) = execute([_rule("A", hungry)], ctx=None)
    assert finding.severity is Severity.ERROR
    assert finding.violation.message == COULD_NOT_RUN
    assert type(exc).__name__ in (finding.violation.detail or "")
    assert finding.fix == RESOURCE_REMEDY
    assert finding.fix != CRASH_REMEDY
    assert "defect in the validator" not in finding.fix


@pytest.mark.parametrize("prio", sorted(set(PRIO_SEVERITY) - {"MUST"}))
def test_a_rule_that_could_not_run_fails_the_run_whatever_it_asks_for(prio):
    """A crash is not a finding at the rule's own priority.

    The test above uses a MUST, whose severity is `error` anyway, so it
    could never see this: for the 23 registered rules that ask for
    anything less, a crash arrived as a warning or as info and the run
    left by 0. That is the tool reporting a clean bill for a file it
    stopped checking -- the one thing a pipeline reading nothing but the
    exit code cannot survive, and the direction the isolation exists to
    avoid. `_meta_findings` was given exactly this repair for the relayed
    channel; `execute` is four lines above it and did not get it.

    What the rule asks for is a property of the rule and stays true in
    the report: `priority` still reads SHOULD. The severity is about the
    run, not about the file.
    """
    def broken(ctx):
        raise KeyError("oops")
        yield  # pragma: no cover - makes this a generator, as rules are

    rule = Rule(id="B", kind="template", prio=prio, title="B",
                spec=None, fn=broken, fix="mend it")
    finding, = execute([rule], ctx=None)
    assert finding.violation.message == COULD_NOT_RUN
    assert finding.severity is Severity.ERROR, prio
    assert finding.as_dict()["priority"] == prio
    assert Report(path="x", findings=[finding]).ok is False
