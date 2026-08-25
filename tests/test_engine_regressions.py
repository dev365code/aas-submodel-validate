"""Regressions a later review found in the matching engine.

Every test here reproduces a confirmed finding: a conformant file being
failed, a defective file being hidden, a crash, or a non-deterministic
report. They were red against the pre-redesign engine.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

from aas_submodel_validate import runner
from builders import hd_env

SRC = str(Path(__file__).resolve().parents[1] / "src")


def _write(tmp_path, env):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return path


def _ids(tmp_path, env):
    return {f.id for f in runner.run(_write(tmp_path, env)).findings}


def _document(env):
    return env["submodels"][0]["submodelElements"][0]["value"][0]


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
    """The teeth the earlier decomposition test lacked (verification found
    the mutant survived it). A stray collection wearing a *DocumentId
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
