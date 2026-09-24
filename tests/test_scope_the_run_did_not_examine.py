"""What the run did not look inside, said without guessing who is to blame.

A generated rule sits inside a scope, and a scope opens only when an
element matches the row naming it. When no element does, every rule
beneath that row leaves the run -- and until now the report said so only
where something *explained* the loss: a near miss, or an element of the
wrong kind claiming the row. That restriction is deliberate and stays,
because there is no way to tell a supplier's own element from a template
element with a typo by looking at it (`docs/divergences.md` #19, #23).

What was given up along with the blame was the *scope*. A file whose
container carries a different identifier passed with every published
number identical to a clean run: no finding, no `rulesNotAsked`, no
`unmatchedElements`, `ok` true. This says which rows went unasked and
whether anything was sitting in their place, and says neither of those
is a defect.
"""
from __future__ import annotations

import json

from aas_submodel_validate import runner
from aas_submodel_validate.model import Severity


def _sid(value):
    return {"type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": value}]}


def _card(value):
    return {"semanticId": _sid("https://admin-shell.io/SubmodelTemplates/"
                               "Cardinality/1/0"),
            "type": "SMT/Cardinality", "valueType": "xs:string",
            "value": value}


def _template(tmp_path):
    """A box that may be absent, holding something that may not."""
    path = tmp_path / "boxes.json"
    path.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:boxtpl", "idShort": "Boxes",
        "kind": "Template", "semanticId": _sid("urn:test:boxes"),
        "submodelElements": [{
            "modelType": "SubmodelElementCollection", "idShort": "Box",
            "semanticId": _sid("urn:test:box"),
            "qualifiers": [_card("ZeroToOne")],
            "value": [{"modelType": "Property", "idShort": "Inside",
                       "semanticId": _sid("urn:test:inside"),
                       "valueType": "xs:string",
                       "qualifiers": [_card("One")]}]}]}]}).encode("utf-8"))
    return path


def _instance(tmp_path, name, elements):
    path = tmp_path / ("%s.json" % name)
    path.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:box", "idShort": "Boxes",
        "semanticId": _sid("urn:test:boxes"),
        "submodelElements": elements}]}).encode("utf-8"))
    return path


def _box(id_short="Box", sid="urn:test:box", inside=True):
    value = [{"modelType": "Property", "idShort": "Inside",
              "semanticId": _sid("urn:test:inside"),
              "valueType": "xs:string", "value": "v"}] if inside else []
    return {"modelType": "SubmodelElementCollection", "idShort": id_short,
            "semanticId": _sid(sid), "value": value}


def test_a_conformant_file_reports_no_unexamined_scope(tmp_path):
    """The number only moves when something actually went unexamined."""
    report = runner.run(_instance(tmp_path, "clean", [_box()]),
                        template=_template(tmp_path))
    assert not report.not_examined, report.not_examined


def test_a_vendor_extension_is_not_an_unexamined_scope(tmp_path):
    """An element the template never mentions is not a defect and is not a
    gap in the check: the template states a minimum, not a whitelist
    (`docs/divergences.md` #19). Every row was still put."""
    extra = {"modelType": "Property", "idShort": "OurOwn",
             "semanticId": _sid("urn:vendor:ours"), "valueType": "xs:string",
             "value": "v"}
    report = runner.run(_instance(tmp_path, "extended", [_box(), extra]),
                        template=_template(tmp_path))
    assert report.count(Severity.ERROR) == 0, [
        (f.id, f.violation.message) for f in report.findings]
    assert not report.not_examined, report.not_examined


def test_an_absent_optional_container_says_the_file_carries_nothing(tmp_path):
    """A file that legitimately omits an optional section left its rules
    unasked too, and that is worth saying plainly -- it is the difference
    between "checked and fine" and "not checked"."""
    report = runner.run(_instance(tmp_path, "absent", []),
                        template=_template(tmp_path))
    assert len(report.not_examined) == 1, report.not_examined
    record = report.not_examined[0]
    assert record.because == "absent", record.because
    assert list(record.unasked) == ["TPL-E02"], record.unasked


def test_a_drifted_container_says_something_was_sitting_there(tmp_path):
    """The case this exists for.

    The container carries an identifier the template does not name, so
    the row it would have matched was never entered and the rule beneath
    it was never put. Measured before this record existed: no finding, no
    `rulesNotAsked`, no `unmatchedElements`, `ok` true -- every published
    number identical to a clean run.

    The element is *not* called a typo. A different identifier may be a
    legitimate extension, and the two are indistinguishable by looking.
    Both facts are reported and neither is named as the cause.
    """
    drifted = _box(id_short="Box", sid="urn:test:box-but-different")
    report = runner.run(_instance(tmp_path, "drifted", [drifted]),
                        template=_template(tmp_path))
    assert report.count(Severity.ERROR) == 0, [
        (f.id, f.violation.message) for f in report.findings]
    assert len(report.not_examined) == 1, report.not_examined
    record = report.not_examined[0]
    assert record.because == "unclaimed-element-present", record.because
    assert list(record.unasked) == ["TPL-E02"], record.unasked
    assert "Box" in record.where, record.where


def test_the_report_says_it_in_json_and_on_the_screen(tmp_path):
    """A record a consumer cannot read is not a record."""
    from aas_submodel_validate.report import render

    drifted = _box(id_short="Box", sid="urn:test:box-but-different")
    report = runner.run(_instance(tmp_path, "drifted2", [drifted]),
                        template=_template(tmp_path))
    document = report.as_dict()
    assert "scopeNotExamined" in document["summary"], sorted(document["summary"])
    assert document["summary"]["scopeNotExamined"][0]["because"] == \
        "unclaimed-element-present"
    assert "not examined" in render(report), render(report)


