"""Every generated 02011 Hierarchical Structures rule fires, and the golden
fixture fires nothing at all.

Same contract as the other generated suites: a required row is proved
live by removing it, a bounded optional by injecting past its maximum,
and an unbounded (0..*) row by putting an element of the wrong kind under
its identifier -- the other half of what the row says.

What this template adds is depth. A `Node` holds `Node`s of its own
identifier, and the table stops one level down while a bill of material
does not, so the walk gives each nested copy the rows of the element it
copies (docs/divergences.md #48). The golden fixture is three levels deep
on purpose, and the tests below put defects at the bottom of it and
below it.
"""
from __future__ import annotations

import copy
import json

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.rules import hs_tables
from builders import HS, _sid, hs_env, inject, strip_row, stub_of
from verdicts import by_id


def _run(tmp_path, env: dict):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return runner.run(path)


def _ids(tmp_path, env: dict):
    return by_id(_run(tmp_path, env))


def _entry(env):
    return env["submodels"][0]["submodelElements"][0]


def _named(statements, id_short):
    return next(e for e in statements if e.get("idShort") == id_short)


def test_the_golden_environment_fires_nothing(tmp_path):
    """02011's submodel identifier is claimed by no second template, so an
    empty verdict is the whole answer."""
    assert set(_ids(tmp_path, hs_env())) == set()


def test_the_golden_environment_is_metamodel_clean_too(tmp_path):
    assert [f for f in _run(tmp_path, hs_env()).findings if f.rule.kind == "meta"] == []


def _mismatched(row) -> dict:
    wrong = stub_of(row)
    wrong.pop("entityType", None)
    wrong.pop("first", None)
    wrong.pop("second", None)
    if row["kind"] == "Property":
        wrong.update(modelType="MultiLanguageProperty",
                     value=[{"language": "en", "text": "x"}])
        wrong.pop("valueType", None)
    else:
        wrong.update(modelType="Property", valueType="xs:string", value="x")
    wrong["idShort"] = "Wrong"
    return wrong


@pytest.mark.parametrize("row", hs_tables.ROWS, ids=[r["id"] for r in hs_tables.ROWS])
def test_every_generated_rule_fires(tmp_path, row):
    env = copy.deepcopy(hs_env())
    low, high = row["card"]
    parent = hs_tables.BY_ID.get(row["parent"])
    if low >= 1:
        strip_row(env, row, tables=hs_tables)
    elif high is not None:
        inject(env, parent, [stub_of(row), stub_of(row)], tables=hs_tables)
    else:
        inject(env, parent, [_mismatched(row)], tables=hs_tables)
    assert row["id"] in _ids(tmp_path, env)


def test_a_defect_below_the_template_is_judged_where_it_is(tmp_path):
    """The template writes a Node inside a Node and stops. A fourth level
    -- a nut in the shaft in the gearbox in the machine -- is below
    anything the table spells out, and a `BulkCount` there carrying the
    wrong type is reported at the nut, under the same rule a first-level
    one would draw. Before the walk re-applied a copy's rows, the run said
    it had not looked inside the nested copies, and nothing in them was
    judged at all."""
    env = copy.deepcopy(hs_env())
    gearbox = _named(_entry(env)["statements"], "Gearbox")
    shaft = _named(gearbox["statements"], "Shaft")
    shaft["statements"].append({
        "idShort": "Nut", "modelType": "Entity", "semanticId": _sid(HS + "Node/1/0"),
        "entityType": "SelfManagedEntity", "globalAssetId": "urn:example:asset:nut",
        "statements": [{"idShort": "BulkCount", "modelType": "Property",
                        "valueType": "xs:string", "value": "four",
                        "semanticId": _sid(HS + "BulkCount/1/0")}]})
    report = _run(tmp_path, env)
    [finding] = [f for f in report.findings if f.id == "HS-E07"]
    assert finding.violation.subject.endswith("EntryNode/Gearbox/Shaft/Nut/BulkCount")
    assert report.notes == [], report.notes


def test_a_nested_node_of_the_wrong_kind_is_named_at_its_depth(tmp_path):
    """The copy's own row judges its kind: a collection wearing Node's
    identifier three levels down is an error against the nested row, at
    the place it sits."""
    env = copy.deepcopy(hs_env())
    shaft = _named(_named(_entry(env)["statements"], "Gearbox")["statements"], "Shaft")
    shaft["statements"].append({"idShort": "Bolt", "modelType": "SubmodelElementCollection",
                                "semanticId": _sid(HS + "Node/1/0")})
    report = _run(tmp_path, env)
    [finding] = [f for f in report.findings if f.id == "HS-E03"]
    assert finding.violation.subject.endswith("Gearbox/Shaft/Bolt")
    assert "must be a Entity" in finding.violation.message


def test_a_node_needs_no_node_of_its_own(tmp_path):
    """The nested Node is 0..*: a part with no parts of its own -- the motor
    -- is a leaf, and the entry's own Node is the one that is 1..*."""
    env = copy.deepcopy(hs_env())
    entry = _entry(env)
    entry["statements"] = [e for e in entry["statements"] if e.get("idShort") != "Gearbox"]
    assert set(_ids(tmp_path, env)) == set()


