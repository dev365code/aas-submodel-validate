"""Rendering a report for a person at a terminal."""
from __future__ import annotations

from typing import Optional

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


def _same_but_for_place(one, other) -> bool:
    """Whether two findings differ in nothing but where they are.

    Measured on the example this project ships: ten findings printed,
    four rules, and one of them says the same sentence five times with
    one path changed -- its message, its evidence, its clause and a
    four-line remedy, over and over. That repetition was forty-eight per
    cent of the printed lines and, once the remedies are wrapped at
    eighty columns, forty-six per cent of the rows.

    Every field is compared, `saw` included. Two findings of the same
    rule that saw different values are two findings: `saw` is what lets
    a reader tell one from a similar one, and a group that collapsed
    them would print one value and drop the other -- the report lying
    about what it read, to save a line.

    A finding with no subject never joins one. Grouping is sound only
    while each member leaves exactly one `at` line behind, because that
    is what keeps the screen adding up to the count in the summary.
    """
    return (bool(other.violation.subject)
            and one.id == other.id
            and one.severity is other.severity
            and one.violation.message == other.violation.message
            and one.violation.detail == other.violation.detail
            and one.spec == other.spec
            and one.fix == other.fix)


#: What each labelled line is, in the words of someone who has not read
#: the source. The four labels were explained on the front page and
#: nowhere else, two thirds of the way down it and nested inside the
#: section about wiring the tool into a build -- so a reader who had run
#: the tool once and wanted to know what to change had the answer filed
#: under a question they were not asking. A label printed on a screen is
#: explained on that screen or it is not explained.
#:
#: Short on purpose: this has to sit inside eighty columns beside the
#: eight-space indent, because a legend that wraps is one more thing to
#: read past.
LABELS = (("at", "where"), ("saw", "what is there now"),
          ("per", "the clause"), ("fix", "what to change"))
#: The one document findings send a reader to, and where it is. Seventeen
#: rules print `docs/divergences.md` and a wheel carries no `docs/` --
#: measured on a built wheel, which has none of it and does not list it
#: as package data. `per` is defined on the front page as the clause to
#: cite when you have to cite one, so the reader most likely to follow
#: it is writing a note for somebody else, and a repository-relative
#: path resolves for neither of them.
#:
#: Shipping the file was the other answer: forty-nine kilobytes on a
#: two-hundred-and-eighty-four kilobyte wheel, landing under
#: `site-packages` where it is no more citable than it was. An address
#: is the citable form, and one line carries it however many findings
#: point there.
DIVERGENCES = "docs/divergences.md"
DIVERGENCES_AT = ("https://github.com/dev365code/aas-submodel-validate/blob/"
                  "main/docs/divergences.md")

#: `note` is not one of the four. It is printed in the column `error`
#: and `warning` are printed in, at the same indent and the same weight,
#: and it is the one word in that column that is not a severity -- so
#: "here is something to change" and "here is something this run did
#: not look at" arrive looking alike. The distinction the report already
#: makes is that a note has no `fix:`; this says so.
NOTE_KEY = "note=something this run did, not a defect -- nothing to change"
#: How many identifiers the summary names before it starts counting. A
#: typo inside one identifier silences eighteen of the measurable rows,
#: and eighteen identifiers inline is the wall this whole line exists to
#: keep off the screen.
NAMED_AT_MOST = 3


