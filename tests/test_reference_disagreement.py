"""Shapes where an independent validator reads the standard differently.

Each case is a submodel on which this project and at least one other
published AAS validator return different answers. The other answer is
*evidence*, never the expected value: what these tests pin is this
project's reading, so that changing it is a decision somebody makes rather
than a diff nobody noticed. Where the difference is a policy this project
already chose, the case names the entry that chose it.

Twelve of the fourteen are rebuilt from this repository's own fixtures, so
they have one author and cannot go stale against a fixture that moved. The
two `custom_*` shapes are not rebuilt from anything -- there is no fixture
for a template this project has no table for -- so they are transcribed
from the comparison run and held only by their hash, which is the weaker
of the two and worth saying rather than blurring.

Rebuilding is the risk this file has to manage, not a convenience: a
rebuild that mutates a *different* element than the one both readers were
given is two answers to two questions, which is what a comparison is
supposed to rule out. Every case was checked element for element against
the document the two readers ran on. Four needed correcting -- two of the
four this file carried before, and two of the ten added with it -- and
each is then pinned by the hash of what it builds, so a fixture edit that
moves a case has to be acknowledged rather than absorbed.

What is pinned per case is the whole answer and not a set of rule ids: the
id, the severity, and the subject, as a sorted list. Ids alone cannot tell
"this element is absent" from "this element has the wrong type" when both
draw one row's rule, cannot see a report doubling, and cannot see a
finding move to a different element -- and this file makes claims about
all three.

Five kinds of difference appear, and they are not the same kind of fact:

* **policy** -- both readings are defensible and this project published
  which one it takes (#19 extensions, #14 element supplementals);
* **coverage** -- one reader asks a question the other does not, which is
  a statement about what each was built to do, and it points both ways;
* **severity** -- both notice and they disagree about what it means;
* **robustness** -- one reader answers and the other does not;
* **control** -- both agree, which a corpus of differences needs most.
"""
from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import re
from typing import NamedTuple, Optional, Tuple

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.rules import dn_tables
from builders import dn_env, hd_env

#: Identifiers of the elements the comparison mutated. Named here because
#: every case has to touch the element the other reader was given, and an
#: idShort would not survive this project's own matching discipline.
MANUFACTURER_NAME = "0112/2///61987#ABA565#009"
PRODUCT_URI = "0112/2///61987#ABN590#002"
MARKING_NAME = "0112/2///61987#ABA231#009"
DOCUMENT_IDENTIFIER = "0173-1#02-AAO099#004"
CLASS_ID = "0173-1#02-ABH996#003"
STATUS_VALUE = "0173-1#02-ABI001#003"

_ALTERNATE_NAME = "urn:example:alternate-manufacturer-name"


def _sid_values(element) -> set:
    """Every identifier this element would match a row by.

    Not `keys[0]`. The walk reads *every* key of a reference and offers the
    keys joined by "/" as one more spelling (#38), and it folds an
    element's supplementals in as well (#14). A locator that read the first
    key only would call an element unique that the walk sees twice, and the
    uniqueness assert below is the whole reason this helper exists.
    """
    values = set()
    for reference in ([element.get("semanticId")]
                      + list(element.get("supplementalSemanticIds") or [])):
        keys = [key.get("value") or "" for key in (reference or {}).get("keys", [])]
        values.update(keys)
        if len(keys) > 1:
            values.add("/".join(keys))
    return values - {""}


def _each(element):
    """This element and everything the walk would reach under it.

    `value` *and* `statements`: an Entity carries its children in the
    second, the engine descends both, and a locator that descended only
    `value` would mutate one of two elements and call it done.
    """
    yield element
    for key in ("value", "statements"):
        items = element.get(key)
        if isinstance(items, list):
            for child in items:
                if isinstance(child, dict) and "modelType" in child:
                    yield from _each(child)


def _find(env: dict, sid: str) -> dict:
    """The one element carrying `sid`, anywhere in the submodel."""
    found = [element for top in env["submodels"][0]["submodelElements"]
             for element in _each(top) if sid in _sid_values(element)]
    assert len(found) == 1, (
        "expected exactly one element for %s, found %d; the fixture moved "
        "and this case no longer mutates what was compared" % (sid, len(found)))
    return found[0]


