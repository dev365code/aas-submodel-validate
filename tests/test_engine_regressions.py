"""What the matching engine decides, and what happens when it decides wrong.

The older half reproduces confirmed findings -- a conformant file being
failed, a defective file being hidden, a crash, a non-deterministic
report -- and was red against the pre-redesign engine.

The newer half comes from the other direction: decisions that could be
reversed with the suite green. Nothing was wrong with them; nothing was
holding them either, which is the same exposure arrived at from the far
side. Each names the reversal it prevents.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

from aas_submodel_validate import runner
from aas_submodel_validate.loader import load
from aas_submodel_validate.rules import dbp_tables, engine, hd_tables, td_tables
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


def _element_wearing(env, sid_value, kind=None):
    """The one element in `env` whose main semanticId is `sid_value`.

    `kind` is needed where a list and its child share an identifier --
    `Language` and `LanguageCode` both spell `0173-1#02-AAN468#008`,
    which is the arrangement the in-list fallback exists for.
    """
    def walk(node):
        if isinstance(node, dict):
            keys = node.get("semanticId", {}).get("keys") or [{}]
            if keys[0].get("value") == sid_value \
                    and (kind is None or node.get("modelType") == kind):
                yield node
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)

    found = list(walk(env))
    assert len(found) == 1, "expected one %s, found %d" % (sid_value, len(found))
    return found[0]


def _document_ids(env):
    return _element_wearing(env, hd_tables.BY_LABEL["DocumentIds"]["sid"])


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
#: No `value`: an empty list is not "no children", it is a declared
#: emptiness the metamodel refuses (tests/builders.py says so), and a
#: fixture that trips a relayed constraint for no reason needs a sentence
#: explaining the finding away. Omitting it draws nothing at all.
NAMELESS_LIST = {"idShort": "Nameless", "modelType": "SubmodelElementList",
                 "typeValueListElement": "SubmodelElementCollection"}


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
    lists. A nameless list placed first among a Document's children is
    then whatever row asks first, and the rules that navigate there read
    it instead of the element they meant: measured, `DocumentClassifications`
    resolves to the nameless list and HD-D2 -- a MUST, the mandatory VDI
    2770 classification -- reports it missing from a file that has it."""
    env = copy.deepcopy(hd_env())
    _document(env)["value"].insert(0, copy.deepcopy(NAMELESS_LIST))
    assert _ids(tmp_path, env) == set()


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


def test_a_list_child_wearing_a_wrong_identifier_is_not_claimed_by_the_row(tmp_path):
    """The licence is for a child that declares *nothing*, not for one
    that declares something else. That is the whole of divergence #11 --
    "keys on the main semanticId being absent, not on having no
    identifiers at all" -- and it is the condition, not a detail of it:
    without it a list child wearing any identifier at all answers to the
    row, and the row stops being about identifiers.

    The Language list's one child, given an identifier that is not
    LanguageCode's. It must go unclaimed, which is what leaves HD-E16
    reporting the row as empty."""
    env = copy.deepcopy(hd_env())
    language = _element_wearing(env, hd_tables.BY_LABEL["Language"]["sid"],
                                kind="SubmodelElementList")
    language["value"][0]["semanticId"] = {
        "type": "ExternalReference",
        "keys": [{"type": "GlobalReference", "value": "urn:not:a:language:code"}]}
    assert "HD-E16" in _ids(tmp_path, env)


def test_a_nameless_list_child_of_the_wrong_kind_is_not_claimed_either(tmp_path):
    """And the licence is for a child of the row's *kind*. A stray
    Property in the Documents list declares nothing, and the sole child
    row there is a collection: claiming it would report `'Document' must
    be a SubmodelElementCollection` against an element that never
    claimed to be one."""
    env = copy.deepcopy(hd_env())
    env["submodels"][0]["submodelElements"][0]["value"].append(
        {"modelType": "Property", "valueType": "xs:string", "value": "stray"})
    assert not [rule_id for rule_id in _ids(tmp_path, env)
                if rule_id.startswith("HD")]


