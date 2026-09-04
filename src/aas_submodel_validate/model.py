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


#: What a rule is about, in the order a report is read: the container the
#: submodel arrived in, then the template it claims to be, then this
#: project's informational lints, then the metamodel channel relayed from
#: aas-core3.0 -- 77 relayed messages must not bury the template
#: findings the reader came for.
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


@dataclass(frozen=True)
class Violation:
    """One concrete thing that is wrong, produced by a rule."""

    message: str
    subject: Optional[str] = None   # offending id/idShort path, or part name
    detail: Optional[str] = None    # extra context, e.g. the value we saw
    #: Remedy for THIS instance, when it needs something more specific than
    #: the rule's standing advice.
    fix: Optional[str] = None


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
        return self.rule.severity

    @property
    def fix(self) -> Optional[str]:
        return self.violation.fix or self.rule.fix

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
            "spec": self.rule.spec,
        }


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
    allow_unmatched: bool = False
    #: The digest of the bytes this run read, or None when there were
    #: none to read. A report that says a file failed and does not say
    #: which bytes it read is an assertion about a filename.
    input_sha256: Optional[str] = None
    #: How much of the input was looked at. Not a fraction of the rules
    #: -- most of those are about other templates and their silence means
    #: nothing -- but of the submodels the file actually holds. An
    #: environment carries submodels this tool has no business judging,
    #: so an unjudged one is a number and not a finding; without the
    #: number the report says nothing about it at all, because `SMT-D1`
    #: speaks only when *nothing* matched.
    submodels_seen: int = 0
    submodels_judged: int = 0

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
            "provenance": {
                "inputSha256": self.input_sha256,
                "engine": None,
                "envelope": None,
            },
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
            },
            "notes": self.notes,
            "findings": [f.as_dict() for f in self.findings],
        }
