"""The run has to stay inside its time budget, in units of the machine.

Correct and unusable is a state this project can ship: every gate here
answers "is the verdict right", none of them answers "did it take four
minutes". The walk was quadratic once and every gate stayed green.

The generator's own quadratic (`_qualify_repeats`, `tools/extract_smt_rules.py`)
is **not** covered by what follows, and deliberately: it runs at build time
over small vendored files, so nothing a caller does reaches it. A third
layer joins these two when that stops being true.

Seconds cannot be the budget. A ceiling recorded on a laptop means nothing
on a runner, and the same runner is slower under load than idle, so an
absolute number is either loose enough to catch nothing or tight enough to
fail for reasons nobody caused. What is recorded is a ratio against a
yardstick measured in the same process in the same run.
"""
from __future__ import annotations

import json
import os
import pathlib

import pytest
from tools import time_budget


def test_the_judgement_has_three_answers_and_they_are_the_thresholds():
    """Under the warning line is silence, past it is worth saying out loud,
    past the failure line is a failure. Both lines are generous on purpose:
    a gate that fires on runner noise is one people learn to pass with a
    re-run, and then it is not a gate."""
    assert time_budget.WARN_AT < time_budget.FAIL_AT
    assert time_budget.judge(1.0, 1.0).ok and not time_budget.judge(1.0, 1.0).warn
    warned = time_budget.judge(time_budget.WARN_AT + 0.01, 1.0)
    assert warned.ok and warned.warn
    failed = time_budget.judge(time_budget.FAIL_AT + 0.01, 1.0)
    assert not failed.ok


def _recorded_here():
    """The recorded budgets, with an entry for the platform running this.

    Budgets can only be written by a run on the platform they describe,
    so the file carries whatever machines have recorded -- and every test
    below that reaches into `budgets[key]` or `recorded_on[key]` to bend
    one number was reading an entry that exists on the machine this was
    written on and nowhere else. The whole matrix met `KeyError: 'Linux'`
    while this one stayed green.

    What those tests are about is the gate's arithmetic, not this
    machine, so an absent platform is given a copy of a recorded one. The
    test that asks what happens when a platform has *no* budget builds
    that case for itself.
    """
    recorded = json.loads(json.dumps(time_budget.load()))
    key = time_budget.platform_key()
    if key not in recorded["budgets"]:
        borrowed = sorted(recorded["budgets"])[0]
        recorded["budgets"][key] = json.loads(
            json.dumps(recorded["budgets"][borrowed]))
        recorded["recorded_on"][key] = json.loads(
            json.dumps(recorded["recorded_on"][borrowed]))
        recorded["platforms_expected"] = sorted(
            set(recorded["platforms_expected"]) | {key})
    return recorded


def test_a_platform_with_no_recorded_budget_passes_quietly():
    """The budgets for a platform can only be written by a run on it, so
    until CI has run there is nothing to compare against. Refusing would
    make the gate impossible to introduce; failing loudly would teach
    everyone to ignore it. It says it has no baseline and passes -- and
    that is asserted here, because "passes quietly" is the behaviour most
    likely to be turned into "passes always" by accident."""
    verdict = time_budget.judge(9999.0, None)
    assert verdict.ok and not verdict.warn
    assert verdict.factor is None


@pytest.mark.parametrize("baseline", [0, 0.0, -1.0])
def test_a_budget_that_cannot_be_divided_by_is_not_a_missing_one(baseline):
    """The accident this separates.

    Written as one `if not baseline`, a budget zeroed by an editing slip
    took the same branch as a platform with no entry: the gate printed
    "no budget recorded for Darwin" -- a sentence a reader would take as
    proof the file was untouched -- and exited 0, with every test here
    still green. A negative one was worse: it divided, reported -107x, and
    called that ok.

    A missing entry is the ordinary state of a platform nothing has run
    on. A zero is a corrupt record, and the two must not agree.
    """
    with pytest.raises(ValueError):
        time_budget.judge(100.0, baseline)


def test_an_unusable_budget_fails_the_command(monkeypatch, capsys):
    """And the corrupt record has to reach the exit code, not just the
    exception."""
    recorded = _recorded_here()
    recorded["budgets"][time_budget.platform_key()] = dict.fromkeys(
        time_budget.LAYERS, 0)
    monkeypatch.setattr(time_budget, "load", lambda: recorded)
    assert time_budget.main(["--check"]) == 1
    assert "unusable budget" in capsys.readouterr().out


def test_far_under_budget_is_said_out_loud_without_failing():
    """The whole design rests on the yardstick being a stable unit, so an
    unexplained *drop* is as informative as a rise: a yardstick that got
    slower greens every layer at once and says nothing. Being fast is not
    a defect, so it does not fail -- it just stops being silent."""
    assert time_budget.UNDER_AT < 1.0
    verdict = time_budget.judge(time_budget.UNDER_AT - 0.01, 1.0)
    assert verdict.ok and verdict.under
    assert not time_budget.judge(1.0, 1.0).under


