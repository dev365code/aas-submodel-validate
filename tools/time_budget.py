"""Is the run still fast enough, in units of the machine that is running?

Every other gate in this project asks whether the verdict is right. None of
them asks whether it arrived, and correct-and-unusable is a real state: the
walk here was quadratic once, correct the whole time, and what noticed was
a person waiting.

What this does **not** watch is worth saying first. `_qualify_repeats` in
`tools/extract_smt_rules.py` counts occurrences inside a comprehension over
the same list, which is quadratic in the row count and sits before its own
early return. It is measured, it is real, and it is unreachable today
because the generator runs at build time over small vendored templates --
so no layer below times it. Generating a table from a caller's file would
reach it, and that is when this file grows a third layer, not before.

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
import atexit
import json
import os
import pathlib
import platform
import shutil
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

#: What is timed, and each of these exists because the others cannot see
#: what it sees.
#:
#: `cold_start` is one whole invocation in a fresh interpreter -- the only
#: figure that is the time a person actually waits. Everything else here
#: imports the package before the clock starts and then repeats a warm
#: call, so import-time work is measured as zero by construction: an index
#: built at import that made the command 2.3x slower left every other layer
#: reading 0.98x.
#:
#: `corpus_pass` is every input the project already treats as its corpus,
#: judged and rendered. Rendering is in because a caller waits for it too,
#: and `runner.run` alone left the report layer unmeasured.
#:
#: `scale` is one wide submodel, and it is here because the corpus cannot
#: do this job: its largest scope holds fifteen elements, so a change that
#: is superlinear in siblings barely moves it. A genuine quadratic added to
#: the walk read 1.0x on the corpus and 1.7x on a real file with three
#: thousand elements.
#:
#: `rules_layer` is the walk over the official example, the layer with a
#: cost history -- it grew per-element work when it started saying which
#: element left rules unasked.
#:
#: A fifth joins them if template tables are ever generated at run time
#: rather than at build time -- that is where the generator's quadratic
#: lives, and nothing here times it today.
LAYERS = ("cold_start", "corpus_pass", "scale", "rules_layer")

#: A layer whose absolute time collapses has stopped doing its work, and a
#: ratio cannot tell that from a fast machine. Moving `analyze`'s cache from
#: per-context to global made the walk 1500x faster and the gate said "far
#: under budget" and passed. Load noise is tens of percent; this is orders,
#: so the two separate cleanly.
COLLAPSED_BELOW = 0.2

#: More passes when the passes disagree. Under load the yardstick and the
#: layer are disturbed differently even side by side, and the fastest of
#: three can still be a pass where only one of them got a clean window.
#: Measured: a loaded machine put an unchanged tree between 0.54x and 1.74x
#: over twenty-four runs of three passes.
SPREAD_TOLERANCE = 1.25
MAX_PASSES = 12


#: Far *under* budget is worth saying too. The whole design rests on the
#: yardstick being a stable unit, so an unexplained drop is as informative
#: as a rise -- a yardstick that slowed down greens every layer at once,
#: silently, and that is the failure this band exists to make visible. It
#: does not fail: being fast is not a defect, and a machine may simply be
#: faster than the one that recorded the budget.
UNDER_AT = 0.5


class Verdict:
    """What one layer's ratio means."""

    def __init__(self, factor: Optional[float], baseline: Optional[float]):
        self.factor = factor
        self.baseline = baseline
        self.warn = factor is not None and factor >= WARN_AT
        self.under = factor is not None and factor < UNDER_AT
        self.ok = factor is None or factor < FAIL_AT

    def __repr__(self):                     # pragma: no cover - diagnostics
        return "Verdict(factor=%r, ok=%r, warn=%r)" % (
            self.factor, self.ok, self.warn)


