"""HD-D1: is the Handover Documentation submodel even here?

The silent-pass lesson from the sibling validators, applied from day
one: a validator pointed at an environment containing no submodel it
knows must say so loudly, because "no findings" is also what a perfect
package looks like. And when the miss is near — right stem, wrong
ECLASS version; right name, wrong identifier — the finding says what it
saw, because "not found" with no diagnosis leaves the reader all of the
work.
"""
from __future__ import annotations

import json

from aas_submodel_validate import runner
from builders import env_json

TEMPLATE_ID = "0173-1#01-AHF578#003"


def _findings(tmp_path, payload: bytes):
    path = tmp_path / "env.json"
    path.write_bytes(payload)
    return {f.id: f for f in runner.run(path).findings}


def test_a_matching_submodel_satisfies_hd_d1(tmp_path):
    assert "HD-D1" not in _findings(tmp_path, env_json(TEMPLATE_ID))


def test_the_cdp_spelling_of_the_same_id_also_matches(tmp_path):
    cdp = "https://api.eclass-cdp.com/0173-1-01-AHF578-003"
    assert "HD-D1" not in _findings(tmp_path, env_json(cdp))


def test_a_wrong_id_fails_with_what_was_seen(tmp_path):
    finding = _findings(tmp_path, env_json("urn:something:else"))["HD-D1"]
    assert str(finding.severity) == "error"
    assert "urn:something:else" in (finding.violation.detail or "")


def test_a_version_drift_gets_a_nearest_miss_diagnosis(tmp_path):
    finding = _findings(tmp_path, env_json("0173-1#01-AHF578#002"))["HD-D1"]
    assert "version suffix" in finding.violation.detail


def test_a_submodel_named_but_not_identified_gets_told_why(tmp_path):
    document = json.loads(env_json("urn:wrong:id"))
    document["submodels"][0]["idShort"] = "HandoverDocumentation"
    finding = _findings(tmp_path, json.dumps(document).encode())["HD-D1"]
    assert "semanticId" in finding.violation.detail


def test_an_unreadable_input_is_not_also_piled_on(tmp_path):
    """A file that failed to load gets the container findings; adding
    'and your Handover submodel is missing' to a file nobody could read
    is noise on top of the real problem."""
    path = tmp_path / "env.json"
    path.write_bytes(b"{ not json")
    ids = {f.id for f in runner.run(path).findings}
    assert "X3" in ids
    assert "HD-D1" not in ids
