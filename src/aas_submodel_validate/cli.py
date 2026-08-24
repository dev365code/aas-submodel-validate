"""The command line. Exit codes are the API a build pipeline calls:
0 clean, 1 findings at error severity, 2 could not run."""
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
    parser.add_argument("path", help=".aasx, AAS environment .json/.xml, or a bare Submodel .json")
    parser.add_argument("-f", "--format", choices=("text", "json"), default="text")
    parser.add_argument("-q", "--quiet", action="store_true", help="exit code only")
    parser.add_argument("--version", action="version",
                        version="aas-submodel-validate %s" % __version__)
    args = parser.parse_args(argv)

    try:
        report = runner.run(args.path)
    except UnreadablePath as exc:
        print("smtv: %s" % exc, file=sys.stderr)
        return EXIT_ERROR

    if not args.quiet:
        if args.format == "json":
            print(json.dumps(report.as_dict(), indent=2))
        else:
            print(render(report))
    return EXIT_OK if report.ok else EXIT_FINDINGS
