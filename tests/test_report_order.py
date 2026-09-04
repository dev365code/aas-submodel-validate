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

from aas_submodel_validate import model, runner
from aas_submodel_validate.model import Finding, Rule, Violation
from builders import build_aasx, hd_env

EXAMPLE = Path(__file__).resolve().parent / "corpus/idta/02004/example.json"

#: The order a reader is promised, written here rather than imported. A
#: test that borrows the ordering it is checking asserts that sorted
#: things are sorted; this is the second copy, and its whole job is to
#: disagree when the first one moves.
SEVERITY = ("error", "warning", "info")
KIND = ("container", "template", "lint", "meta")


def test_this_files_copy_knows_every_kind_there_is():
    """The copy above is deliberate and its *order* is its own -- that is
    what makes it a second opinion. Its *membership* is not: a fifth kind
    in `model.KINDS` would reach `_as_read`, whose `KIND.index` would
    raise ValueError from inside a list comprehension, and the reader of
    that failure would be told nothing about the vocabulary. Nothing
    pinned it, and the test that claimed to could not fail."""
    assert set(KIND) == set(model.KINDS)
    assert set(SEVERITY) == {str(s) for s in model.Severity}


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


def _pair_alike_but_for(component, values):
    """Two findings from one rule about one subject, differing in exactly
    one component of the key -- the smallest input that can say whether
    that component is being asked at all."""
    def rule(rule_id):
        return Rule(id=rule_id, kind="template", prio="MUST", title="t",
                    spec=None, fn=lambda ctx: ())

    alike = {"message": "the value is wrong", "subject": "urn:x"}
    if component == "rule_id":
        return [Finding(rule(value), Violation(**alike)) for value in values]
    return [Finding(rule("T1"), Violation(**{**alike, component: value}))
            for value in values]


def test_no_two_findings_share_a_place_in_the_order(tmp_path):
    """"Total order down to the message so two runs cannot differ" is a
    claim about ties, and a tie is what a sort hands back to whatever
    order the findings arrived in.

    Asked of `runner._reading_order`, not of this file's copy of it. The
    copy is what the order test above needs -- a second opinion about
    where findings belong -- and it is exactly the wrong thing here,
    because this is a claim about the real key: computed from the copy,
    dropping the message from `_reading_order` changed nothing and the
    mutation lived.

    Two halves, because the fixture can only answer the first. Whether
    the key separates everything a real run produces needs a real run.
    Whether the message is what separates two findings alike in every
    other component needs two such findings, and the fixture supplied
    them by accident: the relayed channel happens to report two
    constraints against one path. Asserting that it keeps doing so made
    a test of this ordering fail for work on that channel, so the pair
    that needs the message is built here instead."""
    report = runner.run(_four_kinds_at_one_severity(tmp_path))
    keys = [runner._reading_order(f) for f in report.findings]
    assert len(set(keys)) == len(keys), "two findings share a place in the order"

    for component, values in (("message", ("first thing", "second thing")),
                              ("subject", ("urn:a", "urn:b")),
                              ("rule_id", ("T1", "T2"))):
        one, other = _pair_alike_but_for(component, values)
        assert runner._reading_order(one) != runner._reading_order(other), \
            "two findings alike but for their %s land in one place" % component


def test_a_kind_the_order_does_not_know_goes_last():
    """Registration refuses a kind outside the vocabulary, so a
    registered rule cannot get here; this project builds a few rules by
    hand and they can.

    The fallback used to be the position lints occupy, which put an
    unrecognised kind in the middle of the channels a reader scans --
    between this project's own findings and the relayed ones, where it
    reads as if somebody had placed it there. After everything known is
    the only position that claims nothing."""
    unknown = Rule(id="T1", kind="a kind from the future", prio="MUST",
                   title="t", spec=None, fn=lambda ctx: ())
    last_known = Rule(id="T1", kind=KIND[-1], prio="MUST", title="t",
                      spec=None, fn=lambda ctx: ())
    violation = Violation("the value is wrong", subject="urn:x")
    assert (runner._reading_order(Finding(unknown, violation))
            > runner._reading_order(Finding(last_known, violation)))


