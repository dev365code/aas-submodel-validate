"""Regressions a later review found in the matching engine.

Every test here reproduces a confirmed finding: a conformant file being
failed, a defective file being hidden, a crash, or a non-deterministic
report. They were red against the pre-redesign engine.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

from aas_submodel_validate import runner
from aas_submodel_validate.loader import load
from aas_submodel_validate.rules import engine, hd_tables
from builders import hd_env, inject, strip_row


class _Key:
    """One key of a ModelReference, as `resolve_in_submodel` reads it."""

    def __init__(self, value):
        self.value = value


SRC = str(Path(__file__).resolve().parents[1] / "src")


def _write(tmp_path, env):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return path


def _ids(tmp_path, env):
    return {f.id for f in runner.run(_write(tmp_path, env)).findings}


def _document(env):
    return env["submodels"][0]["submodelElements"][0]["value"][0]


def _classifications_sml(env):
    return _document(env)["value"][1]


def _version(env):
    return _document(env)["value"][2]["value"][0]


# -- matching parity: hand rules must read the tree the way the walk does ----

def test_a_sidless_classification_does_not_trip_hd_d2(tmp_path):
    """A DocumentClassification SMC without its own semanticId is legal
    AAS (the official example ships list children that way) and the
    generated layer accepts it. HD-D2 (MUST) must not then report the
    mandatory classification 'missing'."""
    env = copy.deepcopy(hd_env())
    _classifications_sml(env)["value"][0].pop("semanticId", None)
    ids = _ids(tmp_path, env)
    assert "HD-D2" not in ids


def test_class_rules_still_reach_a_sidless_classification(tmp_path):
    env = copy.deepcopy(hd_env())
    smc = _classifications_sml(env)["value"][0]
    smc.pop("semanticId", None)
    for child in smc["value"]:
        if child.get("idShort") == "ClassId":
            child["value"] = "99-99"
    assert "HD-D3" in _ids(tmp_path, env)


# -- a cardinality violation must not silence the subtree --------------------

def test_a_duplicate_list_still_has_its_children_validated(tmp_path):
    env = copy.deepcopy(hd_env())
    for child in _version(env)["value"]:
        if child.get("idShort") == "StatusValue":
            child["value"] = "released"        # a nested HD-D6 warning
    documents_sml = env["submodels"][0]["submodelElements"][0]
    env["submodels"][0]["submodelElements"].append(copy.deepcopy(documents_sml))
    ids = _ids(tmp_path, env)
    assert "HD-E01" in ids                     # the cardinality violation itself
    assert "HD-D6" in ids                      # was hidden by the `continue`


# -- a mistyped element must not crash the hand rules ------------------------

def test_a_property_wearing_a_document_id_does_not_crash_six_rules(tmp_path):
    env = copy.deepcopy(hd_env())
    env["submodels"][0]["submodelElements"][0]["value"].insert(0, {
        "modelType": "Property", "valueType": "xs:string", "value": "oops",
        "semanticId": {"type": "ExternalReference", "keys": [{
            "type": "GlobalReference",
            "value": "0173-1#02-ABI500#003/0173-1#01-AHF579#003"}]}})
    report = runner.run(_write(tmp_path, env))
    assert [f.id for f in report.findings if "could not run" in f.violation.message] == []


# -- component decomposition must not fabricate a cardinality violation ------

def test_a_document_id_does_not_double_as_its_parent_list(tmp_path):
    """The Document collection's id is a composite of the Documents list
    id and the item id. Splitting it on '/' let the collection match the
    Documents *list* row too, fabricating 'found 2'."""
    env = copy.deepcopy(hd_env())
    ids = _ids(tmp_path, env)
    assert "HD-E01" not in ids                 # exactly one Documents, and it knows it


# -- the in-list fallback is a licence, and it is licensed only in a list ----

#: A list child with no semanticId of its own counts for its list's sole
#: child row (docs/divergences.md #11): the official example ships them
#: that way. The licence is deliberate and it is narrow, and nothing
#: measured how narrow -- three places decide whether it applies and each
#: could be switched on where it does not belong, which turns "this
#: element declares nothing" into "this element is whatever row comes
#: first with a matching kind".
NAMELESS_LIST = {"idShort": "Nameless", "modelType": "SubmodelElementList",
                 "typeValueListElement": "SubmodelElementCollection", "value": []}


def test_a_nameless_element_at_the_top_is_not_the_first_row_that_fits(tmp_path):
    """The submodel's own elements are not inside a list, so the licence
    does not reach them. A SubmodelElementList declaring no semanticId
    would otherwise be claimed by `Documents` -- the first top-level row
    of that kind -- and a file carrying one alongside its real Documents
    would be told it has two of something it has one of."""
    env = copy.deepcopy(hd_env())
    env["submodels"][0]["submodelElements"].append(copy.deepcopy(NAMELESS_LIST))
    assert "HD-E01" not in _ids(tmp_path, env)


def test_a_nameless_child_of_a_collection_is_not_claimed_either(tmp_path):
    """The same licence at the other seam. `child_of` is what the hand
    rules navigate with, and it asks the walk's own matcher -- so it has
    to decide the same question, and its parents are collections, never
    lists. A nameless list placed first among a Document's children would
    otherwise answer to `DocumentIds`, and the rules that read the real
    one would read this instead: HD-D4 would find no primary flag among
    no identifiers."""
    env = copy.deepcopy(hd_env())
    _document(env)["value"].insert(0, copy.deepcopy(NAMELESS_LIST))
    # This project's own findings, not the relayed channel's: a list
    # declaring nothing is a metamodel matter and aas-core3.0 says so.
    assert not [rule_id for rule_id in _ids(tmp_path, env)
                if rule_id.startswith("HD")]


def test_a_leaf_wearing_a_lists_identifier_is_not_walked_into(tmp_path):
    """`child_of` answers with whatever matches the row, and matching does
    not ask about kind -- so a Property wearing a list's identifier is
    what the hand rules get handed, and `children_of` is then asked for
    its children. Its value is a string.

    The refusal that stops this is one line in `children_of` and nothing
    reached it: deleting it left the suite green while a run over such a
    file ended in a traceback dressed as a finding. Placed first among a
    Document's children, because `child_of` takes the first match and the
    real DocumentIds is still there behind it."""
    env = copy.deepcopy(hd_env())
    _document(env)["value"].insert(0, {
        "modelType": "Property", "valueType": "xs:string", "value": "not a list",
        "semanticId": {"type": "ExternalReference", "keys": [{
            "type": "GlobalReference",
            "value": hd_tables.BY_LABEL["DocumentIds"]["sid"]}]}})
    report = runner.run(_write(tmp_path, env))
    assert [f.id for f in report.findings
            if "could not run" in f.violation.message] == []
    # And the walk still says what is wrong with the file: two elements
    # answer to a row that admits one.
    assert "HD-E03" in {f.id for f in report.findings}


# -- one defect must not silence the next element ---------------------------

def test_a_kind_violation_does_not_silence_the_element_beside_it(tmp_path):
    """The comment one scope out says a wrong *count* must not silence
    the per-element checks. This is the same claim one level in: the
    per-element loop skips the rest of *this* element's checks when its
    kind is wrong, and must go on to the next element.

    Two `Version`s where the template wants one: the first a
    MultiLanguageProperty, the second a Property carrying the wrong
    valueType. All three findings, or the second element's defect is
    hidden behind the first element's."""
    row = hd_tables.BY_LABEL["Version"]
    env = copy.deepcopy(hd_env())
    strip_row(env, row, hd_tables)
    sid = {"type": "ExternalReference",
           "keys": [{"type": "GlobalReference", "value": row["sid"]}]}
    inject(env, hd_tables.BY_ID[row["parent"]], [
        {"idShort": "VersionA", "modelType": "MultiLanguageProperty",
         "semanticId": sid, "value": [{"language": "en", "text": "V1"}]},
        {"idShort": "VersionB", "modelType": "Property", "valueType": "xs:int",
         "semanticId": sid, "value": "2"}], hd_tables)
    path = _write(tmp_path, env)
    said = [f.violation.message for f in runner.run(path).findings if f.id == row["id"]]
    assert any("found 2" in m for m in said), said
    assert any("must be a Property" in m for m in said), said
    assert any("valueType xs:string" in m for m in said), \
        "the second element's defect stopped being reported: %s" % said


