"""Suite-wide observation: which rules ever actually fire.

A rule that produces no finding anywhere in the whole suite has never
been observed to work -- it may be correct and merely untested; it may
be dead, and the two are indistinguishable from inside. Every report the
suite produces through runner.run is observed, and the set of rule ids
seen is written out for tools/rule_coverage.py to compare against the
committed baseline: not a target, a number that cannot move without
somebody saying so.
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


@pytest.fixture(autouse=True, scope="session")
def _observe_which_rules_fire():
    from aas_submodel_validate import runner
    original = runner.run

    def wrapped(path, **kwargs):
        report = original(path, **kwargs)
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
