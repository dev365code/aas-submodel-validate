"""A rule built at run time crashes the way a registered one does.

`execute` is the only place in this project where a raising rule becomes
a finding instead of a traceback, and the module it lives in opens by
saying why: a validator that dies on rule 3 of 40 has silently skipped
37. Rules generated from a template a caller supplied are rules, and
they have to arrive through the same door.

Nothing routes them yet. This is the door, tested before anything is
sent through it — because the alternative is discovering on the day the
mode ships that its rules were the one kind that could take the process
down.
"""
from __future__ import annotations

import json
import pathlib
import sys

from aas_submodel_validate import runner, tablegen
from aas_submodel_validate.model import Rule, Severity

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import extract_smt_rules as tool  # noqa: E402


#: A pack shaped the way a caller's own template gets one: their file,
#: and a prefix that is not any published pack's. Built from a vendored
#: template because that is a real template to hand, not because the
#: vendored pack is what a caller passes -- using the vendored pack's
#: own prefix would give the rules ids the registry already publishes,
#: which is the collision the prefix exists to avoid.
def _a_table():
    vendored = next(p for p in tool.PACKS if p["output"].name == "td_tables.py")
    pack = dict(vendored, prefix="TPL-E",
                citation="a template you supplied")
    return tablegen.table_from(
        json.loads(vendored["template"].read_text("utf-8-sig")), pack), pack


def test_rules_from_a_run_time_table_are_rules_the_registry_never_saw():
    """They must not be registered. `docs/rule-coverage.json` is a list
    of every published id and `make exercised` compares against it, so an
    id that appears because somebody passed a file would fail a gate
    about this project's own rules. `runner._meta_rule` is the precedent:
    an unregistered `Rule` the run puts anyway."""
    from aas_submodel_validate.registry import all_rules

    table, pack = _a_table()
    built = tablegen.rules_for(table, pack)
    assert built, "no rules came out of a table with %d rows" % len(table.ROWS)
    assert len(built) == len(table.ROWS)

    registered = {rule.id for rule in all_rules()}
    overlap = sorted({rule.id for rule in built} & registered)
    assert not overlap, (
        "a run-time rule wears an id the registry already publishes: %s" % overlap)


def test_a_run_time_rule_that_raises_becomes_a_finding():
    """The property the funnel exists for, asked of a rule that was never
    registered."""
    def explode(ctx):
        raise ValueError("a rule with a bug in it")
        yield  # pragma: no cover - unreachable, and that is the point

    rule = Rule(id="TPL-E01", kind="template", prio="MUST",
                title="a run-time rule", spec="a template", fn=explode,
                fix="change the file")
    findings = runner.execute([rule], object())
    assert len(findings) == 1, findings
    assert findings[0].violation.message == runner.COULD_NOT_RUN
    assert findings[0].violation.severity is Severity.ERROR, (
        "a rule that could not run reported below error; a pipeline reading "
        "the exit code would get a clean bill for a file this tool stopped "
        "checking")
    assert "ValueError" in (findings[0].violation.detail or "")


def test_a_run_time_rule_answers_the_rows_it_was_built_from(tmp_path):
    """And it actually judges: the rules a table produces give the same
    findings the walk gives for that table, so routing them through
    `execute` is a change of door and not of answer."""
    from aas_submodel_validate.loader import load
    from aas_submodel_validate.rules import engine, profiles
    from builders import env_json

    table, pack = _a_table()
    path = tmp_path / "env.json"
    # An instance of 02003 with one mandatory element missing, so at
    # least one row has something to say.
    path.write_bytes(env_json("0173-1#01-AHX837#002"))
    ctx = runner.Context(load(path), profiles.Selection(None))

    findings = runner.execute(tablegen.rules_for(table, pack), ctx)
    crashed = [f for f in findings if f.violation.message == runner.COULD_NOT_RUN]
    assert not crashed, "a run-time rule could not run: %s" % [
        f.violation.detail for f in crashed]

    walked = engine.analyze(ctx, table)["violations"]
    assert sum(len(v) for v in walked.values()) == len(findings), (
        "the rules reported %d findings and the walk found %d"
        % (len(findings), sum(len(v) for v in walked.values())))