def test_a_rule_that_stops_halfway_still_leaves_a_report_that_can_be_read():
    """A rule yields findings as it goes, so one that raises on its third
    subject has already produced two -- and the crash is reported under
    the same id, at the same severity, with no subject of its own.

    Which puts `None` beside a string in the one component of the key
    that is allowed to be absent, and a tuple sort compares them: the
    guard that turns it into `""` is the whole reason this run ends in a
    report rather than a traceback. Nothing measured it, and removing it
    left the suite green."""
    # A subject shaped like the ones rules really produce, and it has to
    # be: the guard's replacement is a *value*, and only a subject that
    # sorts on the far side of that value can see the wrong one. `str()`
    # in place of the guard yields "None", which lands after "urn:x" and
    # before "HandoverDocumentation/...", so a made-up subject let it
    # through and a real one does not.
    subject = "HandoverDocumentation/Documents/[0]"

    def stops_halfway(ctx):
        yield Violation("the value is wrong", subject=subject)
        raise KeyError("the third subject")

    rule = Rule(id="T1", kind="template", prio="MUST", title="t", spec=None,
                fn=stops_halfway, fix="mend it")
    findings = runner.execute([rule], ctx=None)
    assert [f.violation.subject for f in findings] == [subject, None], \
        "this no longer puts an absent subject beside a present one"
    # Where it lands, not merely that the sort survives. `assert
    # sorted(...)` was a truthiness check on a non-empty list: it caught
    # the guard being deleted, by raising, and let `or "zzz"` through --
    # which sorts the crash to the bottom of its rule's block, under the
    # partial findings, where the reader meets it last.
    ordered = sorted(findings, key=runner._reading_order)
    assert [f.violation.subject for f in ordered] == [None, subject]


def test_this_fixture_would_notice_the_sort_going_away(tmp_path, monkeypatch):
    """A report whose rules happen to fire in reading order observes
    nothing about the sort: delete the sort and such a test stays green.
    Measured -- the suite had such a test, and most changes to the
    ordering lived through it."""
    path = _four_kinds_at_one_severity(tmp_path)
    ordered = [f.id for f in runner.run(path).findings]
    monkeypatch.setattr(runner, "_reading_order", lambda finding: 0)
    as_generated = [f.id for f in runner.run(path).findings]
    assert ordered != as_generated


def test_errors_lead_and_meta_trails(tmp_path):
    env = copy.deepcopy(hd_env())
    submodel = env["submodels"][0]
    # One error (StatusSetDate broken lexically), one lint warning of our
    # own (HDL5, below), one lint info (HDL3, below) and two relayed
    # warnings the fixture has always carried: AASd-120 for the idShort
    # on a list child, and a value/value-type mismatch. Counted here
    # because the comment said "one meta warning" while two arrived.
    documents = submodel["submodelElements"][0]
    documents["value"][0]["idShort"] = "Datasheet"
    # The info, which the comment above claimed before anything produced
    # it: no fixture anywhere made an `info` finding in a sorted report,
    # so `info`'s rank was a number nothing read and could be moved to
    # the front -- lints above the errors -- with the suite green. HDL3
    # answers when a reference's type is not the template's.
    #
    # The key's type moves with it. A `ModelReference` whose first key is
    # a `GlobalReference` violates AASd-123, so flipping the type alone
    # bought the info by making the file illegal in a second way and
    # added a relayed warning nobody asked for.
    documents["semanticId"]["type"] = "ModelReference"
    documents["semanticId"]["keys"][0]["type"] = "Submodel"
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
    assert set(severities) == set(SEVERITY), \
        "this fixture no longer carries all three severities, so it ranks two"
    assert severities == sorted(severities, key=("error", "warning", "info").index)
    kinds = [f.rule.kind for f in report.findings if str(f.severity) == "warning"]
    assert "meta" in kinds and set(kinds) != {"meta"}, \
        "this fixture has only one kind of warning, so it orders nothing"
    assert kinds == sorted(kinds, key=("container", "template", "lint", "meta").index)
    assert report.findings[0].id == "HD-D8"
