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


def test_every_finding_in_the_corpus_says_what_it_read(tmp_path):
    """The whole corpus, every rule: a finding without a `saw` line is a
    finding that did not say what it read."""
    import verdict_diff

    seen = relayed = 0
    for case in verdict_diff.build_corpus(tmp_path):
        try:
            report = runner.run(Path(case.path), template=case.template)
        except TemplateRefused:
            continue
        for finding in report.findings:
            seen += 1
            relayed += finding.id == "META"
            assert finding.violation.detail, (case.label, finding.id, finding.violation.subject)
    assert seen > 900 and relayed > 700


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


# -- a refusal ------------------------------------------------------------------
#
# A file refused before it is judged was still read: its size, the bytes it
# begins with, what its relationships part declares, what the operating
# system answered. That is its `saw`. The corpus holds five refusals; the
# loader can record some twenty more, so the places that record them are
# held here too -- each passes on what it read.


def _calls(path, name):
    import ast

    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == name:
            yield node


def test_every_refusal_the_loader_records_says_what_it_read():
    for path in ("src/aas_submodel_validate/loader.py", "src/aas_submodel_validate/runner.py"):
        for call in _calls(path, "LoadError"):
            assert any(keyword.arg == "detail" for keyword in call.keywords), (path, call.lineno)


def test_every_path_refused_says_what_the_system_answered():
    calls = list(_calls("src/aas_submodel_validate/loader.py", "UnreadablePath"))
    assert calls
    for call in calls:
        assert any(keyword.arg == "detail" for keyword in call.keywords), call.lineno


def test_every_refusal_the_container_raises_says_what_it_read():
    """Out of memory is the one that need not: what the reader met there is
    the interpreter running out, and the class says so by default."""
    import ast

    from aas_submodel_validate import container

    family = {name for name, value in vars(container).items()
              if isinstance(value, type) and issubclass(value, container.ContainerError)
              and value is not container.OutOfMemory}
    tree = ast.parse((ROOT / "src/aas_submodel_validate/container.py").read_text(encoding="utf-8"))
    raised = 0
    for node in ast.walk(tree):
        if (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
                and getattr(node.exc.func, "id", None) in family):
            raised += 1
            assert any(keyword.arg == "detail" for keyword in node.exc.keywords), node.lineno
    assert raised >= 15


def test_a_file_that_is_not_a_zip_shows_what_it_begins_with(tmp_path):
    path = tmp_path / "saved-under-the-wrong-name.aasx"
    path.write_bytes(b'{"assetAdministrationShells": []}')
    [finding] = [f for f in runner.run(path).findings if f.id == "X1"]
    assert finding.violation.detail == (
        '33 bytes, beginning 7b 22 61 73 73 65 74 41 ({"assetA)')


def test_a_package_with_no_origin_shows_what_its_relationships_declare(tmp_path):
    import zipfile

    from builders import CONTENT_TYPES, rels

    path = tmp_path / "no-origin.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([
            ("http://schemas.openxmlformats.org/package/2006/relationships/metadata/"
             "core-properties", "/docProps/core.xml")]))
    [finding] = [f for f in runner.run(path).findings if f.id == "X2"]
    assert finding.violation.detail == "_rels/.rels declares 1 relationship: core-properties"


def test_a_document_over_the_size_bound_shows_its_size(tmp_path, monkeypatch):
    from aas_submodel_validate import container

    monkeypatch.setattr(container, "MAX_PART_BYTES", 100)
    path = tmp_path / "big.json"
    path.write_bytes(b'{"submodels": []}' + b" " * 183)
    [finding] = [f for f in runner.run(path).findings if f.id == "X5"]
    assert finding.violation.detail == "200 bytes, as the file system reports it"


def test_a_document_declaring_a_dtd_shows_the_declaration(tmp_path):
    path = tmp_path / "with-a-dtd.xml"
    path.write_bytes(b'<?xml version="1.0"?>\n<!DOCTYPE environment [<!ENTITY a "b">]>\n'
                     b'<environment xmlns="https://admin-shell.io/aas/3/0"/>')
    [finding] = [f for f in runner.run(path).findings if f.id == "X3"]
    assert finding.violation.detail == "<!DOCTYPE environment ["


# -- the two hand rules the corpus never reaches --------------------------------


def _named(children, name):
    return next(child for child in children if child.get("idShort") == name)


def test_a_document_without_the_vdi_classification_shows_the_systems_it_declares(tmp_path):
    env = copy.deepcopy(hd_env())
    document = env["submodels"][0]["submodelElements"][0]["value"][0]
    classification = _named(document["value"], "DocumentClassifications")["value"][0]
    _named(classification["value"], "ClassificationSystem")["value"] = "IEC 61355"
    [finding] = [f for f in _run(tmp_path, env).findings
                 if "VDI 2770 classification system" in f.violation.message]
    assert finding.violation.detail == "ClassificationSystem: 'IEC 61355'"


def test_ids_none_of_which_is_primary_show_what_each_says(tmp_path):
    env = copy.deepcopy(hd_env())
    document = env["submodels"][0]["submodelElements"][0]["value"][0]
    ids = _named(document["value"], "DocumentIds")
    ids["value"].append(copy.deepcopy(ids["value"][0]))
    for item in ids["value"]:
        _named(item["value"], "DocumentIsPrimary")["value"] = "false"
    [finding] = [f for f in _run(tmp_path, env).findings
                 if "none is marked primary" in f.violation.message]
    assert finding.violation.detail == "DocumentIsPrimary: 'false', 'false'"


def test_every_rule_passes_on_what_it_read():
    """Held where findings are written, not only where the corpus reaches:
    a rule that makes a finding gives it a `detail`."""
    import ast

    written = 0
    for path in sorted((ROOT / "src" / "aas_submodel_validate").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Violation":
                written += 1
                assert len(node.args) >= 3 or any(k.arg == "detail" for k in node.keywords), \
                    (path.name, node.lineno)
    assert written >= 30
