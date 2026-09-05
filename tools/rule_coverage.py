#!/usr/bin/env python3
"""Every rule id fires somewhere in the suite, and the record is checked.

The suite writes .rule-coverage.json (conftest); this compares it with
the committed docs/rule-coverage.json and with the registry. Three
failures it exists for: a registered rule that never fired (dead or
untested -- indistinguishable), a fired id that is not registered (a
finding from nowhere), and a drift between the committed record and
reality (coverage moved and nobody said so).
"""
from __future__ import annotations

import argparse
import json
import pathlib as _pathlib
import sys
import sys as _sys
from pathlib import Path

# The package, from wherever this script is. `make` exports
# PYTHONPATH and the lint job installs the package first, but
# CI's wheel job installs nothing and an unpacked sdist has no
# install at all -- and `MANIFEST.in` grafts this directory for
# exactly that reader. Two scripts here already did this; the
# import added to all eight assumed the other six were as
# lucky.
_TOOLS_SRC = str(_pathlib.Path(__file__).resolve().parent.parent / "src")
if _TOOLS_SRC not in _sys.path:
    _sys.path.insert(0, _TOOLS_SRC)

from aas_submodel_validate._terminal import survive  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    survive()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true",
                        help="record the observed set as the new baseline")
    args = parser.parse_args()

    from aas_submodel_validate import rules  # noqa: F401 - importing registers
    from aas_submodel_validate.registry import all_rules
    registered = {rule.id for rule in all_rules()} | {"META"}

    observed_path = ROOT / ".rule-coverage.json"
    if not observed_path.exists():
        print("no .rule-coverage.json -- run the suite first", file=sys.stderr)
        return 1
    observed = set(json.loads(observed_path.read_text("utf-8")))

    if args.write:
        (ROOT / "docs" / "rule-coverage.json").write_text(
            json.dumps(sorted(observed), indent=0) + "\n", "utf-8")
        print("baseline written: %d ids" % len(observed))
        return 0

    baseline = set(json.loads((ROOT / "docs" / "rule-coverage.json").read_text("utf-8")))
    bad = 0
    for silent in sorted(registered - observed):
        print("never fired in the suite: %s" % silent, file=sys.stderr)
        bad = 1
    for ghost in sorted(observed - registered):
        print("fired but not registered: %s" % ghost, file=sys.stderr)
        bad = 1
    if observed != baseline:
        for gone in sorted(baseline - observed):
            print("in the baseline, no longer firing: %s" % gone, file=sys.stderr)
        for new in sorted(observed - baseline):
            print("firing but not in the baseline (add it deliberately): %s" % new,
                  file=sys.stderr)
        bad = 1
    if not bad:
        print("all %d rule ids fire somewhere, matching the baseline" % len(observed))
    return bad


if __name__ == "__main__":
    sys.exit(main())
