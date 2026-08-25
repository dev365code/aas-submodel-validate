"""A report is read top to bottom by a person with limited patience.

Errors first, then warnings, then notes; within a severity our own
findings before the relayed metamodel channel, because 77 relayed
constraint messages must not bury the two template findings the reader
came for. Total order down to the message so two runs cannot differ.
"""
from __future__ import annotations

import copy
import json

from aas_submodel_validate import runner
from builders import hd_env


def test_errors_lead_and_meta_trails(tmp_path):
    env = copy.deepcopy(hd_env())
    submodel = env["submodels"][0]
    # one error (break StatusSetDate lexically), one meta warning
    # (idShort on a list child), one lint info (reference type)
    documents = submodel["submodelElements"][0]
    documents["value"][0]["idShort"] = "Datasheet"
    # a lint warning of our own, so the kind order below has two kinds to
    # order: the template's own §2.3 spelling draws HDL5. Without it every
    # warning in this fixture came from the metamodel channel, and any
    # kind order at all -- including none -- satisfied the assertion.
    for classification in documents["value"][0]["value"][1]["value"]:
        for leaf in classification["value"]:
            if leaf.get("idShort") == "ClassificationSystem":
                leaf["value"] = "VDI2770:2020"
    version = documents["value"][0]["value"][2]["value"][0]
    for child in version["value"]:
        if child.get("idShort") == "StatusSetDate":
            child["value"] = "not-a-date"
    submodel["semanticId"] = {"type": "ModelReference",
                              "keys": [{"type": "Submodel",
                                        "value": "0173-1#01-AHF578#003"}]}
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    report = runner.run(path)
    severities = [str(f.severity) for f in report.findings]
    assert severities == sorted(severities, key=("error", "warning", "info").index)
    kinds = [f.rule.kind for f in report.findings if str(f.severity) == "warning"]
    assert "meta" in kinds and set(kinds) != {"meta"}, \
        "this fixture has only one kind of warning, so it orders nothing"
    assert kinds == sorted(kinds, key=("container", "template", "lint", "meta").index)
    assert report.findings[0].id == "HD-D8"
