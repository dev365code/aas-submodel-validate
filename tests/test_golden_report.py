"""One whole report is a file, and the file is what the tool says.

`tools/golden_report.py` writes `docs/golden-report.json` from a package
it builds out of this repository's own fixtures. `make check` and CI run
its `--check`; this runs the same comparison on every machine the suite
runs on -- which is what proves the package is the same bytes on each,
since its digest is one of the values held -- and holds the file to what
the README's "What is stable" section says about it.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import golden_report  # noqa: E402

GOLDEN = json.loads((ROOT / "docs" / "golden-report.json").read_text("utf-8"))


def test_the_stored_report_is_the_one_this_tree_produces():
    assert golden_report.main(["--check"]) == 0


def test_every_finding_in_it_is_this_projects_own():
    """The premise that keeps the file still between this project's own
    changes: nothing in it is relayed from the upstream metamodel library,
    whose messages move with its releases and not with this repository."""
    assert GOLDEN["findings"], "a report with no findings holds no values worth holding"
    assert not [f for f in GOLDEN["findings"] if f["kind"] == "meta"], GOLDEN["findings"]


def test_only_the_named_fields_are_markers():
    assert GOLDEN["toolVersion"] == golden_report.MOVING[("toolVersion",)]
    markers = [value for value in json.dumps(GOLDEN).split('"') if value.startswith("<the ")]
    assert len(markers) == len(golden_report.MOVING), markers


def test_the_readme_s_own_consumer_code_reads_keys_every_finding_has():
    """The "What is stable" section gives a consumer code to copy, and the
    keys that code reads are a promise: a finding without one of them
    raises in somebody's pipeline. Read from the page, not restated here."""
    readme = (ROOT / "README.md").read_text("utf-8")
    _, _, stable = readme.partition("What is stable, what is not")
    code = stable.split("```python", 1)[1].split("```", 1)[0]
    read = set(re.findall(r'finding\["(\w+)"\]', code))
    assert {"rule", "severity", "message", "fix"} <= read, read
    assert 'report["findings"]' in code
    for finding in GOLDEN["findings"]:
        assert read <= set(finding), (read - set(finding), finding)
    assert "`schemaVersion` is %d" % GOLDEN["schemaVersion"] in stable
    assert "docs/golden-report.json" in stable
