"""Things about the suite itself that no single test can say.

The subject here is every other file: a rule that raises is reported
under its own id, at its own severity, with the subject it was reading,
so an assertion that a rule fired is satisfied by that rule having
stopped working. Eighty-one places in twenty-four files reduce a report
to identities that way. `conftest.py` refuses it once, for every report
the suite produces, and these tests are what keep that refusal real.

They inject the crash rather than reading `conftest.py` for the string
that would catch it. A gate asserted by grep passes on a gate that has
become a no-op, which is worse than no gate because it reads as covered.
"""
from __future__ import annotations

import copy
import dataclasses
import json

import pytest

from aas_submodel_validate import registry, runner
from builders import hd_env


def _write(tmp_path, env):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return path


def _break(monkeypatch, rule_id: str, only_when=None):
    """Make `rule_id` raise -- always, or only on the inputs `only_when`
    picks out, which is the shape that hides."""
    rule = registry._registry[rule_id]
    original = rule.fn

    def explode(ctx):
        if only_when is None or only_when(ctx):
            raise RuntimeError("injected by %s" % __name__)
        yield from original(ctx)

    monkeypatch.setitem(registry._registry, rule_id,
                        dataclasses.replace(rule, fn=explode))


def test_a_rule_that_crashes_cannot_be_read_as_a_verdict(tmp_path, monkeypatch):
    """The report comes back holding `HD-D3` at error, exactly as a real
    finding would, and the only thing separating them is a message no
    caller was reading. So the suite stops here instead.
    """
    _break(monkeypatch, "HD-D3")
    with pytest.raises(AssertionError, match="could not run"):
        runner.run(_write(tmp_path, hd_env()))


def test_the_refusal_survives_a_rule_that_only_breaks_sometimes(
        tmp_path, monkeypatch):
    """The one that matters, and the one that got past everything.

    A rule that raises on every input fails a great many tests at once
    and is found in minutes. A rule that raises only on the shape one
    test constructs fails nothing, because that test asks whether the id
    is present and it is. Measured before this existed: folding a value
    unconditionally instead of only when it is a string made `HDL4` raise
    on a `DocumentId` naming half a pair, and the test written for
    exactly that walk stayed green.

    Here the rule is broken only for a file carrying two documents, so a
    suite-wide count would not notice.
    """
    def two_documents(ctx):
        for submodel in ctx.loaded.submodels:
            for element in submodel.submodel_elements or []:
                if len(getattr(element, "value", None) or []) > 1:
                    return True
        return False

    _break(monkeypatch, "HDL4", only_when=two_documents)

    #: One document: the rule runs, and nothing here is disturbed.
    runner.run(_write(tmp_path, hd_env()))

    env = copy.deepcopy(hd_env())
    documents = env["submodels"][0]["submodelElements"][0]["value"]
    documents.append(copy.deepcopy(documents[0]))
    with pytest.raises(AssertionError, match="could not run"):
        runner.run(_write(tmp_path, env))


@pytest.mark.allow_crash
def test_the_door_out_of_that_refusal_opens(tmp_path, monkeypatch):
    """A test whose subject *is* the crash path has to be able to hold
    one. The marker is that door, and it is asserted here because it had
    no user when it was written -- an untried door is a wall nobody has
    walked into yet.
    """
    _break(monkeypatch, "HD-D3")
    report = runner.run(_write(tmp_path, hd_env()))
    crashed = [finding for finding in report.findings
               if finding.violation.message == runner.COULD_NOT_RUN]
    assert [finding.id for finding in crashed] == ["HD-D3"]
    assert "defect in the validator" in (crashed[0].fix or "")
