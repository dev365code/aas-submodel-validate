"""A run that could not put a question has to say so -- and only then.

`docs/divergences.md` #23: a generated rule sits inside a scope, and a
scope opens only when an element matches the row that names it. What is
below an unentered scope leaves the run.

The first version of this field tried to report every such loss and got
it wrong in both directions at once. It reported rules that other
scopes had asked -- twenty-six listed, twenty-two of them considered,
because a list of two items walks the same rows twice and only the
second item's misses were written down. And it fired on a manufacturer's
own property, which `docs/divergences.md` #19 promises passes without
comment: one added `Property` on a conformant file, and the file was
told a rule went unasked.

So the contract here is narrower, and it is the narrowing that makes it
true: **this field reports a loss only where the reader has already said
something is wrong.** Two such places, and no others:

- a row matched an element of the wrong kind. The walk reports that and
  does not recurse, so the subtree is gone -- and nothing said so.
- the near-miss lint fired in a scope. The reader has already said an
  identifier there looks like one it knows.

A manufacturer's own element draws neither, so it costs nothing. An
optional element that is simply absent draws neither either.

What this deliberately does not cover: a typo in the middle of a path
segment, which defeats the near-miss lint (#22) and leaves 18 of the 69
measurable rows silent (`tools/scope_silence.py`). Reporting those means
deciding that an unidentifiable element is evidence of a defect, and the
template states a minimum and not a whitelist (#19). That is the policy
question #23 names, and it is still open.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from aas_submodel_validate import runner
from aas_submodel_validate.rules import hd_tables
from builders import build_aasx, hd_env, td_env

MANUFACTURER = {
    "idShort": "AcmeNote", "modelType": "Property", "valueType": "xs:string",
    "value": "internal",
    "semanticId": {"type": "ExternalReference",
                   "keys": [{"type": "GlobalReference",
                             "value": "https://acme.example/own/note"}]},
}


def _judge(tmp_path, environment, tag):
    path = build_aasx(tmp_path / (tag + ".aasx"),
                      payload=json.dumps(environment).encode("utf-8"),
                      files=(("aasx/files/manual.pdf", b"%PDF-1.4"),))
    return runner.run(str(path))


def _find(node, sid):
    if isinstance(node, dict):
        for key in (node.get("semanticId") or {}).get("keys") or []:
            if key.get("value") == sid:
                return node
        for value in node.values():
            found = _find(value, sid)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find(value, sid)
            if found is not None:
                return found
    return None


def _versions_as_a_property(environment):
    """A `Property` wearing the `DocumentVersions` list identifier: the
    row matches, the kind is wrong, the walk reports it and does not
    recurse."""
    versions = _find(environment, hd_tables.BY_LABEL["DocumentVersions"]["sid"])
    versions.clear()
    versions.update({
        "idShort": "DocumentVersions", "modelType": "Property",
        "valueType": "xs:string", "value": "not a list",
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference",
                                 "value": hd_tables.BY_LABEL["DocumentVersions"]["sid"]}]},
    })
    return environment


def _considered(path):
    """The walk's own record of which rows it looked at."""
    from aas_submodel_validate import rules as R
    from aas_submodel_validate.runner import Context, all_rules, execute, load

    ctx = Context(load(str(path)), R.profiles.Selection(None))
    execute(all_rules(), ctx)
    seen = set()
    for result in ctx.__dict__.get("_smt_analysis", {}).values():
        seen |= set(result["instances"])
    return seen


# -- the two directions it got wrong ----------------------------------------


