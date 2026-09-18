"""Shapes where an independent validator reads the standard differently.

Each case is a submodel on which this project and at least one other
published AAS validator return different answers. The other answer is
*evidence*, never the expected value: what these tests pin is this
project's reading, so that changing it is a decision somebody makes rather
than a diff nobody noticed. Where the difference is a policy this project
already chose, the case names the entry that chose it.

The shapes are rebuilt from this repository's own fixtures rather than
copied in, so they have one author and cannot go stale against a fixture
that moved. Rebuilding is the risk this file has to manage, not a
convenience: a rebuild that mutates a *different* element than the one
both readers were given is two answers to two questions, which is what a
comparison is supposed to rule out. Every case below was checked
element-for-element against the document the two readers actually ran on,
and four of them were wrong the first time and were corrected. Each is
then pinned by the hash of what it builds, so a fixture edit that moves a
case has to be acknowledged rather than absorbed.

Three kinds of difference appear, and they are not the same kind of fact:

* **policy** -- both readings are defensible and this project published
  which one it takes (#19 extensions, #28 identity);
* **coverage** -- one reader asks a question the other does not, which is
  a statement about what each was built to do, and it points both ways;
* **robustness** -- one reader answers and the other does not.
"""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.rules import dn_tables
from builders import dn_env, hd_env

#: Identifiers of the elements the comparison mutated. Named here because
#: every case has to touch the element the other reader was given, and an
#: idShort would not survive this project\'s own matching discipline.
MANUFACTURER_NAME = "0112/2///61987#ABA565#009"
PRODUCT_URI = "0112/2///61987#ABN590#002"
MARKING_NAME = "0112/2///61987#ABA231#009"
DOCUMENT_IDENTIFIER = "0173-1#02-AAO099#004"
CLASS_ID = "0173-1#02-ABH996#003"
STATUS_VALUE = "0173-1#02-ABI001#003"

_ALTERNATE_NAME = "urn:example:alternate-manufacturer-name"


def _sid_of(element) -> str:
    keys = (element.get("semanticId") or {}).get("keys") or [{}]
    return keys[0].get("value") or ""


def _each(element):
    yield element
    value = element.get("value")
    if isinstance(value, list):
        for child in value:
            if isinstance(child, dict) and "modelType" in child:
                yield from _each(child)


def _find(env: dict, sid: str) -> dict:
    """The one element carrying `sid`, anywhere in the submodel."""
    found = [element for top in env["submodels"][0]["submodelElements"]
             for element in _each(top) if _sid_of(element) == sid]
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
        for key in ("submodelElements", "value"):
            items = holder.get(key)
            if isinstance(items, list) and any(item is target for item in items):
                holder[key] = [item for item in items if item is not target]
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
    """A submodel of a template this project has no table for."""
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

