"""Result types and the severity vocabulary.

The shape is inherited from this project's older siblings (iirds-validate,
vdi2770): a Violation is one concrete wrong thing, a Rule is the check
that found it, a Finding is the pair with everything a person needs — and
every rule carries a `fix` sentence, because a validator that names a
defect without naming the remedy has told you that something is wrong and
left you to find the specification, which is most of the work and all of
the expertise.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional


class Severity(enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    def __str__(self) -> str:
        return self.value


#: Specification keyword -> how loudly we complain. IDTA templates speak
#: RFC 2119; the mapping is the standard's own emphasis, not ours.
PRIO_SEVERITY = {
    "MUST": Severity.ERROR,
    "MUST NOT": Severity.ERROR,
    "REQUIRED": Severity.ERROR,
    "SHALL": Severity.ERROR,
    "RECOMMENDED": Severity.WARNING,
    "SHOULD": Severity.WARNING,
    "MAY": Severity.INFO,
    "OPTIONAL": Severity.INFO,
}


#: What a rule is about. Listed in the order a report reads *within one
#: severity*, which is where this order applies: the container the
#: submodel arrived in, then the template it claims to be, then this
#: project's informational lints, then the metamodel channel relayed
#: from aas-core3.0 -- 77 relayed messages must not bury the template
#: findings the reader came for. Severity sorts first (`runner`), so
#: under `--meta error` the relayed channel rises above template
#: warnings: that is the caller asking for it, not this order failing.
#:
#: One list, because it was two and neither could see the other: the
#: reading order held its own copy, and a kind outside that copy sorted
#: into the middle of it. `runner` derives its order from this and
#: `registry` refuses anything outside it.
#:
#: A fifth kind is still not a one-line change, and the comment that said
#: so was wrong: `docs/report-schema.md` publishes the vocabulary to
#: consumers, and the report-order tests keep a second copy on purpose --
#: a test that borrows the ordering it checks asserts that sorted things
#: are sorted. Both are pinned against this list for *membership*, so
#: both go red rather than stale; the copy's *order* stays its own, which
#: is the whole reason it is a copy.
KINDS = ("container", "template", "lint", "meta")

#: The one relayed kind, named once. Everything in the other three is
#: this project's own reading of a template; this one is aas-core3.0
#: speaking about the metamodel, and two flags decide its severity and
#: whether `-W` may promote it. Spelled as a literal in three places
#: before, which is two places for the spelling to drift.
META_KIND = "meta"
assert META_KIND in KINDS


#: The longest any one field of a finding travels, in characters.
#:
#: A report interpolates what a file said -- a File value, a property's
#: contents -- and nothing bounded it. Measured: a 200 KB File value
#: produced a 200,670-character report, and the bound on the input is
#: 64 MiB, so the report is bounded by that and nothing smaller.
#:
#: Set here rather than at the one rule that was found doing it. Capping
#: a single place is the mistake this project has met before: the class
#: stays and the next rule to interpolate a value reopens it. Applied
#: by `Violation` and by `Rule`, which between them own every string
#: a finding prints. `Violation` alone was called the one funnel here
#: and was not one: a finding carries its rule's title too, and its
#: `fix` falls back to the rule's when the violation has none.
#: Measured -- a rule whose text was 200,000 characters reached the
#: JSON at full length beside a violation cut at this bound. Every
#: generated pack builds that text out of the template's own strings,
#: so the length is the template's to choose and not this project's.
#:
#: Chosen above the longest sentence this project writes -- `SMT-D1`'s
#: remedy, which names every template this tool has a table for and so
#: grows by roughly a line with each pack added: 403 characters at three
#: packs, 590 at five, 690 at six. The bound is raised when it does
#: rather than the
#: sentence shortened, so the bound can only ever cut something a file
#: supplied. A test asserts that nothing authored comes near it, and it
#: is that test, not this comment, that catches the next pack.
MAX_REPORTED_CHARACTERS = 2000

#: What the reader sees where the rest was. Not a bare ellipsis: a
#: reader who cannot tell a short value from a shortened one cannot tell
#: whether the value in their file is the value in the report.
#:
#: Three dots and not the character. `tests/test_output_encoding.py`
#: refused the first version of this line: a report reaches a terminal
#: whose default code page cannot encode U+2026, and that gate caught it
#: before a Windows reader did.
_ELIDED = "... (%d more characters, not shown)"


def _bounded(text):
    """`text`, cut to the bound, saying how much was cut."""
    if text is None or len(text) <= MAX_REPORTED_CHARACTERS:
        return text
    marker = _ELIDED % (len(text) - MAX_REPORTED_CHARACTERS)
    return text[:MAX_REPORTED_CHARACTERS - len(marker)] + marker


@dataclass(frozen=True)
class Violation:
    """One concrete thing that is wrong, produced by a rule."""

    message: str
    subject: Optional[str] = None   # offending id/idShort path, or part name
    detail: Optional[str] = None    # extra context, e.g. the value we saw
    #: Remedy for THIS instance, when it needs something more specific than
    #: the rule's standing advice.
    fix: Optional[str] = None
    #: The clause THIS instance reads from, when a rule answers for a
    #: table whose rows cite different provisions. The front page tells a
    #: reader `per` is what to cite, and a constant on the rule sent them
    #: to a provision no row had chosen.
    spec: Optional[str] = None
    #: How loudly THIS instance is reported, when the rule's own priority
    #: is the wrong answer. One thing needs it: a rule that could not run
    #: at all. What the rule asks for stays true in the report and stays
    #: in `priority`; whether the run may be called clean is a different
    #: question, and for a check that did not happen the answer is no
    #: however little the check was asking for.
    severity: Optional[Severity] = None

    def __post_init__(self):
        # Every field, not only the two that were found carrying a
        # value. A policy with an exception list is a policy somebody
        # has to remember, and the bound is far above anything this
        # project writes, so it costs the authored text nothing.
        for name in ("message", "subject", "detail", "fix", "spec"):
            value = getattr(self, name)
            bounded = _bounded(value)
            if bounded is not value:
                object.__setattr__(self, name, bounded)


@dataclass(frozen=True)
class Rule:
    id: str
    kind: str                       # container | template | lint | meta
    prio: str
    title: str
    spec: Optional[str]             # where the requirement lives (template §)
    fn: Callable[..., Iterable[Violation]]
    #: One imperative sentence: what to change so this stops being reported.
    fix: Optional[str] = None

    def __post_init__(self):
        # The same three lines `Violation` has, against the same bound and
        # for the same reason. A rule's text is authored here for the hand
        # rules and interpolated from the template's own strings for every
        # generated pack, and the second of those is not this project's to
        # keep short. Measured: the longest text any rule here carries is
        # 690 characters (`SMT-D1`'s remedy) and none reaches the bound, so
        # this cuts nothing that was written on purpose.
        for name in ("title", "spec", "fix"):
            value = getattr(self, name)
            bounded = _bounded(value)
            if bounded is not value:
                object.__setattr__(self, name, bounded)

    @property
    def severity(self) -> Severity:
        return PRIO_SEVERITY.get(self.prio, Severity.WARNING)


@dataclass(frozen=True)
class Finding:
    """A violation with its rule metadata resolved — what users see."""

    rule: Rule
    violation: Violation

    @property
    def id(self) -> str:
        return self.rule.id

    @property
    def severity(self) -> Severity:
        return self.violation.severity or self.rule.severity

    @property
    def fix(self) -> Optional[str]:
        return self.violation.fix or self.rule.fix

    @property
    def spec(self) -> str:
        return self.violation.spec or self.rule.spec

    def as_dict(self) -> dict:
        return {
            "rule": self.rule.id,
            "kind": self.rule.kind,
            "severity": str(self.severity),
            "priority": self.rule.prio,
            "message": self.violation.message,
            "subject": self.violation.subject,
            "detail": self.violation.detail,
            "fix": self.fix,
            "title": self.rule.title,
            "spec": self.spec,
        }


@dataclass(frozen=True)
class UnmatchedElement:
    """An element whose semanticId matched no row, and what that cost.

    The template states a minimum rather than a whitelist
    (`docs/divergences.md` #19), so this is not a finding and carries no
    severity: an element of the supplier's own is entitled to be here. What
    is reportable is the consequence for *this run* -- the rules below the
    row it did not match were never put -- and a record is kept only where
    that consequence is non-empty, which is what keeps a conformant file
    carrying an extra element silent.
    """
    subject: str
    seen: str
    #: Rule ids that went unasked because this element was not entered.
    unasked: tuple = ()
    #: The row identifier this one resembles, where it does. A suspicion
    #: about a typo, never a verdict (`rules/engine.py _near_miss`).
    resembles: Optional[str] = None

    def __post_init__(self):
        # Through the same funnel as a finding. `subject` is built from the
        # file's idShort chain and `seen` is the file's own identifier, so
        # both are file-supplied text, and the policy above says every such
        # field is bounded in one place rather than in a list of exceptions
        # somebody has to remember. Without this a 200 KB idShort produced a
        # 200 KB terminal line from a 2 KB input.
        object.__setattr__(self, "subject", _bounded(self.subject))
        object.__setattr__(self, "seen", _bounded(self.seen))
        object.__setattr__(self, "resembles", _bounded(self.resembles))

    @property
    def count(self) -> int:
        return len(self.unasked)

    def as_dict(self) -> dict:
        out = {"subject": self.subject, "seen": self.seen,
               "rulesNotAskedHere": list(self.unasked)}
        if self.resembles:
            out["resembles"] = self.resembles
        return out


@dataclass(frozen=True)
class NotExamined:
    """A row whose scope this run never opened, and what sat there.

    `unmatched` above names an element and the rules it cost, and is
    recorded only where the reader already reported something that
    explains the loss. This one makes no attribution at all: it says a
    row was not entered, which rules went unasked with it, and -- as a
    separate fact, not a cause -- whether any element in that same scope
    matched no row.

    `because` is one of:

    `absent`
        nothing in that scope matched the row and nothing there was
        unplaceable either. The file does not carry this section, which
        for an optional row is not a defect and for a required one has
        already drawn its own finding.
    `unclaimed-element-present`
        the row was not entered *and* something in that scope matched no
        row. The two facts are reported side by side and neither is
        named as the cause of the other: a different identifier may be a
        legitimate extension (`docs/divergences.md` #19) and there is no
        way to tell that from a typo by looking (#22, #23).
    """

    where: str
    rule: str
    label: str
    unasked: tuple
    because: str

    def as_dict(self) -> dict:
        return {"where": self.where, "rule": self.rule, "label": self.label,
                "rulesNotAskedHere": list(self.unasked),
                "because": self.because}


@dataclass
class Report:
    path: str
    findings: List[Finding] = field(default_factory=list)
    checked: int = 0
    notes: List[str] = field(default_factory=list)
    #: Whether everything this run was handed got read. A refused input
    #: comes back `ok: false` with one error and every rule counted --
    #: which is exactly what a judged file that failed looks like, and
    #: nothing was judged. A consumer had the string "X5" and nothing
    #: else to tell the two apart.
    complete: bool = True
    #: And whether anything reached the rules at all. `complete` is about
    #: what was read; this is about what was judged, and the two are
    #: ordered -- an archive with one bad part among three good ones is
    #: incomplete and judged, while one that would not open is neither.
    #: The exit code is derived from this: a refusal leaves by the
    #: could-not-run code, because X5's own remedy says "it was refused,
    #: not judged" and the run used to exit with the code for judged and
    #: found wanting.
    judged: bool = True
    #: What was asked of this run. The same file comes back `ok` under one
    #: set of flags and not under another -- the official example passes
    #: by default and fails under `--strict-meta` -- and a profile decides
    #: which of two templates answers at all. Two such documents were
    #: indistinguishable, and a reader comparing them had only the prose
    #: inside a finding's message to go on.
    profile: Optional[str] = None
    #: Which severity the relayed channel reported at: `error`,
    #: `warning` or `info`. The flags move the verdict, so a document
    #: that does not carry them cannot be compared with another.
    meta: str = "warning"
    #: Rule ids that were below a scope this run did not enter, and that
    #: no other scope asked either -- a list is walked once per item, so
    #: a row missed in one and asked in another is not one of these. A generated rule sits inside a scope, and a scope
    #: opens only when an element matches the row that names it; an
    #: element whose semanticId matches no row is not recursed into, and
    #: every rule beneath it leaves the run (docs/divergences.md #23).
    #:
    #: The report said nothing, because nothing was wrong with what was
    #: checked. Measured on this project's own fixtures: a typo inside a
    #: path segment of one identifier silences 18 of the 69 measurable
    #: rows, and on the terminal the two reports read the same. (The JSON
    #: never did: `provenance.inputSha256` differs for any two files, so
    #: a consumer diffing stored reports always had that. What it did not
    #: have is any statement of what the run failed to ask.)
    #:
    #: Not a claim about the file, and it moves no verdict. The template
    #: states a minimum and not a whitelist (#19), so an element matching
    #: no row is not by itself a defect -- what is reportable is that
    #: this run did not look inside it.
    not_asked: List[str] = field(default_factory=list)
    #: The elements this run could not place, one record each, and the
    #: rules each of them kept from being asked. `not_asked` above is the
    #: same loss with the elements taken off it: useful for a count, no
    #: use at all for the reader asking *which* element did it. Same
    #: standing as `not_asked` -- a statement about the run, not about the
    #: file, and it moves no verdict.
    unmatched: List[UnmatchedElement] = field(default_factory=list)
    #: Rows whose scope this run never opened, with no claim about why.
    #: `unmatched` reports a loss something explains; this reports the
    #: reach of the check whether or not anything explains it, which is
    #: the half that was given up along with the blame. Same standing as
    #: the two above -- a statement about the run, not about the file,
    #: and it moves no verdict.
    not_examined: List[NotExamined] = field(default_factory=list)
    allow_unmatched: bool = False
    #: The digest of the bytes this run read, or None when there were
    #: none to read. A report that says a file failed and does not say
    #: which bytes it read is an assertion about a filename.
    input_sha256: Optional[str] = None
    #: Where the rule table came from, when it did not come from here.
    #: Absent for a run against the packs this project vendored, so a
    #: reader who sees it knows the verdict was made against a file the
    #: caller supplied and not against a published IDTA template.
    template: Optional[dict] = None
    #: How much of the input was looked at. Not a fraction of the rules
    #: -- most of those are about other templates and their silence means
    #: nothing -- but of the submodels the file actually holds. An
    #: environment carries submodels this tool has no business judging,
    #: so an unjudged one is a number and not a finding; without the
    #: number the report says nothing about it at all, because `SMT-D1`
    #: speaks only when *nothing* matched.
    submodels_seen: int = 0
    submodels_judged: int = 0
    #: Of `submodels_seen`, how many said they are specifications rather
    #: than instances. Subtracting them from `submodels_seen` was the
    #: first attempt and it made that field lie: the schema says it is
    #: how many submodels the input holds, and a file holding two came
    #: back saying zero.
    submodels_specified: int = 0

    def count(self, severity: Severity) -> int:
        return sum(1 for f in self.findings if f.severity is severity)

    @property
    def ok(self) -> bool:
        return self.count(Severity.ERROR) == 0

    def as_dict(self) -> dict:
        from . import __version__

        return {
            "schemaVersion": 1,
            # The evidence envelope. Two of its three fields are reserved
            # and one is computed, and the split is the point: a report
            # becomes evidence when it says what was judged, by which
            # engine, and who vouches for it -- and the third is not this
            # tool's to answer. Signing belongs to whoever issued the
            # document, the way a declaration of conformity does; a
            # validator that signed its own verdicts would be selling an
            # assurance it has no standing to give.
            #
            # Reserved rather than omitted, at the release that fixes the
            # shape: a key that appears later is a schema change, and a
            # key that is always `null` is a promise somebody can build
            # against.
            "provenance": dict({
                "inputSha256": self.input_sha256,
                "engine": None,
                "envelope": None,
            }, **({"template": self.template} if self.template else {})),
            # The shape's number and the producer's are different numbers.
            # A consumer that finds a defect in a report needs to say which
            # build wrote it, and `schemaVersion` cannot answer that.
            "toolVersion": __version__,
            "path": self.path,
            "ok": self.ok,
            "options": {
                "profile": self.profile,
                "meta": self.meta,
                # The older spelling, derived rather than stored: a
                # reader written against 0.1.0 parses this one, and two
                # independently-set fields for one setting is how they
                # come to disagree.
                "strictMeta": self.meta == "error",
                "allowUnmatched": self.allow_unmatched,
            },
            "summary": {
                "errors": self.count(Severity.ERROR),
                "warnings": self.count(Severity.WARNING),
                "info": self.count(Severity.INFO),
                "rulesChecked": self.checked,
                # Additive, so schemaVersion stays 1: a consumer that does
                # not know the key reads exactly what it read before.
                "complete": self.complete,
                "judged": self.judged,
                "submodelsSeen": self.submodels_seen,
                "submodelsJudged": self.submodels_judged,
                "submodelsSpecified": self.submodels_specified,
                # Also additive. A consumer diffing two stored reports is
                # the reader this key exists for: without it a file whose
                # identifier drifted and a conformant one serialise to the
                # same bytes.
                "rulesNotAsked": self.not_asked,
                # The same loss, per element, for the pipeline that wants
                # to act on it. A new flag was deliberately not added: a
                # consumer that wants to fail on this reads it here.
                "unmatchedElements": [u.as_dict() for u in self.unmatched],
                "scopeNotExamined": [n.as_dict() for n in self.not_examined],
            },
            "notes": self.notes,
            "findings": [f.as_dict() for f in self.findings],
        }
