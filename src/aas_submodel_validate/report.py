"""Rendering a report for a person at a terminal."""
from __future__ import annotations

from .model import Report, Severity


def _safe(text) -> str:
    """A field that came out of an untrusted package, made safe to print.

    A subject path can contain an attacker-chosen idShort, and a raw
    escape byte on a terminal is an ANSI/BEL injection. Control characters
    (tab excepted) are shown as their escape, so the report says what the
    file holds without letting the file drive the terminal.

    All three control ranges. The first version kept everything from
    0x20 up, which reads as "the control characters" and is only C0:
    DEL walked through, and so did C1 -- and 0x9B alone is CSI on a
    terminal honouring 8-bit controls, the very byte class this exists
    to stop."""
    return "".join(
        ch if ch == "\t" or (ord(ch) >= 0x20 and not 0x7f <= ord(ch) <= 0x9f)
        else "\\x%02x" % ord(ch)
        for ch in str(text))


def render(report: Report) -> str:
    lines = []
    for finding in report.findings:
        head = "%-7s %-8s %s" % (finding.severity, finding.id, _safe(finding.violation.message))
        lines.append(head)
        if finding.violation.subject:
            lines.append("        at   %s" % _safe(finding.violation.subject))
        if finding.violation.detail:
            lines.append("        saw  %s" % _safe(finding.violation.detail))
        if finding.fix:
            lines.append("        fix: %s" % _safe(finding.fix))
    for note in report.notes:
        lines.append("note    %s" % _safe(note))
    # Hoisted above the branch, not attached to one of them. Today only
    # the second is reachable with something unread, because every load
    # error has a rule to report it -- but that is a fact about the rules,
    # not about the summary, and the summary is what promises to say so.
    incomplete = "" if report.complete else " (not a full verdict: some of it was not read)"
    if report.ok and not report.findings and not report.notes:
        # "rules registered", not "rules checked": a Technical Data file
        # is not judged by 02004's fifty-two, and a run that says it
        # checked them has told the reader something it did not do.
        lines.append("ok — %s (%d rules registered)%s"
                     % (report.path, report.checked, incomplete))
    else:
        # The third count is INFO findings. It said "note(s)" and the
        # report has notes of its own, printed above and not counted
        # here -- one word for two things, with a run that printed a note
        # and summarised "0 note(s)" as the proof.
        # And whether the counts above describe the whole input. A refused
        # file summarises as one error, which is what a judged file that
        # failed looks like -- the JSON report grew a field to tell those
        # apart and the person at the terminal is owed the same sentence.
        lines.append("%d error(s), %d warning(s), %d info — %s%s"
                     % (report.count(Severity.ERROR), report.count(Severity.WARNING),
                        report.count(Severity.INFO), report.path, incomplete))
    return "\n".join(lines)
