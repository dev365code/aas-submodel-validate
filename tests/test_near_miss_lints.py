"""Every pack names an element whose identifier nearly matches a row.

02004's and 02003's packs have registered a near-miss lint from the start
(`HDL2`, `TDL1`), and 02035-2's inherits 02004's (`DBP2L2`). The other
five did not, so in them an identifier one version suffix or one last
segment off took rows out of the run with nothing among the findings
naming the element that did it: the only trace was a record in
`summary.unmatchedElements`, which a pipeline reading findings never
sees, and a drifted element with no rows beneath its own -- a
property, a file -- left not even that (docs/divergences.md #23). Each now registers the same lint, with the
same title, clause and remedy, so the finding reads alike whichever
pack drew it.
"""
from __future__ import annotations

import copy
import json

import pytest

from aas_submodel_validate import runner
from builders import contact_env, dn_env, hs_env, pcf_env, sn_env


def _find(node, short):
    if isinstance(node, dict):
        if node.get("idShort") == short:
            return node
        for value in node.values():
            found = _find(value, short)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find(value, short)
            if found is not None:
                return found
    return None


#: (lint id, fixture, element to drift, identifier it carries, the drift)
CASES = [
    ("DNL1", dn_env, "SerialNumber", "0112/2///61987#ABA951#009",
     "0112/2///61987#ABA951#008"),
    ("CIL1", contact_env, "TelephoneNumber", "0173-1#02-AAO136#002",
     "0173-1#02-AAO136#003"),
    ("PCFL1", pcf_env, "ProductCarbonFootprints",
     "https://admin-shell.io/idta/CarbonFootprint/ProductCarbonFootprints/1/0",
     "https://admin-shell.io/idta/CarbonFootprint/ProductCarbonFootprints/1/1"),
    ("HSL1", hs_env, "Gearbox", "https://admin-shell.io/idta/HierarchicalStructures/Node/1/0",
     "https://admin-shell.io/idta/HierarchicalStructures/Node/1/1"),
    ("SNL1", sn_env, "URIOfTheProduct", "0173-1#02-AAY811#001", "0173-1#02-AAY811#002"),
]


def _run(tmp_path, env, name):
    path = tmp_path / name
    path.write_text(json.dumps(env), encoding="utf-8")
    return runner.run(path)


@pytest.mark.parametrize("lint, fixture, short, carried, drifted", CASES,
                         ids=[case[0] for case in CASES])
def test_a_drifted_identifier_is_named_by_the_pack_s_lint(tmp_path, lint, fixture, short,
                                                          carried, drifted):
    env = copy.deepcopy(fixture())
    element = _find(env, short)
    assert element["semanticId"]["keys"][0]["value"] == carried, element["semanticId"]
    element["semanticId"]["keys"][0]["value"] = drifted
    report = _run(tmp_path, env, "%s.json" % lint)
    named = [f for f in report.findings if f.id == lint]
    assert len(named) == 1, [(f.id, f.violation.subject) for f in report.findings]
    [finding] = named
    assert finding.severity.value == "warning", finding.severity
    assert finding.violation.subject.endswith("/" + short), finding.violation.subject
    assert drifted in finding.violation.detail and carried in finding.violation.detail


@pytest.mark.parametrize("lint, fixture", [(case[0], case[1]) for case in CASES],
                         ids=[case[0] for case in CASES])
def test_the_golden_fixture_draws_no_near_miss(tmp_path, lint, fixture):
    report = _run(tmp_path, fixture(), "%s-golden.json" % lint)
    assert not [f for f in report.findings if f.id == lint], report.findings
