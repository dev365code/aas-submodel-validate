"""Is the run still fast enough, in units of the machine that is running?

Every other gate in this project asks whether the verdict is right. None of
them asks whether it arrived, and correct-and-unusable is a real state: the
table generator carries a quadratic today that only build-time inputs keep
away from a user, and nothing here would notice it moving.

**Seconds cannot be the budget.** A ceiling recorded on a laptop means
nothing on a runner, and the same runner is slower under load than idle, so
an absolute number is either loose enough to catch nothing or tight enough
to fail for reasons nobody caused. What is recorded is a *ratio* against a
yardstick measured in the same process in the same run.

**The ratio does not travel between platforms either**, so each one carries
what was measured on it and a platform with no record passes quietly --
there is no way to write a budget for a machine before a run on it.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import platform
import sys
import tempfile
import time
from typing import Optional

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUDGET_FILE = ROOT / "docs" / "time-budget.json"

# The package and this directory, from wherever this script is. `make`
# exports PYTHONPATH for the suite, but this target runs the file as a
# script, and an unpacked sdist has no install at all -- the same
# reader `MANIFEST.in` grafts `tools` for. Without the second entry the
# sibling this imports for the corpus is not importable as a package.
for _entry in (str(ROOT / "src"), str(ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

#: Half again as expensive is worth saying out loud; twice is a failure.
#: Both are generous on purpose: a gate that fires on runner noise is a gate
#: people learn to pass with a re-run, and then it is not a gate.
WARN_AT = 1.5
FAIL_AT = 2.0

#: Three passes, and the **fastest** one -- of the run and of the yardstick
#: alike. A median still carries whatever else the machine was doing; the
#: fastest pass is the one least interrupted, and it is the figure that
#: repeats.
PASSES = 3

#: The yardstick is sized by the clock, not by a repetition count: enough
#: rounds that one measurement takes at least this long. A few thousand
#: rounds is mostly scheduling, and then the ratio is noisier than either
#: number it is made of.
YARDSTICK_FLOOR_SECONDS = 0.05

#: What is timed. `corpus_pass` is the whole thing a caller experiences.
#: `rules_layer` is the layer with a cost history: the walk grew per-element
#: work when it started saying *which* element left rules unasked, and a
#: layer that has already grown once is the one worth watching separately.
#: A third will join them if template tables are ever generated at run time
#: rather than at build time -- that is where the quadratic lives.
LAYERS = ("corpus_pass", "rules_layer")


class Verdict:
    """What one layer's ratio means."""

    def __init__(self, factor: Optional[float], baseline: Optional[float]):
        self.factor = factor
        self.baseline = baseline
        self.warn = factor is not None and factor >= WARN_AT
        self.ok = factor is None or factor < FAIL_AT

    def __repr__(self):                     # pragma: no cover - diagnostics
        return "Verdict(factor=%r, ok=%r, warn=%r)" % (
            self.factor, self.ok, self.warn)


def judge(measured: float, baseline: Optional[float]) -> Verdict:
    """`measured` and `baseline` are both ratios against the yardstick, so
    the comparison is a pure number and the machine has cancelled out."""
    if not baseline:
        return Verdict(None, None)
    return Verdict(measured / baseline, baseline)


def platform_key() -> str:
    return platform.system() or "unknown"


def load() -> dict:
    return json.loads(BUDGET_FILE.read_text(encoding="utf-8"))


def budgets_for(recorded: dict, key: str) -> dict:
    return recorded.get("budgets", {}).get(key, {})


def _yardstick() -> float:
    """One unit of this machine, in seconds per ten thousand rounds.

    **Pure Python on purpose, and nothing this project defines.** A C
    routine barely notices which interpreter called it, while this project
    is Python all the way down -- so a C yardstick would read the same tree
    as much faster on one interpreter than another and the budgets would be
    about CPython releases rather than about this code. Dictionary, integer
    and string work in a loop is what the rules layer is when you look at
    it closely.

    And it must not call this project: a yardstick that did would slow down
    together with the regression it exists to catch, leaving the ratio flat
    while the wall clock doubled.
    """
    def work(rounds: int) -> int:
        counts: dict = {}
        total = 0
        for i in range(rounds):
            key = i & 1023
            counts[key] = counts.get(key, 0) + i
            total += len(str(key)) + (i % 7)
        return total

    rounds = 4096
    while True:
        start = time.perf_counter()
        work(rounds)
        spent = time.perf_counter() - start
        if spent >= YARDSTICK_FLOOR_SECONDS or rounds > 1 << 24:
            break
        rounds *= 2

    runs = []
    for _ in range(PASSES):
        start = time.perf_counter()
        work(rounds)
        runs.append((time.perf_counter() - start) / rounds)
    # Per ten thousand rounds rather than per round, so the budgets read in
    # the hundreds instead of the millions. Nothing about the comparison
    # changes; a number a person can hold in their head is easier to argue
    # with.
    return min(runs) * 10_000


