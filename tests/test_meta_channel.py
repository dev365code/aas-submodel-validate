"""The metamodel layer is relayed, never re-implemented.

aas-core3.0's verification runs inside every validation and reports
through the `meta` channel: warnings by default (the official published
example itself carries 77), errors under --strict-meta. This project's
own rules never restate an AASd constraint -- one defect, one voice.
"""
from __future__ import annotations

import copy
import json

from aas_submodel_validate import runner
from aas_submodel_validate.model import Severity
from builders import hd_env


def _run(tmp_path, env, **kwargs):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return runner.run(path, **kwargs)


def _broken(env):
    """An AASd-120 violation: an idShort on a list child."""
    env["submodels"][0]["submodelElements"][0]["value"][0]["idShort"] = "Datasheet"
    return env


def test_the_golden_fixture_is_metamodel_clean_too(tmp_path):
    assert _run(tmp_path, hd_env()).findings == []


def test_metamodel_defects_arrive_as_warnings(tmp_path):
    report = _run(tmp_path, _broken(copy.deepcopy(hd_env())))
    meta = [f for f in report.findings if f.id == "META"]
    assert meta and all(f.severity is Severity.WARNING for f in meta)
    assert "AASd-120" in meta[0].violation.message
    assert report.ok  # warnings alone do not fail a run


def test_strict_meta_promotes_them_to_errors(tmp_path):
    report = _run(tmp_path, _broken(copy.deepcopy(hd_env())), strict_meta=True)
    meta = [f for f in report.findings if f.id == "META"]
    assert meta and all(f.severity is Severity.ERROR for f in meta)
    assert not report.ok
