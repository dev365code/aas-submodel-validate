"""The command line. Exit codes are the API a build pipeline calls:
0 clean, 1 findings at error severity, 2 could not run -- which covers a
path that cannot be read and an input this reader refused, because
nothing about either was judged. A report may still be printed on 2,
saying what was refused and what to do about it.

64 is a mistake in how the tool was called -- an unknown option, a
missing argument, a value outside the choices, a second path, or two
flags that contradict. It was 2 until this release, so
a caller branching on 2 could not tell "your file could not be judged"
from "you spelled the flag wrong"; 2 now means only the first. 0.3.0
announced the change one release ahead for callers who branch on it."""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from typing import Optional

from . import __version__, runner, tablegen
from . import bundle as bundling
from ._terminal import survive
from .example import NotBundled, bundled_example, example_name
from .report import render

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2
EXIT_USAGE = 64

#: What a person is told when a file was refused or a rule could not run:
#: once, on stderr, after the report -- never in a finding's remedy, so that
#: the report itself is the same bytes with or without it.
REFUSED = ("If you believe this file is valid, run the same command again with "
           "--bug-report and attach the bundle to an issue.")
CRASHED = ("This is a defect in this tool, not in your file. A diagnostic bundle was "
           "written to {path}. Attach it to an issue: "
           "https://github.com/dev365code/aas-submodel-validate/issues")
SHOWN = ("This is a defect in this tool, not in your file. The diagnostic bundle is "
         "above and was not written, as --show-bundle asks. Attach it to an issue: "
         "https://github.com/dev365code/aas-submodel-validate/issues")
SENT = "Nothing was sent."
#: The findings that say an input, or part of it, was refused rather than
#: judged: the package (X1, X2), a document that would not parse -- or names
#: another metamodel edition -- (X3), and this reader's own bound (X5). Not X6:
#: a path this reader could not open as an input at all -- nothing there, not
#: a regular file, not permitted, not a kind it reads -- is the caller's to
#: correct, and nothing is gained by asking them to report it.
REFUSALS = ("X1", "X2", "X3", "X5")


def _say(*parts) -> None:
    """A line for the person running the check: on stderr, or nowhere when
    there is no stderr. `print(file=None)` writes to stdout, which is where the
    report is -- with stderr closed (`2>&-`, or pythonw with no console) a line
    meant for a person would land inside the JSON a machine was about to read.

    The report goes first: stdout is flushed before the line is written, so a
    log that merges the two streams reads report, then line. And a stderr that
    is there and cannot be written -- a pipe whose reader has gone, a full disk
    -- is let go of rather than raised: the line was for a person who is not
    reading, and without this, it or the interpreter's own flush at exit moved
    the exit code to 120."""
    if sys.stderr is None:
        return
    with contextlib.suppress(OSError, ValueError, AttributeError):
        sys.stdout.flush()
    try:
        print(*parts, file=sys.stderr)
        sys.stderr.flush()
    except (OSError, ValueError):
        sys.stderr = None


def _refused(report) -> bool:
    """A refusal, or a rule that could not run -- but not one that ran out of
    memory or stack, whose remedy says that is not a defect in the file or in
    this tool, and a sentence asking for a bug report would contradict it."""
    return any(finding.id in REFUSALS
               or (finding.violation.message == runner.COULD_NOT_RUN
                   and finding.violation.fix != runner.RESOURCE_REMEDY)
               for finding in report.findings)


def _options(args) -> list:
    """The options a run was given, by name and chosen value only."""
    chosen = [flag for flag, on in (
        ("--quiet", args.quiet), ("--warnings-as-errors", args.warnings_as_errors),
        ("--strict-meta", args.strict_meta), ("--allow-unmatched", args.allow_unmatched),
        ("--show-meta", args.show_meta), ("--require-all-judged", args.require_all_judged),
        ("--bug-report", args.bug_report), ("--show-bundle", args.show_bundle),
        ("--no-bundle", args.no_bundle)) if on]
    # Values from a closed list only: each is one of the parser's choices.
    for flag, value in (("--format", args.format if args.format != "text" else None),
                        ("--meta", args.meta), ("--profile", args.profile)):
        if value is not None:
            chosen.append("%s=%s" % (flag, value))
    return chosen