def test_two_submodels_that_share_a_name_are_two_scopes(tmp_path):
    """A submodel's `idShort` is not its identity: `id` is, and two
    submodels may carry one name without breaking anything. AASd-022 is
    about referables that are *not* identifiable, so a file like this
    draws no metamodel finding and no warning of any kind.

    The record is keyed by `where`, whose first segment is that name. So
    two documents that each lost a scope were reported as one, and the
    number a reader acts on came back halved -- silently, on a legal
    file. Measured: the same two submodels with distinct names report
    ten unexamined scopes and with one shared name report five.

    The analyse loop keeps a record per submodel precisely so that one
    document's answers cannot erase another's; the merge key gave that
    back.
    """
    import copy

    from builders import hd_env

    def two(same_name):
        environment = copy.deepcopy(hd_env())
        first = environment["submodels"][0]
        second = copy.deepcopy(first)
        first["id"], second["id"] = "urn:plant:a", "urn:plant:b"
        if not same_name:
            first["idShort"] = first["idShort"] + "A"
            second["idShort"] = second["idShort"] + "B"
        for submodel in (first, second):
            for element in submodel.get("submodelElements", []):
                if element.get("idShort") == "Entities":
                    element["idShort"] = "Entites"
        environment["submodels"] = [first, second]
        path = tmp_path / ("same.json" if same_name else "apart.json")
        path.write_text(json.dumps(environment), encoding="utf-8")
        return runner.run(str(path))

    shared, apart = two(True), two(False)
    assert [f for f in shared.findings if str(f.severity) == "error"] == []
    assert len(shared.not_examined) == len(apart.not_examined), (
        "two submodels sharing an idShort report %d unexamined scopes where "
        "the same two under different names report %d -- the name is not the "
        "identity and nothing in the report says anything merged"
        % (len(shared.not_examined), len(apart.not_examined)))


def test_a_rule_another_scope_asked_is_not_reported_unexamined(tmp_path):
    """The same subtraction its two siblings get.

    `analyze` takes a proposed loss back off when some other scope of the
    same submodel asked that row -- a list walks its rows once per item,
    and a row missed in the second item was entered in the first. Two
    keys do that and this one did not, so a report named twenty-seven
    rules as unexamined of which twenty-two had been asked, while
    `summary.rulesNotAsked` on the very same report was empty. The two
    keys contradicted each other about one run.
    """
    import copy

    from aas_submodel_validate.rules import hd_tables
    from builders import build_aasx, hd_env
    from test_what_was_not_asked import MANUFACTURER, _considered, _find

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
    named = set()
    for record in report.not_examined:
        named |= set(record.unasked)
    overlap = sorted(named & _considered(path))
    assert not overlap, (
        "%d rules are reported as scopes this run did not examine, and these "
        "%d of them were asked: %s" % (len(named), len(overlap), overlap))


def test_a_vendor_extension_does_not_make_a_conformant_file_speak(tmp_path):
    """`docs/divergences.md` #19: a manufacturer's own property passes
    without comment, and a conformant file carrying one reports nothing
    at all.

    `because` was one boolean for a whole scope -- is anything here
    unplaced -- and every unentered row beside it took that answer. So
    one property the template never mentions flipped a row about a
    section the file does not even have, and the terminal said the file
    carried an element under a section that was not there. The file is
    the same file; only the sentence changed.
    """
    import copy

    from aas_submodel_validate import report as report_module
    from builders import hd_env

    def run(with_extension):
        environment = copy.deepcopy(hd_env())
        if with_extension:
            environment["submodels"][0]["submodelElements"].append({
                "modelType": "Property", "idShort": "AcmeNote",
                "semanticId": _sid("urn:acme:note"),
                "valueType": "xs:string", "value": "internal"})
        path = tmp_path / ("extended.json" if with_extension else "plain.json")
        path.write_text(json.dumps(environment), encoding="utf-8")
        return report_module.render(runner.run(str(path))).strip()

    plain, extended = run(False), run(True)
    assert "not examined" not in extended, (
        "a conformant file speaks because of one element the template never "
        "mentions:\n  without it: %s\n  with it:    %s"
        % (plain.split("\n")[-1][-120:], extended.split("\n")[-1][-160:]))


def test_what_sat_there_is_named_so_opposite_cases_differ(tmp_path):
    """Two situations that mean opposite things wrote one record.

    A row's own container under a drifted identifier: the rules inside it
    were never put, and the container is right there. A row the file
    legitimately omits, beside an unrelated container of the same kind:
    nothing that should have been checked went unchecked. Both are
    `unclaimed-element-present` -- rightly, since neither names a cause
    (`docs/divergences.md` #19) -- and until the record said which element
    sat there, the two were equal as JSON, byte for byte.
    """
    drifted = runner.run(_instance(tmp_path, "drifted3",
                                   [_box(sid="urn:test:box-but-different")]),
                         template=_template(tmp_path))
    beside = runner.run(_instance(tmp_path, "beside", [{
        "modelType": "SubmodelElementCollection", "idShort": "OurOwnBox",
        "semanticId": _sid("urn:vendor:ourbox"), "value": []}]),
        template=_template(tmp_path))
    (one,), (other,) = drifted.not_examined, beside.not_examined
    assert one.because == other.because == "unclaimed-element-present"
    assert one.as_dict() != other.as_dict()
    assert one.as_dict()["unclaimedHere"] == [
        {"subject": "Boxes/Box", "seen": "urn:test:box-but-different"}]
    assert other.as_dict()["unclaimedHere"] == [
        {"subject": "Boxes/OurOwnBox", "seen": "urn:vendor:ourbox"}]
    # And nothing named where nothing sat: the two fields cannot disagree
    # about whether anything was there.
    (absent,) = runner.run(_instance(tmp_path, "absent3", []),
                           template=_template(tmp_path)).not_examined
    assert absent.because == "absent" and absent.as_dict()["unclaimedHere"] == []