def test_one_element_draws_one_near_miss(tmp_path):
    """An element carries every identifier it declares into the near-miss
    search, so it can be almost-right for more than one row at once. It
    is one element and it gets one diagnosis; reporting it against every
    row it approaches would put the same element in the report as many
    times as the template has rows near it."""
    env = copy.deepcopy(hd_env())
    env["submodels"][0]["submodelElements"].append({
        "idShort": "Both", "modelType": "SubmodelElementList",
        "typeValueListElement": "Entity",
        "semanticId": {"type": "ExternalReference", "keys": [
            {"type": "GlobalReference", "value": "0173-1#02-ABI500#004"}]},
        "supplementalSemanticIds": [{"type": "ExternalReference", "keys": [
            {"type": "GlobalReference",
             "value": "https://admin-shell.io/vdi/2770/1/0/EntityForDocumentation"}]}],
        "value": []})
    near = [f for f in runner.run(_write(tmp_path, env)).findings if f.id == "HDL2"]
    assert len(near) == 1, [f.violation.detail for f in near]


# -- navigation for the hand rules: what a key path may address --------------

def test_a_reference_addresses_by_position_only_inside_a_list(tmp_path):
    """The metamodel addresses a SubmodelElementList's children by index
    and everything else by idShort. A submodel's own elements are not a
    list, so a first step of "0" names an element called "0" and nothing
    else -- otherwise every reference whose first step happened to be a
    number would resolve to whatever the file happens to put first, and
    HD-D9 would report that a reference walks somewhere it does not."""
    submodel = load(_write(tmp_path, copy.deepcopy(hd_env()))).submodels[0]
    assert engine.resolve_in_submodel(submodel, [_Key("urn:x"), _Key("Documents")])
    assert engine.resolve_in_submodel(
        submodel, [_Key("urn:x"), _Key("Documents"), _Key("0")])
    assert not engine.resolve_in_submodel(submodel, [_Key("urn:x"), _Key("0")])