#: This project\'s answer on each case: every rule id the run draws, the
#: relayed metamodel channel included, because on one of these the whole
#: point is that something was said at all.
#:
#: `kind` says what a change here would mean -- reversing a published
#: policy, dropping coverage, or a plain regression -- and `direction`,
#: where the difference is coverage, says whose reader asks the question.
#: `why` is the reason this project answers the way it does, and it is a
#: reason from the standard, never "because the other one said so".
VERDICTS = {
    # name: (rule ids, kind, direction, why)
    "hd_baseline": (
        frozenset(), "control", "",
        "a conformant instance draws nothing; both readers agree"),
    "dn_baseline": (
        frozenset(), "control", "",
        "a conformant instance draws nothing; both readers agree"),
    "dn_missing_product_uri": (
        frozenset({"DN-E01"}), "agreement", "",
        "a mandatory top-level element is absent; both readers say so"),
    "dn_wrong_value_type": (
        frozenset({"DN-E01"}), "agreement", "",
        "the template declares xs:anyURI; both readers compare valueType, "
        "though the other records it without calling the file invalid"),
    "dn_additional_element": (
        frozenset(), "policy", "",
        "#19: a template states a minimum, not a whitelist, so an element "
        "the template never mentions is not by itself a defect"),
    "dn_supplemental_identity": (
        frozenset(), "policy", "",
        "#28: the submodel\'s own identity is read from its main semanticId "
        "only, but an element\'s supplementals do count, so the template\'s "
        "identifier carried in one still answers the mandatory row"),
    "dn_absent_id_short": (
        frozenset({"META"}), "robustness", "",
        "malformed input is judged, not refused: idShort is required by the "
        "metamodel and the relayed channel says so"),
    "hd_missing_document_identifier": (
        frozenset({"HD-E06"}), "coverage", "ours",
        "a mandatory element nested under a list is asked for at its own "
        "depth, not only at the top level"),
    "hd_missing_class_id": (
        frozenset({"HD-E10"}), "coverage", "ours",
        "same, below a second list"),
    "hd_wrong_release_vocabulary": (
        frozenset({"HD-D6"}), "coverage", "ours",
        "the template fixes a vocabulary for this value, which is a question "
        "about content rather than structure"),
    "dn_wrong_element_kind": (
        frozenset({"DN-E02"}), "coverage", "ours",
        "the template declares the element kind, so a Property standing where "
        "a MultiLanguageProperty is declared is a template defect"),
    "dn_missing_marking_name": (
        frozenset({"DN-E21"}), "coverage", "ours",
        "a mandatory element inside a list item is asked for per item"),
    "custom_baseline": (
        frozenset({"SMT-D1"}), "coverage", "theirs",
        "there is no table for that template here, and saying so is the "
        "honest answer rather than silence"),
    "custom_missing_count": (
        frozenset({"SMT-D1"}), "coverage", "theirs",
        "the same: a reader given the template as an argument can answer "
        "this and this one cannot, which is why it says so instead"),
}


def _report(tmp_path, name):
    path = tmp_path / (name + ".json")
    path.write_bytes(json.dumps(CASES[name]()).encode("utf-8"))
    return runner.run(path)