def test_the_line_says_each_place_once(tmp_path):
    """The two clauses of the summary line are one reach said in two parts:
    the first counts rule ids across the whole run, the second names places.
    Every way of making the second count rules too met the first -- the
    bundled example said one rule twice, subtracting by id hid a second
    submodel losing the same rule for an unrelated reason (the screen with
    and without it was identical), and a sum over places read as a number
    of rules. So it names sections and what sat beside them, and an element
    the first clause already names is not named again.
    """
    import copy

    from aas_submodel_validate.example import bundled_example
    from aas_submodel_validate.report import render
    from builders import hd_env

    with bundled_example() as path:
        report = runner.run(str(path))
    assert list(report.not_asked) == ["HD-E38"], report.not_asked
    assert any("HD-E38" in record.unasked for record in report.not_examined)
    assert "not examined" not in render(report), render(report)

    def entities(identifier, name):
        return {"modelType": "SubmodelElementList", "idShort": name,
                "semanticId": _sid(identifier), "typeValueListElement": "Entity",
                "value": [{"modelType": "Entity", "entityType": "SelfManagedEntity",
                           "globalAssetId": "urn:x:pump",
                           "semanticId": _sid("https://admin-shell.io/vdi/2770/1/0/"
                                              "EntityForDocumentation")}]}

    environment = hd_env()
    first = environment["submodels"][0]
    second = copy.deepcopy(first)
    first["id"], first["idShort"] = "urn:plant:a", "HandoverA"
    second["id"], second["idShort"] = "urn:plant:b", "HandoverB"
    first["submodelElements"].append(entities(
        "https://admin-shell.io/vdi/2770/1/0/EntityForDocumentation", "Entites"))
    second["submodelElements"].append(entities("urn:vendor:our-entities", "Entities"))
    environment["submodels"] = [first, second]
    both = tmp_path / "both.json"
    both.write_text(json.dumps(environment), encoding="utf-8")
    line = render(runner.run(both))
    assert "1 rule not asked (HD-E38): HandoverA/Entites" in line, line
    assert ("1 section not examined (Entities), beside an element no row "
            "describes (HandoverB/Entities)") in line, line

    drifted = json.loads(_instance(tmp_path, "one", [
        _box(sid="urn:test:box-but-different")]).read_text("utf-8"))
    again = copy.deepcopy(drifted["submodels"][0])
    again["id"] = "urn:test:box-too"
    drifted["submodels"].append(again)
    twice = tmp_path / "twice.json"
    twice.write_text(json.dumps(drifted), encoding="utf-8")
    line = render(runner.run(twice, template=_template(tmp_path)))
    assert ("2 sections not examined (Box), beside elements no row describes "
            "(Boxes[0]/Box, Boxes[1]/Box)") in line, line


def test_an_element_the_line_already_names_is_not_named_again(tmp_path):
    """A near-missed container is named by the clause about rules not
    asked, and the same container sits beside the rows it left unopened --
    its own and an absent one of its kind. Named once."""
    from aas_submodel_validate.report import render

    def row(name, identifier, child):
        return {"modelType": "SubmodelElementCollection", "idShort": name,
                "semanticId": _sid(identifier), "qualifiers": [_card("ZeroToOne")],
                "value": [{"modelType": "Property", "idShort": child,
                           "semanticId": _sid(identifier + "/" + child),
                           "valueType": "xs:string", "qualifiers": [_card("One")]}]}

    template = tmp_path / "box-and-crate-template.json"
    template.write_text(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:bctpl", "idShort": "Plant",
        "kind": "Template", "semanticId": _sid("urn:test:plant"),
        "submodelElements": [row("Box", "https://example.com/ids/box", "Inside"),
                             row("Crate", "https://example.com/ids/crate", "Slat")]}]}),
        encoding="utf-8")
    instance = tmp_path / "near-box.json"
    instance.write_text(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:plant-1", "idShort": "Plant",
        "semanticId": _sid("urn:test:plant"),
        "submodelElements": [{"modelType": "SubmodelElementCollection",
                              "idShort": "Box",
                              "semanticId": _sid("https://example.com/ids/bux"),
                              "value": []}]}]}), encoding="utf-8")
    report = runner.run(instance, template=template)
    assert report.not_asked, "the fixture no longer draws a near miss"
    assert any(record.because == "unclaimed-element-present"
               for record in report.not_examined), report.not_examined
    assert "not examined" not in render(report), render(report)


def test_a_near_miss_elsewhere_does_not_hide_the_place(tmp_path):
    """A drifted leaf elsewhere in the Nameplate explains nothing about a
    section the file omits. The walk used to send every unentered row of
    the place a near miss fired in to `rulesNotAsked`, and the line said
    three rule ids -- the omitted section's -- as rules the drift had kept
    from being asked. It names the section as a place not examined, beside
    the element sitting there, and claims no rule."""
    from aas_submodel_validate.report import render
    from builders import dn_env

    environment = dn_env()
    submodel = environment["submodels"][0]
    submodel["submodelElements"] = [
        element for element in submodel["submodelElements"]
        if element.get("idShort") != "AssetSpecificProperties"] + [
        {"modelType": "SubmodelElementCollection", "idShort": "Extras",
         "semanticId": _sid("urn:vendor:extras"),
         "value": [{"modelType": "Property", "idShort": "C",
                    "valueType": "xs:string", "value": "x"}]},
        {"modelType": "Property", "idShort": "SerialNumberOld",
         "valueType": "xs:string", "value": "1",
         "semanticId": _sid("0112/2///61987#ABA951#008")}]
    path = tmp_path / "leaf.json"
    path.write_text(json.dumps(environment), encoding="utf-8")
    report = runner.run(path)
    line = render(report)
    assert "rules not asked" not in line, line
    assert report.as_dict()["summary"]["rulesNotAsked"] == []
    assert ("1 section not examined (AssetSpecificProperties), beside an "
            "element no row describes (Nameplate/Extras)") in line, line


