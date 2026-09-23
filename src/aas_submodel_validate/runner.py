"""Executing rules over a loaded input.

The one invariant worth a module of its own: a rule that raises becomes
a finding, not a crash. One broken rule must not hide the others — a
validator that dies on rule 3 of 40 has silently skipped 37.
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import List

from aas_core3 import verification

from . import (
    container,
    rules,  # noqa: F401  - importing registers every rule
    tablegen,
)
from .loader import Loaded, LoadError, UnreadablePath, load
from .model import KINDS, META_KIND, Finding, Report, Rule, Severity, Violation
from .registry import all_rules
from .rules import detect
from .semantics import submodel_declares

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
#: What running out of memory or stack while a rule walks the document
#: gets, instead of `CRASH_REMEDY`. `CRASH_REMEDY` says the validator has a
#: bug to report, and that is true of a rule that raised on unexpected data
#: and false here: the input is within the size bound, but building and
#: checking a document costs a multiple of the bytes it holds (SECURITY.md
#: says the bound does not cover that), so running out is the machine's
#: limit, not a defect in the file or one to file against this tool. Told
#: to report it, an author files a bug about their own large-but-legal
#: document.
RESOURCE_REMEDY = ("This reader ran out of the memory or stack a rule's walk "
                   "of this document needed. The input is within the size "
                   "bound, but building and checking a document costs a "
                   "multiple of the bytes it holds -- so this is a limit of "
                   "the machine it ran on, not a defect in your file or in "
                   "this tool. Nothing here is a verdict on the document.")
META_REMEDY = ("Fix the constraint aas-core3.0 names; these are IDTA 01001 "
               "metamodel rules, upstream of any template.")



def execute(rules_to_run, ctx) -> List[Finding]:
    findings: List[Finding] = []
    for rule in rules_to_run:
        try:
            findings.extend(Finding(rule, violation) for violation in rule.fn(ctx))
        except (MemoryError, RecursionError) as exc:
            # Running out of memory or stack is not a rule with a bug; it is
            # the machine's limit, met on a document within the size bound
            # whose parse and checks cost a multiple of it. `CRASH_REMEDY`
            # would send the author to file a bug about their own file.
            findings.append(Finding(rule, Violation(
                COULD_NOT_RUN,
                detail="%s: %s" % (type(exc).__name__, exc),
                fix=RESOURCE_REMEDY,
                severity=Severity.ERROR)))
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
    #: Tables the caller supplied, carried here so that everything asking
    #: "was this submodel judged" asks one place. `submodels_judged` was
    #: handed them and `SMT-D1` was not, so a submodel judged against a
    #: caller's template drew "no submodel declares a semanticId this
    #: tool has a template table for" beside a finding about that very
    #: submodel and a summary reading `judged 1 of 1` -- three statements
    #: denying each other, and the remedy telling the author to relabel a
    #: correct document. `detect.judged` records repairing exactly this
    #: once, for the battery pack.
    supplied: tuple = ()
    #: Submodel identifiers a table the caller supplied answers for. The
    #: packs stand down for these. Two tables for one identifier is one
    #: defect reported twice -- measured: handing `--template` the file
    #: 02003's own pack was generated from gave two errors where the pack
    #: alone gives one, the same missing element under two ids. The
    #: caller asked for their template by name, so theirs answers.
    taken_over: frozenset = frozenset()


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
        # No route. The subject is the upstream reader's own expression
        # -- `.concept_descriptions[10]`, `.asset_administration_shells[0]
        # .id_short` -- and it names things no route here spells: a shell,
        # a concept description, an attribute. `kind` is `meta` on every
        # one of them, and that, not this, is what tells the spelling apart.
        # No grade either: what repairing one takes is decided by the
        # constraint that was broken, and this rule relays hundreds of
        # them without reading any.
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
            named = getattr(target, "id", None)
            yield Finding(_meta_rule("error"), Violation(
                COULD_NOT_RUN,
                # A bare submodel has an id and an Environment has not,
                # so this names the target where there is a name and
                # stays quiet where there is none. The remedy no longer
                # promises the reader a name, which is what made the
                # quiet case a broken instruction rather than a blank.
                subject=named,
                # This reader's own words, not the upstream expression,
                # so it can say what it named: the submodel, by its id.
                path=("document", "submodel") if named is not None else None,
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

    None in four cases, and each is a refusal to answer rather than a
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

    Or it is not a regular file. "The loader has already decided" was
    true of what the answer should be and not of whether asking was safe:
    the loader refuses a FIFO as "not a file" without opening it, and this
    opened it anyway -- and opening a FIFO with no writer blocks until one
    arrives. Measured: `smtv pipe.json` never returned, sitting in the
    `open` below, which made a named pipe the one unreadable shape where
    "could not run" does not arrive at all. A directory and a missing path
    were already covered, by `IsADirectoryError` and `FileNotFoundError`
    under the `OSError` here; a pipe raises nothing, which is why it needs
    asking. It is asked of the descriptor rather than of the name, because
    `is_file()` then `open()` is a sample and a use with a gap between
    them -- the first spelling of this fix did that, and the hang stayed
    reachable.
    """
    import hashlib
    digest = hashlib.sha256()
    read = 0
    try:
        with container.open_regular(path) as handle:
            for block in iter(lambda: handle.read(_DIGEST_BLOCK), b""):
                read += len(block)
                if read > limit:
                    return None
                digest.update(block)
    except (OSError, MemoryError):
        # MemoryError too. A digest is never the reason a run dies -- the
        # whole point of this function is that it declines to answer
        # rather than answering partly -- and the loader's own read has
        # caught it since a hostile file walked out of there as a
        # traceback. The two were reached by different names until the
        # descriptor check made them one call, and this one had never
        # met it.
        return None
    return digest.hexdigest()


