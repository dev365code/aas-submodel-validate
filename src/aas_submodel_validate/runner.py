"""Executing rules over a loaded input.

The one invariant worth a module of its own: a rule that raises becomes
a finding, not a crash. One broken rule must not hide the others — a
validator that dies on rule 3 of 40 has silently skipped 37.
"""
from __future__ import annotations

from typing import List

from .model import Finding, Violation


def execute(rules, ctx) -> List[Finding]:
    findings: List[Finding] = []
    for rule in rules:
        try:
            findings.extend(Finding(rule, violation) for violation in rule.fn(ctx))
        except Exception as exc:  # noqa: BLE001 - the isolation is the point
            findings.append(Finding(rule, Violation(
                "the rule itself could not run",
                detail="%s: %s" % (type(exc).__name__, exc),
                fix="This is a defect in the validator, not in your file; "
                    "please report it.")))
    return findings