def _drop(env: dict, sid: str) -> dict:
    """Remove that element from whichever list holds it."""
    target = _find(env, sid)
    for holder in [env["submodels"][0]] + [
            element for top in env["submodels"][0]["submodelElements"]
            for element in _each(top)]:
        for key in ("submodelElements", "value", "statements"):
            items = holder.get(key)
            if isinstance(items, list) and any(item is target for item in items):
                rest = [item for item in items if item is not target]
                assert rest or key == "submodelElements", (
                    "dropping %s would leave an empty %r, which the metamodel "
                    "refuses -- the case would draw a metamodel finding it was "
                    "never meant to be about" % (sid, key))
                holder[key] = rest
                return env
    raise AssertionError("nothing holds %s" % sid)


# -- the fourteen cases -------------------------------------------------------

def _case_hd_baseline():
    return hd_env()


def _case_hd_missing_document_identifier():
    return _drop(copy.deepcopy(hd_env()), DOCUMENT_IDENTIFIER)


def _case_hd_missing_class_id():
    return _drop(copy.deepcopy(hd_env()), CLASS_ID)


def _case_hd_wrong_release_vocabulary():
    env = copy.deepcopy(hd_env())
    _find(env, STATUS_VALUE)["value"] = "released"
    return env


def _case_dn_baseline():
    return dn_env()


def _case_dn_missing_product_uri():
    return _drop(copy.deepcopy(dn_env()), PRODUCT_URI)


def _case_dn_missing_marking_name():
    return _drop(copy.deepcopy(dn_env()), MARKING_NAME)


def _case_dn_wrong_element_kind():
    env = copy.deepcopy(dn_env())
    element = _find(env, MANUFACTURER_NAME)
    element["modelType"] = "Property"
    element["valueType"] = "xs:string"
    element["value"] = "Example Company Ltd."
    return env


def _case_dn_wrong_value_type():
    env = copy.deepcopy(dn_env())
    _find(env, PRODUCT_URI)["valueType"] = "xs:string"
    return env


def _case_dn_absent_id_short():
    env = copy.deepcopy(dn_env())
    del _find(env, MANUFACTURER_NAME)["idShort"]
    return env


def _case_dn_additional_element():
    env = copy.deepcopy(dn_env())
    env["submodels"][0]["submodelElements"].append({
        "modelType": "Property", "idShort": "VendorExtra",
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference",
                                 "value": "urn:example:vendor-extra"}]},
        "valueType": "xs:string", "value": "x"})
    return env


def _case_dn_supplemental_identity():
    env = copy.deepcopy(dn_env())
    element = _find(env, MANUFACTURER_NAME)
    element["supplementalSemanticIds"] = [copy.deepcopy(element["semanticId"])]
    element["semanticId"] = {"type": "ExternalReference",
                             "keys": [{"type": "GlobalReference",
                                       "value": _ALTERNATE_NAME}]}
    return env


def _custom(elements) -> dict:
    """A submodel of a template this project has no table for.

    Transcribed, not rebuilt: there is no fixture for a template this
    project does not know, so these two are held by their hash alone.
    """
    return {"submodels": [{
        "modelType": "Submodel", "id": "urn:example:custom-instance",
        "idShort": "Custom", "kind": "Instance",
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference",
                                 "value": "urn:example:custom"}]},
        "submodelElements": elements}]}


_COUNT = {"modelType": "Property", "idShort": "Count",
          "semanticId": {"type": "ExternalReference",
                         "keys": [{"type": "GlobalReference",
                                   "value": "urn:example:count"}]},
          "valueType": "xs:int", "value": "1"}
_TITLE = {"modelType": "Property", "idShort": "Title",
          "semanticId": {"type": "ExternalReference",
                         "keys": [{"type": "GlobalReference",
                                   "value": "urn:example:title"}]},
          "valueType": "xs:string", "value": "Example"}


def _case_custom_baseline():
    return _custom([copy.deepcopy(_COUNT), copy.deepcopy(_TITLE)])


def _case_custom_missing_count():
    return _custom([copy.deepcopy(_TITLE)])


