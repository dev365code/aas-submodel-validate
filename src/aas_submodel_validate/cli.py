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
                        help="exit 1 on warnings too")
    parser.add_argument("--strict-meta", action="store_true",
                        help="metamodel findings become errors instead of warnings")
    parser.add_argument("--allow-unmatched", action="store_true",
                        help="an input with no known submodel becomes a note, not an error")
    from .rules.profiles import KEYS as _PROFILE_KEYS
    parser.add_argument("--profile", choices=_PROFILE_KEYS, metavar="IDTA",
                        help="which template answers where two publish one "
                             "submodel identifier (%s)" % ", ".join(_PROFILE_KEYS))
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
    if not args.path:
        parser.error("a path is required (or --rules)")

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
            print(render(report))
    if not report.judged:
        # Nothing reached the rules, so there is no verdict to report --
        # and 1 is the code for a verdict. Said on stderr as well, since
        # -q suppressed the report that would otherwise explain it.
        print("smtv: nothing in %s could be read, so nothing was judged"
              % args.path, file=sys.stderr)
        return EXIT_ERROR
    from .model import Severity
    failed = not report.ok or (args.warnings_as_errors
                               and report.count(Severity.WARNING) > 0)
    return EXIT_FINDINGS if failed else EXIT_OK
