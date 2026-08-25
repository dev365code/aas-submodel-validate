"""What the 02003 template file cannot say, and the lints that watch it.

The generated table carries cardinality, kinds, value types and semantic
identifiers. It cannot say that a value declared `xs:date` is spelled
like one, that a File names a part the container holds, or that a
reference walks to something. Those are here.

Two of them are the same instruments 02004 has, pointed at the second
table: an identifier that nearly matches a row is diagnosed rather than
silently unmatched, and a reference type that differs from the
template's is noted. The engine already computed both for this table and
nothing was reading them.
"""
from __future__ import annotations

import copy
import json

from aas_submodel_validate import runner
from builders import build_aasx, td_env

LOGO = "aasx/files/logo.png"
IMAGE = "aasx/files/front.png"


def _ids(tmp_path, env: dict):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return {finding.id: finding for finding in runner.run(path).findings}


def _general(env):
    return env["submodels"][0]["submodelElements"][0]


def _further(env):
    return env["submodels"][0]["submodelElements"][3]


def _classification(env):
    return env["submodels"][0]["submodelElements"][1]["value"][0]


# -- TD-D1: a date is spelled like a date ------------------------------------

def test_a_dotted_date_is_reported(tmp_path):
    env = copy.deepcopy(td_env())
    _further(env)["value"][1]["value"] = "15.03.2025"
    finding = _ids(tmp_path, env)["TD-D1"]
    assert "xs:date" in finding.fix


def test_a_calendar_date_is_accepted(tmp_path):
    assert "TD-D1" not in _ids(tmp_path, td_env())


# -- TD-D2: a File names a part the container holds --------------------------

def _td_container(tmp_path, env, parts):
    return build_aasx(tmp_path / "p.aasx",
                      payload=json.dumps(env).encode("utf-8"), files=parts)


def _container_ids(path):
    return {finding.id: finding for finding in runner.run(path).findings}


def test_a_logo_the_archive_does_not_hold_is_reported(tmp_path):
    path = _td_container(tmp_path, td_env(), [(IMAGE, b"\x89PNG")])
    finding = _container_ids(path)["TD-D2"]
    assert "logo.png" in (finding.violation.detail or "")


def test_files_the_archive_holds_draw_nothing(tmp_path):
    path = _td_container(tmp_path, td_env(),
                         [(LOGO, b"\x89PNG"), (IMAGE, b"\x89PNG")])
    assert "TD-D2" not in _container_ids(path)


def test_without_a_container_the_file_rule_is_silent(tmp_path):
    """An environment JSON names files this rule cannot see. Silence
    there is honesty: the defect would be in packaging, and there is no
    packaging."""
    assert "TD-D2" not in _ids(tmp_path, td_env())


# -- TD-D3: a reference walks to something -----------------------------------

def test_a_reference_to_a_property_area_that_is_not_there_is_reported(tmp_path):
    env = copy.deepcopy(td_env())
    reference = _classification(env)["value"][-1]
    assert reference["idShort"] == "ReferenceToTechnicalPropertyArea"
    reference["value"]["keys"][-1]["value"] = "7"
    finding = _ids(tmp_path, env)["TD-D3"]
    assert "7" in (finding.violation.detail or "")


def test_a_reference_that_resolves_draws_nothing(tmp_path):
    assert "TD-D3" not in _ids(tmp_path, td_env())


def test_a_reference_into_another_submodel_is_left_alone(tmp_path):
    """A reference out of this submodel is a promise this tool cannot
    check offline, and saying nothing is the honest answer."""
    env = copy.deepcopy(td_env())
    reference = _classification(env)["value"][-1]
    reference["value"]["keys"][0]["value"] = "urn:somewhere:else"
    assert "TD-D3" not in _ids(tmp_path, env)


# -- TDL1 / TDL2: the instruments 02004 has, pointed at this table ------------

def test_a_version_drifted_identifier_is_diagnosed(tmp_path):
    env = copy.deepcopy(td_env())
    _general(env)["value"][0]["semanticId"]["keys"][0]["value"] = "0173-1#02-AAO677#003"
    finding = _ids(tmp_path, env)["TDL1"]
    assert "0173-1#02-AAO677#004" in (finding.violation.detail or "")


def test_a_reference_type_that_differs_from_the_template_is_noted(tmp_path):
    env = copy.deepcopy(td_env())
    env["submodels"][0]["semanticId"]["type"] = "ExternalReference"
    env["submodels"][0]["semanticId"]["keys"][0]["type"] = "GlobalReference"
    finding = _ids(tmp_path, env)["TDL2"]
    assert "ModelReference" in (finding.violation.detail or "")


def test_the_golden_environment_draws_no_lint(tmp_path):
    ids = _ids(tmp_path, td_env())
    assert "TDL1" not in ids and "TDL2" not in ids