def test_a_nameless_collection_child_is_not_claimed_by_a_navigating_rule(tmp_path):
    """`children_of` decides this a third time, and separately from
    `child_of`: its parent is whatever the hand rule reached, which is a
    collection when the list it wanted is absent. A Document with no
    DocumentIds falls back to the Document itself, and nameless
    collections sitting there must not answer for `DocumentId`.

    Two of them, because one is not enough to be seen: HD-D5 asks which
    of several identifiers is primary and says nothing about a single
    one. With two, the mutant reports that a file carrying no
    DocumentIds at all has failed to mark one of them primary."""
    env = copy.deepcopy(hd_env())
    document = _document(env)
    absent = _document_ids(env)
    document["value"] = [child for child in document["value"] if child is not absent]
    for suffix in ("A", "B"):
        document["value"].insert(0, {
            "modelType": "SubmodelElementCollection",
            "value": [{"modelType": "Property", "valueType": "xs:string",
                       "idShort": "Q" + suffix, "value": "z"}]})
    ids = _ids(tmp_path, env)
    assert "HD-E03" in ids            # the missing DocumentIds, still reported
    assert "HD-D5" not in ids         # and no rule read the nameless ones instead


def test_a_reference_indexes_only_where_the_metamodel_indexes(tmp_path):
    """`in_list` is recomputed at every step, and only the first step was
    asserted. Below it a collection's children are addressed by idShort;
    a key path that walks into one and then says "0" names a child called
    "0" and nothing else.

    Wrong in the quiet direction: HD-D9 would call a reference resolved
    that walks nowhere, which is the silence this rule exists to break."""
    submodel = load(_write(tmp_path, copy.deepcopy(hd_env()))).submodels[0]

    def walks(*steps):
        return engine.resolve_in_submodel(
            submodel, [_Key("u")] + [_Key(step) for step in steps])

    assert walks("Documents", "0")                    # a list: by index
    assert not walks("Documents", "0", "0")           # its child is a collection
    assert not walks("Documents", "0", "DocumentIds", "0", "0")


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