@pytest.mark.parametrize("name", sorted(CASES), ids=sorted(CASES))
def test_each_case_builds_the_document_that_was_compared(name):
    """The pin.

    Each verdict below was compared against another reader\'s on one
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


@pytest.mark.parametrize("name", sorted(CASES), ids=sorted(CASES))
def test_each_case_draws_the_verdict_that_was_decided(tmp_path, name):
    """This project\'s answer, pinned.

    The other reader\'s answer is recorded in docs/divergences.md and never
    here: writing it in as the expectation would turn this suite into a
    test of somebody else\'s release, and on several of these cases the two
    disagree on purpose.
    """
    expected, _kind, _direction, why = VERDICTS[name]
    drawn = {finding.rule.id for finding in _report(tmp_path, name).findings}
    assert drawn == set(expected), "%s -- %s" % (name, why)


def test_every_case_carries_a_pin_and_a_verdict():
    """Neither map may quietly fall behind the case list."""
    assert set(CASES) == set(INPUTS) == set(VERDICTS)


def test_the_malformed_input_is_answered_rather_than_refused(tmp_path):
    """The robustness case, asserted on what makes it one.

    A submodel element with no idShort is malformed, and a reader may
    reasonably report it or reasonably reject the file -- but it has to do
    one of them. What it must not do is die on the way, which is what made
    this case worth keeping: this project answers, names the element\'s
    absence through the relayed metamodel channel, and exits as it does for
    any input it could read.
    """
    report = _report(tmp_path, "dn_absent_id_short")
    assert [f for f in report.findings if f.rule.kind == "meta"], (
        "the metamodel channel no longer reports the absent idShort")
    assert report.findings, "malformed input drew nothing at all"


def test_a_mandatory_row_is_satisfied_by_a_supplemental_identity(tmp_path):
    """The asymmetry worth writing down, asserted on its mechanism.

    At the submodel level this project reads the main semanticId only,
    because a published template wears one of our anchors in a supplemental
    and reading those would let one template answer for another (#28). At
    the element level supplementals do count: an element whose main
    identifier is the supplier\'s own but which also carries the template\'s
    is the element the template means.

    So `ManufacturerName` -- mandatory, exactly one -- is answered here,
    and a reader taking main identifiers only reports it missing. Two
    levels reading differently is the kind of thing that gets tidied into
    one rule by somebody who has not read why, so the mechanism is pinned
    and not just the empty verdict.
    """
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


def test_the_corpus_is_not_a_sales_document():
    """A set of only-we-are-right cases proves nothing about a reading.

    This holds the corpus honest: it must carry controls where both agree,
    policy differences where the other reading is defensible, and coverage
    differences pointing *both* ways -- including the two that say plainly
    that a reader handed the template as an argument answers a question
    this project declines to.
    """
    kinds = {kind for _ids, kind, _d, _w in VERDICTS.values()}
    assert {"control", "agreement", "policy", "coverage", "robustness"} <= kinds
    directions = {direction for _i, kind, direction, _w in VERDICTS.values()
                  if kind == "coverage"}
    assert directions == {"ours", "theirs"}, (
        "every coverage difference points the same way; that is a sales "
        "document, not a comparison")


def test_the_declined_cases_are_the_ones_a_template_argument_would_change():
    """Pinned so that widening the input mode is a decision, not a drift.

    Both `custom_*` cases draw SMT-D1 -- \'no table here answers for that
    template\' -- and nothing else. If this project ever accepts a template
    as an argument, these two are the cases whose verdicts change, and
    changing them should require editing this expectation on purpose.
    """
    declined = {name for name, (ids, _k, _d, _w) in VERDICTS.items()
                if ids == frozenset({"SMT-D1"})}
    assert declined == {"custom_baseline", "custom_missing_count"}


#: Number words as the divergences row spells them, so prose and corpus
#: cannot drift apart in either direction.
_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
          7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
          12: "twelve"}


def test_the_published_counts_match_the_corpus():
    """Every count row 54 states, derived from the cases rather than
    remembered.

    A published number that nobody recomputes is a number that goes wrong
    the first time a case is added, and this project has put a wrong one
    into its own record before. So the row is read back and each figure in
    it has to be the figure the corpus produces.
    """
    import pathlib
    import re

    text = pathlib.Path(__file__).resolve().parents[1].joinpath(
        "docs", "divergences.md").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| 54 |")]
    assert len(rows) == 1, "row 54 is missing or duplicated"
    row = rows[0]

    golden = {n for n in CASES if n.endswith("_baseline")
              and not n.startswith("custom")}
    custom = {n for n in CASES if n.startswith("custom")}
    kinds = [kind for _i, kind, _d, _w in VERDICTS.values()]
    directions = [direction for _i, kind, direction, _w in VERDICTS.values()
                  if kind == "coverage"]
    agree = sum(1 for kind in kinds if kind in ("control", "agreement"))

    expected = [
        "the %s golden fixtures" % _WORDS[len(golden)],
        "%s single mutations" % _WORDS[len(CASES) - len(golden) - len(custom)],
        "%s submodels of a template" % _WORDS[len(custom)],
        "**%d of the %d**" % (agree, len(CASES)),
        "on **%d** they differ" % (len(CASES) - agree),
        "%s differences are policy" % _WORDS[kinds.count("policy")],
        "%s differences are questions" % _WORDS[directions.count("ours")],
        "**%s point the other way**" % _WORDS[directions.count("theirs")],
    ]
    missing = [phrase for phrase in expected
               if phrase.lower() not in row.lower()]
    assert not missing, (
        "docs/divergences.md row 54 no longer states what the corpus "
        "measures; missing: %s" % missing)
    # and no stray figure claims a different total
    assert not re.search(r"\bof the (?!%d\b)\d+\b" % len(CASES), row), (
        "row 54 cites a total other than the corpus size")