def _bundle(args, path, report, exit_code, started, *, trigger, error=None):
    """Draw the bundle, then write it unless only drawing was asked for. A
    bundle that cannot be drawn or written is said so, once, and the run goes
    on: it is never a reason for the exit code to move. Not only a directory
    nobody can write to -- anything in here that fails."""
    try:
        made = bundling.build(path=path, options=_options(args),
                              report=report.as_dict() if report is not None else None,
                              exit_code=exit_code, seconds=time.perf_counter() - started,
                              trigger=trigger, note=args.note, out=args.bundle_out,
                              template=args.template is not None, example=args.example,
                              error=error)
        _say(bundling.dumps(made) if args.show_bundle else made["readable"])
        if args.show_bundle:
            if trigger == "crash":
                _say(SHOWN)
            _say(SENT)
            return None
        return bundling.write(made, args.bundle_out)
    except Exception as exc:                # noqa: BLE001 -- the run's report and exit code are not the bundle's to change
        reason = ((exc.strerror if isinstance(exc, OSError) else None)
                  or "%s in this tool" % type(exc).__name__)
        _say("The diagnostic bundle could not be written: %s. %s" % (reason, SENT))
        return None


def _after(args, path, report, exit_code, started) -> None:
    """What follows a run on stderr: the bundle, where one was asked for, or
    one sentence saying how to ask for it, where the input was refused."""
    refused = report is None or _refused(report)
    if args.bug_report or args.show_bundle:
        where = _bundle(args, path, report, exit_code, started,
                        trigger="refusal" if refused else "manual")
        if where is not None:
            _say("A diagnostic bundle was written to %s." % where)
            _say(SENT)
    elif refused and report is not None:
        _say(REFUSED)


class _Parser(argparse.ArgumentParser):
    """An `ArgumentParser` whose usage errors leave by 64, not by 2.

    Only `error` is overridden. `exit` is what `--help` and `--version`
    leave through, and both of those are 0: they are not mistakes, and
    routing them through here too would make asking for the help page a
    failure in every pipeline that runs it.

    The message stays argparse's own. Writing it out here with the code
    changed would drift from argparse the moment either side moved, and
    would be untranslated wherever argparse is not -- the code is the
    contract, the sentence is argparse's to phrase.

    The number is written down rather than read from `os.EX_USAGE`,
    which is 64 on Unix and does not exist on Windows. Reading it there
    raises at import, which is a worse failure than the one it avoids.
    """

    def error(self, message):
        # argparse prints the usage block and the sentence, then leaves by
        # 2. The printing is what is wanted and the code is not, so the
        # exit is suppressed and replaced. The replacement is outside the
        # suppression rather than inside the `except`, so that this still
        # leaves by 64 if a future argparse returns from `error` instead
        # of raising -- falling through to the caller would hand `None`
        # to the loader two calls later, which is the traceback this
        # parser exists to prevent.
        with contextlib.suppress(SystemExit):
            super().error(message)
        raise SystemExit(EXIT_USAGE)


