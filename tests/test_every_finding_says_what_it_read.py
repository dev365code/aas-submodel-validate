"""Every finding shows what it read.

A finding's `saw` is the value the reader found where it looked, and it is
what lets a person tell one finding from a similar one without opening the
file. The relayed channel -- most of what a real file draws: 789 of the
corpus's 1,001 findings -- had none. It passed aas-core3.0's sentence on
with a path, and the object at the end of most paths is a whole element or
concept description, of which the check read one or two attributes.

Which ones is written in the check. `relayed_reads.py` is generated from
aas-core3.0's own verification module, per class and sentence, and a
relayed finding shows those attributes' values; a path that ends at a
value shows the value. Nothing here restates a constraint.
"""
from __future__ import annotations

import copy
import inspect
import json
import sys
from pathlib import Path

from aas_core3 import verification

from aas_submodel_validate import relayed_reads, runner
from aas_submodel_validate.tablegen import TemplateRefused
from builders import hd_env

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import extract_meta_reads  # noqa: E402


def _run(tmp_path, env, **kwargs):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return runner.run(path, **kwargs)


def _relayed(report, words):
    return [f for f in report.findings if f.id == "META" and words in f.violation.message]


def _first(node, kind):
    if isinstance(node, dict):
        if node.get("modelType") == kind and "value" in node:
            return node
        node = list(node.values())
    if isinstance(node, list):
        for item in node:
            found = _first(item, kind)
            if found is not None:
                return found
    return None


def test_the_table_is_what_the_installed_checks_read():
    """Generated, and held to the module it was generated from: a release
    of aas-core3.0 that reads differently fails here before it reports a
    value its check never looked at."""
    assert extract_meta_reads.extract(inspect.getsource(verification)) == relayed_reads.READS


def test_a_check_on_a_list_shows_what_each_item_carries(tmp_path):
    env = copy.deepcopy(hd_env())
    env["submodels"][0]["submodelElements"][0]["value"][0]["idShort"] = "Datasheet"
    [finding] = _relayed(_run(tmp_path, env), "AASd-120")
    assert finding.violation.detail == "value[*].idShort: 'Datasheet'"


def test_a_long_list_is_shown_in_part_and_says_how_much_is_left(tmp_path):
    env = copy.deepcopy(hd_env())
    documents = env["submodels"][0]["submodelElements"][0]
    item = documents["value"][0]
    documents["value"] = []
    for number in range(1, 8):
        copied = copy.deepcopy(item)
        copied["idShort"] = "Document%02d" % number
        documents["value"].append(copied)
    [finding] = _relayed(_run(tmp_path, env), "AASd-120")
    assert finding.violation.detail == (
        "value[*].idShort: 'Document01', 'Document02', 'Document03', 'Document04', "
        "'Document05' and 2 more")


def test_a_check_on_a_concept_description_shows_the_attribute_it_read(tmp_path):
    env = copy.deepcopy(hd_env())
    env["conceptDescriptions"] = [{"modelType": "ConceptDescription", "id": "urn:example:cd:1",
                                   "isCaseOf": []}]
    [finding] = _relayed(_run(tmp_path, env), "Is-case-of")
    assert finding.violation.subject == ".concept_descriptions[0]"
    assert finding.violation.detail == "isCaseOf: []"


def test_a_check_on_a_value_shows_the_value(tmp_path):
    """A File's value is a path, and an empty one is refused by aas-core3.0's
    check on the value itself: the finding's path ends at the value."""
    env = copy.deepcopy(hd_env())
    _first(env, "File")["value"] = ""
    findings = _relayed(_run(tmp_path, env), "must not be empty")
    assert findings and all(f.violation.detail == "value: ''" for f in findings)


def test_a_check_the_table_does_not_know_still_says_what_it_looked_at(tmp_path, monkeypatch):
    """A newer aas-core3.0 can report a sentence this table was not
    generated from. Its finding names the object it is about, by kind and
    name, rather than going out with nothing."""
    monkeypatch.setattr(relayed_reads, "READS", {})
    env = copy.deepcopy(hd_env())
    env["conceptDescriptions"] = [{"modelType": "ConceptDescription", "id": "urn:example:cd:1",
                                   "isCaseOf": []}]
    [finding] = _relayed(_run(tmp_path, env), "Is-case-of")
    assert finding.violation.detail == "ConceptDescription 'urn:example:cd:1'"


def test_every_relayed_finding_in_the_corpus_says_what_it_read(tmp_path):
    import verdict_diff

    seen = 0
    for case in verdict_diff.build_corpus(tmp_path):
        if not Path(case.path).is_file():
            continue
        try:
            report = runner.run(Path(case.path), template=case.template)
        except TemplateRefused:
            continue
        for finding in report.findings:
            if finding.id == "META":
                seen += 1
                assert finding.violation.detail, (case.label, finding.violation.subject)
    assert seen > 700


# -- a finding that found nothing ----------------------------------------------


def _held(children):
    """What the scope holds, written from the file's own JSON."""
    shown = []
    for index, child in enumerate(children[:5]):
        name = repr(child["idShort"]) if child.get("idShort") else "[%d]" % index
        keys = (child.get("semanticId") or {}).get("keys") or []
        shown.append("%s (%s)" % (name, keys[0]["value"] if keys else "no semanticId"))
    listed = ", ".join(shown)
    if len(children) > 5:
        listed += " and %d more" % (len(children) - 5)
    return "this scope holds %d element%s: %s" % (
        len(children), "" if len(children) == 1 else "s", listed)


def _absent(tmp_path, env):
    return [f for f in _run(tmp_path, env).findings if "found 0" in f.violation.message]


def test_a_missing_element_shows_what_its_scope_holds(tmp_path):
    """What the walk read to find nothing is everything the scope holds:
    each element by its name and the identifier rows are matched on."""
    env = copy.deepcopy(hd_env())
    document = env["submodels"][0]["submodelElements"][0]["value"][0]
    document["value"] = [child for child in document["value"]
                         if child.get("idShort") != "DocumentIds"]
    [finding] = _absent(tmp_path, env)
    assert finding.violation.detail == _held(document["value"])


def test_a_long_scope_is_shown_in_part(tmp_path):
    env = copy.deepcopy(hd_env())
    document = env["submodels"][0]["submodelElements"][0]["value"][0]
    document["value"] = [child for child in document["value"]
                         if child.get("idShort") != "DocumentIds"]
    for number in range(6):
        document["value"].append({"modelType": "Property", "idShort": "Extra%d" % number,
                                  "valueType": "xs:string", "value": "x"})
    [finding] = _absent(tmp_path, env)
    assert finding.violation.detail == _held(document["value"])
    assert finding.violation.detail.endswith(" and %d more" % (len(document["value"]) - 5))


def test_a_scope_with_nothing_in_it_says_so(tmp_path):
    env = copy.deepcopy(hd_env())
    env["submodels"][0]["submodelElements"][0]["value"][0]["value"] = []
    findings = _absent(tmp_path, env)
    assert findings
    assert {f.violation.detail for f in findings} == {"this scope holds no elements"}