#: How many places a note names before it stops and says so. The count a
#: note carries is never bounded; this is about what a reader can read.
NAMED_IN_A_NOTE = 3


def _supplied_table(template):
    """The table a caller's own template describes, or a refusal.

    Bounded before it is parsed. A template is not covered by the bound
    on the document being judged -- they are different files -- and 46
    MiB of template sits comfortably inside the 64 MiB this reader
    advertises, which is why the row count is bounded separately in
    `tablegen`.
    """
    import hashlib
    import json

    path = pathlib.Path(template)
    try:
        with container.open_regular(path) as handle:
            raw = handle.read(container.MAX_PART_BYTES + 1)
    except OSError as exc:
        raise tablegen.TemplateRefused("cannot read %s: %s" % (path, exc)) from exc
    if len(raw) > container.MAX_PART_BYTES:
        raise tablegen.TemplateRefused(
            "%s is above the %d byte limit this reader takes in"
            % (path, container.MAX_PART_BYTES))
    try:
        document = json.loads(raw.decode("utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise tablegen.TemplateRefused(
            "%s is not JSON this reader can read: %s" % (path, exc)) from exc
    except (RecursionError, MemoryError) as exc:
        # Not a defect in the file. `loader.py` classifies this on the
        # sibling path and says why; this reader reached one of the two,
        # so a template three thousand collections deep came out as a
        # traceback at exit 1 -- the code for a verdict with findings,
        # about a file nothing finished reading.
        raise tablegen.TemplateRefused(
            "%s is nested more deeply than this reader can follow (%s); the "
            "file may be fine and this machine could not walk it"
            % (path, type(exc).__name__)) from exc
    except ValueError as exc:
        # A bare `ValueError` from `json` is not always malformed JSON:
        # an integer past the interpreter's digit limit raises one, and
        # calling that "not JSON this reader can read" tells a caller
        # their file is broken when it is not.
        if type(exc) is ValueError:
            raise tablegen.TemplateRefused(
                "%s met a limit of this interpreter while being read: %s"
                % (path, exc)) from exc
        raise tablegen.TemplateRefused(
            "%s is not JSON this reader can read: %s" % (path, exc)) from exc

    # The same open-content markers the generator reads. Empty here, this
    # built a rule for every placeholder the template declares and then
    # faulted the manufacturer's own element that sits under it
    # (`docs/divergences.md` #19 names that outcome in advance).
    pack = {"prefix": "TPL-E", "citation": "a template you supplied",
            "skip_sids": tablegen.OPEN_CONTENT_MARKERS,
            "item_names": {}, "example_types": ()}
    digest = hashlib.sha256(raw).hexdigest()
    try:
        # The reading, not only the parsing. The first repair wrapped
        # `json.loads` and left the three calls after it, so JSON that
        # parses and is not shaped like a template took the process down:
        # fourteen of sixteen malformed shapes left as a traceback at
        # exit 1, which is the code for a verdict about a file nothing
        # finished reading.
        #
        # The name comes from the digest already computed above. It used
        # to be a second serialisation of the whole document, which cost
        # a full pass for nothing and could exhaust the stack one level
        # shallower than the parse -- so the repair held on one side of a
        # one-level boundary and not the other.
        table = tablegen.table_from(document, pack,
                                    name="<template %s>" % digest[:16])
    except tablegen.TemplateRefused:
        raise
    except (RecursionError, MemoryError) as exc:
        raise tablegen.TemplateRefused(
            "%s is nested more deeply than this reader can follow (%s); the "
            "file may be fine and this machine could not walk it"
            % (path, type(exc).__name__)) from exc
    except (KeyError, TypeError, AttributeError, IndexError, ValueError) as exc:
        raise tablegen.TemplateRefused(
            "%s parses as JSON and is not shaped like an IDTA template: "
            "%s: %s" % (path, type(exc).__name__, exc)) from exc
    # How many the file held, not how many were read. `build` takes the
    # first submodel and there is no way for a reader to tell "your
    # other templates matched nothing" from "your other templates were
    # never opened" -- and those ask opposite things of them.
    #
    # Read without a guard, because `build` has already refused anything
    # this could fail on: a document that is not a dict, or one whose
    # `submodels` is missing or empty, leaves as a `TemplateRefused`
    # above. A guard here would be a second answer to a question already
    # settled, and the branch under it could not be entered -- which is
    # the shape a dead `except` clause in `cli` was just removed for.
    declared = len(document["submodels"])
    return {"table": table, "pack": pack, "sha256": digest,
            "declared": declared}


def run(path, *, strict_meta: bool = False, allow_unmatched: bool = False,
        profile: str = None, template=None) -> Report:
    """Validate one input.

    A path this reader cannot open comes back as a report rather than as
    an exception. It used to propagate -- "the caller's mistake and the
    CLI's exit-2, not a finding about the file" -- which is a defensible
    reading and was not what happened: the same permission denial reached
    an `.aasx` through the container reader and became an `X1` finding
    with a JSON document behind it, while `.json` and `.xml` reached this
    function and raised. One contract instead, since a consumer that
    parses stdout should not have to know which extension it sent.
    """
    try:
        loaded = load(path)
    except UnreadablePath as exc:
        loaded = Loaded(path=str(path), form="unopened")
        loaded.errors.append(LoadError("access", str(exc), subject=str(path),
                                       fix=getattr(exc, "fix", None)))
    rules_to_run = all_rules()
    # The same bound the reader itself applies to a bare document. A
    # container may deliver more in total, and a container this reader
    # accepted is one whose own bounds already held.
    report = Report(path=str(path),
                    input_sha256=_digest(path, container.MAX_TOTAL_PART_BYTES))
    supplied = None
    if template is not None:
        supplied = _supplied_table(template)
        rules_to_run = list(rules_to_run) + tablegen.rules_for(
            supplied["table"], supplied["pack"])
        report.template = {"sha256": supplied["sha256"],
                           "path": str(template),
                           # Said plainly, because a verdict against a
                           # file the caller brought is not a verdict
                           # against a published template and a reader
                           # who cannot tell them apart has been told
                           # something untrue.
                           "published": False,
                           "semanticId": supplied["table"].TEMPLATE_SEMANTIC_ID,
                           "rows": len(supplied["table"].ROWS),
                           # How many the file held, which `rows` and
                           # `semanticId` cannot say: both describe the
                           # one submodel the table came from and read
                           # the same whether the file held one or five.
                           # The note beside it says so in a sentence,
                           # and a sentence is not something a consumer
                           # should have to match on.
                           "submodels": supplied["declared"]}
        # A table with no rows in it. `--require-all-judged` counts
        # submodels and this one was judged, so a template whose every
        # element is open content -- or which identifies none of them --
        # came back `ok` at exit 0 having asked nothing at all, with the
        # count only in `provenance.template.rows` where a person
        # reading the screen never sees it.
        if not supplied["table"].ROWS:
            report.notes.append(
                "the template you supplied states no rule this reader can "
                "check: every element it declares is open content or "
                "carries no semanticId. Nothing in your file was compared "
                "against it, and a pass here says only that.")
        # An element the template asks for and identifies with nothing.
        # Matching here is by identifier and never by idShort, so
        # outside a list -- where a sole item row is matched by kind --
        # no element can answer such a row. Stated rather than enforced:
        # as an obligation it was an error no file could clear, and the
        # remedy it printed ended "with semanticId " and nothing.
        unidentified = [row["label"] for row in supplied["table"].ROWS
                        if row.get("unidentified")]
        if unidentified:
            named = unidentified[:NAMED_IN_A_NOTE]
            report.notes.append(
                "the template you supplied describes %d element%s it gives "
                "no semanticId (%s). Elements are matched by identifier "
                "here and never by idShort, so nothing in your file can "
                "answer for %s and this run did not ask. Give %s a "
                "semanticId in the template and %s become%s a rule."
                % (len(unidentified), "" if len(unidentified) == 1 else "s",
                   ", ".join(named)
                   + ("" if len(named) == len(unidentified) else ", and more"),
                   "it" if len(unidentified) == 1 else "them",
                   "it" if len(unidentified) == 1 else "each of them",
                   "it" if len(unidentified) == 1 else "they",
                   "s" if len(unidentified) == 1 else ""))
        # A copy of an element inside itself the template makes mandatory:
        # every copy would need a copy of its own, and no finite file has
        # that many. Judged as optional, and said.
        endless = [row["label"] for row in supplied["table"].ROWS if row.get("endless")]
        if endless:
            report.notes.append(
                "the template you supplied makes a copy of an element inside "
                "itself mandatory (%s): every copy would need a copy of its "
                "own, which no finite file has, so this run judges %s as "
                "optional." % (", ".join(endless[:NAMED_IN_A_NOTE])
                               + ("" if len(endless) <= NAMED_IN_A_NOTE else ", and more"),
                               "it" if len(endless) == 1 else "them"))
        # A qualifier of the caller's this reader could not read. Said
        # once, in a note, and nothing about the file changes: the value
        # feeds one `info` rule whose own remedy calls it tidiness
        # rather than conformance, and a run-time table registers no
        # lints, so under this flag nothing reads it at all. Refusing
        # the template over it threw away every verdict on the file --
        # including the errors it had -- over a suggestion.
        unreadable = [(row["label"], row["allowed_idshort_unreadable"])
                      for row in supplied["table"].ROWS
                      if "allowed_idshort_unreadable" in row]
        if unreadable:
            named = unreadable[:NAMED_IN_A_NOTE]
            report.notes.append(
                "the template you supplied states an AllowedIdShort this "
                "reader cannot read on %d of its rows (%s). IDTA's spelling "
                "is `Name[\\d{2,3}]`, lower bound first. Nothing else about "
                "the verdict changes: that qualifier is a naming "
                "suggestion, and a table built from your file reports none."
                % (len(unreadable),
                   ", ".join(
                       "%s: `%s`" % (label, value) if isinstance(value, str)
                       # A qualifier of this type carrying no string is
                       # a legal file -- `Qualifier.value` is optional --
                       # and quoting `None` back would send the caller
                       # looking for that word in their template.
                       else "%s: no value" % label
                       for label, value in named)
                   + ("" if len(named) == len(unreadable) else ", and more")))
    # Held rather than discarded: the walk's own record of which rows it
    # considered lives on the context, and `not_asked` is the difference
    # between that and the tables. Built inline before, so the one thing
    # that knows what the run failed to ask was thrown away at the end of
    # the expression that produced the findings.
    tables = () if supplied is None else (supplied["table"],)
    ctx = Context(loaded, rules.profiles.Selection(profile),
                  supplied=tables,
                  taken_over=frozenset(t.TEMPLATE_SEMANTIC_ID for t in tables))
    report.findings = execute(rules_to_run, ctx)
    report.not_asked = rules.engine.rows_not_reached(ctx)
    report.unmatched = rules.engine.unmatched_elements(ctx)
    report.not_examined = rules.engine.scope_not_examined(ctx)
    # The reach of the check, the way the battery coverage note reports
    # one: a note and not a finding, because nothing here says the file
    # is wrong -- only that this reader did not look.
    repeats = rules.engine.repeats_not_entered(ctx)
    if repeats:
        # How many are named, read once. Written as two literals -- the
        # slice and the comparison that decides whether to say the naming
        # stopped -- widening one left the other saying "and more" after
        # a list that held everything. The count above is all of them;
        # only the naming is bounded, because a note that printed five
        # hundred paths would tell a reader neither how much went
        # unexamined nor where to start.
        named = repeats[:NAMED_IN_A_NOTE]
        # Not "you supplied": 02011 is vendored and self-containing, and
        # not "the outermost occurrence": a copy where the template puts
        # one is judged at any depth now (#48). What is left for this note
        # is a copy the walk did not reach -- inside a container no row
        # describes, or beneath a copy of the wrong kind.
        report.notes.append(
            "a template here describes an element that contains itself "
            "(%s); this reader judges a copy where the template puts one, "
            "and did not reach %d nested cop%s sitting elsewhere (%s). "
            "Nothing here is a statement about what they hold."
            % (repeats[0][1], len(repeats),
               "y" if len(repeats) == 1 else "ies",
               ", ".join(subject for subject, _ in named)
               + ("" if len(named) == len(repeats) else ", and more")))
    report.findings.extend(_meta_findings(loaded, strict_meta))
    if allow_unmatched:
        # The verdict that no template matched, and only that. A presence
        # rule that could not run has not given it: moved with the rest,
        # its crash became a note and the run printed `ok` with the
        # matching question never answered.
        def forgiven(finding):
            return (finding.id == detect.RULE_ID
                    and finding.violation.message != COULD_NOT_RUN)
        unmatched = [f for f in report.findings if forgiven(f)]
        report.findings = [f for f in report.findings if not forgiven(f)]
        for finding in unmatched:
            report.notes.append("%s (allowed): %s -- %s"
                                % (detect.RULE_ID, finding.violation.message,
                                   finding.violation.detail or ""))
    # Only for a key that chooses a table. One that merely settles a
    # collision chose nothing by design, and telling its user the flag
    # did nothing contradicts the finding it just silenced.
    if profile in rules.profiles.KEYS and not any(
            # `rules.profiles.PROFILES and ...` stood here. It is a
            # module constant and never empty, so the conjunct changed
            # no answer and no test could tell it was gone -- the same
            # shape as the encoding guard removed beside it.
            Context(loaded, selection).selection.chosen(submodel)
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
    # The other way the flag decides nothing, and the quiet one. A
    # supplied table takes an identifier from *both* sides of a pair, so
    # the choice is made before the flag is read -- and the note above
    # asks `Selection.chosen`, which knows about the pair and not about
    # the stand-down, so it stays silent on exactly this run. The
    # stand-down note beside it names the pack that stood down and not
    # the flag that selected it, and a caller who passed the flag on
    # purpose reads that as their side having answered.
    elif profile in rules.profiles.KEYS:
        overridden = sorted(
            pair.default.TEMPLATE_SEMANTIC_ID
            for pair in rules.profiles.PROFILES
            if profile in (pair.key, pair.default_key)
            and pair.default.TEMPLATE_SEMANTIC_ID in ctx.taken_over)
        if overridden:
            report.notes.append(
                "--profile %s chose nothing: the template you supplied "
                "answers for %s, which is the identifier that pair "
                "publishes, so both sides of it stood down."
                % (profile, ", ".join(overridden)))
    # What the battery pack could look at in this run, computed from its
    # table rather than quoted from a document, and marked as the floor
    # it is. A note and not a finding: it reports the reach of a check,
    # not a defect in the file.
    # `judgeable`, not `instances`: the rule this note describes reads
    # the first. Left on the second, the note said "BAT-R8 reported 2 of
    # the 9 elements this table holds" in a run where the pack had stood
    # down and BAT-R8 reported none. The last walker of `instances` to
    # move across.
    coverage = rules.battery.coverage_note(detect.judgeable(ctx))
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
    # Everything judged, not everything matched to a template table. The
    # count came from the template packs alone, so a battery passport
    # summarised `judged 0 of 3 submodels` under eight findings about
    # those three -- and `--require-all-judged` could never pass on the
    # one input the pack was built for.
    # The supplied table too. `judged` walks a fixed list of packs, so a
    # submodel judged against a table built at run time was counted as
    # unjudged -- the report would carry findings about it and say
    # `judged 0 of 1`, and `--require-all-judged` could never pass. The
    # same contradiction the battery pack had repaired once.
    report.submodels_judged = len(detect.judged(ctx))
    if supplied is not None:
        answered = supplied["table"].TEMPLATE_SEMANTIC_ID
        took_part = rules.engine.matched_submodels(ctx, supplied["table"])
        if took_part:
            report.notes.append(
                "judged against the template you supplied (%s), which is not "
                "a published IDTA template; what a template states is checked "
                "and nothing else. A verdict against a template you supplied "
                "is not a statement about conformance to a published one."
                % template)
        else:
            # Said, rather than left to a `provenance.template` a consumer
            # reads as "this verdict was made against a supplied template".
            # Measured: with `--example` and a template claiming something
            # the bundled document does not carry, the pack produced the
            # entire verdict and the note claimed it.
            # Which of the two reasons, because they take different
            # remedies. `matched_submodels` reads `instances`, so a
            # submodel declared `kind: Template` is filtered out before
            # it gets here -- and the report then said the identifier
            # was declared by nothing, in the same breath as saying a
            # specification had been set aside. It is declared; it is
            # not an instance. Telling the reader to change the
            # identifier fixes nothing and breaks a correct file.
            spoken_for = [submodel for submodel in loaded.submodels
                          if submodel_declares(submodel, answered)]
            if spoken_for:
                report.notes.append(
                    "the template you supplied (%s) claims %s, and what "
                    "declares it here is a specification rather than an "
                    "instance, so it was set aside before any rule ran. "
                    "Nothing was judged against your template and this "
                    "verdict is this tool's own."
                    % (template, answered))
            else:
                report.notes.append(
                    "the template you supplied (%s) claims %s, which no "
                    "submodel in this input declares; nothing was judged "
                    "against it and this verdict is this tool's own."
                    % (template, answered))
        # A third statement, and not a branch of the two above: those
        # two are one question with two answers -- did your template
        # judge anything -- and this is a different question about the
        # same file. Written between them, it took the `else` from the
        # first, and then every single-submodel template that *did*
        # answer drew the sentence meant for one that answered nothing.
        # Said whether or not it answered, because a file whose second
        # template is the one the input declares looks exactly like a
        # file whose template matches nothing, and the reader can act on
        # the first.
        if supplied["declared"] > 1:
            report.notes.append(
                "the template file declares %d submodels; the table came "
                "from the first of them (%s) and the rest were not read."
                % (supplied["declared"], answered))
        # `PACKS` answers "there is a table generated from the published
        # template"; the three identifiers below have rules and no table,
        # and they stand down the same way. Asked of `PACKS` alone, a
        # supplied template claiming one of them took two `BAT-R8`
        # warnings away and the report said nothing -- a reader comparing
        # two reports of one file sees the run get quieter and reads that
        # as the file improving, which is the failure this note exists to
        # prevent.
        if took_part and (any(pack.semantic_id == answered
                              for pack in detect.PACKS)
                          or answered in detect.PACK_ONLY_SEMANTIC_IDS):
            report.notes.append(
                "a pack of this tool's own also answers for %s and stood "
                "down; your template decided this run. None of that pack's "
                "rules ran -- not its table and not its hand-written ones, "
                "which are readings of a specification and are not "
                "derivable from a template (docs/scope.md)." % answered)
    report.findings.sort(key=_reading_order)
    # The registered rules, not everything that ran. A table the caller
    # supplied contributes rules on purpose and registers none of them,
    # and `docs/report-schema.md` says this number is "every rule
    # registered in this build ... the number does not move when a
    # different template answers". Counted from the rules actually run
    # it moves with the caller's file instead: measured here, 232 with
    # no flag and 258 with a twenty-six row template, and the second
    # figure is whatever that file happens to declare. A published
    # number that depends on an argument is not a property of the
    # build. This comment carried three fixed figures and every one went
    # stale -- two of them before the count last moved -- so it states
    # the shape, which is what lasts.
    # What the template contributed is in
    # `provenance.template.rows`, which is where a reader who wants it
    # should look.
    report.checked = len(all_rules())
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