def test_a_near_miss_claims_only_the_rows_it_resembles(tmp_path):
    """A list one version suffix off keeps its own rows from being asked,
    and says so. A section beside it that the file does not carry --
    `DocumentedEntities`, optional -- was reported with it, as rules the
    drift had kept from being asked; nothing about the drift reached them.
    That section is still a place this run did not examine, and says so
    there."""
    from builders import hd_env

    environment = hd_env()
    document = environment["submodels"][0]["submodelElements"][0]["value"][0]
    versions = next(element for element in document["value"]
                    if element.get("idShort") == "DocumentVersions")
    versions["semanticId"]["keys"][0]["value"] = "0173-1#02-ABI503#004"
    path = tmp_path / "drifted.json"
    path.write_text(json.dumps(environment), encoding="utf-8")
    summary = runner.run(path).as_dict()["summary"]
    unasked = set(summary["rulesNotAsked"])
    assert "HD-E14" in unasked, sorted(unasked)          # beneath the drifted list
    assert "HD-E36" not in unasked, sorted(unasked)      # beneath the omitted section
    assert any(record["rule"] == "HD-E35" and "HD-E36" in record["rulesNotAskedHere"]
               for record in summary["scopeNotExamined"]), summary["scopeNotExamined"]


def test_a_near_miss_of_a_row_its_sibling_entered_claims_nothing(tmp_path):
    """A second list one version suffix off, beside the intact one. The
    intact list entered the row, so the drift kept nothing from being
    asked -- and the optional sections beneath that row which neither list
    carries are not the drift's doing either. Taking the entered row's
    subtree anyway charged three of them to the drifted copy."""
    from builders import hd_env

    environment = hd_env()
    document = environment["submodels"][0]["submodelElements"][0]["value"][0]
    versions = next(element for element in document["value"]
                    if element.get("idShort") == "DocumentVersions")
    copy = json.loads(json.dumps(versions))
    copy["idShort"] = "DocumentVersions2"
    copy["semanticId"]["keys"][0]["value"] = "0173-1#02-ABI503#004"
    document["value"].append(copy)
    path = tmp_path / "beside.json"
    path.write_text(json.dumps(environment), encoding="utf-8")
    summary = runner.run(path).as_dict()["summary"]
    assert summary["rulesNotAsked"] == [], summary["rulesNotAsked"]
    assert summary["unmatchedElements"] == [], summary["unmatchedElements"]


def test_what_only_the_drifted_copy_holds_is_its_loss(tmp_path):
    """The same drifted copy beside the intact list, now carrying a
    `RefersToEntities` the intact one does not. Everything else it holds
    was asked of its sibling and is taken back; what only it holds -- the
    `RefersTo` item row beneath that section -- was asked of nothing, and
    the drift is why. Skipping every row a sibling entered said nothing
    was lost here."""
    from builders import hd_env

    environment = hd_env()
    document = environment["submodels"][0]["submodelElements"][0]["value"][0]
    versions = next(element for element in document["value"]
                    if element.get("idShort") == "DocumentVersions")
    copy = json.loads(json.dumps(versions))
    copy["idShort"] = "DocumentVersions2"
    copy["semanticId"]["keys"][0]["value"] = "0173-1#02-ABI503#004"
    copy["value"][0]["value"].append({
        "modelType": "SubmodelElementList", "idShort": "RefersToEntities",
        "semanticId": _sid("0173-1#02-ABK288#002"),
        "typeValueListElement": "ReferenceElement",
        "value": [{"modelType": "ReferenceElement", "semanticId": _sid("0173-1#02-ABK288#002"),
                   "value": {"type": "ExternalReference",
                             "keys": [{"type": "GlobalReference", "value": "urn:x:pump"}]}}]})
    document["value"].append(copy)
    path = tmp_path / "beside-holding-more.json"
    path.write_text(json.dumps(environment), encoding="utf-8")
    summary = runner.run(path).as_dict()["summary"]
    assert summary["rulesNotAsked"] == ["HD-E27"], summary["rulesNotAsked"]
    [record] = summary["unmatchedElements"]
    assert record["subject"].endswith("/DocumentVersions2"), record
    assert record["rulesNotAskedHere"] == ["HD-E27"], record


def _refers_to_entities():
    return {"modelType": "SubmodelElementList", "idShort": "RefersToEntities",
            "semanticId": _sid("0173-1#02-ABK288#002"),
            "typeValueListElement": "ReferenceElement",
            "value": [{"modelType": "ReferenceElement", "semanticId": _sid("0173-1#02-ABK288#002"),
                       "value": {"type": "ExternalReference",
                                 "keys": [{"type": "GlobalReference", "value": "urn:x:pump"}]}}]}


def _beside_intact(copies):
    """hd_env's Document with drifted copies of its DocumentVersions list
    beside the intact one, each named and saying whether it holds a
    RefersToEntities the intact list does not."""
    from builders import hd_env

    environment = hd_env()
    document = environment["submodels"][0]["submodelElements"][0]["value"][0]
    versions = next(element for element in document["value"]
                    if element.get("idShort") == "DocumentVersions")
    for short, holds in copies:
        copy = json.loads(json.dumps(versions))
        copy["idShort"] = short
        copy["semanticId"]["keys"][0]["value"] = "0173-1#02-ABI503#004"
        if holds:
            copy["value"][0]["value"].append(_refers_to_entities())
        document["value"].append(copy)
    return environment, document


