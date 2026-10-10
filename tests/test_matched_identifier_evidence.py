"""The spelling that opened a compatibility row is evidence in its findings."""
from __future__ import annotations

import json

from aas_submodel_validate import runner
from builders import contact_env, sn_env

CONTACT = "https://admin-shell.io/zvei/nameplate/1/0/ContactInformations"
OLD_IP = CONTACT + "/IPCommunication/"
CURRENT_IP = CONTACT + "/ContactInformation/IPCommunication"
SOFTWARE = "https://admin-shell.io/idta/SoftwareNameplate/1/0/SoftwareNameplate/"
OLD_URI = SOFTWARE + "SoftwareNameplateInstance/ConfigurationPath"


def _reference(value):
    return {"type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": value}]}


def _named(environment, name):
    def walk(elements):
        for element in elements:
            yield element
            if isinstance(element.get("value"), list):
                yield from walk(e for e in element["value"] if "modelType" in e)
    return next(element for submodel in environment["submodels"]
                for element in walk(submodel["submodelElements"])
                if element.get("idShort") == name)


def _ip_without_child():
    environment = contact_env()
    element = _named(environment, "IPCommunication01")
    element["value"] = [child for child in element["value"]
                        if child.get("idShort") != "AddressOfAdditionalLink"]
    return environment, element


def _detail(tmp_path, environment, rule):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(environment), encoding="utf-8")
    report = runner.run(path)
    [finding] = [finding for finding in report.findings if finding.id == rule]
    return finding.violation.detail


def test_a_matching_primary_identifier_keeps_its_semantic_id_note(tmp_path):
    environment, element = _ip_without_child()
    element["semanticId"] = _reference(OLD_IP)
    element["supplementalSemanticIds"] = [_reference(CURRENT_IP)]
    detail = _detail(tmp_path, environment, "CI-E22")
    assert "matched semanticId %s at " % OLD_IP in detail
    assert "matched supplementalSemanticId" not in detail


def test_only_the_supplemental_identifier_that_opened_the_row_is_named(tmp_path):
    environment, element = _ip_without_child()
    element["semanticId"] = _reference("urn:supplier:ip")
    element["supplementalSemanticIds"] = [
        _reference("urn:supplier:elsewhere"), _reference(OLD_IP)]
    detail = _detail(tmp_path, environment, "CI-E22")
    assert "matched supplementalSemanticId %s at " % OLD_IP in detail
    assert "urn:supplier:" not in detail


def test_matching_supplementals_are_all_named_in_file_order(tmp_path):
    environment, element = _ip_without_child()
    element["semanticId"] = _reference("urn:supplier:ip")
    element["supplementalSemanticIds"] = [_reference(OLD_IP), _reference(CURRENT_IP)]
    detail = _detail(tmp_path, environment, "CI-E22")
    notes = ["matched supplementalSemanticId %s at " % value
             for value in (OLD_IP, CURRENT_IP)]
    assert all(note in detail for note in notes), detail
    assert detail.index(notes[0]) < detail.index(notes[1]), detail


def test_a_kind_violation_still_names_the_alias_that_opened_the_row(tmp_path):
    environment, element = _ip_without_child()
    element.update(modelType="Property", valueType="xs:string", value="wrong kind")
    element["semanticId"] = _reference("urn:supplier:ip")
    element["supplementalSemanticIds"] = [_reference(OLD_IP)]
    detail = _detail(tmp_path, environment, "CI-E21")
    assert "found a Property" in detail
    assert "matched supplementalSemanticId %s at " % OLD_IP in detail
    assert "urn:supplier:ip" not in detail


def test_configuration_uri_names_its_matching_supplemental_too(tmp_path):
    environment = sn_env()
    element = _named(environment, "ConfigurationURI")
    element["semanticId"] = _reference("urn:supplier:configuration")
    element["supplementalSemanticIds"] = [_reference(OLD_URI)]
    element["valueType"] = "xs:string"
    detail = _detail(tmp_path, environment, "SN-E35")
    assert "matched supplementalSemanticId %s at " % OLD_URI in detail
    assert "urn:supplier:configuration" not in detail
