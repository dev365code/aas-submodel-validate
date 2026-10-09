"""The committed coverage baseline and the suite's observation are distinct."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from aas_submodel_validate import runner
from aas_submodel_validate.registry import all_rules
from test_verdict_diff import _a_template_case

ROOT = Path(__file__).resolve().parents[1]


def test_every_published_id_is_accounted_for(tmp_path):
    """Read the real baseline through the real gate, with a full observation.

    Generating that observation is the full suite's job. This test isolates
    the gate's comparison so an unrelated wall-clock failure cannot be
    scored as a broken mutation of the baseline.
    """
    (tmp_path / "docs").mkdir()
    shutil.copy(ROOT / "docs/rule-coverage.json", tmp_path / "docs/rule-coverage.json")
    (tmp_path / ".rule-coverage.json").write_text(
        json.dumps(sorted({rule.id for rule in all_rules()} | {"META"})), encoding="utf-8")
    # Run the gate in a process: main reads argv and ROOT, and neither
    # should leak into the suite that is observing this test.
    command = (
        "import sys; from pathlib import Path\n"
        "sys.path.insert(0, %r)\n"
        "from tools import rule_coverage\n"
        "rule_coverage.ROOT = Path(%r)\n"
        "sys.argv = ['rule_coverage.py', '--check']\n"
        "raise SystemExit(rule_coverage.main())\n"
    ) % (str(ROOT), str(tmp_path))
    done = subprocess.run([sys.executable, "-c", command], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "all " in done.stdout and "rule ids fire" in done.stdout


def test_a_run_time_id_stays_out_of_the_coverage_record(tmp_path, monkeypatch):
    """An actual supplied-table finding reaches the suite's real observer."""
    import conftest

    case = _a_template_case(tmp_path)
    report = runner.run(case.path, template=case.template)
    assert any(f.id == "TPL-E01" for f in report.findings), report.as_dict()
    observation = tmp_path / "observed.json"
    monkeypatch.setattr(conftest, "OBSERVED", observation)
    monkeypatch.setattr(conftest, "_WHOLE_SUITE", True)
    conftest._record(conftest.FIRED)
    assert not any(rid.startswith("TPL-") for rid in json.loads(observation.read_text()))