def judge(measured: float, baseline: Optional[float]) -> Verdict:
    """`measured` and `baseline` are both ratios against the yardstick, so
    what is compared is a pure number.

    A *missing* baseline is the ordinary state of a platform nothing has
    run on, and it passes. A baseline that is present but cannot be
    divided by -- zero, or negative -- is a corrupt record, and the two
    must not share a branch: written as one `if not baseline`, a budget
    zeroed by an editing accident reported "no budget recorded for Darwin"
    and passed, which is the sentence a reader would take as proof the
    file was untouched.
    """
    if baseline is None:
        return Verdict(None, None)
    if baseline <= 0:
        raise ValueError(
            "a budget of %r cannot be compared against; a platform with no "
            "budget leaves the entry out rather than zeroing it" % baseline)
    return Verdict(measured / baseline, baseline)


def platform_key() -> str:
    return platform.system() or "unknown"


def load() -> dict:
    return json.loads(BUDGET_FILE.read_text(encoding="utf-8"))


def budgets_for(recorded: dict, key: str) -> dict:
    return recorded.get("budgets", {}).get(key, {})


def _yardstick_rounds() -> int:
    """How many rounds one yardstick measurement takes, sized by the clock."""
    rounds = 4096
    while True:
        start = time.perf_counter()
        _work(rounds)
        spent = time.perf_counter() - start
        if spent >= YARDSTICK_FLOOR_SECONDS or rounds > 1 << 24:
            break
        rounds *= 2
    return rounds


def _work(rounds: int) -> int:
    counts: dict = {}
    total = 0
    for i in range(rounds):
        key = i & 1023
        counts[key] = counts.get(key, 0) + i
        total += len(str(key)) + (i % 7)
    return total


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
    rounds = _yardstick_rounds()
    runs = []
    for _ in range(PASSES):
        start = time.perf_counter()
        _work(rounds)
        runs.append((time.perf_counter() - start) / rounds)
    # Per ten thousand rounds rather than per round, so the budgets read in
    # the hundreds instead of the millions. Nothing about the comparison
    # changes; a number a person can hold in their head is easier to argue
    # with.
    return min(runs) * 10_000


def _corpus():
    """Every input `verdict_diff` puts both versions through -- the set this
    project already treats as its corpus.

    Built before the clock starts, so the figure is a pass over inputs that
    are already there rather than the cost of writing them. Each pass still
    opens and inflates all sixty from a warm page cache, which is what a
    caller does too.

    Cleaned up on exit. `verdict_diff` removes its own workspace and this
    borrowed the `mkdtemp` without the `rmtree`, so every `make check` and
    every matrix row left about 1.6 MB behind -- measured at 289 MB on the
    machine that wrote it.
    """
    from tools import verdict_diff

    workspace = pathlib.Path(tempfile.mkdtemp(prefix="time-budget-"))
    atexit.register(shutil.rmtree, str(workspace), True)
    return [path for _label, path in verdict_diff.build_corpus(workspace)]


def _wide_submodel(siblings: int = 3000):
    """One conformant submodel with many siblings in one scope.

    The corpus cannot stand in for this. Its largest scope holds fifteen
    elements, so anything superlinear in siblings is invisible there: a
    pairwise comparison added to the walk moved the corpus by 1% and this
    by 70%. A file of this width is ordinary in a real handover.
    """
    import json

    from aas_submodel_validate.rules import dn_tables

    # It has to wear a template this project *has a table for*. A submodel
    # of an unknown template draws SMT-D1 and the walk never enters it, so
    # a wide file of one would have timed the refusal and not the walk --
    # which is what the first version of this did, and a genuine quadratic
    # in the walk read 1.02x against it.
    element = {"modelType": "Property",
               "semanticId": {"type": "ExternalReference",
                              "keys": [{"type": "GlobalReference",
                                        "value": "urn:example:filler"}]},
               "valueType": "xs:string", "value": "x"}
    elements = []
    for index in range(siblings):
        item = json.loads(json.dumps(element))
        item["idShort"] = "Filler%04d" % index
        elements.append(item)
    return {"submodels": [{
        "modelType": "Submodel", "id": "urn:example:wide", "idShort": "Wide",
        "kind": "Instance",
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference",
                                 "value": dn_tables.TEMPLATE_SEMANTIC_ID}]},
        "submodelElements": elements}]}


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