CASES = {
    "custom_baseline": _case_custom_baseline,
    "custom_missing_count": _case_custom_missing_count,
    "dn_absent_id_short": _case_dn_absent_id_short,
    "dn_additional_element": _case_dn_additional_element,
    "dn_baseline": _case_dn_baseline,
    "dn_missing_marking_name": _case_dn_missing_marking_name,
    "dn_missing_product_uri": _case_dn_missing_product_uri,
    "dn_supplemental_identity": _case_dn_supplemental_identity,
    "dn_wrong_element_kind": _case_dn_wrong_element_kind,
    "dn_wrong_value_type": _case_dn_wrong_value_type,
    "hd_baseline": _case_hd_baseline,
    "hd_missing_class_id": _case_hd_missing_class_id,
    "hd_missing_document_identifier": _case_hd_missing_document_identifier,
    "hd_wrong_release_vocabulary": _case_hd_wrong_release_vocabulary,
}

#: Cases transcribed rather than rebuilt, and therefore held by hash alone.
TRANSCRIBED = frozenset({"custom_baseline", "custom_missing_count"})


#: What each case builds, by hash. A remembered verdict is worth nothing if
#: the input drifted underneath it, so a fixture edit that moves a case has
#: to move this line too and say why.
INPUTS = {
    "custom_baseline": "d6fdfb25e1c1c1a3688780ce395d735c102b990a3cc0ab9ae0234b27951c9ba0",
    "custom_missing_count": "74fd1c0f1f7e657a1e2b0ed64377a5971a367734e7538e19352addd87cbf987d",
    "dn_absent_id_short": "33fe27305b2623f3cc80b668900d947fc3d07ce07354cae9bceca66fcfe0cbb5",
    "dn_additional_element": "18df9bf6bc297c218ad477eb0080f0b4784776a4d2254352d6bb112f1dd5d38b",
    "dn_baseline": "938e9b952a5e26115b82dd494d9f42bdca8ba730ad79574a41736ae8c7418e42",
    "dn_missing_marking_name": "0fa0ddd7687a8d39dd5e427c56f1e9c1239a7a4dae7f278d4fb02f5b44d99c93",
    "dn_missing_product_uri": "a6897b2fa37f11cead72c4ca619bc43dcd37eea8c5ee806c198d25740ca191b2",
    "dn_supplemental_identity": "64dfd6b9483ee9f398a104620f5e465562e371d56625358f1843e23d81299a7c",
    "dn_wrong_element_kind": "e073f7833a50299f1862e9c5119db951a2fde06b81f6f2a702a1af77968028e7",
    "dn_wrong_value_type": "5f792ea4389790ab50148dafb1c6470e01338b054861768d9ef0f40d8b029bf2",
    "hd_baseline": "bc6829aa7271cfd653ac65ce5b0a0dfab34cfe0441b4870b4f83c50c52c17317",
    "hd_missing_class_id": "b8d896f23063b6ce685cb42f522fb5eddffa1dd9757210ed8e47574605c26b02",
    "hd_missing_document_identifier": "15f9a290a4343a17c855e5d5f05480b486ebc393d936c919691b421a29199b81",
    "hd_wrong_release_vocabulary": "9b3cc127ec209672bd2e7f9d708a2808261fb6265563eac7b223e2ba630f3b90",
}


class Verdict(NamedTuple):
    """This project's whole answer on one case.

    `findings` is a sorted list of `(rule id, severity, subject)` and not a
    set of ids, because this file claims things ids cannot carry: that one
    row's rule fires for two different reasons on two cases, that a nested
    row is answered *at its own depth*, and that a report is not doubled.
    `ok` and `judged` carry the rest of what a caller sees -- whether the
    file was called conformant, and whether it was judged at all.
    """
    findings: Tuple[Tuple[str, str, Optional[str]], ...]
    ok: bool
    judged: int
    kind: str
    direction: str
    why: str


def _v(findings, ok, judged, kind, why, direction=""):
    return Verdict(tuple(findings), ok, judged, kind, direction, why)


