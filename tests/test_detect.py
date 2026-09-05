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

import copy
import json
from pathlib import Path

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.report import render
from builders import env_json, hd_env, wearing_our_anchor_as_a_supplemental

ROOT = Path(__file__).resolve().parents[1]

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



def _template_kind(env):
    """Mark every submodel in `env` as a template rather than an instance."""
    for submodel in env["submodels"]:
        submodel["kind"] = "Template"
    return env


def test_a_template_submodel_is_not_an_instance_and_is_not_judged(tmp_path):
    """`ModellingKind.Template` means "specification of the common
    features ... that such an instance can be instantiated using it".
    A cardinality is a requirement on the instance; asking a template to
    satisfy it is a category error.

    The tool did ask. Run against the official 02004 template that this
    project vendors as its own source of truth, it reported that the
    template has no VDI 2770 classification and told the reader to add
    one -- and no flag escaped it. That is a finding on a conformant
    file, which is the direction this project calls the expensive one,
    aimed at the file it measures everything else against."""
    from aas_submodel_validate.cli import EXIT_OK, main

    # A file that would fail if it were judged. The first version of
    # this used a conformant one, so breaking the template check
    # entirely left it green: it could not tell "not judged" from
    # "judged and clean", which is the whole of what it claims to say.
    env = copy.deepcopy(hd_env())
    for submodel in env["submodels"]:
        submodel["submodelElements"] = []
    instance = tmp_path / "instance.json"
    instance.write_text(json.dumps(copy.deepcopy(env)), "utf-8")
    assert main(["-q", str(instance)]) != EXIT_OK, (
        "the fixture is meant to fail when judged and it passes")

    path = tmp_path / "template.json"
    path.write_text(json.dumps(_template_kind(env)), "utf-8")
    assert main(["-q", str(path)]) == EXIT_OK, (
        "a submodel declared as a template was judged as an instance")


def test_the_vendored_templates_pass_the_tool_that_reads_them(tmp_path):
    """The strongest form of the same test, and the one a stranger runs
    first: point it at the published template. Every rule in this
    project is generated from these three files."""
    from aas_submodel_validate.cli import EXIT_OK, main

    vendored = sorted((ROOT / "src" / "aas_submodel_validate" / "data"
                       / "smt").rglob("template.json"))
    assert len(vendored) == 3, vendored
    for template in vendored:
        assert main(["-q", "--allow-unmatched", str(template)]) == EXIT_OK, (
            "%s is the template this project reads its rules out of, and "
            "the tool reports defects in it" % template.name)


def test_a_file_of_nothing_but_templates_says_so(tmp_path):
    """And the sentence has to be the right one. Skipping templates
    without saying anything would leave `SMT-D1` reporting that no
    submodel declares an identifier this tool has a table for -- which
    is false, and unhelpful: they declare it, they are simply not
    instances."""
    path = tmp_path / "templates.json"
    path.write_text(json.dumps(_template_kind(copy.deepcopy(hd_env()))), "utf-8")
    report = runner.run(path)
    assert not [f for f in report.findings if f.id == "SMT-D1"], (
        "the run says nothing here declares a known identifier, and one does")
    assert any("template" in note.lower() for note in report.notes), (
        "nothing in the report says why the submodel was not judged: %r"
        % report.notes)


#: (instances, templates) in the input, and what the three counts must
#: say. Four mutations of the counting survived a whole review round --
#: subtracting templates from `seen` again, pinning `specified` to zero,
#: dropping the subtraction in `--require-all-judged`, removing the
#: clause from the summary -- because nothing anywhere read these three
#: numbers together.
COUNTS = [(1, 0, (1, 1, 0)), (0, 1, (1, 0, 1)), (1, 1, (2, 1, 1)),
          (2, 1, (3, 2, 1)), (0, 2, (2, 0, 2))]


@pytest.mark.parametrize("instances,templates,expected", COUNTS)
def test_the_three_counts_agree_about_one_input(tmp_path, instances,
                                                templates, expected):
    """`submodelsSeen` is what the input holds, `submodelsSpecified` how
    many said they are specifications, `submodelsJudged` how many a
    table answered for. The first is the schema's own sentence, and
    taking the templates out of it made that sentence false."""
    env = copy.deepcopy(hd_env())
    one = env["submodels"][0]
    env["submodels"] = []
    for index in range(instances + templates):
        copied = copy.deepcopy(one)
        copied["id"] = "%s/%d" % (copied["id"], index)
        if index >= instances:
            copied["kind"] = "Template"
        env["submodels"].append(copied)
    path = tmp_path / "counts.json"
    path.write_text(json.dumps(env), "utf-8")
    report = runner.run(path)
    got = (report.submodels_seen, report.submodels_judged,
           report.submodels_specified)
    assert got == expected, "(seen, judged, specified)"
    summary = report.as_dict()["summary"]
    assert (summary["submodelsSeen"], summary["submodelsJudged"],
            summary["submodelsSpecified"]) == expected
    if templates:
        # The last line, not the report: the note above it also says
        # "not judged", so reading the whole render could not tell the
        # summary's clause from the note and the clause could be
        # deleted whole while this stayed green.
        summary_line = render(report).splitlines()[-1]
        assert "not judged" in summary_line, (
            "the summary line says nothing about the ones set aside: %r"
            % summary_line)
        assert str(templates) in summary_line


@pytest.mark.parametrize("instances,templates,fails", [
    (1, 0, False),      # judged everything there was
    (1, 1, False),      # the template is not coverage a caller can give
    (0, 1, False),      # nothing but specifications: nothing to require
    (0, 0, True),       # no submodels at all -- the emptiest pass of the lot
])
def test_require_all_judged_asks_only_for_what_can_be_given(tmp_path, instances,
                                                            templates, fails):
    """The subtraction was dead code for a template-only input: `or not
    submodels_judged` fired anyway, so the flag failed a file whose only
    fault was being a specification -- which the front page says it does
    not do, while `--help` says it fails when there was nothing to
    judge. Both are true of different inputs and the code now tells
    them apart."""
    from aas_submodel_validate.cli import EXIT_FINDINGS, EXIT_OK, main

    env = copy.deepcopy(hd_env())
    one = env["submodels"][0]
    env["submodels"] = []
    for index in range(instances + templates):
        copied = copy.deepcopy(one)
        copied["id"] = "%s/%d" % (copied["id"], index)
        if index >= instances:
            copied["kind"] = "Template"
        env["submodels"].append(copied)
    path = tmp_path / "require.json"
    path.write_text(json.dumps(env), "utf-8")
    got = main(["-q", "--allow-unmatched", "--require-all-judged", str(path)])
    assert got == (EXIT_FINDINGS if fails else EXIT_OK), (
        "%d instance(s) + %d template(s) left by %d" % (instances, templates, got))
