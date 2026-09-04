"""Executing rules over a loaded input.

The one invariant worth a module of its own: a rule that raises becomes
a finding, not a crash. One broken rule must not hide the others — a
validator that dies on rule 3 of 40 has silently skipped 37.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from aas_core3 import verification

from . import (
    container,
    rules,  # noqa: F401  - importing registers every rule
)
from .loader import Loaded, load
from .model import KINDS, Finding, Report, Rule, Violation
from .registry import all_rules
from .rules import detect

#: What a rule that raised is reported as. Named rather than written
#: twice, because the coverage collector has to tell this apart from the
#: rule working: a crash arrives as a finding under the rule's own id, so
#: counting it as a firing lets `make exercised` -- the gate that exists
#: to find rules which never run -- pass on a rule that only ever crashes.
COULD_NOT_RUN = "the rule itself could not run"

#: Two sentences this module ships that no rule owns, named so the remedy
#: census can hold them. Both were unpinned: rewriting the first to blame
#: the author for a crash in this validator, and the second to say the
#: metamodel's own constraints may be ignored, left every gate green.
CRASH_REMEDY = ("This is a defect in the validator, not in your file; "
                "please report it.")
META_REMEDY = ("Fix the constraint aas-core3.0 names; these are IDTA 01001 "
               "metamodel rules, upstream of any template.")



def execute(rules_to_run, ctx) -> List[Finding]:
    findings: List[Finding] = []
    for rule in rules_to_run:
        try:
            findings.extend(Finding(rule, violation) for violation in rule.fn(ctx))
        except Exception as exc:  # noqa: BLE001 - the isolation is the point
            findings.append(Finding(rule, Violation(
                COULD_NOT_RUN,
                detail="%s: %s" % (type(exc).__name__, exc),
                fix=CRASH_REMEDY)))
    return findings


@dataclass
class Context:
    """Everything a rule is handed."""

    loaded: Loaded
    #: Which of two templates answers, where two publish one submodel
    #: identifier. No default: a context that guessed would hand the walk
    #: a table nobody chose, which is the mistake `rules/engine.py`'s
    #: table argument was stripped of its own default to prevent.
    selection: object


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
        fix=META_REMEDY)


def _meta_findings(loaded: Loaded, strict: bool):
    rule = _meta_rule(strict)
    targets = [loaded.environment] if loaded.environment is not None else loaded.submodels
    for target in targets:
        for error in verification.verify(target):
            yield Finding(rule, Violation(error.cause, subject=str(error.path)))


#: Reading order: errors before warnings before notes; within a severity
#: our own channels before the relayed metamodel one, because 77 relayed
#: constraint messages must not bury the template findings the
#: reader came for. Total down to the message, so two runs cannot differ.
#: Derived from `model.KINDS`, not restated: this was a second copy, and
#: a kind missing from it sorted as if it were a lint -- into the middle
#: of the reader's own channels rather than after them. Registration
#: refuses a kind outside the vocabulary, so the fallback below is
#: unreachable for a registered rule; it stays for the ones this project
#: builds by hand, and it sends what it does not recognise to the end.
_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
_KIND_ORDER = {kind: position for position, kind in enumerate(KINDS)}


def _reading_order(finding: Finding):
    return (_SEVERITY_ORDER[str(finding.severity)],
            _KIND_ORDER.get(finding.rule.kind, len(KINDS)),
            finding.id,
            finding.violation.subject or "",
            finding.violation.message)


#: Small on purpose: the peak cost of hashing is one block, and this
#: reader's promise is about what it takes into memory, not about what
#: it declines to look at.
_DIGEST_BLOCK = 64 * 1024


def _digest(path, limit: int) -> str:
    """The sha256 of the file as it arrived, or None.

    None in three cases, and each is a refusal to answer rather than a
    partial answer. The file cannot be opened -- the loader has already
    decided what that is, and a digest must not be a second, louder
    answer to the same question. Or it is larger than this reader takes
    in at all, in which case nothing was judged and a digest of bytes
    nobody read is evidence of nothing. Or it grew past the bound while
    being read, which is the same case arriving later.

    Streamed in small blocks, so the peak is one block whatever the file
    weighs -- a digest is not a reason to take in what the rest of the
    reader refuses, and the first version read a megabyte at a time and
    was caught by the fixture that weighs a run.
    """
    import hashlib
    digest = hashlib.sha256()
    read = 0
    try:
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(_DIGEST_BLOCK), b""):
                read += len(block)
                if read > limit:
                    return None
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()


def run(path, *, strict_meta: bool = False, allow_unmatched: bool = False,
        profile: str = None) -> Report:
    """Validate one input. UnreadablePath propagates: that is the caller's
    mistake and the CLI's exit-2, not a finding about the file."""
    loaded = load(path)
    rules_to_run = all_rules()
    # The same bound the reader itself applies to a bare document. A
    # container may deliver more in total, and a container this reader
    # accepted is one whose own bounds already held.
    report = Report(path=str(path),
                    input_sha256=_digest(path, container.MAX_TOTAL_PART_BYTES))
    report.findings = execute(rules_to_run,
                              Context(loaded, rules.profiles.Selection(profile)))
    report.findings.extend(_meta_findings(loaded, strict_meta))
    if allow_unmatched:
        unmatched = [f for f in report.findings if f.id == detect.RULE_ID]
        report.findings = [f for f in report.findings if f.id != detect.RULE_ID]
        for finding in unmatched:
            report.notes.append("%s (allowed): %s -- %s"
                                % (detect.RULE_ID, finding.violation.message,
                                   finding.violation.detail or ""))
    # Only for a key that chooses a table. One that merely settles a
    # collision chose nothing by design, and telling its user the flag
    # did nothing contradicts the finding it just silenced.
    if profile in rules.profiles.KEYS and not any(
            rules.profiles.PROFILES and Context(loaded, selection).selection.chosen(submodel)
            for submodel in loaded.submodels
            for selection in (rules.profiles.Selection(profile),)):
        report.notes.append(
            "--profile %s named a template no submodel here answers to, so it "
            "chose nothing; the verdict is the one you would have got without it"
            % profile)
    # What the battery pack could look at in this run, computed from its
    # table rather than quoted from a document, and marked as the floor
    # it is. A note and not a finding: it reports the reach of a check,
    # not a defect in the file.
    coverage = rules.battery.coverage_note(loaded.submodels)
    if coverage is not None:
        report.notes.append(coverage)
    report.findings.sort(key=_reading_order)
    report.checked = len(rules_to_run)
    # Every load error means content that was not read: an archive that
    # would not open, a chain that went nowhere, a part that would not
    # parse, a document over the bound. What was not read was not judged,
    # and the report is the only place that can say so.
    report.complete = not loaded.errors
    report.judged = not loaded.nothing_was_judged
    # What was asked, recorded beside what was found: the flags move the
    # verdict, so a document that does not carry them cannot be compared
    # with another.
    report.profile = profile
    report.strict_meta = strict_meta
    report.allow_unmatched = allow_unmatched
    return report
