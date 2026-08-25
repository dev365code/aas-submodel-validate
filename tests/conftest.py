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
from pathlib import Path

import pytest

FIRED: set = set()
OBSERVED = Path(__file__).resolve().parents[1] / ".rule-coverage.json"


@pytest.fixture(autouse=True, scope="session")
def _observe_which_rules_fire():
    from aas_submodel_validate import runner
    original = runner.run

    def wrapped(path, **kwargs):
        report = original(path, **kwargs)
        FIRED.update(finding.id for finding in report.findings)
        return report

    runner.run = wrapped
    try:
        yield
    finally:
        runner.run = original
        OBSERVED.write_text(json.dumps(sorted(FIRED), indent=0), "utf-8")