#: `kind` says what a change here would mean -- reversing a published
#: policy, dropping coverage, or a plain regression -- and `direction`,
#: where the difference is coverage, says whose reader asks the question.
#: `why` is the reason this project answers the way it does, and it is a
#: reason from the standard, never "because the other one said so".
VERDICTS = {
    "hd_baseline": _v(
        [], True, 1, "control",
        "a conformant instance draws nothing; both readers agree"),
    "dn_baseline": _v(
        [], True, 1, "control",
        "a conformant instance draws nothing; both readers agree"),
    "dn_missing_product_uri": _v(
        [("DN-E01", "error", "Nameplate")], False, 1, "agreement",
        "a mandatory top-level element is absent; both readers say so, and "
        "the subject is the scope because there is no element to name"),
    "dn_wrong_value_type": _v(
        [("DN-E01", "error", "Nameplate/URIOfTheProduct")], False, 1, "severity",
        "the template declares xs:anyURI; both readers compare valueType and "
        "disagree about what that means -- the other records it and still "
        "calls the file valid, this one does not. Same row as the case above "
        "and a different answer, which is why the subject is pinned"),
    "dn_additional_element": _v(
        [], True, 1, "policy",
        "#19: a template states a minimum, not a whitelist, so an element "
        "the template never mentions is not by itself a defect -- and it "
        "costs nothing elsewhere either, which is what unmatched and "
        "not_asked being empty says"),
    "dn_supplemental_identity": _v(
        [], True, 1, "policy",
        "#14: an element's supplementals are folded into the spellings it "
        "may match by, so the template's identifier carried in one still "
        "answers the mandatory row; #28 is the other half, at the submodel "
        "level, and is asserted separately below"),
    "dn_absent_id_short": _v(
        [("META", "warning", ".submodels[0]")], True, 1, "robustness",
        "malformed input is judged, not refused: idShort is required by the "
        "metamodel and the relayed channel says so, at warning, so the file "
        "is still read and still reported on"),
    "hd_missing_document_identifier": _v(
        [("HD-E06", "error",
          "HandoverDocumentation/Documents/[0]/DocumentIds/[0]")],
        False, 1, "coverage",
        "a mandatory element nested under a list is asked for at its own "
        "depth, which is what the subject says", direction="ours"),
    "hd_missing_class_id": _v(
        [("HD-E10", "error",
          "HandoverDocumentation/Documents/[0]/DocumentClassifications/[0]")],
        False, 1, "coverage",
        "same, below a second list", direction="ours"),
    "hd_wrong_release_vocabulary": _v(
        [("HD-D6", "warning",
          "HandoverDocumentation/Documents/[0]/DocumentVersions/[0]")],
        True, 1, "coverage",
        "the template fixes a vocabulary for this value, which is a question "
        "about content rather than structure -- and this project says so at "
        "warning, so the file is not called non-conformant for it",
        direction="ours"),
    "dn_wrong_element_kind": _v(
        [("DN-E02", "error", "Nameplate/ManufacturerName")], False, 1,
        "coverage",
        "the template declares the element kind, so a Property standing where "
        "a MultiLanguageProperty is declared is a template defect",
        direction="ours"),
    "dn_missing_marking_name": _v(
        [("DN-E21", "error", "Nameplate/Markings/[0]")], False, 1, "coverage",
        "a mandatory element inside a list item is asked for per item, and "
        "the subject names the item", direction="ours"),
    "custom_baseline": _v(
        [("SMT-D1", "error", None)], False, 0, "coverage",
        "there is no table for that template here, and saying so is the "
        "honest answer rather than silence -- nothing was judged",
        direction="theirs"),
    "custom_missing_count": _v(
        [("SMT-D1", "error", None)], False, 0, "coverage",
        "the same: a reader given the template as an argument can answer "
        "this and this one cannot, which is why it says so instead",
        direction="theirs"),
}


def _report(tmp_path, name):
    path = tmp_path / (name + ".json")
    path.write_bytes(json.dumps(CASES[name]()).encode("utf-8"))
    return runner.run(path)


def _answer(report):
    return sorted((finding.rule.id, str(finding.severity),
                   finding.violation.subject) for finding in report.findings)


