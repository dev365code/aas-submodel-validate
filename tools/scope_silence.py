"""How many rules stop being asked when one identifier is wrong.

`docs/divergences.md` #23 records the shape: a row whose `semanticId`
does not match is never entered, so every rule beneath it leaves the run
with it. The entry says so in prose and gives a number. This measures
it, because a number in a published document that nothing recomputes is
a number that was true once.

Two shapes of wrong identifier, and they are not equally dangerous:

- **tail** -- the last character, which is what a template version bump
  writes (`.../2/0` to `.../2/1`, `#003` to `#004`). The near-miss lint
  exists for exactly this and catches it.
- **middle** -- a character inside a path segment that is not the last,
  which is what a hand-edited file gets. #22 records that this defeats
  the lint's segment comparison, and then nothing speaks at all.

The difference between the two numbers is the whole argument for the
lint, and for what is still missing after it.

Neither number is a verdict on a file anyone has. Both are measured
against the fixtures in `tests/builders.py`, which are conformant by
construction -- so a rule going quiet here is a rule that would have
gone quiet on a real file with the same defect.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from aas_submodel_validate import runner  # noqa: E402
from aas_submodel_validate.rules import dbp_tables, hd_tables, td_tables  # noqa: E402
from builders import build_aasx, dbp_env, hd_env, td_env  # noqa: E402

PACKS = (("hd", hd_tables, hd_env), ("td", td_tables, td_env), ("dbp", dbp_tables, dbp_env))
#: The lints are the only thing that speaks when a row is not entered, so
#: they are counted apart from findings about the file's content.
LINTS = ("HDL1", "HDL2", "TDL1", "TDL2")


def drift(value: str, mode: str) -> str:
    """The same identifier, spelled one character wrong."""
    if mode == "tail":
        return value[:-1] + ("1" if value[-1] != "1" else "2")
    if "/" in value:
        parts = value.split("/")
        for index in range(len(parts) - 2, 0, -1):
            if len(parts[index]) > 3:
                parts[index] = parts[index][:2] + "Z" + parts[index][3:]
                return "/".join(parts)
    if "#" in value:
        head, _, tail = value.rpartition("#")
        return head[:-1] + "9#" + tail
    return value[:2] + "Z" + value[3:]


def _wear(node, sid: str, mode: str, changed: list) -> None:
    if isinstance(node, dict):
        for key in (node.get("semanticId") or {}).get("keys") or []:
            if key.get("value") == sid:
                key["value"] = drift(sid, mode)
                changed.append(sid)
        for value in node.values():
            _wear(value, sid, mode, changed)
    elif isinstance(node, list):
        for value in node:
            _wear(value, sid, mode, changed)


def _judge(directory: str, environment: dict, tag: str):
    path = build_aasx(
        os.path.join(directory, tag + ".aasx"),
        payload=json.dumps(environment).encode("utf-8"),
        files=(("aasx/files/manual.pdf", b"%PDF-1.4"),),
    )
    return {finding.id for finding in runner.run(str(path)).findings}


def measure(mode: str):
    """(rows tried, rows that produced nothing, rows only a lint spoke for)."""
    tried, mute, lint_only, detail, absent = 0, [], [], [], []
    with tempfile.TemporaryDirectory() as directory:
        for name, tables, make in PACKS:
            base = _judge(directory, make(), name + "-base")
            for index, row in enumerate(tables.ROWS):
                sid = row.get("sid")
                if not sid:
                    continue
                environment = copy.deepcopy(make())
                changed = []
                _wear(environment, sid, mode, changed)
                if not changed:
                    absent.append(row["id"])
                    continue          # the fixture does not carry this row
                tried += 1
                new = _judge(directory, environment, "%s-%d" % (name, index)) - base
                if not new:
                    mute.append(row["id"])
                    detail.append((row["id"], row["label"], "nothing"))
                elif new <= set(LINTS):
                    lint_only.append(row["id"])
                    detail.append((row["id"], row["label"], "only " + ", ".join(sorted(new))))
    return tried, mute, lint_only, detail, absent


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("tail", "middle", "both"), default="both")
    parser.add_argument("--verbose", action="store_true", help="name every row")
    args = parser.parse_args(argv)

    for mode in (("tail", "middle") if args.mode == "both" else (args.mode,)):
        tried, mute, lint_only, detail, absent = measure(mode)
        # The denominator, said out loud. Seventeen generated rows do not
        # appear in the fixtures at all, so this measures 69 of 86 and a
        # reader who takes 24 against 86 has a different, smaller number
        # than the one measured.
        print("%s: %d of %d generated rows are carried by the fixtures; of those, "
              "%d produced nothing at all and %d spoke only through a lint"
              % (mode, tried, tried + len(absent), len(mute), len(lint_only)))
        if args.verbose:
            for rid, label, what in detail:
                print("    %-9s %-34s %s" % (rid, label[:34], what))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