def test_no_rule_is_called_unasked_when_some_scope_asked_it(tmp_path):
    """A `Documents` list of two: the first item claims every row, the
    second is short of one and carries a supplier property. The rows the
    first item asked were written down as unasked because the second
    item's scope missed them, and nothing subtracted.

    Measured before the repair: 26 reported, 22 of them considered."""
    environment = copy.deepcopy(hd_env())
    documents = _find(environment, hd_tables.BY_LABEL["Documents"]["sid"])
    full = documents["value"][0]
    lean = copy.deepcopy({k: v for k, v in full.items() if k != "value"})
    lean["idShort"] = "SecondDoc"
    lean["value"] = [copy.deepcopy(full["value"][0]), copy.deepcopy(MANUFACTURER)]
    documents["value"].append(lean)

    path = build_aasx(tmp_path / "pair.aasx",
                      payload=json.dumps(environment).encode("utf-8"),
                      files=(("aasx/files/manual.pdf", b"%PDF-1.4"),))
    report = runner.run(str(path))
    overlap = set(report.not_asked) & _considered(path)
    assert not overlap, sorted(overlap)


def test_a_manufacturers_own_element_costs_nothing(tmp_path):
    """#19: "A manufacturer's own properties pass without comment." One
    added property turned a clean report into one claiming a rule went
    unasked, which is a comment."""
    clean = _judge(tmp_path, hd_env(), "clean")
    environment = copy.deepcopy(hd_env())
    environment["submodels"][0]["submodelElements"].append(copy.deepcopy(MANUFACTURER))
    plus = _judge(tmp_path, environment, "plus")
    assert clean.not_asked == [] and plus.not_asked == [], plus.not_asked
    assert {f.id for f in plus.findings} == {f.id for f in clean.findings}

    # And several of them, in several scopes, which is what a real
    # supplier file looks like.
    environment = copy.deepcopy(hd_env())
    documents = _find(environment, hd_tables.BY_LABEL["Documents"]["sid"])
    documents["value"][0]["value"].append(copy.deepcopy(MANUFACTURER))
    environment["submodels"][0]["submodelElements"].append(copy.deepcopy(MANUFACTURER))
    assert _judge(tmp_path, environment, "many").not_asked == []


def test_a_conformant_file_is_asked_everything(tmp_path):
    for label, make in (("hd", hd_env), ("td", td_env)):
        assert _judge(tmp_path, make(), "clean-" + label).not_asked == [], label


# -- the two it reports, both of them already reported as wrong -------------


def test_an_element_of_the_wrong_kind_takes_its_subtree_and_says_so(tmp_path):
    """A `Property` wearing a list's identifier. The walk matches the
    row, reports the kind, and does not recurse -- so the subtree left
    the run and the report said nothing. Twenty-one rules on the
    measured case, nine of them mandatory."""
    report = _judge(tmp_path, _versions_as_a_property(copy.deepcopy(hd_env())), "wrongkind")
    assert any(f.id == "HD-E13" for f in report.findings), \
        "the kind finding this hangs off is gone"
    assert report.not_asked, "the subtree left the run and nothing said so"
    assert "HD-E17" in report.not_asked, report.not_asked


def test_a_near_miss_names_what_it_cost(tmp_path):
    """The official example is the case: its `Entities` list wears the
    item's identifier, the lint says so every run, and `HD-E38` --
    mandatory inside that list -- was never put."""
    import aas_submodel_validate as package

    example = Path(package.__file__).parent / "data/example/idta-02004-2.0.aasx"
    report = runner.run(str(example))
    assert report.ok
    assert any(f.id == "HDL2" for f in report.findings)
    assert report.not_asked == ["HD-E38"], report.not_asked


# -- shape --------------------------------------------------------------


def test_the_order_is_the_tables_order_and_does_not_move(tmp_path):
    """The first version's only ordering assertion compared the list to
    itself sorted by its own index, which is true of any list. Deleting
    the ordering entirely left the suite green and the output varying
    with `PYTHONHASHSEED`, on a key whose whole purpose is that two
    stored reports can be compared."""
    from aas_submodel_validate.rules import td_tables

    report = _judge(tmp_path, _versions_as_a_property(copy.deepcopy(hd_env())), "order")
    assert len(report.not_asked) > 1, report.not_asked

    order = [row["id"] for row in list(hd_tables.ROWS) + list(td_tables.ROWS)]
    assert report.not_asked == sorted(report.not_asked, key=order.index)
    assert len(report.not_asked) == len(set(report.not_asked))


