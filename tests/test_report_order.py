"""A report is read top to bottom by a person with limited patience.

Errors first, then warnings, then notes; within a severity our own
findings before the relayed metamodel channel, because 77 relayed
constraint messages must not bury the two template findings the reader
came for. Total order down to the message so two runs cannot differ.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from aas_submodel_validate import runner
from builders import build_aasx, hd_env

EXAMPLE = Path(__file__).resolve().parent / "corpus/idta/02004/example.json"

#: The order a reader is promised, written here rather than imported. A
#: test that borrows the ordering it is checking asserts that sorted
#: things are sorted; this is the second copy, and its whole job is to
#: disagree when the first one moves.
SEVERITY = ("error", "warning", "info")
KIND = ("container", "template", "lint", "meta")


def _as_read(finding):
    return (SEVERITY.index(str(finding.severity)),
            KIND.index(finding.rule.kind),
            finding.id,
            finding.violation.subject or "",
            finding.violation.message)


def _four_kinds_at_one_severity(tmp_path):
    """The official example, inside a container declaring a supplementary
    part it does not hold.

    It discriminates twice, which is why it is this and not something
    smaller. The example's findings come out in an order the sort has to
    change -- ungathered it opens with HD-D6 and sorted with HD-D10, and
    the relayed messages move from document order to path order. And the
    missing part adds a container warning, so `X4` and `HD-D10` land at
    one severity with the kind order and the id order disagreeing about
    which leads. Without the second, every id prefix in this file happens
    to sort in kind order, and dropping the kind from the key changes
    nothing at all."""
    return build_aasx(tmp_path / "example-with-a-missing-part.aasx",
                      payload=EXAMPLE.read_bytes(),
                      suppl_targets=("aasx/files/absent.png",))


def test_the_report_is_read_in_the_promised_order(tmp_path):
    """Every finding, against the order written down above."""
    report = runner.run(_four_kinds_at_one_severity(tmp_path))
    kinds = {f.rule.kind for f in report.findings if str(f.severity) == "warning"}
    assert kinds == set(KIND), "the fixture stopped carrying all four kinds"
    keys = [_as_read(f) for f in report.findings]
    assert keys == sorted(keys)


def test_the_kind_decides_before_the_id(tmp_path):
    """The reason there is a kind in the key at all: 77 relayed messages
    must not bury the findings the reader came for. Asserted where it
    costs something -- `X4` sorts after `HD-D10` by id and before it by
    kind, so this passes only if the kind is asked first."""
    report = runner.run(_four_kinds_at_one_severity(tmp_path))
    warnings = [f.id for f in report.findings if str(f.severity) == "warning"]
    assert warnings.index("X4") < warnings.index("HD-D10")
    assert warnings.index("HDL5") < warnings.index("META")


def test_no_two_findings_share_a_place_in_the_order(tmp_path):
    """"Total order down to the message so two runs cannot differ" is a
    claim about ties, and a tie is what a sort hands back to whatever
    order the findings arrived in. Five pairs here agree on severity,
    kind, id and subject; the message is the only thing left to separate
    them.

    Dropping the message from the key is the one mutation of this
    ordering that still lives, and it lives because it cannot be seen:
    the relayed channel emits `AASd-109` before `AASd-120`, which is also
    the order the message would sort them into, so the tie resolves the
    same way with the component and without it. What is asserted instead
    is the property the component exists for -- the key is total -- and
    that the tie is real, so this stops being a sentence about nothing
    the day an input arrives in the other order."""
    report = runner.run(_four_kinds_at_one_severity(tmp_path))
    keys = [_as_read(f) for f in report.findings]
    assert len(set(keys)) == len(keys), "two findings share a place in the order"
    without_message = [key[:-1] for key in keys]
    assert len(set(without_message)) < len(without_message), \
        "nothing here needs the message to be separated, so this asserts nothing"


def test_this_fixture_would_notice_the_sort_going_away(tmp_path, monkeypatch):
    """A report whose rules happen to fire in reading order observes
    nothing about the sort: delete the sort and such a test stays green.
    Measured -- the suite had one, and ten of thirteen mutations of the
    ordering lived through it."""
    path = _four_kinds_at_one_severity(tmp_path)
    ordered = [f.id for f in runner.run(path).findings]
    monkeypatch.setattr(runner, "_reading_order", lambda finding: 0)
    as_generated = [f.id for f in runner.run(path).findings]
    assert ordered != as_generated


def test_errors_lead_and_meta_trails(tmp_path):
    env = copy.deepcopy(hd_env())
    submodel = env["submodels"][0]
    # one error (break StatusSetDate lexically), one meta warning
    # (idShort on a list child), one lint info (reference type)
    documents = submodel["submodelElements"][0]
    documents["value"][0]["idShort"] = "Datasheet"
    # a lint warning of our own, so the kind order below has two kinds to
    # order: the template's own §2.3 spelling draws HDL5. Without it every
    # warning in this fixture came from the metamodel channel, and any
    # kind order at all -- including none -- satisfied the assertion.
    for classification in documents["value"][0]["value"][1]["value"]:
        for leaf in classification["value"]:
            if leaf.get("idShort") == "ClassificationSystem":
                leaf["value"] = "VDI2770:2020"
    version = documents["value"][0]["value"][2]["value"][0]
    for child in version["value"]:
        if child.get("idShort") == "StatusSetDate":
            child["value"] = "not-a-date"
    submodel["semanticId"] = {"type": "ModelReference",
                              "keys": [{"type": "Submodel",
                                        "value": "0173-1#01-AHF578#003"}]}
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    report = runner.run(path)
    severities = [str(f.severity) for f in report.findings]
    assert severities == sorted(severities, key=("error", "warning", "info").index)
    kinds = [f.rule.kind for f in report.findings if str(f.severity) == "warning"]
    assert "meta" in kinds and set(kinds) != {"meta"}, \
        "this fixture has only one kind of warning, so it orders nothing"
    assert kinds == sorted(kinds, key=("container", "template", "lint", "meta").index)
    assert report.findings[0].id == "HD-D8"
