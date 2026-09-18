"""The run has to stay inside its time budget, in units of the machine.

Correct and unusable is a state this project can ship: every gate here
answers "is the verdict right", none of them answers "did it take four
minutes", and the generator already carries a quadratic that nothing here
would notice until somebody waited for it.

Seconds cannot be the budget. A ceiling recorded on a laptop means nothing
on a runner, and the same runner is slower under load than idle, so an
absolute number is either loose enough to catch nothing or tight enough to
fail for reasons nobody caused. What is recorded is a ratio against a
yardstick measured in the same process in the same run.
"""
from __future__ import annotations

import json

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


def test_the_yardstick_does_not_measure_this_project():
    """A yardstick that called the code it normalises would slow down
    together with the regression it exists to catch, and the ratio would
    stay flat while the wall clock doubled."""
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
    assert recorded["thresholds"] == {"warn_at": time_budget.WARN_AT,
                                      "fail_at": time_budget.FAIL_AT}
    assert recorded["budgets"], "no platform has a budget yet"
    for key, budgets in recorded["budgets"].items():
        assert set(budgets) == set(time_budget.LAYERS), key
        assert key in recorded["recorded_on"], key
        about = recorded["recorded_on"][key]
        for field in ("machine", "python", "inputs", "yardstick_seconds",
                      "absolute_seconds"):
            assert field in about, (key, field)


def test_a_measurement_covers_every_layer_the_budget_names():
    """Measuring fewer layers than the file judges would leave a budget
    that can never be compared against anything."""
    measured = time_budget.measure()
    assert set(measured["layers"]) == set(time_budget.LAYERS)
    assert measured["yardstick_seconds"] > 0
    assert measured["inputs"] >= 40
    for layer, seconds in measured["layers"].items():
        assert seconds > 0, layer


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
    recorded = json.loads(json.dumps(time_budget.load()))
    key = time_budget.platform_key()
    recorded["budgets"][key] = dict.fromkeys(time_budget.LAYERS, 1e-09)
    monkeypatch.setattr(time_budget, "load", lambda: recorded)
    assert time_budget.main(["--check"]) == 1
    assert "over budget" in capsys.readouterr().out


def test_the_corpus_layer_is_the_whole_corpus():
    """Timing a subset and calling it the corpus would let the budget stay
    green while the part that grew was the part not timed. What the budget
    was measured over is recorded beside it, so a corpus that shrank is
    visible without re-running anything."""
    for key, about in time_budget.load()["recorded_on"].items():
        assert about["inputs"] >= 40, key