def render(report: Report, *, show_meta: bool = False,
           failed: Optional[bool] = None) -> str:
    """The report as a person reads it.

    `failed` is the verdict the caller reached, and it is a parameter
    because the caller reaches it with things this function cannot see.
    `report.ok` is "no findings at error severity"; the exit code is
    that, plus `-W`, plus `--require-all-judged`. Recomputing the word
    from `report.ok` would agree on the default flags and disagree on
    exactly the flags somebody reached for deliberately -- which was
    measurable: `--example` and `--example -W` printed byte-identical
    screens and left by 0 and 1, so the one fact the reader wanted was
    the one fact only `$?` held.

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
    # Which labels actually reached the screen. Collected while
    # rendering rather than derived from the report, because the two can
    # differ -- a finding with no `saw` prints no `saw` line, and a
    # legend explaining a label the reader never saw is noise dressed as
    # help.
    shown = set()
    # Never an error. `--strict-meta` promotes this channel to the
    # verdict, and a finding that decided the exit code has to be on the
    # screen -- folding is for a relayed warning nobody asked to be
    # judged by, not for the reason a run failed.
    visible = [finding for finding in report.findings
               if not (finding.rule.kind == META_KIND and not show_meta
                       and finding.severity is not Severity.ERROR)]
    folded = len(report.findings) - len(visible)
    at = 0
    while at < len(visible):
        finding = visible[at]
        # Adjacent runs only. The order is promised elsewhere -- severity,
        # then kind, then id, then message -- and gathering matches from
        # anywhere in the list would quietly rewrite it. Findings that
        # are equal in all of those are already neighbours, so an
        # adjacent run loses nothing a scan would have found.
        same = [finding]
        if finding.violation.subject:
            while (at + len(same) < len(visible)
                   and _same_but_for_place(finding, visible[at + len(same)])):
                same.append(visible[at + len(same)])
        at += len(same)
        head = "%-7s %-8s %s" % (finding.severity, finding.id, _safe(finding.violation.message))
        lines.append(head)
        for member in same:
            if member.violation.subject:
                lines.append("        at   %s" % _safe(member.violation.subject))
                shown.add("at")
        if finding.violation.detail:
            lines.append("        saw  %s" % _safe(finding.violation.detail))
            shown.add("saw")
        if finding.spec:
            # The clause, on the screen. It has been in the JSON since
            # the first release and nowhere else, so the person writing
            # "conforms: yes/no" into a report -- who needs the citation
            # more than anyone -- had to re-run with `-f json` to get it.
            lines.append("        per  %s" % _safe(finding.spec))
            shown.add("per")
        if finding.fix:
            lines.append("        fix: %s" % _safe(finding.fix))
            shown.add("fix")
    if folded:
        # Where they would have been printed: the reading order puts this
        # channel last, so the fold sits under the findings it stands in
        # for rather than above them.
        lines.append("%-7s %-8s %d finding%s relayed from aas-core3.0 about the "
                     "metamodel, upstream of any template (--show-meta lists them)"
                     % ("", "", folded, "" if folded == 1 else "s"))
    for note in report.notes:
        lines.append("note    %s" % _safe(note))
    # Under the findings and over the summary, which is where a terminal
    # leaves the reader: eighty-eight rows scroll past and the last
    # screenful is what they are looking at. A legend at the top would
    # be above everything it explains and off the screen by the time it
    # was wanted.
    keyed = [" ".join("%s=%s" % pair for pair in LABELS if pair[0] in shown)]
    if report.notes:
        keyed.append(NOTE_KEY)
    # Only where a printed line actually sent the reader there. Derived
    # from what reached the screen, like the labels above: a run that
    # never cites the document gets no line about it.
    if any(DIVERGENCES in line for line in lines):
        keyed.append("%s is at %s" % (DIVERGENCES, DIVERGENCES_AT))
    for entry in keyed:
        if entry:
            lines.append("key     %s" % entry)
    # Hoisted above the branch, not attached to one of them. Today only
    # the second is reachable with something unread, because every load
    # error has a rule to report it -- but that is a fact about the rules,
    # not about the summary, and the summary is what promises to say so.
    incomplete = "" if report.complete else " (not a full verdict: some of it was not read)"
    # How much of the file a template answered for, said in both forms.
    # A submodel this tool has no table for is not a defect, so it is a
    # number rather than a finding -- but a report that omits the number
    # lets a reader believe the whole file was judged.
    # The same debt as `incomplete`, one layer further in. `incomplete`
    # is about what was read; this is about what was asked of what was
    # read. A conformant file and one with a typo inside a path segment
    # of a single identifier print the same line, and the second was put
    # two dozen fewer questions -- the JSON grew `rulesNotAsked` for
    # exactly that, and the sentence three comments down says the person
    # at the terminal is owed the same thing.
    unasked = ""
    if report.not_asked:
        # Named, not just counted. The ids have been in
        # `summary.rulesNotAsked` since they were introduced and the
        # terminal said only how many -- so the reader was told
        # something had been skipped and handed nothing to look it up
        # by. Named up to a bound and then counted, because eighteen
        # identifiers inline is the wall this line exists to prevent.
        named = report.not_asked[:NAMED_AT_MOST]
        rest = len(report.not_asked) - len(named)
        # `row` is gone from this sentence. It is not an AAS word and not
        # an IDTA word -- it is this project's name for a line of its own
        # template table, so a reader who went and learned the standard
        # still would not find it, which is worse than jargon they could
        # look up. It was in the sentence a first-time reader was most
        # likely to stop on.
        unasked = ("; %d rule%s not asked (%s%s): %s element is not one the "
                   "template describes, so this run did not look inside it"
                   % (len(report.not_asked),
                      "" if len(report.not_asked) == 1 else "s",
                      ", ".join(named),
                      "" if not rest else ", and %d more -- -f json lists them" % rest,
                      "its" if len(report.not_asked) == 1 else "their"))
    judged = ""
    specified = ""
    if report.submodels_specified:
        specified = " (%d of them %s, not judged)" % (
            report.submodels_specified,
            "is a specification" if report.submodels_specified == 1
            else "are specifications")
    if not report.submodels_seen and report.judged:
        # Zero is falsy, so the clause below was suppressed on the one
        # input the front page calls the emptiest pass of the lot: an
        # environment holding nothing. The screen said `0 error(s)` and
        # nothing about having judged nothing.
        judged = "; no submodels to judge"
    elif report.submodels_seen:
        # Formatted first, joined after: composing a format string out
        # of an already-formatted one means a per cent sign in the
        # second kills the whole summary line.
        judged = "; judged %d of %d submodel%s" % (
            report.submodels_judged, report.submodels_seen,
            "" if report.submodels_seen == 1 else "s") + specified
    # The verdict the caller reached, or this report's own reading of
    # itself when nobody said. Both branches wear it: the clean one
    # already led with `ok`, and the branch a stranger actually lands on
    # -- the one with findings -- led with a count, so the run the front
    # page sends every newcomer to was the one run that printed no
    # verdict at all. It has eighty-seven warnings, no errors, and
    # leaves by 0.
    verdict = "FAILED" if (not report.ok if failed is None else failed) else "ok"
    if report.ok and not report.findings and not report.notes:
        # "rules registered", not "rules checked": a Technical Data file
        # is not judged by 02004's fifty-two, and a run that says it
        # checked them has told the reader something it did not do.
        lines.append("%s -- %s (%d rules registered%s%s)%s"
                     % (verdict, report.path, report.checked, judged,
                        unasked, incomplete))
    else:
        # The third count is INFO findings. It said "note(s)" and the
        # report has notes of its own, printed above and not counted
        # here -- one word for two things, with a run that printed a note
        # and summarised "0 note(s)" as the proof.
        # And whether the counts above describe the whole input. A refused
        # file summarises as one error, which is what a judged file that
        # failed looks like -- the JSON report grew a field to tell those
        # apart and the person at the terminal is owed the same sentence.
        lines.append("%s -- %d error(s), %d warning(s), %d info -- %s%s%s%s"
                     % (verdict,
                        report.count(Severity.ERROR), report.count(Severity.WARNING),
                        report.count(Severity.INFO), report.path, judged, unasked,
                        incomplete))
    return "\n".join(lines)
