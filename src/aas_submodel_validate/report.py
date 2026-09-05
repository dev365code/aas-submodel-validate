"""Rendering a report for a person at a terminal."""
from __future__ import annotations

from .model import META_KIND, Report, Severity


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


def render(report: Report, *, show_meta: bool = False) -> str:
    """The report as a person reads it.

    The metamodel channel is folded by default. It is relayed from
    aas-core3.0 about the metamodel, upstream of any template, and on
    the official example this project points a newcomer at it is
    seventy-seven of eighty-seven findings -- every one of them carrying
    the same remedy sentence. Most of them can be acted on -- on that
    example forty-five of the seventy-seven are about the submodel
    itself and thirty-three of those clear by deleting an idShort the
    metamodel says should not be there -- so the reason for folding
    them is length and not futility. Printed in full they are the first
    thing a stranger sees and the verdict is three hundred lines below
    them.

    Folded, not dropped. The summary line still counts them, the JSON
    report is untouched, and the fold says how many there are and which
    flag opens it: a reader who cannot see a finding must at least be
    told that it exists. And never folded once `--strict-meta` has made
    them errors, because then they are the verdict.
    """
    lines = []
    folded = 0
    for finding in report.findings:
        # Never an error. `--strict-meta` promotes this channel to the
        # verdict, and a finding that decided the exit code has to be on
        # the screen -- folding is for a relayed warning nobody asked to
        # be judged by, not for the reason a run failed.
        if (finding.rule.kind == META_KIND and not show_meta
                and finding.severity is not Severity.ERROR):
            folded += 1
            continue
        head = "%-7s %-8s %s" % (finding.severity, finding.id, _safe(finding.violation.message))
        lines.append(head)
        if finding.violation.subject:
            lines.append("        at   %s" % _safe(finding.violation.subject))
        if finding.violation.detail:
            lines.append("        saw  %s" % _safe(finding.violation.detail))
        if finding.spec:
            # The clause, on the screen. It has been in the JSON since
            # the first release and nowhere else, so the person writing
            # "conforms: yes/no" into a report -- who needs the citation
            # more than anyone -- had to re-run with `-f json` to get it.
            lines.append("        per  %s" % _safe(finding.spec))
        if finding.fix:
            lines.append("        fix: %s" % _safe(finding.fix))
    if folded:
        # Where they would have been printed: the reading order puts this
        # channel last, so the fold sits under the findings it stands in
        # for rather than above them.
        lines.append("%-7s %-8s %d finding%s relayed from aas-core3.0 about the "
                     "metamodel, upstream of any template (--show-meta lists them)"
                     % ("", "", folded, "" if folded == 1 else "s"))
    for note in report.notes:
        lines.append("note    %s" % _safe(note))
    # Hoisted above the branch, not attached to one of them. Today only
    # the second is reachable with something unread, because every load
    # error has a rule to report it -- but that is a fact about the rules,
    # not about the summary, and the summary is what promises to say so.
    incomplete = "" if report.complete else " (not a full verdict: some of it was not read)"
    # How much of the file a template answered for, said in both forms.
    # A submodel this tool has no table for is not a defect, so it is a
    # number rather than a finding -- but a report that omits the number
    # lets a reader believe the whole file was judged.
    judged = ""
    if not report.submodels_seen and report.judged:
        # Zero is falsy, so the clause below was suppressed on the one
        # input the front page calls the emptiest pass of the lot: an
        # environment holding nothing. The screen said `0 error(s)` and
        # nothing about having judged nothing.
        judged = "; no submodels to judge"
    elif report.submodels_seen:
        judged = "; judged %d of %d submodel%s" % (
            report.submodels_judged, report.submodels_seen,
            "" if report.submodels_seen == 1 else "s")
    if report.ok and not report.findings and not report.notes:
        # "rules registered", not "rules checked": a Technical Data file
        # is not judged by 02004's fifty-two, and a run that says it
        # checked them has told the reader something it did not do.
        lines.append("ok -- %s (%d rules registered%s)%s"
                     % (report.path, report.checked, judged, incomplete))
    else:
        # The third count is INFO findings. It said "note(s)" and the
        # report has notes of its own, printed above and not counted
        # here -- one word for two things, with a run that printed a note
        # and summarised "0 note(s)" as the proof.
        # And whether the counts above describe the whole input. A refused
        # file summarises as one error, which is what a judged file that
        # failed looks like -- the JSON report grew a field to tell those
        # apart and the person at the terminal is owed the same sentence.
        lines.append("%d error(s), %d warning(s), %d info -- %s%s%s"
                     % (report.count(Severity.ERROR), report.count(Severity.WARNING),
                        report.count(Severity.INFO), report.path, judged, incomplete))
    return "\n".join(lines)