def test_the_yardstick_does_not_measure_this_project():
    """A yardstick that called the code it normalises would slow down
    together with the regression it exists to catch, and the ratio would
    stay flat while the wall clock doubled.

    Asserted on what the yardstick *is*, not on one function being absent
    from it. Bombing `runner.run` and watching the yardstick survive said
    nothing about the twenty other modules here: routed through one of
    them the yardstick reported every layer at 0.12x of its budget,
    permanently green, and every test in this file passed.
    """
    import dis
    import inspect

    package = "aas_submodel_validate"
    for function in (time_budget._work, time_budget._yardstick,
                     time_budget._yardstick_rounds):
        assert package not in inspect.getsource(function), function.__name__
        for instruction in dis.get_instructions(function):
            name = instruction.argval
            if not isinstance(name, str):
                continue
            if instruction.opname.startswith("IMPORT"):
                assert not name.startswith(package), (function.__name__, name)
            borrowed = getattr(time_budget, name, None)
            origin = getattr(borrowed, "__name__", "") if inspect.ismodule(
                borrowed) else getattr(borrowed, "__module__", "") or ""
            assert not origin.startswith(package), (function.__name__, name)

    from aas_submodel_validate import runner

    def explode(*args, **kwargs):          # pragma: no cover - must not run
        raise AssertionError("the yardstick called this project")

    original, runner.run = runner.run, explode
    try:
        assert time_budget._yardstick() > 0
    finally:
        runner.run = original


def test_the_yardstick_is_sized_by_the_clock_not_by_a_number():
    """A fixed repetition count measures scheduling noise on a fast machine.
    The yardstick grows until one measurement takes long enough to mean
    something."""
    assert time_budget.YARDSTICK_FLOOR_SECONDS >= 0.01


def test_the_budget_file_records_what_it_was_measured_on():
    """A ratio with no record of the machine, the interpreter and the
    absolute seconds is a number nobody can argue with later."""
    recorded = time_budget.load()
    assert recorded["thresholds"] == {
        "warn_at": time_budget.WARN_AT, "fail_at": time_budget.FAIL_AT,
        "collapsed_below": time_budget.COLLAPSED_BELOW}
    assert recorded["budgets"], "no platform has a budget yet"
    for key, budgets in recorded["budgets"].items():
        assert set(budgets) == set(time_budget.LAYERS), key
        assert all(budget > 0 for budget in budgets.values()), key
        assert key in recorded["recorded_on"], key
        about = recorded["recorded_on"][key]
        for field in ("machine", "python", "inputs", "yardstick_seconds",
                      "absolute_seconds"):
            assert field in about, (key, field)
        # and the seconds have to reconstruct the ratio above them. They did
        # not: the budget was a mean of several runs and the seconds came
        # from one of them, so a reader who divided got a third number.
        for layer, budget in budgets.items():
            seconds = about["absolute_seconds"][layer]
            unit = about["yardstick_seconds"][layer]
            assert abs(seconds / unit - budget) / budget < 0.05, (key, layer)


def test_a_measurement_covers_every_layer_the_budget_names():
    """Measuring fewer layers than the file judges would leave a budget
    that can never be compared against anything."""
    measured = time_budget.measure()
    assert set(measured["layers"]) == set(time_budget.LAYERS)
    assert set(measured["ratios"]) == set(time_budget.LAYERS)
    assert measured["yardstick_seconds"] > 0
    assert measured["inputs"] >= 40
    for layer, seconds in measured["layers"].items():
        assert seconds > 0, layer
        assert measured["ratios"][layer] > 0, layer
        # each layer divided by the yardstick measured in its own pass
        assert abs(seconds / measured["units"][layer]
                   - measured["ratios"][layer]) < 1e-9, layer


def test_the_layers_measure_things_the_others_cannot_see():
    """Each layer earns its place by seeing what the rest do not.

    `cold_start` is the only one that pays import cost: everything else
    imports the package before the clock starts and then repeats a warm
    call, so an index built at import made the command 2.3x slower and left
    every other layer reading 0.98x. `scale` is the only one wide enough to
    show a superlinear change: the corpus's largest scope holds fifteen
    elements, and a genuine quadratic in the walk moved it by 1% while
    moving a three-thousand-element file by 70%.
    """
    assert {"cold_start", "scale"} <= set(time_budget.LAYERS)
    assert len(time_budget._wide_submodel()["submodels"][0]
               ["submodelElements"]) >= 1000


