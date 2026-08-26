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
#: aas-core3.0 -- 77 relayed messages must not bury the two template
#: findings the reader came for.
#:
#: One list, because it was two and neither could see the other: the
#: reading order held its own copy, and a kind outside that copy sorted
#: into the middle of it. `runner` derives its order from this and
#: `registry` refuses anything outside it, so a fifth kind is a change to
#: this line and nowhere else.
KINDS = ("container", "template", "lint", "meta")


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

    def count(self, severity: Severity) -> int:
        return sum(1 for f in self.findings if f.severity is severity)

    @property
    def ok(self) -> bool:
        return self.count(Severity.ERROR) == 0

    def as_dict(self) -> dict:
        return {
            "schemaVersion": 1,
            "path": self.path,
            "ok": self.ok,
            "summary": {
                "errors": self.count(Severity.ERROR),
                "warnings": self.count(Severity.WARNING),
                "info": self.count(Severity.INFO),
                "rulesChecked": self.checked,
                # Additive, so schemaVersion stays 1: a consumer that does
                # not know the key reads exactly what it read before.
                "complete": self.complete,
            },
            "notes": self.notes,
            "findings": [f.as_dict() for f in self.findings],
        }
