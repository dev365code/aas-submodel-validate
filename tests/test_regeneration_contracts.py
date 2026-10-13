"""Regeneration and comparison must preserve bytes and source claims."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from tools import verdict_diff

from builders import hd_env

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/battery-passport"


def test_verdict_comparison_keeps_the_parent_bytecode_policy(tmp_path, monkeypatch):
    """A child judging another tree must not write bytecode inside it."""
    source = tmp_path / "src"
    shutil.copytree(ROOT / "src", source,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    # A sentinel proves which reader the child imported and checks the
    # settings themselves: an empty local cache alone can also reflect
    # the interpreter's policy rather than the caller's environment.
    main = source / "aas_submodel_validate/__main__.py"
    main.write_text(
        "import json, os\n"
        "print(json.dumps({'findings': [{'rule': 'PROBE', 'severity': 'info', "
        "'subject': os.environ.get('PYTHONDONTWRITEBYTECODE', '') + '|' + "
        "os.environ.get('PYTHONPYCACHEPREFIX', '')}]}))\n", encoding="utf-8")
    case = tmp_path / "handover.json"
    case.write_text(json.dumps(hd_env()), encoding="utf-8")
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setenv("PYTHONPYCACHEPREFIX", str(tmp_path / "external-cache"))

    answer = verdict_diff._judge(source, verdict_diff.Case("handover", case))

    assert answer[2] == 0, answer
    assert answer[0] == (("PROBE", "info", "1|" + str(tmp_path / "external-cache")),)
    assert not list(source.rglob("*.pyc"))
    assert not list(source.rglob("__pycache__"))


@pytest.mark.skipif(not DATA.is_dir(), reason="no data/battery-passport in this tree (sdist)")
def test_ledger_header_names_each_template_pin_and_only_its_templates():
    """The ledger is static; its summary must follow every source URL."""
    lines = (DATA / "sources.sha256").read_text("utf-8").splitlines()
    expected = {}
    for index, line in enumerate(lines):
        match = re.search(r"submodel-templates/([0-9a-f]{40})/", line)
        if match:
            directory = lines[index + 1].split("  ", 1)[1].split("/")[1]
            template = directory.removeprefix("_base_").split("_v", 1)[0]
            expected.setdefault(match[1], set()).add(template)
    stated = {}
    for line in lines:
        match = re.fullmatch(r"# Submodel template pin ([0-9a-f]{40}): (.+)\.", line)
        if match:
            stated[match[1]] = set(match[2].split(", "))
    assert stated == expected


def test_divergence_59_describes_the_repaired_list_items_as_current():
    """All three lists omit item idShorts in 1.1; 1.0 is history."""
    template = json.loads((ROOT / "src/aas_submodel_validate/data/smt/02035-1/1.1/template.json")
                          .read_text("utf-8"))
    lists = {}

    def visit(node):
        if isinstance(node, dict):
            if node.get("modelType") == "SubmodelElementList":
                lists[node["idShort"]] = node["value"]
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(template)
    names = ("Markings", "EUDeclarationOfConformity", "ResultsOfTestReportsProvingCompliance")
    assert set(lists) == set(names)
    assert all(items and all("idShort" not in item for item in items)
               for items in lists.values())
    row = next(line for line in (ROOT / "docs/divergences.md").read_text("utf-8").splitlines()
               if line.startswith("| 59 |"))
    assert "The 1.1 items of all three lists omit idShorts" in row
    assert "The 1.0 items carried idShorts" in row
    assert "two document-list items still carry" not in row
