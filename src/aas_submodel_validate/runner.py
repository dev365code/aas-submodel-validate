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
from .model import KINDS, META_KIND, Finding, Report, Rule, Severity, Violation
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
#: When the relayed channel itself stops. Not `CRASH_REMEDY`: that
#: sentence says the defect is the validator's, and this one need not
#: be -- aas-core3 may have met something in the file its own code
#: cannot process, such as a year with more digits than CPython will
#: convert. What the reader needs to know is that a channel went
#: quiet, so the report is short of an answer rather than carrying a
#: wrong one.
#:
#: It names no cause, and that is the repair. `except Exception` here
#: catches every way the call can end -- a defect in this project that
#: surfaces inside it, a `MemoryError`, an upstream defect that has
#: nothing to do with the file -- and the sentence said "stopped on this
#: input" about all of them, which blames the author for two of the
#: three. It also told the reader to look at "the value it names", and
#: on an Environment there is no value to name: the subject below is
#: `None` for every input that holds one, so the one condition under
#: which they were asked to file a report could never be evaluated.
RELAY_STOPPED = ("The metamodel channel stopped, so this report does not "
                 "say whether the metamodel is satisfied; the rest of the "
                 "verdict stands. What stopped it is recorded beside this "
                 "finding -- please report that, whether the cause turns "
                 "out to be this file, this tool, or the library whose "
                 "answers it relays.")

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
            # At `error`, whatever the rule asks for. For the 23
            # registered rules below MUST this arrived as a warning or
            # as info and the run left by 0 -- a clean bill for a file
            # this tool stopped checking, which is the one thing a
            # pipeline reading only the exit code cannot survive. The
            # relayed channel was given this repair; `execute` sits four
            # lines above it and was not.
            findings.append(Finding(rule, Violation(
                COULD_NOT_RUN,
                detail="%s: %s" % (type(exc).__name__, exc),
                fix=CRASH_REMEDY,
                severity=Severity.ERROR)))
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
        id="META", kind=META_KIND, prio=META_PRIO[_meta_level(strict)],
        title="the AAS metamodel, verified by aas-core3.0",
        spec="IDTA 01001 (metamodel constraints)",
        fn=lambda ctx: (),
        fix=META_REMEDY)


#: The three settings of the one dial, as the priorities that decide a
#: severity. A channel with two flags deciding it is what made `-W`
#: unusable; answering that with a third would have been the same
#: mistake, so `--strict-meta` is the older spelling of `error` rather
#: than a second control.
META_PRIO = {"error": "MUST", "warning": "SHOULD", "info": "MAY"}


def _meta_level(strict) -> str:
    """`--meta`'s level, from either spelling.

    `True`/`False` are what `--strict-meta` and 0.1.0's callers pass; a
    string is what `--meta` passes.
    """
    if isinstance(strict, str):
        if strict not in META_PRIO:
            raise ValueError("no such meta level: %r" % strict)
        return strict
    return "error" if strict else "warning"


def _meta_findings(loaded: Loaded, strict):
    rule = _meta_rule(strict)
    # Every environment the input held, or the bare submodels when it
    # held none. One slot used to hold "the" environment and an AASX may
    # declare several aas-spec parts, so all but the last went
    # unverified -- silently, since the walk had already seen their
    # submodels and the report called itself complete.
    targets = loaded.environments or loaded.submodels
    for target in targets:
        # Isolated like every other rule. "A rule that raises becomes a
        # finding, not a crash -- one broken rule must not hide the
        # others" is written down as a non-negotiable, and the one
        # channel this reader does not own was the one channel it was
        # not applied to. A date whose year runs past CPython's 4,300
        # digit limit for `int()` made aas-core3 raise inside
        # `verify()`, and the exception left through `main`: traceback,
        # no report, and exit 1 -- which is the code for a verdict with
        # findings, about a file nothing finished reading.
        try:
            for error in verification.verify(target):
                yield Finding(rule, Violation(error.cause,
                                              subject=str(error.path)))
        except Exception as exc:                     # noqa: BLE001
            # The remedy `execute()` gives a rule that dies, because
            # this is the same event: a defect in the validator, and
            # telling the reader to fix the constraint aas-core3.0
            # names is telling them to fix their file for our bug.
            #
            # And reported at the severity of a channel that could not
            # run, not at the level `--meta` sets. That dial is for the
            # constraint findings the channel relays; without this the
            # crash arrived as a folded warning and the run left by 0 --
            # quietly wrong, where the unisolated version had at least
            # been loudly wrong.
            yield Finding(_meta_rule("error"), Violation(
                COULD_NOT_RUN,
                # A bare submodel has an id and an Environment has not,
                # so this names the target where there is a name and
                # stays quiet where there is none. The remedy no longer
                # promises the reader a name, which is what made the
                # quiet case a broken instruction rather than a blank.
                subject=getattr(target, "id", None),
                detail="%s: %s" % (type(exc).__name__, exc),
                fix=RELAY_STOPPED))


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
            # Every submodel, not the instances. This note says whether
            # the flag chose anything at all, and a template answers to
            # a template's identifier -- narrowing it made the note say
            # the flag chose nothing while the note beside it said why
            # the thing it chose was set aside. Two notes denying each
            # other in one report.
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
    coverage = rules.battery.coverage_note(detect.instances(loaded))
    if coverage is not None:
        report.notes.append(coverage)
    # How much of the input a template answered for. Counted from the
    # same helper the presence rule uses, so the number and the finding
    # cannot disagree about what "judged" means.
    templates = detect.templates(loaded)
    if templates:
        named = ", ".join(sorted(
            str(getattr(submodel, "id_short", None)
                or getattr(submodel, "id", None) or "(unnamed)")
            for submodel in templates))
        report.notes.append(
            "%d submodel%s in this input %s declared kind Template (%s). A "
            "template is a specification and not an instance, and every "
            "rule here is a requirement on an instance, so %s not judged."
            % (len(templates), "" if len(templates) == 1 else "s",
               "is" if len(templates) == 1 else "are", named,
               "it was" if len(templates) == 1 else "they were"))
    # `submodels_seen` is what the input holds, which is what the schema
    # says it is. Taking the templates out of it made that sentence
    # false -- a file with two submodels reported zero -- and hid the
    # thing the note exists to say. They are counted on their own, and
    # `--require-all-judged` is what subtracts them, because that flag
    # is about coverage a caller can do something about and nothing
    # turns a specification into an instance.
    report.submodels_seen = len(loaded.submodels)
    report.submodels_specified = len(templates)
    report.submodels_judged = len({id(submodel) for _pack, submodel
                                   in detect.matched(Context(loaded, rules.profiles.Selection(profile)))})
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
    report.meta = _meta_level(strict_meta)
    report.allow_unmatched = allow_unmatched
    return report
