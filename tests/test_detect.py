"""SMT-D1: is any submodel this tool knows even here?

The silent-pass lesson from the sibling validators, applied from day
one: a validator pointed at an environment containing no submodel it
knows must say so loudly, because "no findings" is also what a perfect
package looks like. And when the miss is near — right stem, wrong
ECLASS version; right name, wrong identifier — the finding says what it
saw, because "not found" with no diagnosis leaves the reader all of the
work.

One rule for all templates, not one per template. Two would contradict
each other on every input: a Technical Data file would fail Handover's
presence rule and a Handover file would fail Technical Data's, and both
failures would be wrong.
"""
from __future__ import annotations

import json

from aas_submodel_validate import runner
from builders import env_json

HANDOVER_ID = "0173-1#01-AHF578#003"
TECHNICAL_DATA_ID = "0173-1#01-AHX837#002"


def _findings(tmp_path, payload: bytes):
    path = tmp_path / "env.json"
    path.write_bytes(payload)
    return {f.id: f for f in runner.run(path).findings}


def test_a_handover_submodel_satisfies_the_presence_rule(tmp_path):
    assert "SMT-D1" not in _findings(tmp_path, env_json(HANDOVER_ID))


def test_a_technical_data_submodel_satisfies_it_too(tmp_path):
    """The rule this replaced was Handover's alone, so this file used to
    be told it was missing a Handover submodel — which it never claimed
    to be."""
    assert "SMT-D1" not in _findings(tmp_path, env_json(TECHNICAL_DATA_ID))


def test_the_cdp_spelling_of_the_same_id_also_matches(tmp_path):
    cdp = "https://api.eclass-cdp.com/0173-1-01-AHF578-003"
    assert "SMT-D1" not in _findings(tmp_path, env_json(cdp))


def test_a_wrong_id_fails_with_what_was_seen(tmp_path):
    finding = _findings(tmp_path, env_json("urn:something:else"))["SMT-D1"]
    assert str(finding.severity) == "error"
    assert "urn:something:else" in (finding.violation.detail or "")


def test_the_remedy_names_every_template_on_offer(tmp_path):
    """A reader who reached this finding does not know which templates
    exist. Naming only one would send a Technical Data author to the
    wrong identifier."""
    finding = _findings(tmp_path, env_json("urn:something:else"))["SMT-D1"]
    assert HANDOVER_ID in finding.fix
    assert TECHNICAL_DATA_ID in finding.fix


def test_a_version_drift_gets_a_nearest_miss_diagnosis(tmp_path):
    finding = _findings(tmp_path, env_json("0173-1#01-AHF578#002"))["SMT-D1"]
    assert "version suffix" in finding.violation.detail


def test_a_version_drift_is_diagnosed_for_the_second_template_too(tmp_path):
    finding = _findings(tmp_path, env_json("0173-1#01-AHX837#001"))["SMT-D1"]
    assert "version suffix" in finding.violation.detail


def test_a_submodel_named_but_not_identified_gets_told_why(tmp_path):
    document = json.loads(env_json("urn:wrong:id"))
    document["submodels"][0]["idShort"] = "HandoverDocumentation"
    finding = _findings(tmp_path, json.dumps(document).encode())["SMT-D1"]
    assert "semanticId" in finding.violation.detail


def test_the_name_hint_covers_the_second_template_as_well(tmp_path):
    document = json.loads(env_json("urn:wrong:id"))
    document["submodels"][0]["idShort"] = "TechnicalData"
    finding = _findings(tmp_path, json.dumps(document).encode())["SMT-D1"]
    assert "semanticId" in finding.violation.detail


def test_an_unreadable_input_is_not_also_piled_on(tmp_path):
    """A file that failed to load gets the container findings; adding
    'and your submodel is missing' to a file nobody could read is noise
    on top of the real problem."""
    path = tmp_path / "env.json"
    path.write_bytes(b"{ not json")
    ids = {f.id for f in runner.run(path).findings}
    assert "X3" in ids
    assert "SMT-D1" not in ids


def test_the_handover_rule_no_longer_exists_under_its_old_id():
    """HD-D1 was a rule about one template pretending to be a rule about
    the tool. Keeping the id would leave a stored report ambiguous about
    which question it answered."""
    from aas_submodel_validate.registry import all_rules
    assert "HD-D1" not in {rule.id for rule in all_rules()}
