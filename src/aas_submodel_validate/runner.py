"""Executing rules over a loaded input.

The one invariant worth a module of its own: a rule that raises becomes
a finding, not a crash. One broken rule must not hide the others — a
validator that dies on rule 3 of 40 has silently skipped 37.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from aas_core3 import verification

from . import rules  # noqa: F401  - importing registers every rule
from .loader import Loaded, load
from .model import Finding, Report, Rule, Violation
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


def _meta_rule(strict: bool) -> Rule:
    """The channel aas-core3.0's metamodel verification reports through.

    Deliberately not a registered rule: its findings are the verifier's,
    relayed -- this project re-implements no AASd/AASc constraint. Default
    severity is warning, because the *official published example* carries
    77 of these and a validator that errors on the reference material by
    default is a validator nobody runs twice; --strict-meta promotes them
    for shops that want the metamodel enforced too.
    """
    return Rule(
        id="META", kind="meta", prio="MUST" if strict else "SHOULD",
        title="the AAS metamodel, verified by aas-core3.0",
        spec="IDTA 01001 (metamodel constraints)",
        fn=lambda ctx: (),
        fix="Fix the constraint aas-core3.0 names; these are IDTA 01001 "
            "metamodel rules, upstream of any template.")


def _meta_findings(loaded: Loaded, strict: bool):
    rule = _meta_rule(strict)
    targets = [loaded.environment] if loaded.environment is not None else loaded.submodels
    for target in targets:
        for error in verification.verify(target):
            yield Finding(rule, Violation(error.cause, subject=str(error.path)))


#: Reading order: errors before warnings before notes; within a severity
#: our own channels before the relayed metamodel one, because 77 relayed
#: constraint messages must not bury the two template findings the
#: reader came for. Total down to the message, so two runs cannot differ.
_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
_KIND_ORDER = {"container": 0, "template": 1, "lint": 2, "meta": 3}


def _reading_order(finding: Finding):
    return (_SEVERITY_ORDER[str(finding.severity)],
            _KIND_ORDER.get(finding.rule.kind, 2),
            finding.id,
            finding.violation.subject or "",
            finding.violation.message)


def run(path, *, strict_meta: bool = False, allow_unmatched: bool = False) -> Report:
    """Validate one input. UnreadablePath propagates: that is the caller's
    mistake and the CLI's exit-2, not a finding about the file."""
    loaded = load(path)
    rules_to_run = all_rules()
    report = Report(path=str(path))
    report.findings = execute(rules_to_run, Context(loaded))
    report.findings.extend(_meta_findings(loaded, strict_meta))
    if allow_unmatched:
        unmatched = [f for f in report.findings if f.id == "HD-D1"]
        report.findings = [f for f in report.findings if f.id != "HD-D1"]
        for finding in unmatched:
            report.notes.append("HD-D1 (allowed): %s -- %s"
                                % (finding.violation.message,
                                   finding.violation.detail or ""))
    report.findings.sort(key=_reading_order)
    report.checked = len(rules_to_run)
    return report