def _summary_of(tmp_path, environment, name):
    path = tmp_path / name
    path.write_text(json.dumps(environment), encoding="utf-8")
    return runner.run(path).as_dict()["summary"]


def test_a_group_of_drifted_copies_is_charged_what_any_of_them_holds(tmp_path):
    """Two copies drifted alike beside the intact list, and only the second
    holds a RefersToEntities. They carry one drift between them and are
    charged once -- with what the second holds, which nothing asked."""
    environment, _ = _beside_intact([("DocumentVersions2", False),
                                     ("DocumentVersions3", True)])
    summary = _summary_of(tmp_path, environment, "two-copies.json")
    assert summary["rulesNotAsked"] == ["HD-E27"], summary["rulesNotAsked"]
    assert [record["rulesNotAskedHere"] for record in summary["unmatchedElements"]] \
        == [["HD-E27"]], summary["unmatchedElements"]


def test_an_item_matched_by_its_kind_is_followed_as_the_walk_follows_it(tmp_path):
    """The drifted copy's DocumentVersion carries no semanticId of its own,
    as the official example's list items do not. The walk takes such an
    item by its kind, and so does the charge."""
    environment, document = _beside_intact([("DocumentVersions2", True)])
    del document["value"][-1]["value"][0]["semanticId"]
    summary = _summary_of(tmp_path, environment, "item-by-kind.json")
    assert summary["rulesNotAsked"] == ["HD-E27"], summary["rulesNotAsked"]


def test_a_near_miss_is_charged_though_no_row_beside_it_is_unentered(tmp_path):
    """The Document also carries DocumentedEntities, so its scope leaves no
    row unentered. The charge used to wait for one to be, and what only the
    drifted copy holds went unsaid."""
    environment, document = _beside_intact([("DocumentVersions2", True)])
    document["value"].append({
        "modelType": "SubmodelElementList", "idShort": "DocumentedEntities",
        "semanticId": _sid("https://admin-shell.io/vdi/2770/1/0/Document/DocumentedEntities"),
        "typeValueListElement": "ReferenceElement",
        "value": [{"modelType": "ReferenceElement",
                   "value": {"type": "ExternalReference",
                             "keys": [{"type": "GlobalReference", "value": "urn:x:pump"}]}}]})
    summary = _summary_of(tmp_path, environment, "nothing-unentered.json")
    assert summary["rulesNotAsked"] == ["HD-E27"], summary["rulesNotAsked"]


def test_a_drifted_place_beside_a_sibling_that_entered_it_is_recorded(tmp_path):
    """Rules put elsewhere in the submodel are taken off a place's record,
    so that a section one list item omits is not reported as unexamined
    when the next item has it. Taken off a place with something of the
    row's kind sitting in it, that hid the very case the record exists
    for: a list drifted in one Document, correctly identified in the next,
    and the report byte for byte the one without it."""
    import copy

    from aas_submodel_validate.report import render
    from builders import hd_env

    def documented(identifier):
        return {"modelType": "SubmodelElementList", "idShort": "DocumentedEntities",
                "typeValueListElement": "ReferenceElement",
                "semanticId": _sid(identifier),
                "value": [{"modelType": "ReferenceElement",
                           "semanticId": _sid("https://admin-shell.io/vdi/2770/1/0/"
                                              "Document/DocumentedEntity"),
                           "value": {"type": "ExternalReference",
                                     "keys": [{"type": "GlobalReference",
                                               "value": "urn:x:pump"}]}}]}

    environment = hd_env()
    documents = environment["submodels"][0]["submodelElements"][0]["value"]
    good, drifted = copy.deepcopy(documents[0]), copy.deepcopy(documents[0])
    good["value"].append(documented(
        "https://admin-shell.io/vdi/2770/1/0/Document/DocumentedEntities"))
    drifted["value"].append(documented(
        "https://admin-shell.io/vdi/2771/1/0/Document/DocumentedEntities"))
    documents[:] = [good, drifted]
    path = tmp_path / "siblings.json"
    path.write_text(json.dumps(environment), encoding="utf-8")
    report = runner.run(path)
    (record,) = [r for r in report.not_examined
                 if r.because == "unclaimed-element-present"]
    assert record.where.endswith("Documents/[1]"), record
    assert "DocumentedEntities" in render(report), render(report)


def test_the_path_order_compares_digits_without_converting_them(monkeypatch):
    """`int()` refuses more than 4,300 digits on every interpreter CI runs,
    and an idShort is the file's to write: measured, one such submodel name
    turned two rules into "the rule itself could not run". And no two names
    may tie, or their order is left to string hashing.

    The refusal is put in place here rather than left to the interpreter,
    so that this asks the same question on one that has no such limit."""
    import builtins

    from aas_submodel_validate.rules import engine
    from aas_submodel_validate.rules.engine import _in_path_order, _sitting_order

    def refusing(value=0, *rest):
        if isinstance(value, str) and len(value) > 4300:
            raise ValueError("Exceeds the limit (4300 digits)")
        return builtins.int(value, *rest)

    monkeypatch.setattr(engine, "int", refusing, raising=False)

    long_run = "S" + "7" * 5000
    assert _in_path_order((long_run, "")) < _in_path_order((long_run + "1", ""))
    assert _in_path_order(("Part9", "")) < _in_path_order(("Part10", ""))
    keys = [_sitting_order((name, "urn:x")) for name in ("Part1", "Part01", "Part001")]
    assert len(set(map(repr, keys))) == 3, keys
    assert sorted(["Part01", "Part1", "Part001"],
                  key=lambda name: _sitting_order((name, None))) == \
        sorted(["Part001", "Part1", "Part01"],
               key=lambda name: _sitting_order((name, None)))


