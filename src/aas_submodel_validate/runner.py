"""Executing rules over a loaded input.

The one invariant worth a module of its own: a rule that raises becomes
a finding, not a crash. One broken rule must not hide the others — a
validator that dies on rule 3 of 40 has silently skipped 37.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from . import rules  # noqa: F401  - importing registers every rule
from .loader import Loaded, load
from .model import Finding, Report, Violation
from .registry import all_rules


def execute(rules_to_run, ctx) -> List[Finding]:
    findings: List[Finding] = []
    for rule in rules_to_run:
        try:
            findings.extend(Finding(rule, violation) for violation in rule.fn(ctx))
        except Exception as exc:  # noqa: BLE001 - the isolation is the point
            findings.append(Finding(rule, Violation(
                "the rule itself could not run",
                detail="%s: %s" % (type(exc).__name__, exc),
                fix="This is a defect in the validator, not in your file; "
                    "please report it.")))
    return findings


@dataclass
class Context:
    """Everything a rule is handed."""

    loaded: Loaded


def run(path) -> Report:
    """Validate one input. UnreadablePath propagates: that is the caller's
    mistake and the CLI's exit-2, not a finding about the file."""
    loaded = load(path)
    rules_to_run = all_rules()
    report = Report(path=str(path))
    report.findings = execute(rules_to_run, Context(loaded))
    report.checked = len(rules_to_run)
    return report
