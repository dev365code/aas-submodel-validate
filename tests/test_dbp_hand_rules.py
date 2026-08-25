"""02004's hand rules, asked of 02035-2's table.

The bodies are the same ones `tests/test_hand_rules.py` exercises; what
these check is that they still reach something when the table under them
has sixteen fewer rows. A rule that installed cleanly and then found
nothing would be indistinguishable from a rule that was right, which is
what `make exercised` exists to refuse -- and did refuse, for ten of
these eleven, before this file was written.
"""
from __future__ import annotations

import copy
import json

from aas_submodel_validate import runner
from builders import build_aasx, dbp_env

PROFILE = "02035-2"


def _findings(tmp_path, env):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return {f.id: f for f in runner.run(path, profile=PROFILE).findings}


def _first_document(env):
    return env["submodels"][0]["submodelElements"][0]["value"][0]


def _classification(env):
    return _first_document(env)["value"][1]["value"][0]


def _document_version(env):
    return _first_document(env)["value"][2]["value"][0]


def _set(container, id_short, value):
    for child in container["value"]:
        if child.get("idShort") == id_short:
            child["value"] = value
            return
    raise KeyError(id_short)


def test_a_class_id_outside_the_twelve_fails(tmp_path):
    env = copy.deepcopy(dbp_env())
    _set(_classification(env), "ClassId", "99-99")
    assert "99-99" in (_findings(tmp_path, env)["DBP2-D3"].violation.detail or "")


def test_a_class_name_without_english_fails(tmp_path):
    env = copy.deepcopy(dbp_env())
    for child in _classification(env)["value"]:
        if child.get("idShort") == "ClassName":
            child["value"] = [{"language": "de", "text": "Betrieb"}]
    assert "DBP2-D4" in _findings(tmp_path, env)


def test_two_document_ids_but_no_primary_warns(tmp_path):
    env = copy.deepcopy(dbp_env())
    ids_list = _first_document(env)["value"][0]
    first = ids_list["value"][0]
    first["value"] = [c for c in first["value"] if c.get("idShort") != "DocumentIsPrimary"]
    second = copy.deepcopy(first)
    _set(second, "DocumentIdentifier", "XF90-885")
    ids_list["value"].append(second)
    assert str(_findings(tmp_path, env)["DBP2-D5"].severity) == "warning"


def test_a_digital_file_missing_from_the_container_fails(tmp_path):
    """D7's reach is the table's File rows: 02004 has two, this template
    has one. The rule crossed over because it asks the table rather than
    naming them."""
    packed = build_aasx(tmp_path / "p.aasx",
                        payload=json.dumps(dbp_env()).encode("utf-8"))
    assert "DBP2-D7" in {f.id for f in runner.run(packed, profile=PROFILE).findings}


def test_a_version_without_a_pdf_rendition_warns(tmp_path):
    env = copy.deepcopy(dbp_env())
    for child in _document_version(env)["value"]:
        if child.get("idShort") == "DigitalFiles":
            for digital in child["value"]:
                digital["contentType"] = "application/step"
    assert "DBP2-D10" in _findings(tmp_path, env)


def test_the_non_canonical_vdi_spelling_draws_the_lint(tmp_path):
    """This template's own ExampleValue is the non-canonical spelling, so
    a battery passport written from it draws this lint on day one -- the
    same divergence 02004 has (#9), inherited with the classification."""
    env = copy.deepcopy(dbp_env())
    _set(_classification(env), "ClassificationSystem", "VDI2770:2020")
    assert "DBP2L5" in _findings(tmp_path, env)


def test_an_off_pattern_idshort_is_information(tmp_path):
    """The only AllowedIdShort row this template keeps is DigitalFile --
    02004 has five. The lint's reach narrowed with the table and it still
    reaches."""
    env = copy.deepcopy(dbp_env())
    for child in _document_version(env)["value"]:
        if child.get("idShort") == "DigitalFiles":
            child["value"][0]["idShort"] = "Attachment"
    finding = _findings(tmp_path, env)["DBP2L1"]
    assert str(finding.severity) == "info"


def test_an_eclass_version_drift_is_diagnosed(tmp_path):
    env = copy.deepcopy(dbp_env())
    _first_document(env)["value"][0]["semanticId"]["keys"][0]["value"] = \
        "0173-1#02-ABI501#004"
    assert "DBP2L2" in _findings(tmp_path, env)


def test_a_reference_type_that_differs_from_the_template_is_noted(tmp_path):
    env = copy.deepcopy(dbp_env())
    env["submodels"][0]["semanticId"]["type"] = "ExternalReference"
    env["submodels"][0]["semanticId"]["keys"][0]["type"] = "GlobalReference"
    assert "DBP2L3" in _findings(tmp_path, env)


def test_a_duplicate_document_id_pair_warns(tmp_path):
    env = copy.deepcopy(dbp_env())
    documents = env["submodels"][0]["submodelElements"][0]["value"]
    documents.append(copy.deepcopy(documents[0]))
    assert "DBP2L4" in _findings(tmp_path, env)