def test_names_are_cut_with_a_count_never_silently():
    from aas_submodel_validate.report import _named_at_most

    assert _named_at_most([]) == ""
    assert _named_at_most(["a"]) == "a"
    assert _named_at_most(["a", "b", "c"]) == "a, b, c"
    assert _named_at_most(["a", "b", "c", "d", "e"]) == "a, b, c, and 2 more"
    # A list already cut upstream, with how many there were.
    assert _named_at_most(["a", "b", "c", "d", "e"], 12) == "a, b, c, and 9 more"


def test_a_list_cut_short_says_how_many_it_left_out(tmp_path):
    """Three names and then silence reads as three names in all.

    The clause beside it on the same line names three and counts the rest
    ("and 2 more"); this one cut at three and said nothing, on the one
    line a generated-only pack speaks on at all.
    """
    from aas_submodel_validate.report import render

    rows = [{"modelType": "SubmodelElementCollection", "idShort": "Box%d" % n,
             "semanticId": _sid("urn:test:box%d" % n),
             "qualifiers": [_card("ZeroToOne")],
             "value": [{"modelType": "Property", "idShort": "Inside",
                        "semanticId": _sid("urn:test:inside"),
                        "valueType": "xs:string", "qualifiers": [_card("One")]}]}
            for n in range(1, 6)]
    template = tmp_path / "five-boxes-template.json"
    template.write_text(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:fivetpl", "idShort": "Boxes",
        "kind": "Template", "semanticId": _sid("urn:test:boxes"),
        "submodelElements": rows}]}), encoding="utf-8")
    boxes = [_box(id_short="Box%d" % n, sid="urn:test:drift%d" % n)
             for n in range(1, 6)]
    line = render(runner.run(_instance(tmp_path, "five", boxes), template=template))
    assert ("5 sections not examined (Box1, Box2, Box3, and 2 more), beside "
            "elements no row describes (Boxes/Box1, Boxes/Box2, Boxes/Box3, "
            "and 2 more)") in line, line


def _boxes(tmp_path, numbers, template_name):
    """A template of optional boxes numbered `numbers`, each holding one
    property."""
    rows = [{"modelType": "SubmodelElementCollection", "idShort": "Box%d" % n,
             "semanticId": _sid("urn:test:box%d" % n),
             "qualifiers": [_card("ZeroToOne")],
             "value": [{"modelType": "Property", "idShort": "Inside",
                        "semanticId": _sid("urn:test:inside"),
                        "valueType": "xs:string", "qualifiers": [_card("One")]}]}
            for n in numbers]
    template = tmp_path / template_name
    template.write_text(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:manytpl", "idShort": "Boxes",
        "kind": "Template", "semanticId": _sid("urn:test:boxes"),
        "submodelElements": rows}]}), encoding="utf-8")
    return template


def test_what_sat_there_is_in_path_order_and_bounded(tmp_path):
    """Every unopened row of a kind names every unplaced element of that
    kind beside it, so the lists grow as rows times elements: measured, a
    thousand optional rows against a thousand vendor containers wrote a
    50 MB report. Each record names a few, in path order -- `[2]` before
    `[10]`, and the same order in every process -- and says how many."""
    from aas_submodel_validate.report import render
    from aas_submodel_validate.rules.engine import UNCLAIMED_NAMED

    # Numbered 8 to 19 and written in reverse: the file's own order is not
    # path order, and path order is not spelling order (8, 9, 10 -- not
    # 10, 11, 12), so a list sorted either wrong way keeps the wrong ones.
    numbers = range(8, 20)
    boxes = [_box(id_short="Box%d" % n, sid="urn:test:drift%d" % n)
             for n in reversed(numbers)]
    report = runner.run(_instance(tmp_path, "twelve", boxes),
                        template=_boxes(tmp_path, numbers, "twelve-template.json"))
    record = report.not_examined[0].as_dict()
    assert record["unclaimedHereCount"] == 12, record
    assert [pair["subject"] for pair in record["unclaimedHere"]] == [
        "Boxes/Box%d" % n for n in numbers[:UNCLAIMED_NAMED]], record
    line = render(report)
    assert ("12 sections not examined (Box8, Box9, Box10, and 9 more), beside "
            "elements no row describes (Boxes/Box8, Boxes/Box9, Boxes/Box10, "
            "and 9 more)") in line, line


def test_two_lists_at_one_place_are_two_lists(tmp_path):
    """A record names what sat beside its own row, so two kinds unplaced at
    one place are two lists, and the line counts both."""
    from aas_submodel_validate.report import render

    template = tmp_path / "box-and-rack-template.json"
    template.write_text(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:brtpl", "idShort": "Boxes",
        "kind": "Template", "semanticId": _sid("urn:test:boxes"),
        "submodelElements": [
            {"modelType": "SubmodelElementCollection", "idShort": "Box",
             "semanticId": _sid("urn:test:box"), "qualifiers": [_card("ZeroToOne")],
             "value": [{"modelType": "Property", "idShort": "Inside",
                        "semanticId": _sid("urn:test:inside"),
                        "valueType": "xs:string", "qualifiers": [_card("One")]}]},
            {"modelType": "SubmodelElementList", "idShort": "Rack",
             "semanticId": _sid("urn:test:rack"), "qualifiers": [_card("ZeroToOne")],
             "typeValueListElement": "Property", "valueTypeListElement": "xs:string",
             "semanticIdListElement": _sid("urn:test:slot"),
             "value": [{"modelType": "Property", "semanticId": _sid("urn:test:slot"),
                        "valueType": "xs:string", "qualifiers": [_card("One")]}]}]}]}),
        encoding="utf-8")
    vendor_box = _box(id_short="VendorBox", sid="urn:vendor:box")
    vendor_rack = {"modelType": "SubmodelElementList", "idShort": "VendorRack",
                   "semanticId": _sid("urn:vendor:rack"),
                   "typeValueListElement": "Property", "valueTypeListElement": "xs:string",
                   "semanticIdListElement": _sid("urn:vendor:slot"),
                   "value": [{"modelType": "Property", "semanticId": _sid("urn:vendor:slot"),
                              "valueType": "xs:string", "value": "a"}]}
    line = render(runner.run(_instance(tmp_path, "two-kinds", [vendor_box, vendor_rack]),
                             template=template))
    assert ("beside elements no row describes (Boxes/VendorBox, "
            "Boxes/VendorRack)") in line, line