def test_an_index_resolves_past_a_list_child_that_carries_an_id_short():
    """A SubmodelElementList's children are addressed by index, and
    AASd-120 says they carry no idShort. The official example gives them
    one anyway -- `Datasheet`, `CADmodel` -- and that is the file's
    defect, reported by the relayed channel. A reference addressing the
    same children by index is not defective, and resolving it must not
    depend on the idShort being absent: the fixtures here happen to leave
    it out, so nothing asked.

    Read from the published example rather than built, because what makes
    this worth asserting is that the shape occurs in the reference
    material."""
    submodel = load("tests/corpus/idta/02004/example.json").submodels[0]
    children = submodel.submodel_elements[0].value
    assert [child.id_short for child in children[:2]] == ["Datasheet", "CADmodel"], \
        "the example stopped carrying the defect this asks about"
    assert engine.resolve_in_submodel(
        submodel, [_Key("u"), _Key("Documents"), _Key("0")])
    assert engine.resolve_in_submodel(
        submodel, [_Key("u"), _Key("Documents"), _Key("Datasheet")])


#: What survives everything above, measured, with the reason -- so the
#: next person measuring does not spend an afternoon rediscovering it.
#:
#: *The walk's cache, disabled.* `analyze` recomputes instead of reading
#: its slot. `_analyze` builds a fresh result and reads nothing outside
#: the context, so this is equivalent; what is *not* equivalent is the
#: cache's key, and giving it a single slot is caught by three tests.
#:
#: *The first `and` of the near-miss IRI guard, loosened to `or`.*
#: Equivalent, and provably: the branch it opens goes on to require
#: `seen_head == exp_head`, and a head shared with a value containing
#: `://` either contains `://` itself or is the `a:/` that makes the
#: other value `a://...`. Either way the original condition held too.
#:
#: *Taking the last matching child instead of the first*, in
#: `resolve_in_submodel`. Observable only where two children answer to
#: one key -- a duplicate idShort (AASd-022) or an idShort that is a bare
#: number in a list (AASd-002). Both are files the relayed channel
#: already refuses, so a fixture for this would be asserting the order in
#: which two defects are reported.


def test_a_reference_to_the_submodel_itself_resolves(tmp_path):
    """A ModelReference whose only key is the submodel points at
    something that exists, so HD-D9 has nothing to report. It is the one
    path through this function that never enters the loop, and it decides
    a MUST."""
    submodel = load(_write(tmp_path, copy.deepcopy(hd_env()))).submodels[0]
    assert engine.resolve_in_submodel(submodel, [_Key("urn:example:handover")])


# -- determinism: same input, same bytes, whatever the hash seed -------------

