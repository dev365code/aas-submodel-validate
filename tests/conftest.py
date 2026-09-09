"""Suite-wide observation: which rules ever actually fire, and a refusal
to let any of them fire by crashing.

A rule that produces no finding anywhere in the whole suite has never
been observed to work -- it may be correct and merely untested; it may
be dead, and the two are indistinguishable from inside. Every report the
suite produces through runner.run is observed, and the set of rule ids
seen is written out for tools/rule_coverage.py to compare against the
committed baseline: not a target, a number that cannot move without
somebody saying so.

The same wrapper answers a second question. `runner.execute` reports a
rule that raised under that rule's own id, at that rule's own severity,
with the subject it was reading -- so `assert "HD-D9" in ids` is
satisfied by HD-D9 having stopped working, and so is a pinned list of
`(id, severity)` pairs. Measured across this suite: eighty-one places
reduce a report to identities that way, in twenty-four files. Asking at
each of them was never going to hold.

The observation below already had to know this -- it excludes a crashed
rule from the set of rules seen to fire, because `make exercised` would
otherwise pass on a rule that only ever crashes -- and the same sentence
was true of every assertion in the suite and had not been carried there.

So it is asked once, here, for every report the suite produces. Note the
difference between the two: the observation *filters* a crash out of the
fired set, because its question is which rules genuinely work. This
*fails*, because a crash is not a verdict and no test should be able to
read one as a verdict by accident. Filtering here would make a broken
rule quiet, which is the whole thing `runner.execute` turns a raise into
a finding to avoid.

A test whose subject is the crash path says so with
`@pytest.mark.allow_crash` and then asserts on the message. Measured
when this went in: no test in the suite needed it. It exists so that the
first one that does has a door rather than a wall.
"""
from __future__ import annotations

import json
import pathlib
import sys
from pathlib import Path

import pytest

# Which copy of the package the suite judges. This is a src-layout
# project, so `aas_submodel_validate` is not importable from the
# repository root: `make check` exports PYTHONPATH and anything that
# does not -- a bare `pytest`, an editor's run button -- falls through
# to whatever is installed. On a machine that has ever run `pip install
# aas-submodel-validate` that is the released version, and the suite
# then reports on code the author did not write. The failing direction
# wastes an afternoon; the passing direction is worse, because a
# contributor sees green for a change that was never executed. Putting
# the tree in front costs nothing and removes both.
_TREE = Path(__file__).resolve().parents[1]
for _entry in (_TREE / "src", _TREE / "tests"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

FIRED: set = set()
OBSERVED = Path(__file__).resolve().parents[1] / ".rule-coverage.json"


#: Whether this session saw the whole suite. A filtered run -- `-k`, a
#: single file, `-m`, `--lf` -- fires a handful of rules and would write
#: that handful out as the observation, so `make exercised` then reports
#: every other rule as dead and the next full run inherits it. One
#: `pytest -k something` used to poison the tree until somebody ran the
#: whole suite again and thought to look.
def _whole_suite(config) -> bool:
    option = config.option
    if getattr(option, "keyword", "") or getattr(option, "markexpr", ""):
        return False
    if getattr(option, "last_failed", False) or getattr(option, "failed_first", False):
        return False
    if getattr(option, "deselect", None):
        return False
    # An argument naming a file collects part of the tree and says
    # nothing about the rest; one naming a directory collects all of it
    # below there, which for this suite is the whole thing. Counting
    # arguments instead of looking at them called `pytest
    # tests/test_semantics.py` a full run and wrote out its handful.
    for argument in (config.args or []):
        if argument.startswith("-"):
            continue
        named = pathlib.Path(argument.split("::", 1)[0])
        if named.is_file():
            return False
    return True


def _record(fired) -> None:
    if _WHOLE_SUITE:
        OBSERVED.write_text(json.dumps(sorted(fired), indent=0), "utf-8")


_WHOLE_SUITE = True


def pytest_configure(config):
    global _WHOLE_SUITE
    _WHOLE_SUITE = _whole_suite(config)
    config.addinivalue_line(
        "markers",
        "allow_crash: this test's subject is a rule that could not run")


#: The test being run, and whether it said it expects a crash. Set by the
#: autouse fixture below; read by the wrapper, which has no other way to
#: know whose report it is holding.
_ALLOWS_CRASH = False


@pytest.fixture(autouse=True)
def _crashes_are_not_verdicts(request):
    global _ALLOWS_CRASH
    _ALLOWS_CRASH = request.node.get_closest_marker("allow_crash") is not None
    try:
        yield
    finally:
        _ALLOWS_CRASH = False


@pytest.fixture(autouse=True, scope="session")
def _observe_which_rules_fire():
    from aas_submodel_validate import runner
    original = runner.run

    def wrapped(path, **kwargs):
        report = original(path, **kwargs)
        # A stop in the relayed metamodel channel is not one of this
        # project's rules crashing, and `runner` models it as its own
        # thing: same message, but `RELAY_STOPPED` for a remedy, which
        # says a channel went quiet rather than that this validator is
        # defective. It is an expected outcome on inputs aas-core3.0
        # cannot process -- a year with more digits than CPython will
        # convert, a nesting depth past the interpreter's stack -- so
        # whether it happens is a property of the platform, not of the
        # file. Measured the hard way: this check went in without the
        # exclusion, `make check` was green here, and nine CI jobs went
        # red on `META could not run` because their stack gives out
        # where this machine's does not.
        crashed = sorted(finding.id for finding in report.findings
                         if finding.violation.message == runner.COULD_NOT_RUN
                         and finding.fix != runner.RELAY_STOPPED)
        assert _ALLOWS_CRASH or not crashed, (
            "%s could not run, and this test would otherwise have read that "
            "as a verdict: a crashed rule is reported under its own id, at "
            "its own severity, with the subject it was reading. If that is "
            "what this test is about, mark it `allow_crash` and assert on "
            "the message." % ", ".join(crashed))
        # A rule that raised is reported under its own id, so counting it
        # here would let `make exercised` -- whose whole job is to find
        # rules that never run -- pass on a rule that only ever crashes.
        # Measured: break one rule's body and the gate still says all 124
        # fire. It is asking about ids, and a crash brings the id with it.
        FIRED.update(finding.id for finding in report.findings
                     if finding.violation.message != runner.COULD_NOT_RUN)
        return report

    runner.run = wrapped
    try:
        yield
    finally:
        runner.run = original
        _record(FIRED)