def test_the_json_report_carries_it(tmp_path):
    report = _judge(tmp_path, _versions_as_a_property(copy.deepcopy(hd_env())), "json")
    document = report.as_dict()
    assert document["summary"]["rulesNotAsked"] == report.not_asked
    assert json.loads(json.dumps(document))["summary"]["rulesNotAsked"] == report.not_asked


def test_the_person_at_the_terminal_is_told_too(tmp_path):
    from aas_submodel_validate.report import render

    typo = render(_judge(tmp_path, _versions_as_a_property(copy.deepcopy(hd_env())), "term"))
    clean = render(_judge(tmp_path, hd_env(), "term-clean"))
    assert "not asked" not in clean
    assert "rules not asked" in typo


def test_a_near_miss_in_one_branch_is_not_charged_to_another(tmp_path):
    """`docs/divergences.md` #23 promises the claim is about the scope
    the near miss was found in. It was about the whole run.

    `_scope` recorded how many near misses stood before it began, and
    then asked at the end whether that number had grown -- but the
    recursion into children happens inside the row loop, between those
    two lines. So a near miss anywhere below made every ancestor scope
    see the list grow and attribute a loss of its own.

    Measured on this fixture: dropping `DocumentVersions` reports no
    unasked rule at all, and dropping it *and* drifting `ClassId` in a
    different branch reports twenty-three -- every one of them about
    `DocumentVersions`, which the drift has nothing to do with. The same
    file, the same missing collection, two different answers depending on
    something that happened elsewhere.
    """
    import copy

    def edit(env, drop=None, drift=None):
        env = copy.deepcopy(env)

        def go(node):
            if isinstance(node, dict):
                if drift and node.get("idShort") == drift and node.get("semanticId"):
                    key = node["semanticId"]["keys"][0]
                    key["value"] = key["value"][:-1] + "9"
                for name, value in list(node.items()):
                    if isinstance(value, list):
                        node[name] = [c for c in value
                                      if not (isinstance(c, dict)
                                              and c.get("idShort") == drop)]
                        for child in node[name]:
                            go(child)
                    elif isinstance(value, dict):
                        go(value)
            elif isinstance(node, list):
                for item in node:
                    go(item)
        go(env)
        return env

    def asked(env, name):
        path = tmp_path / ("%s.json" % name)
        path.write_text(json.dumps(env), "utf-8")
        return set(runner.run(path).not_asked)

    from builders import hd_env
    dropped = asked(edit(hd_env(), drop="DocumentVersions"), "dropped")
    both = asked(edit(hd_env(), drop="DocumentVersions", drift="ClassId"), "both")
    elsewhere = asked(edit(hd_env(), drift="ClassId"), "drift")

    assert both - dropped <= elsewhere, (
        "a near miss in one branch added %s to what another branch reports"
        % sorted((both - dropped) - elsewhere))


def test_a_near_miss_on_a_leaf_loses_nothing_and_one_on_a_parent_still_does(tmp_path):
    """The positive control for the repair above, and its own boundary.

    Charging the near miss to the scope that found it could have been
    done by never reporting anything, so this asserts both directions on
    the same fixture: an identifier drifted on a collection still costs
    its whole subtree, and one drifted on a childless property costs
    nothing, because nothing was underneath it to lose.

    Before the repair the leaf reported two rules -- an ancestor scope
    reacting to a descendant's near miss and attributing the loss to
    itself."""
    import copy

    def drift(name):
        env = copy.deepcopy(hd_env())
        hit = []

        def go(node):
            if isinstance(node, dict):
                if node.get("idShort") == name and node.get("semanticId"):
                    key = node["semanticId"]["keys"][0]
                    key["value"] = key["value"][:-1] + "9"
                    hit.append(name)
                for value in node.values():
                    go(value)
            elif isinstance(node, list):
                for item in node:
                    go(item)
        go(env)
        assert hit, "no element named %r in this fixture" % name
        path = tmp_path / ("%s.json" % name)
        path.write_text(json.dumps(env), "utf-8")
        return runner.run(path).not_asked

    from builders import hd_env
    assert len(drift("Documents")) > 20, "a drifted collection lost nothing"
    assert len(drift("DocumentVersions")) > 10
    assert drift("ClassId") == [], (
        "a drifted leaf property reported rules; there is nothing below it")


