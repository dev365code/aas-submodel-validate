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
from builders import env_json, wearing_our_anchor_as_a_supplemental

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


def test_a_submodel_wearing_our_anchor_in_a_supplemental_is_not_recognised(tmp_path):
    """IDTA 02035-4 declares an identity of its own and carries this
    project's Technical Data anchor as a supplemental. Folding
    supplementals into submodel matching -- which is exactly what element
    matching already does one level down -- would make that published
    file Technical Data, and its differences from Technical Data would be
    reported as its defects.

    Nothing stopped that generalisation before this test: swapping
    `candidate_values(submodel.semantic_id)` for
    `element_candidate_values(submodel)` left the whole suite green.
    """
    from aas_submodel_validate.rules import td_tables
    ids = _findings(tmp_path, wearing_our_anchor_as_a_supplemental(
        td_tables.TEMPLATE_SEMANTIC_ID, "TechnicalData"))
    assert "SMT-D1" in ids, "the honest answer is that we do not know this file"
    assert not [rule_id for rule_id in ids if rule_id.startswith("TD")], \
        "a template of its own was judged as ours"


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


def test_a_reference_stacking_keys_also_matches_as_the_joined_path():
    """`candidate_values` adds the "/"-join when a reference stacks
    several keys, in both spellings of the function -- the aas-core3 one
    the walk reads and the dict one the builders read. Losing the join
    silently unmatches any file that spells one identifier across two
    keys, which is the quiet direction; losing it in only one spelling
    splits the builders' idea of "matches" from the walk's."""
    from aas_core3 import types as aas

    from aas_submodel_validate.semantics import (
        candidate_values,
        candidate_values_from_dict,
    )
    reference = aas.Reference(
        type=aas.ReferenceTypes.EXTERNAL_REFERENCE,
        keys=[aas.Key(type=aas.KeyTypes.GLOBAL_REFERENCE, value="a"),
              aas.Key(type=aas.KeyTypes.GLOBAL_REFERENCE, value="b")])
    assert "a/b" in candidate_values(reference)
    assert "a/b" in candidate_values_from_dict(
        {"type": "ExternalReference",
         "keys": [{"type": "GlobalReference", "value": "a"},
                  {"type": "GlobalReference", "value": "b"}]})


def test_an_absent_reference_yields_an_empty_set_not_none():
    """The empty frozenset is load-bearing: callers ask `anchor in ...`
    and membership in None is a crash wearing a helper's name."""
    from aas_submodel_validate.semantics import candidate_values_from_dict
    assert candidate_values_from_dict(None) == frozenset()
    assert candidate_values_from_dict({}) == frozenset()


def test_the_nearest_miss_summary_caps_at_three_values():
    """`sorted(set(seen))[:3]` -- deterministic, deduplicated, and
    bounded: an environment declaring forty foreign identifiers gets a
    three-item summary, not a page. And a value equal to a pack's own
    identifier never draws the version-suffix hint -- such a submodel
    matched, so the hint would be diagnosing a success."""
    from aas_submodel_validate.rules.detect import PACKS, _nearest_miss

    class _Sub:
        def __init__(self, value):
            from aas_core3 import types as aas
            self.id_short = "Whatever"
            self.semantic_id = aas.Reference(
                type=aas.ReferenceTypes.EXTERNAL_REFERENCE,
                keys=[aas.Key(type=aas.KeyTypes.GLOBAL_REFERENCE, value=value)])

    detail = _nearest_miss([_Sub("urn:d"), _Sub("urn:c"),
                            _Sub("urn:b"), _Sub("urn:a")])
    assert detail == "semanticId value(s): urn:a, urn:b, urn:c"

    equal = _nearest_miss([_Sub(PACKS[0].semantic_id)])
    assert "version suffix" not in equal


def test_a_named_submodel_with_no_semantic_id_says_absent():
    """The name-hint sentence quotes what the semanticId is, and for a
    submodel that has none the honest word is "absent" -- not an empty
    string a reader parses as a typo."""
    from aas_submodel_validate.rules.detect import _nearest_miss

    class _Sub:
        id_short = "HandoverDocumentation"
        semantic_id = None

    detail = _nearest_miss([_Sub()])
    assert "absent" in detail
    assert "never by name" in detail


def test_an_input_declaring_nothing_says_so():
    from aas_submodel_validate.rules.detect import _nearest_miss

    class _Sub:
        id_short = "Whatever"
        semantic_id = None

    assert "no submodel in the input declares" in _nearest_miss([_Sub()])