def test_what_the_walk_could_not_reach_in_a_bill_is_said(tmp_path):
    """A collection wearing Node's identifier three levels down is a node
    of the wrong kind, reported at its place; the node inside it is
    reached by nothing, so what it carries goes unjudged -- and the note
    says so, naming that node and not the one already reported."""
    env = copy.deepcopy(hs_env())
    shaft = _named(_named(_entry(env)["statements"], "Gearbox")["statements"], "Shaft")
    shaft["statements"].append({
        "idShort": "Bolt", "modelType": "SubmodelElementCollection",
        "semanticId": _sid(HS + "Node/1/0"),
        "value": [{"idShort": "Washer", "modelType": "Entity",
                   "semanticId": _sid(HS + "Node/1/0"),
                   "entityType": "SelfManagedEntity", "globalAssetId": "urn:example:asset:washer",
                   "statements": [{"idShort": "BulkCount", "modelType": "Property",
                                   "valueType": "xs:string", "value": "many",
                                   "semanticId": _sid(HS + "BulkCount/1/0")}]}]})
    report = _run(tmp_path, env)
    assert [f.violation.subject.rsplit("/", 1)[-1] for f in report.findings
            if f.id == "HS-E03"] == ["Bolt"]
    assert not [f for f in report.findings if f.id == "HS-E07"]
    [note] = [n for n in report.notes if "contains itself" in n]
    assert "Shaft/Bolt/Washer" in note and "Shaft/Bolt," not in note, note
    assert "Shaft/Bolt)" not in note, note
    assert "did not reach 1 element carrying that identifier, inside ones it judged" in note, note


def _stray(name, inside=()):
    return {"idShort": name, "modelType": "Entity", "semanticId": _sid(HS + "Node/1/0"),
            "entityType": "SelfManagedEntity", "globalAssetId": "urn:example:asset:" + name,
            **({"statements": list(inside)} if inside else {})}


def test_a_node_beside_the_entry_is_not_a_nested_copy(tmp_path):
    """A Node at the submodel's root, holding one of its own, beside a
    complete bill. The template puts no Node there: it is an element no
    row describes, and draws what any such element draws -- nothing
    (docs/divergences.md #19). The note called it a nested copy sitting
    elsewhere, and the Node inside it one more: the first is not nested,
    and neither is inside anything the run judged."""
    env = copy.deepcopy(hs_env())
    env["submodels"][0]["submodelElements"].append(_stray("Stray", [_stray("Inner")]))
    report = _run(tmp_path, env)
    assert report.findings == [], [(f.id, f.violation.subject) for f in report.findings]
    assert report.notes == [], report.notes


def test_nodes_under_an_entry_the_run_could_not_place_are_said_once(tmp_path):
    """The entry node's identifier drifts, so the walk enters none of the
    bill. What that costs is said where a place not examined is said --
    `scopeNotExamined`, naming the drifted element -- and the note used to
    say it again, calling the entry's first-level Nodes nested copies
    sitting elsewhere: they are neither, and the one Node nested inside
    them is inside nothing the run judged."""
    env = copy.deepcopy(hs_env())
    keys = _entry(env)["semanticId"]["keys"]
    keys[0]["value"] = keys[0]["value"].replace("EntryNode", "EntryNod")
    report = _run(tmp_path, env)
    assert not [n for n in report.notes if "contains itself" in n], report.notes
    [place] = report.as_dict()["summary"]["scopeNotExamined"]
    assert place["label"] == "EntryNode", place
    assert [e["subject"] for e in place["unclaimedHere"]] == [
        "HierarchicalStructures/EntryNode"], place


def _box(inside):
    return {"idShort": "Box", "modelType": "SubmodelElementCollection", "value": [inside]}


def test_a_node_in_a_container_the_entry_holds_is_counted(tmp_path):
    """A collection no row describes, directly inside the entry node,
    holding a Node that holds a Node. The entry node is judged, so the two
    Nodes the walk never reached are the reach of the check, and the note
    names both. Counting only copies inside a judged *Node* left them
    unsaid -- the entry node carries another identifier -- while the same
    collection one level down, inside the gearbox, was counted."""
    env = copy.deepcopy(hs_env())
    _entry(env)["statements"].append(_box(_stray("Pin", [_stray("Tip")])))
    [note] = [n for n in _run(tmp_path, env).notes if "contains itself" in n]
    assert "did not reach 2 elements carrying that identifier" in note, note
    assert "EntryNode/Box/Pin, " in note and "EntryNode/Box/Pin/Tip)" in note, note


def test_a_node_under_a_node_whose_identifier_drifted_is_counted(tmp_path):
    """The gearbox's identifier drifts, so the walk claims it for no row and
    never enters it; the shaft inside it is a Node the run did not judge,
    inside an entry node it did. The gearbox is named by `HSL1`; the shaft
    inside it, which no lint sees, is said in this note."""
    env = copy.deepcopy(hs_env())
    _named(_entry(env)["statements"], "Gearbox")["semanticId"] = _sid(HS + "Node/1/1")
    [note] = [n for n in _run(tmp_path, env).notes if "contains itself" in n]
    assert "did not reach 1 element carrying that identifier" in note, note
    assert "EntryNode/Gearbox/Shaft)" in note, note


def test_a_stray_at_the_root_does_not_change_what_the_bill_is_told(tmp_path):
    """A Node at the root beside a collection wearing Node's identifier deep
    in the bill: the washer inside that collection is counted and the stray
    is not. Each path carries its own answer to "did the run judge
    something above here" -- kept for a level instead, the entry node's
    answer stood for the stray beside it."""
    env = copy.deepcopy(hs_env())
    shaft = _named(_named(_entry(env)["statements"], "Gearbox")["statements"], "Shaft")
    shaft["statements"].append({"idShort": "Bolt", "modelType": "SubmodelElementCollection",
                                "semanticId": _sid(HS + "Node/1/0"),
                                "value": [_stray("Washer")]})
    env["submodels"][0]["submodelElements"].append(_stray("Stray"))
    [note] = [n for n in _run(tmp_path, env).notes if "contains itself" in n]
    assert "did not reach 1 element carrying that identifier" in note, note
    assert "Shaft/Bolt/Washer)" in note and "Stray" not in note, note
