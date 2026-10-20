"""Every finding names the line in the file it read.

A finding says where by a path of idShorts, which a reader then has to find
in the file. It now also names the line the thing it is about begins on --
JSON's `{`, XML's start tag -- and, inside a package, the part. The model
keeps no positions, so the line is found by walking the document's shape
beside the model; these tests hold that walk to readings it does not share.
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

from aas_core3 import jsonization, types, xmlization

from aas_submodel_validate import positions, runner
from aas_submodel_validate.evidence import spelt
from aas_submodel_validate.tablegen import TemplateRefused
from builders import hd_env

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


# -- readings the walk does not share ---------------------------------------------


def _read_json_one_character_at_a_time(text):
    """Each object's line, by the path of keys and indexes that reaches it.
    A repeated key's later object overwrites the earlier, as json.loads
    keeps the later."""
    found, at, line = {}, 0, 1

    def blank():
        nonlocal at, line
        while at < len(text) and text[at] in " \t\r\n":
            line += text[at] == "\n"
            at += 1

    def string():
        nonlocal at
        start, at = at, at + 1
        while text[at] != '"':
            at += 2 if text[at] == "\\" else 1
        at += 1
        return json.loads(text[start:at])

    def value(path):
        nonlocal at
        blank()
        if text[at] == "{":
            found[path] = line
            at += 1
            blank()
            if text[at] == "}":
                at += 1
                return
            while True:
                blank()
                key = string()
                blank()
                at += 1                                   # the colon
                value(path + (key,))
                blank()
                at += 1                                   # a comma or the brace
                if text[at - 1] == "}":
                    return
        elif text[at] == "[":
            at += 1
            blank()
            if text[at] == "]":
                at += 1
                return
            index = 0
            while True:
                value(path + (index,))
                index += 1
                blank()
                at += 1
                if text[at - 1] == "]":
                    return
        elif text[at] == '"':
            string()
        else:
            while at < len(text) and text[at] not in ",]} \t\r\n":
                at += 1

    value(())
    return found


def _paths_of(model, path=()):
    """Every object of the model, with the path of JSON keys that reaches it."""
    yield model, path
    for name, value in vars(model).items():
        if isinstance(value, types.Class):
            yield from _paths_of(value, path + (spelt(name),))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, types.Class):
                    yield from _paths_of(item, path + (spelt(name), index))


def _json_documents(tmp_path):
    import verdict_diff

    texts = []
    for case in verdict_diff.build_corpus(tmp_path):
        path = Path(case.path)
        if path.suffix == ".json" and path.is_file():
            texts.append(path.read_bytes().decode("utf-8-sig"))
    texts += [p.read_text(encoding="utf-8")
              for p in sorted((ROOT / "src/aas_submodel_validate/data/smt").rglob("template.json"))]
    return texts


def _model_of(text, form):
    if form == "json":
        document = json.loads(text)
        if document.get("modelType") == "Submodel":
            return jsonization.submodel_from_jsonable(document)
        return jsonization.environment_from_jsonable(document)
    return xmlization.environment_from_str(text)


# -- the walk, against those readings ---------------------------------------------


def test_every_object_of_a_json_document_is_placed_where_its_brace_opens(tmp_path):
    placed = 0
    for text in _json_documents(tmp_path):
        try:
            model = _model_of(text, "json")
        except Exception:  # noqa: BLE001 - corpus documents meant not to build
            continue
        expected = _read_json_one_character_at_a_time(text)
        found = positions._json_lines(text, model)
        for obj, path in _paths_of(model):
            assert found.get(id(obj)) == expected[path], path
            placed += 1
    assert placed > 10000


def test_the_line_of_an_object_comes_from_the_repeated_key_the_model_was_built_from():
    one = {"modelType": "Submodel", "id": "urn:a", "idShort": "First"}
    two = {"modelType": "Submodel", "id": "urn:b", "idShort": "Second"}
    text = ('{\n"submodels": [\n' + json.dumps(one) + '\n],\n"submodels": [\n\n'
            + json.dumps(two) + "\n]\n}")
    model = _model_of(text, "json")
    assert model.submodels[0].id == "urn:b"
    assert positions._json_lines(text, model)[id(model.submodels[0])] == 7


def test_a_brace_inside_a_string_opens_nothing():
    text = ('{\n"submodels": [\n{"modelType": "Submodel", "id": "urn:{a}", '
            '"idShort": "Braces",\n"description": [{"language": "en", "text": "{{{"}]}\n]\n}')
    model = _model_of(text, "json")
    found = positions._json_lines(text, model)
    assert found[id(model.submodels[0])] == 3
    assert found[id(model.submodels[0].description[0])] == 4


def test_a_document_on_one_line_is_all_on_line_one(tmp_path):
    tried = 0
    for text in _json_documents(tmp_path)[:8]:
        flat = json.dumps(json.loads(text))
        try:
            model = _model_of(flat, "json")
        except Exception:  # noqa: BLE001 - corpus documents meant not to build
            continue
        assert set(positions._json_lines(flat, model).values()) == {1}
        tried += 1
    assert tried >= 3


def _xml_of(model):
    """The model as aas-core3.0 writes it, an element to a line."""
    import io

    stream = io.StringIO()
    xmlization.write(model, stream)
    return stream.getvalue().replace("><", ">\n<")


def test_every_object_of_an_xml_document_is_placed_on_its_start_tag(tmp_path):
    """Read back against the document itself: an object that is an item of
    a list is written by aas-core3.0 as an element named for its class, and
    where that element's text is found once in the document, the line it
    starts on is the object's. Only items: an object held by an attribute
    of its own is written under the attribute's name, so its text alone --
    written under its class's -- is some other object's."""
    checked = placed = 0
    for text in _json_documents(tmp_path)[:40]:
        try:
            model = _model_of(text, "json")
        except Exception:  # noqa: BLE001
            continue
        document = _xml_of(model)
        built = _model_of(document, "xml")
        found = positions._xml_lines(document, built)
        everything = [built, *built.descend()]
        assert all(id(obj) in found for obj in everything)
        placed += len(everything)
        items = [item for obj in everything for value in vars(obj).values()
                 if isinstance(value, list) for item in value if isinstance(item, types.Class)]
        for obj in items:
            alone = xmlization.to_str(obj).replace(' xmlns="%s"' % xmlization.NAMESPACE, "", 1)
            alone = alone.replace("><", ">\n<")
            if document.count(alone) == 1:
                assert found[id(obj)] == document[:document.index(alone)].count("\n") + 1
                checked += 1
    assert placed > 10000 and checked > 1000


# -- what a finding says -------------------------------------------------------


def _run(tmp_path, text, name="env.json"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return runner.run(path)


def test_every_finding_in_the_corpus_names_a_line_unless_no_line_holds_it(tmp_path):
    """No line is the answer for a finding about the whole file (no subject),
    about a package's structure -- an archive that will not open (X1), a
    chain that goes nowhere (X2), a declared part that is not there (X4) --
    about a path nothing was opened at (X6), and about a file refused for
    its size; every other finding names one."""
    import verdict_diff

    named = 0
    for case in verdict_diff.build_corpus(tmp_path):
        try:
            report = runner.run(Path(case.path), template=case.template)
        except TemplateRefused:
            continue
        for finding in report.findings:
            if finding.violation.line is not None:
                named += 1
                continue
            assert (finding.violation.subject is None
                    or finding.id in {"X1", "X2", "X4", "X6"}
                    or (finding.id == "X5" and "levels" not in finding.violation.message)), (
                case.label, finding.id, finding.violation.subject)
    assert named > 950


def test_a_package_names_the_part_each_line_is_in():
    report = runner.run(ROOT / "src/aas_submodel_validate/data/example/idta-02004-2.0.aasx")
    parts = {f.violation.part for f in report.findings}
    assert parts == {"aasx/https___demo_com_ContactInformationAAS/"
                     "https___demo_com_ContactInformationAAS.aas.xml"}
    assert all(f.violation.line for f in report.findings)
    first = report.findings[0].as_dict()
    assert isinstance(first["line"], int) and first["part"] in parts


def test_the_screen_gives_the_line_and_names_the_part_only_when_there_are_two(tmp_path):
    import zipfile

    from aas_submodel_validate.report import render
    from builders import CONTENT_TYPES, ORIGIN_REL, SPEC_REL, rels

    env = copy.deepcopy(hd_env())
    env["submodels"][0]["submodelElements"][0]["value"][0]["idShort"] = "Datasheet"
    one = render(_run(tmp_path, json.dumps(env, indent=1)), show_meta=True)
    assert re.search(r"(?m)^        at   \S.*, line \d+$", one), one
    path = tmp_path / "two.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         rels([(SPEC_REL, "/aasx/one.json"), (SPEC_REL, "/aasx/two.json")]))
        archive.writestr("aasx/one.json", json.dumps(env, indent=1))
        archive.writestr("aasx/two.json", json.dumps(env, indent=2))
    two = render(runner.run(path), show_meta=True)
    assert re.search(r", line \d+ of aasx/one\.json$", two, re.M), two
    assert re.search(r", line \d+ of aasx/two\.json$", two, re.M), two


def test_a_syntax_error_names_the_line_the_parser_stopped_on(tmp_path):
    [finding] = [f for f in _run(tmp_path, '{\n"submodels": [\n,\n]\n}').findings if f.id == "X3"]
    assert finding.violation.line == 3
    xml = ('<environment xmlns="https://admin-shell.io/aas/3/0">\n<submodels>\n'
           '<submodel>\n</environment>\n')
    [finding] = [f for f in _run(tmp_path, xml, "env.xml").findings if f.id == "X3"]
    assert finding.violation.line == 4


def test_an_element_the_reader_did_not_expect_names_its_line(tmp_path):
    """aas-core3.0 stops at the element it did not expect, before the
    parser reaches what is wrong further down; the line is that element's."""
    xml = '<environment\nxmlns="https://admin-shell.io/aas/3/0">\n<x>\n</y>\n'
    [finding] = [f for f in _run(tmp_path, xml, "env.xml").findings if f.id == "X3"]
    assert finding.violation.line == 3