@pytest.mark.parametrize("name", sorted(CASES), ids=sorted(CASES))
def test_each_case_builds_the_document_that_was_compared(name):
    """The pin.

    Each verdict below was compared against another reader's on one
    particular document. If the document changes, the two answers are
    answers to different questions and the comparison has to be redone --
    which is exactly the mistake this file made once, mutating a different
    element than the one both readers were given.
    """
    blob = json.dumps(CASES[name](), sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(blob).hexdigest() == INPUTS[name], (
        "case %r no longer builds the document its verdict was compared on; "
        "re-run the comparison before repinning" % name)


def test_no_two_cases_build_the_same_document():
    """A mutation that stops mutating is a case that quietly becomes its own
    control, and each hash is only ever compared to its own constant, so
    nothing else would notice."""
    assert len(set(INPUTS.values())) == len(CASES)


@pytest.mark.parametrize("name", sorted(CASES), ids=sorted(CASES))
def test_each_case_draws_the_verdict_that_was_decided(tmp_path, name):
    """This project's answer, pinned whole.

    The other reader's answer is recorded in docs/divergences.md and never
    here: writing it in as the expectation would turn this suite into a
    test of somebody else's release, and on several of these cases the two
    disagree on purpose.
    """
    expected = VERDICTS[name]
    report = _report(tmp_path, name)
    assert _answer(report) == list(expected.findings), (
        "%s -- %s" % (name, expected.why))
    assert (report.ok, report.submodels_judged) == (expected.ok, expected.judged), (
        "%s: the caller-visible answer changed -- %s" % (name, expected.why))


@pytest.mark.parametrize(
    "name", sorted(n for n, v in VERDICTS.items() if not v.findings),
    ids=sorted(n for n, v in VERDICTS.items() if not v.findings))
def test_a_silent_case_is_silent_everywhere(tmp_path, name):
    """Drawing no finding is not the same as costing nothing.

    An element the template never mentions could pass the rules and still
    be charged for in `unmatchedElements`, or take rules out of the run and
    be counted in `rulesNotAsked`. Under an id-set comparison the policy
    case and the plain control looked identical; they are only identical if
    the other two surfaces are empty too.
    """
    report = _report(tmp_path, name)
    assert list(report.not_asked) == [], "%s left rules unasked" % name
    assert list(report.unmatched) == [], "%s charged an element" % name


def test_every_case_carries_a_pin_and_a_verdict():
    """Neither map may quietly fall behind the case list."""
    assert set(CASES) == set(INPUTS) == set(VERDICTS)


def test_the_malformed_input_is_answered_rather_than_refused(tmp_path):
    """The robustness case, asserted on what makes it one.

    A submodel element with no idShort is malformed, and a reader may
    reasonably report it or reasonably reject the file -- but it has to do
    one of them. What it must not do is die on the way.

    "Did not die" is the hard half to assert, because this project relays a
    *crashed* rule as a finding too, under the same `META` id and the same
    `meta` kind. So a relay that threw would satisfy "a meta finding
    exists" -- the exact event this case exists to rule out. The assertions
    are therefore that the finding is not the could-not-run one, that it
    names the constraint it was supposed to find, and that the submodel was
    judged and reported on like any other.
    """
    report = _report(tmp_path, "dn_absent_id_short")
    relayed = [f for f in report.findings if f.rule.kind == "meta"]
    assert relayed, "the metamodel channel no longer reports the absent idShort"
    assert all(f.violation.message != runner.COULD_NOT_RUN for f in relayed), (
        "the relay crashed and was reported as a finding; that is dying on "
        "the way, not answering")
    assert any("AASd-117" in (f.violation.detail or "") + f.violation.message
               for f in relayed), (
        "the relayed finding no longer names the constraint an absent "
        "idShort violates")
    assert (report.submodels_judged, report.ok) == (1, True), (
        "the malformed file was no longer judged, or its exit changed")


def test_a_row_is_asked_once_per_list_item_not_once_per_list(tmp_path):
    """Not a compared case -- a gate the compared cases cannot be.

    Two of the corpus cases say a mandatory element below a
    `SubmodelElementList` is asked for *per item*. They cannot show it:
    every list in both fixtures holds exactly one item, so "asked per item"
    and "asked in the one item there is" draw the same verdict. Descend
    into only the first match and all fourteen stay green.

    So this builds what the corpus has not got: a second `Markings` item,
    conformant except for the mandatory `MarkingName`. The defect has to be
    reported, and reported against the *second* item.
    """
    env = copy.deepcopy(dn_env())
    markings = _find(env, "0112/2///61360_7#AAS006#001")
    second = copy.deepcopy(markings["value"][0])
    second["value"] = [child for child in second["value"]
                       if MARKING_NAME not in _sid_values(child)]
    markings["value"].append(second)
    path = tmp_path / "two-markings.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    report = runner.run(path)
    assert _answer(report) == [("DN-E21", "error", "Nameplate/Markings/[1]")], (
        "a mandatory element missing from the second list item was not "
        "reported against the second item")


def test_a_mandatory_row_is_satisfied_by_a_supplemental_identity(tmp_path):
    """The asymmetry worth writing down, both halves asserted.

    At the *element* level supplementals count: an element whose main
    identifier is the supplier's own but which also carries the template's
    is the element the template means, so `ManufacturerName` -- mandatory,
    exactly one -- is answered, and a reader taking main identifiers only
    reports it missing.

    At the *submodel* level they do not, because a published template wears
    one of our anchors in a supplemental and folding them in would let one
    template answer for another (#28).

    Two levels reading differently is the kind of thing that gets tidied
    into one rule by somebody who has not read why, and the tidy is one
    line. Asserting the element half alone does not catch it -- the tidy
    goes the other way.
    """
    from aas_submodel_validate import semantics
    from aas_submodel_validate.loader import load
    from aas_submodel_validate.rules import engine, profiles

    assert dn_tables.BY_ID["DN-E02"]["card"] == (1, 1), (
        "this case rests on the row being mandatory")
    path = tmp_path / "supplemental.json"
    path.write_bytes(json.dumps(_case_dn_supplemental_identity()).encode("utf-8"))
    ctx = runner.Context(load(path), profiles.Selection(None))
    matched = engine.analyze(ctx, dn_tables)["instances"].get("DN-E02") or []
    assert len(matched) == 1, (
        "the mandatory row is no longer answered by the supplemental "
        "identity, or the element-level reading changed")

    submodel = ctx.loaded.submodels[0]
    assert semantics.submodel_declares(
        submodel, dn_tables.TEMPLATE_SEMANTIC_ID), "wrong fixture"
    borrowed = copy.deepcopy(_case_dn_baseline())
    borrowed["submodels"][0]["supplementalSemanticIds"] = [
        copy.deepcopy(borrowed["submodels"][0]["semanticId"])]
    borrowed["submodels"][0]["semanticId"] = {
        "type": "ExternalReference",
        "keys": [{"type": "GlobalReference", "value": "urn:example:not-ours"}]}
    other = tmp_path / "borrowed.json"
    other.write_bytes(json.dumps(borrowed).encode("utf-8"))
    assert not semantics.submodel_declares(
        load(other).submodels[0], dn_tables.TEMPLATE_SEMANTIC_ID), (
        "a submodel wearing our anchor in a supplemental is now read as "
        "ours; the two levels have been tidied into one rule")


def test_the_corpus_is_not_a_sales_document():
    """A set of only-we-are-right cases proves nothing about a reading.

    This holds the corpus honest: controls where both agree, a case where
    both notice and disagree about what it means, policy differences where
    the other reading is defensible, and coverage differences pointing
    *both* ways -- named case by case, because a count of labels is
    satisfied by swapping two of them, which leaves the published sentence
    naming the wrong cases.
    """
    kinds = {verdict.kind for verdict in VERDICTS.values()}
    assert {"control", "agreement", "severity", "policy", "coverage",
            "robustness"} == kinds
    assert {name for name, v in VERDICTS.items() if v.direction == "theirs"} == {
        "custom_baseline", "custom_missing_count"}
    assert {name for name, v in VERDICTS.items() if v.direction == "ours"} == {
        "dn_missing_marking_name", "dn_wrong_element_kind",
        "hd_missing_class_id", "hd_missing_document_identifier",
        "hd_wrong_release_vocabulary"}
    assert all(bool(v.direction) == (v.kind == "coverage")
               for v in VERDICTS.values()), (
        "a direction on something that is not a coverage difference, or a "
        "coverage difference that does not say whose question it is")


def test_the_declined_cases_are_the_ones_a_template_argument_would_change(tmp_path):
    """Pinned so that widening the input mode is a decision, not a drift.

    Both `custom_*` cases draw SMT-D1 -- 'no table here answers for that
    template' -- and judge nothing. If this project ever accepts a template
    as an argument, these two are the cases whose verdicts change, and
    changing them should require editing this expectation on purpose. Read
    from the run and not from the table, so it is a fact about the tool.
    """
    for name in sorted(TRANSCRIBED):
        report = _report(tmp_path, name)
        assert _answer(report) == [("SMT-D1", "error", None)], name
        assert report.submodels_judged == 0, (
            "%s is now judged; the input mode widened" % name)


#: Number words as the divergences row spells them, so prose and corpus
#: cannot drift apart. Zero upward, because a count reaching a number this
#: map has not got should fail with the message below, not a KeyError.
_WORDS = {0: "no", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
          6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
          11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
          15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
          19: "nineteen", 20: "twenty"}


def _row_54() -> str:
    text = pathlib.Path(__file__).resolve().parents[1].joinpath(
        "docs", "divergences.md").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| 54 |")]
    assert len(rows) == 1, "row 54 is missing or duplicated"
    return rows[0]


def _figures() -> dict:
    golden = {n for n in CASES if n.endswith("_baseline")} - TRANSCRIBED
    kinds = [v.kind for v in VERDICTS.values()]
    directions = [v.direction for v in VERDICTS.values() if v.kind == "coverage"]
    agree = sum(1 for kind in kinds if kind in ("control", "agreement"))
    return {
        "total": len(CASES), "golden": len(golden),
        "mutations": len(CASES) - len(golden) - len(TRANSCRIBED),
        "transcribed": len(TRANSCRIBED), "agree": agree,
        "severity": kinds.count("severity"),
        "differ": len(CASES) - agree - kinds.count("severity"),
        "policy": kinds.count("policy"),
        "ours": directions.count("ours"), "theirs": directions.count("theirs"),
    }


def test_the_published_counts_match_the_corpus():
    """Every count row 54 states, derived from the cases rather than
    remembered -- and no count it states that the cases do not produce.

    A published number nobody recomputes goes wrong the first time a case
    is added, and this project has put a wrong one into its own record
    before. Containment alone was not enough: it let a fabricated sentence
    with two invented figures sit beside the true ones, because nothing
    read the row for numbers it should not contain.
    """
    row, figures = _row_54(), _figures()
    expected = [
        "the %s golden fixtures" % _WORDS[figures["golden"]],
        "%s single mutations" % _WORDS[figures["mutations"]],
        "%s submodels of a template" % _WORDS[figures["transcribed"]],
        "**%d of the %d**" % (figures["agree"], figures["total"]),
        "on **%d** both notice" % figures["severity"],
        "on **%d** they differ" % figures["differ"],
        "%s differences are policy" % _WORDS[figures["policy"]],
        "%s differences are questions" % _WORDS[figures["ours"]],
        "**%s point the other way**" % _WORDS[figures["theirs"]],
    ]
    missing = [phrase for phrase in expected if phrase.lower() not in row.lower()]
    assert not missing, (
        "docs/divergences.md row 54 no longer states what the corpus "
        "measures; missing: %s" % missing)

    # and the other direction: no figure the corpus does not produce. Code
    # spans (upstream commits, identifiers) and divergence references are
    # not claims about this corpus, so they are removed before looking.
    prose = re.sub(r"`[^`]*`", " ", row)
    prose = re.sub(r"#\d+", " ", prose)
    prose = prose[prose.index("|", 1) + 1:] if prose.startswith("| 54 |") else prose
    allowed = set(figures.values())
    stray = sorted({int(n) for n in re.findall(r"\b\d+\b", prose)} - allowed)
    assert not stray, (
        "row 54 states figures the corpus does not produce: %s" % stray)