def test_an_element_with_no_identifier_is_not_counted_as_sitting_there(tmp_path):
    """A container with no identifier is the commonest shape of a
    manufacturer's own, and counting it made conformant files speak, which
    `docs/divergences.md` #19 promises they do not. The price is written
    down: a template container that lost its `semanticId` reads as a
    section the file does not carry."""
    from aas_submodel_validate.report import render
    from builders import td_env

    bare = _box()
    del bare["semanticId"]
    (record,) = runner.run(_instance(tmp_path, "bare", [bare]),
                           template=_template(tmp_path)).not_examined
    assert record.because == "absent", record

    environment = td_env()
    submodel = environment["submodels"][0]
    submodel["submodelElements"] = [
        element for element in submodel["submodelElements"]
        if element.get("idShort") != "FurtherInformation"] + [
        {"modelType": "SubmodelElementCollection", "idShort": "VendorExtras",
         "value": [{"modelType": "Property", "idShort": "Colour",
                    "valueType": "xs:string", "value": "red"}]}]
    path = tmp_path / "vendor.json"
    path.write_text(json.dumps(environment), encoding="utf-8")
    assert "not examined" not in render(runner.run(path))


def test_seen_is_the_elements_own_identifier(tmp_path):
    """Not whichever of its spellings sorts first -- a supplemental stood in
    for the element's own. Failing its own, the first supplemental the
    file gives; keys joined as the matching joins them."""
    def seen(name, element):
        (record,) = runner.run(_instance(tmp_path, name, [element]),
                               template=_template(tmp_path)).not_examined
        return record.as_dict()["unclaimedHere"][0]["seen"]

    both = _box(sid="urn:vendor:crate")
    both["supplementalSemanticIds"] = [_sid("https://aaa.example/first/in/order")]
    assert seen("both", both) == "urn:vendor:crate"

    only = _box()
    del only["semanticId"]
    only["supplementalSemanticIds"] = [_sid("urn:z:written-first"),
                                       _sid("urn:a:written-second")]
    assert seen("only", only) == "urn:z:written-first"

    stacked = _box()
    stacked["semanticId"] = {"type": "ExternalReference",
                             "keys": [{"type": "GlobalReference", "value": "urn:vendor:catalog"},
                                      {"type": "GlobalReference", "value": "crate"}]}
    assert seen("stacked", stacked) == "urn:vendor:catalog/crate"


def test_a_long_name_sitting_there_does_not_grow_the_report(tmp_path):
    """File-supplied text goes through one bound, and this record's place
    and elements are file-supplied: a 200,000-character idShort made the
    summary line 200,892 characters and the record as long, with every
    test green."""
    from aas_submodel_validate.model import MAX_REPORTED_CHARACTERS
    from aas_submodel_validate.report import render

    long_box = _box(id_short="B" * 200_000, sid="urn:test:box-but-different")
    report = runner.run(_instance(tmp_path, "long", [long_box]),
                        template=_template(tmp_path))
    (record,) = report.not_examined
    written = json.dumps(record.as_dict())
    assert len(written) < 4 * MAX_REPORTED_CHARACTERS, len(written)
    assert max(len(line) for line in render(report).splitlines()) < 4 * MAX_REPORTED_CHARACTERS

    # And the place itself, which is built from the document's idShorts
    # too and was not bounded at all.
    deep = json.loads(_instance(tmp_path, "deep", [
        _box(sid="urn:test:box-but-different")]).read_text("utf-8"))
    deep["submodels"][0]["idShort"] = "S" * 200_000
    path = tmp_path / "deep.json"
    path.write_text(json.dumps(deep), encoding="utf-8")
    (record,) = runner.run(path, template=_template(tmp_path)).not_examined
    assert len(record.where) <= MAX_REPORTED_CHARACTERS, len(record.where)

    # The label comes from the template's idShort, and the identifier from
    # the document's own semanticId: both are text somebody else wrote.
    long_label = json.loads(_template(tmp_path).read_text("utf-8"))
    long_label["submodels"][0]["submodelElements"][0]["idShort"] = "L" * 200_000
    template = tmp_path / "long-label-template.json"
    template.write_text(json.dumps(long_label), encoding="utf-8")
    (record,) = runner.run(_instance(tmp_path, "label", [
        _box(sid="urn:test:box-but-different")]), template=template).not_examined
    assert len(record.label) <= MAX_REPORTED_CHARACTERS, len(record.label)

    (record,) = runner.run(_instance(tmp_path, "longseen", [
        _box(sid="urn:vendor:" + "x" * 200_000)]),
        template=_template(tmp_path)).not_examined
    assert len(json.dumps(record.as_dict())) < 4 * MAX_REPORTED_CHARACTERS


