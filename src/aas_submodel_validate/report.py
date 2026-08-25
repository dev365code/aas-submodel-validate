"""Rendering a report for a person at a terminal."""
from __future__ import annotations

from .model import Report, Severity


def _safe(text) -> str:
    """A field that came out of an untrusted package, made safe to print.

    A subject path can contain an attacker-chosen idShort, and a raw
    escape byte on a terminal is an ANSI/BEL injection. Control characters
    (tab excepted) are shown as their escape, so the report says what the
    file holds without letting the file drive the terminal."""
    return "".join(
        ch if ch == "\t" or ord(ch) >= 0x20 else "\\x%02x" % ord(ch)
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
    if report.ok and not report.findings:
        lines.append("ok — %s (%d rules)" % (report.path, report.checked))
    else:
        lines.append("%d error(s), %d warning(s), %d note(s) — %s"
                     % (report.count(Severity.ERROR), report.count(Severity.WARNING),
                        report.count(Severity.INFO), report.path))
    return "\n".join(lines)