def test_an_intact_submodel_does_not_answer_for_a_drifted_one(tmp_path):
    """The subtraction that takes a proposed loss back off -- "some other
    scope asked this row" -- reached across submodels.

    Within one document it is right and stays: a list walks the same rows
    once per item, and a row missed in the second item was entered in the
    first. Across documents it is not a fact about either. Measured on
    this fixture: a submodel with a drifted `Documents` identifier
    reports thirty-six rules unasked on its own, and five with an intact
    copy of itself beside it -- the same thirty-six rows, about the same
    drifted document, erased by a second document that has nothing to do
    with them.
    """
    import copy

    from builders import hd_env

    def drift(env):
        env = copy.deepcopy(env)

        def go(node):
            if isinstance(node, dict):
                if node.get("idShort") == "Documents" and node.get("semanticId"):
                    key = node["semanticId"]["keys"][0]
                    key["value"] = key["value"][:-1] + "9"
                for value in node.values():
                    go(value)
            elif isinstance(node, list):
                for item in node:
                    go(item)
        go(env)
        return env

    def asked(env, name):
        path = tmp_path / ("%s.json" % name)
        path.write_text(json.dumps(env), "utf-8")
        return runner.run(path).not_asked

    drifted = drift(hd_env())
    alone = asked(drifted, "alone")
    assert len(alone) > 20, alone

    pair = copy.deepcopy(drifted)
    intact = copy.deepcopy(hd_env())["submodels"][0]
    intact["id"] = intact["id"] + ":second"
    pair["submodels"].append(intact)
    beside = asked(pair, "beside")

    assert set(alone) <= set(beside), (
        "an intact sibling erased %s from what the drifted submodel reports"
        % sorted(set(alone) - set(beside)))


def test_a_row_asked_in_one_list_item_is_not_reported_from_another(tmp_path):
    """The subtraction that has to stay, pinned because nothing pinned it.

    A `SubmodelElementList` walks the same rows once per item, so a row
    entered in the first item and missed in the second is proposed as a
    loss by the second and is not one. The walk subtracts what it asked
    before reporting -- and removing that subtraction changed no test at
    all, which the mutation round found.

    Measured on two `Document` items with the second's `DocumentVersions`
    identifier drifted: four rules unasked with the subtraction and
    twenty-two without, the extra eighteen being rows the first item
    answered.
    """
    import copy

    from builders import hd_env

    def find(node, name):
        if isinstance(node, dict):
            if node.get("idShort") == name:
                return node
            for value in node.values():
                found = find(value, name)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = find(item, name)
                if found is not None:
                    return found
        return None

    env = copy.deepcopy(hd_env())
    documents = find(env, "Documents")
    second = copy.deepcopy(documents["value"][0])

    def drift(node):
        if isinstance(node, dict):
            if node.get("idShort") == "DocumentVersions" and node.get("semanticId"):
                key = node["semanticId"]["keys"][0]
                key["value"] = key["value"][:-1] + "9"
            for value in node.values():
                drift(value)
        elif isinstance(node, list):
            for item in node:
                drift(item)
    drift(second)
    documents["value"].append(second)

    path = tmp_path / "two-items.json"
    path.write_text(json.dumps(env), "utf-8")
    report = runner.run(path)
    assert report.not_asked, "the drifted item proposed nothing; fixture is stale"
    # Every rule the first item answered is a rule this run asked, so it
    # cannot be in the list. Read from the run rather than counted here:
    # a number would go stale with the table.
    asked = {finding.id for finding in report.findings}
    assert not (set(report.not_asked) & asked), (
        "reported as unasked and also reported on: %s"
        % sorted(set(report.not_asked) & asked))
    assert len(report.not_asked) < 10, (
        "the second item proposed %d rules; the first item answered most of "
        "them and they are being reported anyway" % len(report.not_asked))