def main(argv: Optional[list] = None) -> int:
    survive()
    parser = _Parser(
        prog="smtv",
        description="Validate an AAS submodel against its IDTA template, offline.",
        # Someone wiring this into a build reads `--help` before a
        # README, so the codes they will branch on have to be here. They
        # were on the front page only, which put them where the reader
        # who depends on them was least likely to look.
        # Wrapped by hand: a raw-description epilog is printed as
        # written, and this ran off the eightieth column in one line.
        # A line about what a verdict is, where somebody wiring this into
        # a build reads first. The scope document says it and the front
        # page says it two thirds down a section; neither is in front of
        # the person deciding what to do with the exit code.
        epilog="a verdict here is conformance to a submodel template. Where\n"
               "this tool reads a regulation it reports where a published\n"
               "reading of it and a template disagree, which is not a\n"
               "determination of compliance and not legal advice.\n"
               "\n"
               "exit codes:\n"
               "  0  nothing at error severity\n"
               "  1  at least one error -- or a warning, under -W\n"
               "  2  could not run: a path that cannot be read, or an input\n"
               "     this reader refused. Nothing was judged, so neither\n"
               "     of those is a verdict.\n"
               " 64  a mistake in how this was called (EX_USAGE): an unknown\n"
               "     option, a missing argument, a value outside the choices,\n"
               "     a second path, or two flags that contradict. This was 2\n"
               "     before 0.4.0, which is why 2 above no longer covers it.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?",
                        help=".aasx, AAS environment .json/.xml, or a bare Submodel .json")
    parser.add_argument("-f", "--format", choices=("text", "json"),
                        default="text",
                        help="text for a person, json for a pipeline; the "
                             "JSON shape is described in this project's "
                             "docs/report-schema.md, which a clone and the "
                             "source distribution carry")
    parser.add_argument("-q", "--quiet", action="store_true", help="exit code only")
    parser.add_argument("-W", "--warnings-as-errors", action="store_true",
                        help="exit 1 on warnings too")
    parser.add_argument("--meta", choices=("error", "warning", "info"),
                        default=None, metavar="LEVEL",
                        help="severity for the relayed metamodel channel: "
                             "error, warning (the default), or info -- which "
                             "keeps reporting it while leaving it out of what "
                             "-W fails on")
    parser.add_argument("--strict-meta", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--allow-unmatched", action="store_true",
                        help="an input with no known submodel becomes a note, not an error")
    parser.add_argument("--show-meta", action="store_true",
                        help="list the relayed metamodel findings instead of "
                             "folding them into one line")
    parser.add_argument("--require-all-judged", action="store_true",
                        help="exit 1 unless every submodel in the input was "
                             "judged, not only the ones this tool has a "
                             "table for -- and unless there was one to judge")
    from .rules.battery import settles_only
    from .rules.profiles import KEYS as _PROFILE_KEYS
    parser.add_argument("--profile", choices=_PROFILE_KEYS + settles_only(),
                        metavar="IDTA",
                        help="which template answers where two publish one "
                             "submodel identifier: %s choose the table that "
                             "judges; %s only settle which template the file "
                             "claims to be, because this tool has a table for "
                             "neither side of that collision"
                             % (", ".join(_PROFILE_KEYS), ", ".join(settles_only())))
    parser.add_argument("--template", metavar="FILE",
                        help="judge against an IDTA-shaped template file of "
                             "your own. Only what a template states is "
                             "checked: which elements, of which kind, under "
                             "which identifiers, how many of each, the "
                             "valueType each declares, and a list's item "
                             "type. An AllowedIdShort pattern is read into "
                             "the table and reported only by a pack's own "
                             "lint, so a table built from your file carries "
                             "it and says nothing about it; one this reader "
                             "cannot read is named in a note instead. The "
                             "hand-written rules and recorded readings that "
                             "come with a pack are not derivable from a "
                             "template and do not apply. A verdict against a "
                             "template you supplied is not a statement about "
                             "conformance to a published IDTA template")
    parser.add_argument("--example", action="store_true",
                        help="judge the official IDTA 02004 example that "
                             "travels in this package; needs no file of your "
                             "own, no repository and no network")
    parser.add_argument("--rules", action="store_true",
                        help="list every rule and exit")
    parser.add_argument("--bug-report", action="store_true",
                        help="write a diagnostic bundle for this run: structure, "
                             "counts and rule ids, nothing from the file. A "
                             "summary is shown, the bundle is written here, and "
                             "nothing is sent")
    parser.add_argument("--note", metavar="TEXT",
                        help="a sentence of your own to put in the bundle")
    parser.add_argument("--bundle-out", metavar="DIR",
                        help="where to write the bundle (default: here)")
    parser.add_argument("--show-bundle", action="store_true",
                        help="show the bundle and write nothing")
    parser.add_argument("--no-bundle", action="store_true",
                        help="do not write a bundle when this tool fails on a file")
    parser.add_argument("--version", action="version",
                        version="aas-submodel-validate %s" % __version__)
    args = parser.parse_args(argv)

    if args.strict_meta and args.meta not in (None, "error"):
        # `--strict-meta` is the older spelling of `--meta error`, and
        # `args.meta or args.strict_meta` let the newer one drop it
        # without a word -- so a build pinned on `--strict-meta` went
        # green the moment anyone added `--meta info` beside it. That is
        # the failure the dial was introduced to end, arriving through
        # the dial. Agreeing is fine; disagreeing is the caller's to
        # resolve.
        parser.error("--strict-meta is --meta error; it cannot be combined "
                     "with --meta %s" % args.meta)
    if args.rules:
        # One statable rule rather than a line drawn where somebody
        # noticed. `--rules` judges nothing, so every flag about judging
        # is a question it does not answer -- and answering a different
        # question in silence is the thing this tool refuses everywhere
        # else. `--meta` is the exception because it is not ignored: it
        # decides the severity the relayed channel is listed at, so the
        # listing really does differ.
        #
        # The first version of this refused a path and `--profile` and
        # went on quietly dropping `-q`, whose whole contract is "exit
        # code only", and `-f json`. Half a rule reads as arbitrary.
        # `is not None`, not truth. `args.path` is None when no path was
        # given and `""` when one was -- and a shell hands over `""` from
        # `smtv "$FILE"` with `FILE` unset. Read for truth, the two look
        # the same, so `--rules ""` printed the listing and dropped what
        # the caller typed: the silent answer to a different question
        # that this check exists to refuse, arriving through the shell
        # instead of through a flag.
        ignored = [name for name, given in (
            ("a path", args.path is not None), ("--profile", args.profile),
            ("-q", args.quiet), ("-f json", args.format != "text"),
            ("-W", args.warnings_as_errors),
            ("--allow-unmatched", args.allow_unmatched),
            ("--require-all-judged", args.require_all_judged),
            ("--show-meta", args.show_meta),
            # `--template` decides which table judges, which is the
            # strongest case on this list for a flag `--rules` would
            # have to ignore. It was added to the parser and not to
            # here, so `--rules --template /no/such/file.json` printed
            # the listing and exited 0 -- the silent answer to a
            # different question that the comment above is about.
            #
            # And then added here reading for truth, two entries below
            # the one that carries the paragraph about why that is
            # wrong: `--template ""` is what a shell hands over from
            # `--template "$TPL"` with `TPL` unset, and it printed the
            # listing and left by 0. Six entries on this list take a
            # value -- a path, `--profile`, `-f`, `--template`, `--note`
            # and `--bundle-out` -- and the other five are safe:
            # the path, `--note` and `--bundle-out` by the same
            # `is not None` the paragraph above is about, and `--profile`
            # and `-f` by `choices`, which refuses an empty string before
            # this runs.
            #
            # That count was written by eye three times and was wrong
            # three times -- two, then three, and `-f` appeared in none
            # of them. It is now held by a gate that reads the entries
            # from this list and asks each `add_argument` whether it
            # takes a value, so the sentence cannot be the only witness
            # to its own number.
            ("--template", args.template is not None),
            # Everything about the bundle describes a run, and `--rules`
            # is not one.
            ("--bug-report", args.bug_report), ("--show-bundle", args.show_bundle),
            ("--no-bundle", args.no_bundle), ("--note", args.note is not None),
            ("--bundle-out", args.bundle_out is not None)) if given]
        if ignored:
            parser.error("--rules lists the rules and judges nothing, so it "
                         "would ignore %s; --meta (or --strict-meta) is what "
                         "it reads, because that changes the listing"
                         % ", ".join(ignored))
    if args.rules and args.example:
        # `--rules` returned before the conflict check below, so one
        # flag was obeyed and the other silently dropped -- while
        # `--example <path>` is an error. The same kind of mistake,
        # answered two ways.
        parser.error("--example judges the bundled package and --rules lists "
                     "the rules; ask for one")
    if args.rules:
        from . import rules  # noqa: F401 - importing registers
        from .registry import all_rules
        from .runner import _meta_rule
        for rule in list(all_rules()) + [_meta_rule(args.meta or args.strict_meta)]:
            print("%-8s %-9s %-10s %s" % (rule.id, rule.kind, rule.severity, rule.title))
        return EXIT_OK
    if args.example and args.path is not None:
        # Whichever one won, the other would be judged without being
        # mentioned -- a report about bytes the caller did not think it
        # was reading, which is what the provenance field exists to stop.
        parser.error("--example judges the bundled package; give it or a "
                     "path, not both")
    if args.path is None and not args.example:
        # Asked of absence, not of emptiness. `smtv ""` took this branch
        # while `smtv " "` did not, so the one a shell produces by
        # accident was called a mistake in the call and the one a person
        # types was called a path -- a difference of one space deciding
        # which half of the exit-code contract a caller lands on. It
        # exited 2 at v0.3.0 and 64 would have been this release's own
        # regression. An empty path now reaches the loader and comes back
        # "no such file", like every other path with nothing behind it.
        parser.error("a path is required (or --example, or --rules)")

    if args.example:
        # A context manager, because from a zipapp the example is not a
        # file until something extracts it. `NotBundled` is exit 2 rather
        # than a traceback: nothing was judged, and 1 is the code for a
        # verdict.
        try:
            with bundled_example() as path:
                # Named by what it is, not by where it had to be put.
                # Extracting from an archive gives a temporary path that
                # is true, useless to the reader, and gone by the time
                # anyone looks it up; `provenance.inputSha256` still
                # identifies the bytes exactly.
                if not args.quiet and args.format == "text":
                    # The first screen a stranger sees is a verdict
                    # they did not ask for, on a file they did not
                    # name: ten findings, a folded channel and a
                    # summary counting eighty-seven. The front page says this is
                    # IDTA's own example and that its defects are the
                    # point; the terminal did not, and the file it names
                    # is fifty lines below.
                    print("judging IDTA's published 02004 2.0 example, "
                          "carried in this package -- unmodified, defects "
                          "and all.")
                return _judged(str(path), args, shown_as=example_name())
        except NotBundled as exc:
            print("smtv: %s" % exc, file=sys.stderr)
            return EXIT_ERROR
    return _judged(args.path, args)