def test_near_miss_wording_is_deterministic(tmp_path):
    env = copy.deepcopy(hd_env())
    env["submodels"][0]["submodelElements"].append({
        "idShort": "Strays", "modelType": "SubmodelElementList",
        "typeValueListElement": "SubmodelElementCollection",
        "semanticId": {"type": "ExternalReference", "keys": [
            {"type": "GlobalReference", "value": "0173-1#02-ABI500#004"},
            {"type": "GlobalReference", "value": "0173-1#02-ABI500#005"}]},
        "value": []})
    path = _write(tmp_path, env)
    seen = set()
    for seed in ("0", "1", "2", "3", "4"):
        out = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, %r);"
             "from aas_submodel_validate import runner;"
             "r = runner.run(%r);"
             "print([f.violation.detail for f in r.findings if f.id=='HDL2'])"
             % (SRC, str(path))],
            capture_output=True, text=True, env={"PYTHONHASHSEED": seed, "PATH": ""})
        seen.add(out.stdout)
    assert len(seen) == 1, "near-miss wording varied with PYTHONHASHSEED: %s" % seen


# -- the golden and the official example are unchanged by the redesign -------

def test_the_golden_is_still_clean(tmp_path):
    assert _ids(tmp_path, hd_env()) == set()


def test_the_official_example_verdict_is_unchanged():
    report = runner.run("tests/corpus/idta/02004/example.json")
    non_meta = sorted((f.id, f.violation.subject or "")
                      for f in report.findings if f.id != "META")
    assert report.ok
    assert {i for i, _ in non_meta} == {"HD-D6", "HDL2", "HDL5", "HD-D10"}


def test_a_reference_piercing_a_leaf_is_a_finding_not_a_crash(tmp_path):
    """A ModelReference whose key path runs past a Property (a leaf) must
    resolve to 'walks to nothing', not crash HD-D9 by iterating the
    Property's string value."""
    env = copy.deepcopy(hd_env())
    submodel = env["submodels"][0]
    submodel["submodelElements"].append({
        "idShort": "Entities", "modelType": "SubmodelElementList",
        "typeValueListElement": "Entity",
        "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference",
            "value": "https://admin-shell.io/vdi/2770/1/0/EntitiesForDocumentation"}]},
        "value": [{"modelType": "Entity", "entityType": "CoManagedEntity", "idShort": "M",
                   "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference",
                       "value": "https://admin-shell.io/vdi/2770/1/0/EntityForDocumentation"}]}}]})
    _document(env)["value"].append({
        "idShort": "DocumentedEntities", "modelType": "SubmodelElementList",
        "typeValueListElement": "ReferenceElement",
        "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference",
            "value": "https://admin-shell.io/vdi/2770/1/0/Document/DocumentedEntities"}]},
        "value": [{"modelType": "ReferenceElement",
                   "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference",
                       "value": "https://admin-shell.io/vdi/2770/1/0/Document/DocumentedEntity"}]},
                   "value": {"type": "ModelReference", "keys": [
                       {"type": "Submodel", "value": "urn:example:handover"},
                       {"type": "SubmodelElementList", "value": "Documents"},
                       {"type": "SubmodelElementCollection", "value": "0"},
                       {"type": "SubmodelElementList", "value": "DocumentVersions"},
                       {"type": "SubmodelElementCollection", "value": "0"},
                       {"type": "Property", "value": "StatusValue"},
                       {"type": "Property", "value": "deeper"}]}}]})
    report = runner.run(_write(tmp_path, env))
    assert [f.id for f in report.findings if "could not run" in f.violation.message] == []
    assert "HD-D9" in {f.id for f in report.findings}


def test_a_stray_composite_in_a_multirow_scope_does_not_fabricate_a_count(tmp_path):
    """The teeth the earlier decomposition test lacked (verification found
    the mutant survived it). A stray collection wearing a *DocumentId
    item* composite id, placed among a Document's real children, must not
    be counted as a DocumentIds list -- which is exactly what splitting
    the composite on '/' would do (docs/divergences.md #8)."""
    env = copy.deepcopy(hd_env())
    document = _document(env)
    document["value"].append({
        "modelType": "SubmodelElementCollection",
        "semanticId": {"type": "ExternalReference", "keys": [{"type": "GlobalReference",
            "value": "0173-1#02-ABI501#003/0173-1#01-AHF580#003"}]},
        "value": []})
    ids = _ids(tmp_path, env)
    assert "HD-E03" not in ids     # DocumentIds is still exactly one, not "found 2"
