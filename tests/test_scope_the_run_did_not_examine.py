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


def test_a_rule_the_line_named_as_not_asked_is_not_counted_again(tmp_path):
    """The two clauses of the summary line are one reach, said in two parts.

    `rulesNotAsked` names the rules a reported defect explains and the
    scope record lists every rule beneath a row nobody entered, so one
    rule can be in both -- and on the bundled example it is. The line
    said "1 rule not asked (HD-E38)" and then "1 rule not examined" about
    that same rule, and a reader adds the two. Nor is one rule under two
    scopes two rules: the records are per scope, the count is not.
    """
    import copy

    from aas_submodel_validate.example import bundled_example
    from aas_submodel_validate.report import render

    with bundled_example() as path:
        report = runner.run(str(path))
    assert list(report.not_asked) == ["HD-E38"], report.not_asked
    assert any("HD-E38" in record.unasked for record in report.not_examined)
    assert "not examined" not in render(report), render(report)

    # One rule, in two scopes: two submodels of one name, each with the
    # container drifted. Two records, one rule.
    drifted = json.loads(_instance(tmp_path, "one", [
        _box(sid="urn:test:box-but-different")]).read_text("utf-8"))
    second = copy.deepcopy(drifted["submodels"][0])
    second["id"] = "urn:test:box-too"
    drifted["submodels"].append(second)
    twice = tmp_path / "twice.json"
    twice.write_text(json.dumps(drifted), encoding="utf-8")
    report = runner.run(twice, template=_template(tmp_path))
    assert len(report.not_examined) == 2, report.not_examined
    line = render(report)
    assert "1 rule not examined, under 1 section " in line, line


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
    assert "(Box1, Box2, Box3, and 2 more; sitting there: " in line, line
    assert "Boxes/Box3, and 2 more)" in line, line