def _repeats_for(call) -> int:
    repeats = 1
    while True:
        start = time.perf_counter()
        for _ in range(repeats):
            call()
        spent = time.perf_counter() - start
        if spent >= LAYER_FLOOR_SECONDS or repeats > 1 << 14:
            break
        repeats *= 2
    return repeats


def _ratio_of(call, rounds: int) -> tuple:
    """The layer's cost in yardstick units, measured *beside* the yardstick.

    Measuring the yardstick once and the layers afterwards does not cancel
    the machine out -- it cancels *steady* load out and amplifies load that
    covers one window and not the other. Measured: bursts of background CPU
    work timed to land on the yardstick alone drove the reported ratio to
    0.41x, and bursts landing on the layers alone drove it to 1.33x, on one
    idle machine with one unchanged tree. So each pass times the yardstick
    and the layer back to back and divides them there, and the passes are
    compared as ratios rather than as two separately-minimised numbers.
    """
    repeats = _repeats_for(call)
    seen = []
    while len(seen) < MAX_PASSES:
        start = time.perf_counter()
        _work(rounds)
        unit = (time.perf_counter() - start) / rounds * 10_000

        start = time.perf_counter()
        for _ in range(repeats):
            call()
        seconds = (time.perf_counter() - start) / repeats

        seen.append((seconds / unit, seconds, unit))
        if len(seen) >= PASSES:
            ratios = [ratio for ratio, _s, _u in seen]
            if max(ratios) / min(ratios) <= SPREAD_TOLERANCE:
                break
    return min(seen)


