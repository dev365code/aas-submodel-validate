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

import pytest

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "src" / "aas_submodel_validate").is_dir():
    pytest.skip("an installed package, not a checkout: the golden report is "
                "compared against the tree it was written from",
                allow_module_level=True)
sys.path.insert(0, str(ROOT / "tools"))
import golden_report  # noqa: E402

GOLDEN = json.loads((ROOT / "docs" / "golden-report.json").read_text("utf-8"))


def test_the_stored_report_is_the_one_this_tree_produces():
    assert golden_report.main(["--check"]) == 0


def test_a_report_from_another_copy_of_the_package_is_refused(tmp_path, monkeypatch):
    """The child is told which tree to run and asked where the package it
    imported came from. Pointed at a tree with no package in it, it finds
    the copy planted on its path and refuses it by name: a report from
    another copy was the failure this refusal was written against. The
    copy is planted because finding none at all ends in no report too --
    for a missing module, with the refusal switched off as well as on --
    and this passed wherever nothing was installed."""
    (tmp_path / "src").mkdir()
    planted = tmp_path / "elsewhere" / "aas_submodel_validate"
    planted.mkdir(parents=True)
    (planted / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "elsewhere"))
    monkeypatch.setattr(golden_report, "ROOT", tmp_path)
    with pytest.raises(SystemExit) as refused:
        golden_report.report()
    assert "this tree was not the package imported" in str(refused.value), refused.value
    assert "elsewhere" in str(refused.value), refused.value


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
