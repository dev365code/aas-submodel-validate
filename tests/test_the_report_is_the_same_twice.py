"""A report of the same input is the same report, in any process.

Not a property anybody thought to check, and one this project needs more
than most: a validator's whole value is that its answer today is the
answer it gave when somebody signed off on it. Two runs that disagree
about the order of a list are two reports a reader cannot diff.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Two seeds is enough to see it and cheap enough to always run. The
#: defect this pins gave five different orders for five seeds.
SEEDS = ("0", "1")


def test_rules_not_asked_is_ordered_the_same_in_any_process():
    """`rows_not_reached` sorts by the position a rule has in its table,
    and falls back to one shared position for anything the tables do not
    place. `sorted` is stable, so everything sharing that fallback keeps
    the order it arrived in -- and it arrives out of a `set`, whose
    iteration order is string-hash order and is randomised per process.

    Nothing reaches that fallback today: every analysed table is an
    imported module and every id in it is placed. It is reachable the
    moment a table is not a module, which is what the arriving
    `--template` mode makes one. Measured then: five seeds, five orders.

    The fix is one line -- break the tie on the id -- and it is here
    rather than with that mode because a fallback that is only correct
    while nothing takes it is not correct.
    """
    asking = (
        "import sys; sys.path[:0] = ['src']\n"
        "from aas_submodel_validate.rules import engine\n"
        "class C: pass\n"
        "c = C()\n"
        "c.__dict__['_smt_analysis'] = {'<not a module>': "
        "{'lost_candidates': ['TPL-E0%d' % i for i in range(1, 9)]}}\n"
        "print(','.join(engine.rows_not_reached(c)))\n")
    answers = set()
    for seed in SEEDS:
        done = subprocess.run([sys.executable, "-c", asking],
                              capture_output=True, text=True, cwd=str(ROOT),
                              env=dict(os.environ, PYTHONHASHSEED=seed))
        assert done.returncode == 0, done.stderr
        answers.add(done.stdout.strip())
    assert len(answers) == 1, (
        "two processes ordered the same rules differently: %s" % sorted(answers))


def test_the_same_input_gives_the_same_report_in_any_process(tmp_path):
    """And the whole document, which is what a reader actually diffs."""
    path = tmp_path / "env.json"
    path.write_text(json.dumps({"assetAdministrationShells": [], "submodels": []}),
                    encoding="utf-8")
    documents = set()
    for seed in SEEDS:
        done = subprocess.run(
            [sys.executable, "-m", "aas_submodel_validate", str(path), "-f", "json"],
            capture_output=True, text=True, cwd=str(ROOT),
            env=dict(os.environ, PYTHONPATH="src", PYTHONHASHSEED=seed))
        documents.add(done.stdout)
    assert len(documents) == 1, "the report is not the same document twice"