def test_the_corpus_is_not_left_on_the_disk():
    """The corpus is written to a temp directory every run, which is every
    `make check` and every matrix row. This borrowed the `mkdtemp` from
    `verdict_diff` without its `rmtree` and left about 1.6 MB behind each
    time -- 289 MB by the time anybody looked."""
    import glob
    import subprocess
    import sys
    import tempfile

    pattern = os.path.join(tempfile.gettempdir(), "time-budget-*")
    before = set(glob.glob(pattern))
    subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path[:0] = ['src', '.']\n"
         "from tools import time_budget; time_budget._corpus()"],
        cwd=str(pathlib.Path(__file__).resolve().parents[1]), check=True,
        capture_output=True)
    assert set(glob.glob(pattern)) - before == set()


def test_the_command_reports_what_it_found(capsys):
    """The sibling coverage gate once had a tested judgement and a `main`
    that threw it away. The command is what `make check` runs, so the
    command is what has to carry the verdict."""
    assert time_budget.main(["--check"]) == 0
    printed = capsys.readouterr().out
    assert "x of" in printed or "no budget" in printed, printed


def test_the_check_fails_when_a_layer_is_over_its_budget(monkeypatch, capsys):
    """The judgement has to reach the exit code. Measured against a budget
    small enough that any real run exceeds it."""
    recorded = _recorded_here()
    key = time_budget.platform_key()
    recorded["budgets"][key] = dict.fromkeys(time_budget.LAYERS, 1e-09)
    monkeypatch.setattr(time_budget, "load", lambda: recorded)
    assert time_budget.main(["--check"]) == 1
    assert "over budget" in capsys.readouterr().out


def test_the_corpus_layer_is_the_whole_corpus():
    """Timing a subset and calling it the corpus would let the budget stay
    green while the part that grew was the part not timed."""
    for key, about in time_budget.load()["recorded_on"].items():
        assert about["inputs"] >= 40, key


def test_a_corpus_that_shrank_fails_the_command(monkeypatch, capsys):
    """And the recorded count has to be *compared*, not merely recorded.

    It was not. `measure()` counted the corpus, the file recorded what it
    was counted at, and nothing put the two side by side -- so pruning a
    dozen inputs from `verdict_diff`, an ordinary tidy, took the corpus
    from sixty to forty-five and bought a silent 40% of headroom while
    every test here stayed green.
    """
    recorded = _recorded_here()
    about = recorded["recorded_on"][time_budget.platform_key()]
    about["inputs"] = about["inputs"] + 15
    monkeypatch.setattr(time_budget, "load", lambda: recorded)
    assert time_budget.main(["--check"]) == 1
    assert "budget was recorded over" in capsys.readouterr().out


def test_a_platform_losing_its_budget_by_rename_fails_the_command(
        monkeypatch, capsys):
    """A renamed key and a deleted one both read as "no budget recorded",
    which is the sentence for a platform nothing has run on. Renaming
    `Darwin` to `Darwin_arm64` turned the whole gate off and every test
    here passed."""
    recorded = _recorded_here()
    key = time_budget.platform_key()
    recorded["budgets"][key + "_renamed"] = recorded["budgets"].pop(key)
    monkeypatch.setattr(time_budget, "load", lambda: recorded)
    assert time_budget.main(["--check"]) == 1
    assert "budgets are missing for" in capsys.readouterr().out


def test_the_expected_platforms_are_the_ones_with_budgets():
    """The list is a ledger of what has been recorded, not a wish. A
    platform nothing has run on is simply not on it."""
    recorded = time_budget.load()
    assert sorted(recorded["platforms_expected"]) == sorted(recorded["budgets"])


def test_a_layer_that_stopped_working_fails_even_though_it_is_fast(
        monkeypatch, capsys):
    """A ratio cannot tell a fast machine from a layer that stopped doing
    its work. Moving `analyze`'s cache from per-context to global made the
    walk 1500x faster; the gate said "far under budget" and passed, which
    is also what a loaded machine says. Absolute seconds separate them:
    load is tens of percent, a collapse is orders."""
    recorded = _recorded_here()
    about = recorded["recorded_on"][time_budget.platform_key()]
    for layer in time_budget.LAYERS:
        about["absolute_seconds"][layer] *= 1000
    monkeypatch.setattr(time_budget, "load", lambda: recorded)
    assert time_budget.main(["--check"]) == 1
    assert "collapsed" in capsys.readouterr().out


def test_a_warning_is_visible_where_warnings_are_read(monkeypatch, capsys):
    """Nothing read `warn` except one word in a log line, so a layer at
    1.7x of its budget passed with nobody told. On a runner it is a
    workflow annotation now."""
    recorded = _recorded_here()
    key = time_budget.platform_key()
    recorded["budgets"][key] = {
        layer: budget / (time_budget.WARN_AT + 0.2)
        for layer, budget in recorded["budgets"][key].items()}
    about = recorded["recorded_on"][key]
    about["absolute_seconds"] = dict.fromkeys(time_budget.LAYERS, 0)
    monkeypatch.setattr(time_budget, "load", lambda: recorded)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert time_budget.main(["--check"]) == 0
    assert "::warning" in capsys.readouterr().out