def _judged(path: str, args, shown_as: Optional[str] = None) -> int:
    """The run, and the one place a defect escaping it is met. The bundle is
    written and the exception raised again, so the process leaves as it did
    before any bundle existed: a traceback and exit 1. A path the caller gave
    never arrives here as an exception -- the loader makes it `X6` -- so an
    `OSError` that does is this tool's, one of its own files it could not
    open. A pipe closed on the output is the exception: that is the reader of
    the output leaving, and it writes nothing."""
    started = time.perf_counter()
    try:
        return _judge(path, args, shown_as, started)
    except Exception as exc:
        if not isinstance(exc, BrokenPipeError) and not args.no_bundle:
            where = _bundle(args, path, None, 1, started, trigger="crash", error=exc)
            if where is not None:
                _say(CRASHED.format(path=where))
                _say(SENT)
        raise


def _judge(path: str, args, shown_as: Optional[str], started: float) -> int:
    try:
        report = runner.run(path, strict_meta=args.meta or args.strict_meta,
                            allow_unmatched=args.allow_unmatched,
                            profile=args.profile, template=args.template)
    except tablegen.TemplateRefused as refused:
        # 2, not 64 and not 1. Naming a file is not a mistake in how the
        # tool was called -- the flag was spelled right and the path was
        # given -- and the build tool's own 1 is a build tool's answer.
        # This is "could not judge the input", which is what every other
        # unreadable input here gets.
        print("smtv: %s" % refused, file=sys.stderr)
        _after(args, path, None, EXIT_ERROR, started)
        return EXIT_ERROR
    if shown_as:
        report.path = shown_as

    from .model import Severity
    # Reached before anything is printed, because the summary line now
    # states it. While the screen said nothing about the verdict the two
    # could not disagree; the measurement that ended that was `--example`
    # and `--example -W` printing byte-identical screens and leaving by
    # 0 and 1.
    #
    # `judged` is in here. Exit 2 is "could not run" and not "passed", so
    # a screen reading `ok` above a process leaving by 2 would be the
    # same lie one layer over. Which of the two it was stays legible: a
    # refused input still says `(not a full verdict: some of it was not
    # judged)`, which is how this report has always told them apart.
    expected = report.submodels_seen - report.submodels_specified
    # `judged < seen` alone read `0 < 0` as satisfied, so the flag failed
    # a file with one unjudged submodel and passed one with none at all:
    # the risk ordering backwards, on the input an exporter is most
    # likely to produce by accident.
    short = bool(args.require_all_judged
                 and (report.submodels_judged < expected
                      or not report.submodels_seen))
    # Every warning, including the relayed ones. A version of this
    # exempted that channel, on the reasoning that no edit to a submodel
    # can clear a finding about the metamodel -- which is false, and the
    # example this project ships disproves it: 45 of its 77 relayed
    # findings are about `.submodels`, 33 of them an idShort that has
    # only to be deleted. A submodel with an empty `id` raises one
    # relayed finding and nothing else, and passed `-W` while the summary
    # line above it counted the warning. `--meta info` is the way to say
    # this channel should not decide a build, and it says so out loud.
    failed = (not report.judged or not report.ok or short
              or (args.warnings_as_errors
                  and report.count(Severity.WARNING) > 0))

    if not args.quiet:
        if args.format == "json":
            print(json.dumps(report.as_dict(), indent=2))
        else:
            print(render(report, show_meta=args.show_meta, failed=failed))
    if not report.judged:
        # Nothing reached the rules, so there is no verdict to report --
        # and 1 is the code for a verdict. Said on stderr as well, since
        # -q suppressed the report that would otherwise explain it.
        #
        # The refusal's own sentence where there is one. A path that was
        # never opened now carries a finding, which is the machine
        # contract; the person who typed a wrong filename is owed "no
        # such file" and not a general statement that nothing was judged,
        # and the two audiences are why one line goes to each stream. That
        # statement said "could be read", and of a document read to the end
        # and stopped while building it was false; what is known is that
        # nothing was judged.
        refusal = next((finding.violation.message for finding in report.findings
                        if finding.id == "X6"), None)
        print("smtv: %s"
              % (refusal or "nothing in %s was judged" % path), file=sys.stderr)
        _after(args, path, report, EXIT_ERROR, started)
        return EXIT_ERROR
    if short:
        # The report has carried this number since day one; a caller
        # reading only the exit code could not see it. An unjudged
        # submodel is not a defect in the file -- an environment holds
        # submodels this tool has no business judging -- so it stays out
        # of the default verdict and becomes one only when asked for.
        # The number compared, not the number seen: with a template in
        # the file those differ, and a caller reading only this line was
        # told two were missing when one was.
        print("smtv: judged %d of %d submodel%s; --require-all-judged was given"
              % (report.submodels_judged, expected,
                 "" if expected == 1 else "s"), file=sys.stderr)
    code = EXIT_FINDINGS if failed else EXIT_OK
    _after(args, path, report, code, started)
    return code
