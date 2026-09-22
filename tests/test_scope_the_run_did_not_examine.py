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
