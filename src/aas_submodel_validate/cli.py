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
from .example import bundled_example
from .loader import UnreadablePath
from .report import render

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="smtv",
        description="Validate an AAS submodel against its IDTA template, offline.")
    parser.add_argument("path", nargs="?",
                        help=".aasx, AAS environment .json/.xml, or a bare Submodel .json")
    parser.add_argument("-f", "--format", choices=("text", "json"), default="text")
    parser.add_argument("-q", "--quiet", action="store_true", help="exit code only")
    parser.add_argument("-W", "--warnings-as-errors", action="store_true",
                        help="exit 1 on this tool's warnings too (not the "
                             "relayed metamodel channel -- see --strict-meta)")
    parser.add_argument("--strict-meta", action="store_true",
                        help="metamodel findings become errors instead of warnings")
    parser.add_argument("--allow-unmatched", action="store_true",
                        help="an input with no known submodel becomes a note, not an error")
    parser.add_argument("--show-meta", action="store_true",
                        help="list the relayed metamodel findings instead of "
                             "folding them into one line")
    parser.add_argument("--require-all-judged", action="store_true",
                        help="exit 1 unless every submodel in the input was "
                             "judged, not only the ones this tool has a table for")
    from .rules.battery import _settles_only
    from .rules.profiles import KEYS as _PROFILE_KEYS
    parser.add_argument("--profile", choices=_PROFILE_KEYS + _settles_only(),
                        metavar="IDTA",
                        help="which template answers where two publish one "
                             "submodel identifier: %s choose the table that "
                             "judges; %s only settle which template the file "
                             "claims to be, because this tool has a table for "
                             "neither side of that collision"
                             % (", ".join(_PROFILE_KEYS), ", ".join(_settles_only())))
    parser.add_argument("--example", action="store_true",
                        help="judge the official IDTA 02004 example that "
                             "travels in this package; needs no file of your "
                             "own, no repository and no network")
    parser.add_argument("--rules", action="store_true",
                        help="list every rule and exit")
    parser.add_argument("--version", action="version",
                        version="aas-submodel-validate %s" % __version__)
    args = parser.parse_args(argv)

    if args.rules:
        from . import rules  # noqa: F401 - importing registers
        from .registry import all_rules
        from .runner import _meta_rule
        for rule in list(all_rules()) + [_meta_rule(args.strict_meta)]:
            print("%-8s %-9s %-10s %s" % (rule.id, rule.kind, rule.severity, rule.title))
        return EXIT_OK
    if args.example and args.path:
        # Whichever one won, the other would be judged without being
        # mentioned -- a report about bytes the caller did not think it
        # was reading, which is what the provenance field exists to stop.
        parser.error("--example judges the bundled package; give it or a "
                     "path, not both")
    if args.example:
        args.path = str(bundled_example())
    if not args.path:
        parser.error("a path is required (or --example, or --rules)")

    try:
        report = runner.run(args.path, strict_meta=args.strict_meta,
                            allow_unmatched=args.allow_unmatched,
                            profile=args.profile)
    except UnreadablePath as exc:
        print("smtv: %s" % exc, file=sys.stderr)
        return EXIT_ERROR

    if not args.quiet:
        if args.format == "json":
            print(json.dumps(report.as_dict(), indent=2))
        else:
            print(render(report, show_meta=args.show_meta))
    if not report.judged:
        # Nothing reached the rules, so there is no verdict to report --
        # and 1 is the code for a verdict. Said on stderr as well, since
        # -q suppressed the report that would otherwise explain it.
        print("smtv: nothing in %s could be read, so nothing was judged"
              % args.path, file=sys.stderr)
        return EXIT_ERROR
    from .model import META_KIND, Severity
    # `-W` promotes this tool's warnings. The metamodel channel is
    # relayed from aas-core3.0 and has `--strict-meta` for exactly this,
    # and two flags governing one channel meant the broader one always
    # won: the official example ships eighty-seven warnings, seventy-
    # seven of them about IDTA's own concept descriptions, so `-W` failed
    # every build over findings no edit to the submodel could clear.
    ours = sum(1 for f in report.findings
               if f.severity is Severity.WARNING and f.rule.kind != META_KIND)
    failed = not report.ok or (args.warnings_as_errors and ours > 0)
    if args.require_all_judged and report.submodels_judged < report.submodels_seen:
        # The report has carried this number since day one; a caller
        # reading only the exit code could not see it. An unjudged
        # submodel is not a defect in the file -- an environment holds
        # submodels this tool has no business judging -- so it stays out
        # of the default verdict and becomes one only when asked for.
        print("smtv: judged %d of %d submodels; --require-all-judged was given"
              % (report.submodels_judged, report.submodels_seen), file=sys.stderr)
        failed = True
    return EXIT_FINDINGS if failed else EXIT_OK