def _plant(tmp_path, rows):
    """A template of optional collections `rows` = [(idShort, identifier)],
    each holding one property, under a submodel `Plant`."""
    template = tmp_path / "plant-template.json"
    template.write_text(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:planttpl", "idShort": "Plant",
        "kind": "Template", "semanticId": _sid("urn:test:plant"),
        "submodelElements": [{
            "modelType": "SubmodelElementCollection", "idShort": name,
            "semanticId": _sid(identifier), "qualifiers": [_card("ZeroToOne")],
            "value": [{"modelType": "Property", "idShort": "Inside",
                       "semanticId": _sid(identifier + "/Inside"),
                       "valueType": "xs:string", "qualifiers": [_card("One")]}]}
            for name, identifier in rows]}]}), encoding="utf-8")
    return template


def _in_plant(tmp_path, name, elements):
    path = tmp_path / ("%s.json" % name)
    path.write_text(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:plant-1", "idShort": "Plant",
        "semanticId": _sid("urn:test:plant"), "submodelElements": elements}]}),
        encoding="utf-8")
    return path


def _container(name, identifier):
    return {"modelType": "SubmodelElementCollection", "idShort": name,
            "semanticId": _sid(identifier), "value": []}


def test_a_mixed_place_names_only_what_the_line_has_not(tmp_path):
    """A near-missed container and one of the supplier's own, beside the
    same unopened row. Filtered record by record, the line named the first
    twice -- once as not asked and again as sitting there -- and a record
    whose every neighbour was already named would hide the second."""
    from aas_submodel_validate.report import render

    template = _plant(tmp_path, [("Box", "https://example.com/ids/box")])
    line = render(runner.run(_in_plant(tmp_path, "mixed", [
        _container("Box", "https://example.com/ids/bux"),
        _container("Mine", "urn:vendor:mine")]), template=template))
    assert "1 rule not asked (TPL-E02): Plant/Box" in line, line
    assert ("1 section not examined (Box), beside an element no row "
            "describes (Plant/Mine)") in line, line
    assert line.count("Plant/Box") == 1, line


def test_the_line_counts_sections_and_elements_each_as_what_they_are(tmp_path):
    """One unopened row beside two containers, and two unopened rows beside
    one: sections and elements are counted apart, and each says so in its
    own number."""
    from aas_submodel_validate.report import render

    one_row = _plant(tmp_path, [("Box", "urn:test:box")])
    line = render(runner.run(_in_plant(tmp_path, "two-beside-one", [
        _container("MineA", "urn:vendor:a"), _container("MineB", "urn:vendor:b")]),
        template=one_row))
    assert ("1 section not examined (Box), beside elements no row describes "
            "(Plant/MineA, Plant/MineB)") in line, line

    two_rows = _plant(tmp_path, [("Box", "urn:test:box"), ("Crate", "urn:test:crate")])
    line = render(runner.run(_in_plant(tmp_path, "one-beside-two", [
        _container("Mine", "urn:vendor:mine")]), template=two_rows))
    assert ("2 sections not examined (Box, Crate), beside an element no row "
            "describes (Plant/Mine)") in line, line


def test_a_blank_identifier_is_no_identifier(tmp_path):
    """A key whose value normalises to nothing carried no identifier, and
    was counted as one: `seen` came out null where the page promises a
    string."""
    (record,) = runner.run(_in_plant(tmp_path, "blank", [_container("Blank", " ")]),
                           template=_plant(tmp_path, [("Box", "urn:test:box")])).not_examined
    assert record.because == "absent", record


def test_a_template_row_numbered_rather_than_named_does_not_crash(tmp_path):
    """A supplied template's idShort is whatever its JSON says. A number
    there went into the record's label and crashed the run on its way
    through the bound: a traceback and exit 1, the code for findings."""
    template = _plant(tmp_path, [("Box", "urn:test:box")])
    document = json.loads(template.read_text("utf-8"))
    document["submodels"][0]["submodelElements"][0]["idShort"] = 5
    template.write_text(json.dumps(document), encoding="utf-8")
    (record,) = runner.run(_in_plant(tmp_path, "numbered", []),
                           template=template).not_examined
    assert record.label == "5", record


def test_names_on_the_summary_line_are_escaped(tmp_path):
    """The summary line carries names the file wrote, and a raw escape
    there drove the terminal: measured, it cleared the screen and printed a
    fake "ok" line over a run with an error in it. Both clauses."""
    from aas_submodel_validate.report import render

    template = _plant(tmp_path, [("Box", "https://example.com/ids/box")])
    beside = render(runner.run(_in_plant(tmp_path, "escape-beside", [
        _container("Evil\x1b[2Jok", "urn:vendor:x")]), template=template))
    near = render(runner.run(_in_plant(tmp_path, "escape-near", [
        _container("Box\x1b[2Jok", "https://example.com/ids/bux")]), template=template))
    for line in (beside.splitlines()[-1], near.splitlines()[-1]):
        assert "\x1b" not in line and "\\x1b[2Jok" in line, repr(line)


def test_the_path_order_reads_a_bounded_prefix():
    """A key is one tuple per run of digits and a subject is a whole path;
    a root idShort alternating letters and digits cost about 9 MB per
    element sorted. The key reads a bounded prefix, and the whole subject
    breaks the tie past it."""
    from aas_submodel_validate.rules.engine import _PATH_KEY_CHARACTERS, _in_path_order

    long_path = "a1" * 50_000
    parts = _in_path_order((long_path, ""))[0]
    assert len(parts) <= _PATH_KEY_CHARACTERS + 1, len(parts)
    assert _in_path_order((long_path + "x", "")) != _in_path_order((long_path + "y", ""))