#: What survives everything above, measured, with the reason -- so the
#: next person measuring does not spend an afternoon rediscovering it.
#:
#: *The walk's cache, disabled.* `analyze` recomputes instead of reading
#: its slot. No caller mutates the result, so the findings are the same
#: -- but "equivalent" is the wrong word and was measured to be: the
#: module docstring says walking once per rule is how a validator gets
#: quadratic, and disabling the cache takes the official example from
#: three walks to sixty-seven. Equivalent on the verdict, not on the
#: cost, and the cost has no test.
#:
#: What is *not* equivalent is the cache's key. Giving it a single slot
#: for every table fails most of the suite. An earlier note here said
#: three, which was a truncated list of failures being read as a count --
#: and the number is left out now rather than corrected, because it moves
#: with the suite and a note is worth having only while its figures are.
#:
#: *The first `and` of the near-miss IRI guard, loosened to `or`.*
#: Equivalent, but not for the reason first written here. The argument
#: was that a head shared with a value containing `://` must itself
#: contain `://`, which is false where the slashes are stripped off the
#: end. What actually holds is one scope out: `_scope` offers the
#: near-miss search only elements it did not claim, and an unclaimed
#: element's candidates intersect no row's match set -- so `seen ==
#: expected` never arrives here, and the term that compares them cannot
#: decide anything.


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
    """The teeth the earlier decomposition test lacked -- it passed with
    the decomposition changed under it. A stray collection wearing a *DocumentId
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


# -- what the walk does when the optional parts of a submodel are absent ----


def test_a_submodel_without_an_id_short_still_names_its_findings(tmp_path):
    """`idShort` is optional on a Submodel, and every subject the walk
    reports is built from it. Without the fallback the path a reader
    follows begins `None/` -- not a crash, and not a place."""
    env = copy.deepcopy(hd_env())
    env["submodels"][0].pop("idShort", None)
    version = _version(env)
    for child in version["value"]:
        if child.get("idShort") == "StatusSetDate":
            child["value"] = "not-a-date"
    subjects = [f.violation.subject or "" for f in runner.run(_write(tmp_path, env)).findings
                if f.id == "HD-D8"]
    assert subjects and all(s.startswith("submodel/") for s in subjects), subjects


def test_a_submodel_with_no_elements_at_all_is_judged_not_crashed(tmp_path):
    """`submodelElements` is optional too, and the walk iterates it. A
    submodel that declares none is a submodel missing everything the
    template requires -- which is a verdict, and the generated rules give
    it. Iterating `None` is a TypeError."""
    env = copy.deepcopy(hd_env())
    env["submodels"][0].pop("submodelElements", None)
    findings = {f.id: f for f in runner.run(_write(tmp_path, env)).findings}
    assert "HD-E01" in findings
    assert not [f for f in findings.values()
                if "could not run" in f.violation.message]


#: Conjuncts of the walk's guards that survive everything above. They are
#: dead against the tables as generated today, and none of them is dead
#: against a table the generator could produce -- which is a different
#: claim from the one first written here, and the reason they stay.
#:
#: *`reference is not None` and `expected` in the submodel reference-type
#: check.* `matched_submodels` reaches a submodel through
#: `candidate_values(submodel.semantic_id)`, and that is the empty set for
#: `None`, so a submodel with no semanticId never arrives. All three
#: vendored tables declare `TEMPLATE_SUBMODEL_SID_TYPE =
#: "ModelReference"` -- asserted for each of them now; two were pinned
#: and the pack this file exercises was not.
#:
#: *`row["sid_type"]`.* All 86 generated rows carry one, and all 86 say
#: `ExternalReference`. Not "cannot be otherwise": the generator reads
#: `semanticId.type` off the element and writes what it finds, the
#: vendoring gate is a hash and an undeclared-file sweep with no
#: structural check in it, and `semanticId` is optional on a
#: SubmodelElement. A future template may omit one.
#:
#: *`row["value_type"]` and `declared is not None`.* The first note here
#: argued this from a census of which kinds lack a `value_type`
#: attribute, got the census wrong (`Entity` was the 59th row, left out
#: of a list of four kinds that came to 58), and argued only the
#: direction that licenses dropping one of the two terms. The evidence
#: that actually holds is the kind guard above, which has already forced
#: the element's class to match the row's:
#:
#:   - All 27 rows that name a `value_type` are kind `Property`, and
#:     aas-core3 refuses a Property with no `valueType` on every loader
#:     path -- measured, JSON-missing, JSON-null and XML. So `declared`
#:     is never `None` where the row speaks.
#:   - Every row that names none is a kind whose class has no
#:     `value_type` attribute at all. So `declared` is always `None`
#:     where the row is silent.
#:
#: Both terms are therefore dead, and dead *because of an invariant of a
#: dependency*, which is the kind of thing this project has been wrong
#: about twice already (#17, #31). If aas-core3 ever admits a Property
#: without a valueType, dropping `declared is not None` turns a
#: conformant file into a `could not run` finding at the rule's own MUST.
#:
#: *`not candidates` in the near-miss sweep.* An element with no
#: identifiers reaches `_near_miss` with an empty set, which matches
#: nothing -- checked against every match set of all 86 rows in all three
#: tables. Skipping it early is a saving, not a decision.


def test_all_three_tables_expect_a_model_reference_to_the_template():
    """The walk reports a submodel whose semanticId is an
    ExternalReference where the table says ModelReference. Two packs
    pinned the value they compare against and this one did not, in a note
    that asserted it about all three."""
    for tables in (hd_tables, td_tables, dbp_tables):
        assert tables.TEMPLATE_SUBMODEL_SID_TYPE == "ModelReference"


def test_every_generated_row_says_which_reference_type_it_expects():
    """`sid_type` gates the reference-type lint. A row without one is
    what the generator writes for an element carrying no semanticId --
    which the metamodel permits and the vendoring gate, being a hash,
    would not notice."""
    for tables in (hd_tables, td_tables, dbp_tables):
        for row in tables.ROWS:
            assert row["sid_type"] == "ExternalReference", row["id"]


def test_only_properties_declare_a_value_type():
    """The valueType lint dereferences the element's own `value_type`
    once the row names one. It is safe because every row that names one
    is a Property row and the kind guard has already run -- not because
    of which kinds happen to lack the attribute."""
    for tables in (hd_tables, td_tables, dbp_tables):
        for row in tables.ROWS:
            if row["value_type"]:
                assert row["kind"] == "Property", row["id"]
