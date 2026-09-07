"""The command line. Exit codes are the API a build pipeline calls:
0 clean, 1 findings at error severity, 2 could not run -- which covers a
path that cannot be read and an input this reader refused, because
nothing about either was judged. A report may still be printed on 2,
saying what was refused and what to do about it."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from . import __version__, runner
from ._terminal import survive
from .example import NotBundled, bundled_example, example_name
from .loader import UnreadablePath
from .report import render

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


def main(argv: Optional[list] = None) -> int:
    survive()
    parser = argparse.ArgumentParser(
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
               "     of those is a verdict.",
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
    parser.add_argument("--example", action="store_true",
                        help="judge the official IDTA 02004 example that "
                             "travels in this package; needs no file of your "
                             "own, no repository and no network")
    parser.add_argument("--rules", action="store_true",
                        help="list every rule and exit")
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
        ignored = [name for name, given in (
            ("a path", args.path), ("--profile", args.profile),
            ("-q", args.quiet), ("-f json", args.format != "text"),
            ("-W", args.warnings_as_errors),
            ("--allow-unmatched", args.allow_unmatched),
            ("--require-all-judged", args.require_all_judged),
            ("--show-meta", args.show_meta)) if given]
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
    if args.example and args.path:
        # Whichever one won, the other would be judged without being
        # mentioned -- a report about bytes the caller did not think it
        # was reading, which is what the provenance field exists to stop.
        parser.error("--example judges the bundled package; give it or a "
                     "path, not both")
    if not (args.path or args.example):
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
                return _judge(str(path), args, shown_as=example_name())
        except NotBundled as exc:
            print("smtv: %s" % exc, file=sys.stderr)
            return EXIT_ERROR
    return _judge(args.path, args)


def _judge(path: str, args, shown_as: Optional[str] = None) -> int:
    try:
        report = runner.run(path, strict_meta=args.meta or args.strict_meta,
                            allow_unmatched=args.allow_unmatched,
                            profile=args.profile)
    except UnreadablePath as exc:
        print("smtv: %s" % exc, file=sys.stderr)
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
    # read)`, which is how this report has always told them apart.
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
        # such file" and not a general statement that nothing was read,
        # and the two audiences are why one line goes to each stream.
        refusal = next((finding.violation.message for finding in report.findings
                        if finding.id == "X6"), None)
        print("smtv: %s"
              % (refusal or "nothing in %s could be read, so nothing was judged"
                 % path), file=sys.stderr)
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
    return EXIT_FINDINGS if failed else EXIT_OK