def _corpus():
    """Every input `verdict_diff` puts both versions through -- the set this
    project already treats as its corpus, built once so the timing is the
    run and not the disk."""
    from tools import verdict_diff

    workspace = pathlib.Path(tempfile.mkdtemp(prefix="time-budget-"))
    return [path for _label, path in verdict_diff.build_corpus(workspace)]


def _rules_layer_input():
    """The official example, loaded once. Loading is not the rules layer."""
    from tools import verdict_diff

    from aas_submodel_validate.loader import load as load_input

    return load_input(verdict_diff.EXAMPLE)


#: A layer is timed in repetitions, not once, for the same reason the
#: yardstick is: a tenth of a millisecond is scheduling noise, and a ratio
#: made of two noisy numbers moves further than either. A layer already
#: slower than this floor is timed once, which is the corpus.
LAYER_FLOOR_SECONDS = 0.05


def _time(call) -> float:
    """Seconds for one call, taken from the fastest of several passes."""
    repeats = 1
    while True:
        start = time.perf_counter()
        for _ in range(repeats):
            call()
        spent = time.perf_counter() - start
        if spent >= LAYER_FLOOR_SECONDS or repeats > 1 << 14:
            break
        repeats *= 2

    runs = []
    for _ in range(PASSES):
        start = time.perf_counter()
        for _ in range(repeats):
            call()
        runs.append((time.perf_counter() - start) / repeats)
    return min(runs)


def measure() -> dict:
    """The layers, in seconds, and the yardstick beside them."""
    from aas_submodel_validate import runner
    from aas_submodel_validate.rules import engine, hd_tables, profiles

    corpus = _corpus()
    loaded = _rules_layer_input()

    def corpus_pass():
        for path in corpus:
            runner.run(path)

    def rules_layer():
        # The walk over the official example, and only the table that
        # answers for it: asking the other five would spend most of the
        # measurement on packs declining a file that is not theirs, and a
        # number made mostly of no-ops moves for reasons nobody caused. A
        # fresh context each time, because `analyze` caches per context --
        # timing a cache hit would measure nothing.
        engine.analyze(runner.Context(loaded, profiles.Selection(None)),
                       hd_tables)

    return {
        "yardstick_seconds": _yardstick(),
        "inputs": len(corpus),
        "layers": {"corpus_pass": _time(corpus_pass),
                   "rules_layer": _time(rules_layer)},
    }


def _ratios(measured: dict) -> dict:
    unit = measured["yardstick_seconds"]
    return {layer: seconds / unit
            for layer, seconds in measured["layers"].items()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="compare against the recorded budgets")
    parser.add_argument("--record", action="store_true",
                        help="print what this machine measures, for the file")
    args = parser.parse_args(argv)

    measured = measure()
    ratios = _ratios(measured)
    key = platform_key()

    if args.record:
        print(json.dumps({
            "platform": key,
            # Three significant figures, because a layer whose ratio is
            # under one would otherwise be recorded in a band wide enough
            # to hide a fifth of its cost.
            "budgets": {layer: float("%.3g" % ratio)
                        for layer, ratio in ratios.items()},
            "recorded_on": {
                "machine": platform.machine(),
                "python": platform.python_version(),
                "inputs": measured["inputs"],
                "yardstick_seconds": float("%.4g" % measured["yardstick_seconds"]),
                "absolute_seconds": {layer: float("%.4g" % seconds)
                                     for layer, seconds
                                     in measured["layers"].items()},
            }}, indent=1))
        return 0

    budgets = budgets_for(load(), key)
    bad = False
    for layer in LAYERS:
        verdict = judge(ratios[layer], budgets.get(layer))
        if verdict.factor is None:
            print("%-12s %7.1f units, no budget recorded for %s"
                  % (layer, ratios[layer], key))
            continue
        note = "over budget" if not verdict.ok else (
            "close to budget" if verdict.warn else "")
        print("%-12s %7.1f units, %.2fx of its budget %s"
              % (layer, ratios[layer], verdict.factor, note))
        bad = bad or not verdict.ok
    return 1 if bad else 0


if __name__ == "__main__":                  # pragma: no cover
    raise SystemExit(main())