def test_a_document_that_will_not_build_names_the_object_it_stopped_in(tmp_path):
    text = ('{\n"submodels": [\n{\n"modelType": "Submodel",\n"id": "urn:a"\n},\n'
            '{\n"modelType": "Submodel",\n"id": 5\n}\n]\n}')
    [finding] = [f for f in _run(tmp_path, text).findings if f.id == "X3"]
    assert finding.violation.line == 7


def test_a_document_nested_past_the_bound_names_the_line_it_crossed_on(tmp_path):
    from aas_submodel_validate import container

    deep = "[" * (container.MAX_NESTING // 2) + "\n" + "[" * container.MAX_NESTING
    [finding] = [f for f in _run(tmp_path, '{"submodels":\n' + deep).findings if f.id == "X5"]
    assert finding.violation.line == 3
    deep = "<a>" * (container.MAX_NESTING // 2) + "\n" + "<a>" * container.MAX_NESTING
    [finding] = [f for f in _run(tmp_path, '<environment xmlns="x">\n' + deep, "env.xml").findings
                 if f.id == "X5"]
    assert finding.violation.line == 3


def test_a_relayed_finding_names_the_line_of_the_object_its_check_read(tmp_path):
    """The deepest object on aas-core3.0's path, not the document it
    verified: an empty isCaseOf is the concept description's."""
    env = copy.deepcopy(hd_env())
    env["conceptDescriptions"] = [{"modelType": "ConceptDescription", "id": "urn:a"},
                                  {"modelType": "ConceptDescription", "id": "urn:b",
                                   "isCaseOf": []}]
    text = json.dumps(env, indent=1)
    [finding] = [f for f in _run(tmp_path, text).findings
                 if f.id == "META" and "Is-case-of" in f.violation.message]
    assert finding.violation.line == _read_json_one_character_at_a_time(text)[
        ("conceptDescriptions", 1)]


def test_a_rule_finding_names_the_line_of_the_element_it_judged(tmp_path):
    env = copy.deepcopy(hd_env())
    version = env["submodels"][0]["submodelElements"][0]["value"][0]["value"][2]["value"][0]
    for index, child in enumerate(version["value"]):
        if child.get("idShort") == "StatusSetDate":
            child["value"] = "06.02.2020"
            path = ("submodels", 0, "submodelElements", 0, "value", 0, "value", 2,
                    "value", 0, "value", index)
    text = json.dumps(env, indent=1)
    [finding] = [f for f in _run(tmp_path, text).findings if f.id == "HD-D8"]
    lines = _read_json_one_character_at_a_time(text)
    # HD-D8 names the DocumentVersion that holds the date, and its line is
    # where that version opens.
    assert finding.violation.subject.endswith("DocumentVersions/[0]")
    assert finding.violation.line == lines[path[:-2]]


def test_an_input_that_changed_under_the_run_gives_no_line(tmp_path, monkeypatch):
    """The lines are found by reading the document again once the run is
    over, so the second reading has to be of the same file: one whose
    digest is not the one the report carries gives no line at all, rather
    than lines of another file under findings about this one."""
    env = copy.deepcopy(hd_env())
    env["submodels"][0]["submodelElements"][0]["value"][0]["idShort"] = "Datasheet"
    text = json.dumps(env, indent=1)
    assert any(f.violation.line for f in _run(tmp_path, text).findings)
    asked = []
    real = runner._digest

    def changed(path, limit):
        asked.append(path)
        return real(path, limit) if len(asked) == 1 else "0" * 64

    monkeypatch.setattr(runner, "_digest", changed)
    report = _run(tmp_path, text)
    assert report.findings and len(asked) == 2
    assert all(f.violation.line is None for f in report.findings)


def test_a_walk_that_goes_wrong_gives_no_line_and_the_run_goes_on(tmp_path, monkeypatch):
    env = copy.deepcopy(hd_env())
    env["submodels"][0]["submodelElements"][0]["value"][0]["idShort"] = "Datasheet"
    text = json.dumps(env, indent=1)

    def broken(_text, _root):
        raise RuntimeError("a walk gone wrong")

    monkeypatch.setattr(positions, "_json_lines", broken)
    report = _run(tmp_path, text)
    assert report.findings
    assert all(f.violation.line is None for f in report.findings)
