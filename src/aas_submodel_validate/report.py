"""Rendering a report for a person at a terminal."""
from __future__ import annotations

from .model import Report, Severity


def render(report: Report) -> str:
    lines = []
    for finding in report.findings:
        head = "%-7s %-6s %s" % (finding.severity, finding.id, finding.violation.message)
        lines.append(head)
        if finding.violation.subject:
            lines.append("        at   %s" % finding.violation.subject)
        if finding.violation.detail:
            lines.append("        saw  %s" % finding.violation.detail)
        if finding.fix:
            lines.append("        fix: %s" % finding.fix)
    if report.ok and not report.findings:
        lines.append("ok — %s (%d rules)" % (report.path, report.checked))
    else:
        lines.append("%d error(s), %d warning(s), %d note(s) — %s"
                     % (report.count(Severity.ERROR), report.count(Severity.WARNING),
                        report.count(Severity.INFO), report.path))
    return "\n".join(lines)