def measure() -> dict:
    """The layers, in seconds, and the yardstick beside them."""
    import json
    import subprocess

    from tools import verdict_diff

    from aas_submodel_validate import report as report_module
    from aas_submodel_validate import runner
    from aas_submodel_validate.rules import engine, hd_tables, profiles

    corpus = _corpus()
    loaded = _rules_layer_input()
    wide = pathlib.Path(tempfile.mkdtemp(prefix="time-budget-"))
    atexit.register(shutil.rmtree, str(wide), True)
    wide_path = wide / "wide.json"
    wide_path.write_bytes(json.dumps(_wide_submodel()).encode("utf-8"))

    def cold_start():
        # A whole invocation in a fresh interpreter, which is the only
        # figure here that is the time a person waits. Everything else has
        # imported the package before the clock started.
        subprocess.run([sys.executable, "-m", "aas_submodel_validate",
                        str(verdict_diff.EXAMPLE)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       cwd=str(ROOT),
                       env=dict(os.environ, PYTHONPATH=str(ROOT / "src")))

    def scale():
        runner.run(wide_path)

    def corpus_pass():
        for path in corpus:
            # Rendered too: a caller waits for the report, and timing only
            # the judgement left that layer unmeasured -- a change that made
            # rendering six times more expensive moved nothing here.
            report_module.render(runner.run(path))

    def rules_layer():
        # The walk over the official example, and only the table that
        # answers for it: asking the other five would spend most of the
        # measurement on packs declining a file that is not theirs, and a
        # number made mostly of no-ops moves for reasons nobody caused. A
        # fresh context each time, because `analyze` caches per context --
        # timing a cache hit would measure nothing.
        engine.analyze(runner.Context(loaded, profiles.Selection(None)),
                       hd_tables)

    rounds = _yardstick_rounds()
    bodies = {"cold_start": cold_start, "corpus_pass": corpus_pass,
              "scale": scale, "rules_layer": rules_layer}
    measured = {layer: _ratio_of(bodies[layer], rounds) for layer in LAYERS}
    return {
        # The unit from the pass each layer's figure came from, so a reader
        # who divides the seconds below by it gets the ratio above it.
        "yardstick_seconds": min(unit for _r, _s, unit in measured.values()),
        "inputs": len(corpus),
        "ratios": {layer: ratio for layer, (ratio, _s, _u) in measured.items()},
        "layers": {layer: seconds for layer, (_r, seconds, _u) in measured.items()},
        "units": {layer: unit for layer, (_r, _s, unit) in measured.items()},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="compare against the recorded budgets")
    parser.add_argument("--record", action="store_true",
                        help="print what this machine measures, for the file")
    args = parser.parse_args(argv)

    measured = measure()
    ratios = measured["ratios"]
    key = platform_key()

    if args.record:
        print(json.dumps({
            "platform": key,
            # Three significant figures, because a layer whose ratio is
            # under one would otherwise be recorded in a band wide enough
            # to hide a fifth of its cost.
            "budgets": {layer: float("%.3g" % ratio)
                        for layer, ratio in ratios.items()},
            "platforms_expected": [key],
            "recorded_on": {
                "machine": platform.machine(),
                "python": platform.python_version(),
                "inputs": measured["inputs"],
                # The unit beside each layer, not one shared number: each
                # figure is divided by the yardstick measured in its own
                # pass, so only the pair reconstructs the ratio.
                "yardstick_seconds": {layer: float("%.4g" % unit) for layer, unit
                                      in measured["units"].items()},
                "absolute_seconds": {layer: float("%.4g" % seconds)
                                     for layer, seconds
                                     in measured["layers"].items()},
            }}, indent=1))
        return 0

    recorded = load()
    budgets = budgets_for(recorded, key)
    about = recorded.get("recorded_on", {}).get(key, {})
    bad = False

    # The corpus is not a constant. `measure()` counts it and the file
    # records what it was counted at, and nothing compared the two: pruning
    # a dozen inputs from `verdict_diff` -- an ordinary tidy -- took the
    # corpus from sixty to forty-five and bought a silent 40% of headroom.
    if about.get("inputs") not in (None, measured["inputs"]):
        print("corpus is %d inputs, budget was recorded over %d"
              % (measured["inputs"], about["inputs"]))
        bad = True

    # A platform loses its budget by being renamed as easily as by being
    # deleted, and "no budget recorded" is what both look like. So the file
    # lists the keys that already have one; a platform nothing has run on
    # is simply not on the list, and adding it means adding it twice --
    # once as the claim and once as the figure.
    expected = set(recorded.get("platforms_expected") or ())
    gone = sorted(expected - set(recorded.get("budgets", {})))
    if gone:
        print("budgets are missing for %s, which this file expects"
              % ", ".join(gone))
        bad = True

    for layer in LAYERS:
        try:
            verdict = judge(ratios[layer], budgets.get(layer))
        except ValueError as exc:
            print("%-12s %7.3g units, unusable budget: %s" % (layer, ratios[layer], exc))
            bad = True
            continue
        if verdict.factor is None:
            print("%-12s %7.3g units, no budget recorded for %s"
                  % (layer, ratios[layer], key))
            continue
        # A ratio cannot tell "this machine is fast" from "this layer
        # stopped doing its work". Absolute seconds can: a cache moved from
        # per-context to global made the walk 1500x faster and the ratio
        # said only "far under budget", which is a sentence a loaded
        # machine also produces.
        floor = (about.get("absolute_seconds", {}).get(layer) or 0) * COLLAPSED_BELOW
        collapsed = bool(floor) and measured["layers"][layer] < floor
        note = ("over budget" if not verdict.ok else
                "collapsed -- this layer is no longer doing its work"
                if collapsed else
                "close to budget" if verdict.warn else
                "far under budget -- check the yardstick" if verdict.under
                else "")
        print(("%-12s %7.3g units, %.2fx of its budget %s"
               % (layer, ratios[layer], verdict.factor, note)).rstrip())
        if verdict.warn and verdict.ok and os.environ.get("GITHUB_ACTIONS"):
            # A warning nobody sees is not a warning. Nothing read `warn`
            # except this line, so a layer 1.7x its budget passed as two
            # words in a log.
            print("::warning title=time budget::%s is %.2fx of its budget"
                  % (layer, verdict.factor))
        bad = bad or not verdict.ok or collapsed
    return 1 if bad else 0


if __name__ == "__main__":                  # pragma: no cover
    raise SystemExit(main())
