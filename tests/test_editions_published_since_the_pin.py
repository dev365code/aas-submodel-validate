"""The repaired upstream editions and the spellings their predecessors used."""
from __future__ import annotations

import copy
import json

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.model import Severity
from builders import contact_env, pcf_env, sn_env

CONTACT = "https://admin-shell.io/zvei/nameplate/1/0/ContactInformations"
IP = CONTACT + "/ContactInformation/IPCommunication"
SOFTWARE = "https://admin-shell.io/idta/SoftwareNameplate/1/0/SoftwareNameplate/"


def _elements(environment):
    def walk(elements):
        for element in elements:
            yield element
            if isinstance(element.get("value"), list):
                yield from walk(e for e in element["value"] if "modelType" in e)
    for submodel in environment["submodels"]:
        yield from walk(submodel.get("submodelElements", []))


def _named(environment, name):
    return next(e for e in _elements(environment) if e.get("idShort") == name)


def _set_sid(element, identifier):
    element["semanticId"]["keys"][0]["value"] = identifier


def _run(tmp_path, environment):
    path = tmp_path / "edition.json"
    path.write_text(json.dumps(environment), encoding="utf-8")
    return runner.run(path)


def test_carbon_footprints_can_carry_several_of_each_required_list(tmp_path):
    environment = pcf_env()
    for element in list(_elements(environment)):
        if element.get("idShort") in ("PcfCalculationMethods", "LifeCyclePhases"):
            second = copy.deepcopy(element)
            second["idShort"] += "02"
            parent = next(e for e in _elements(environment)
                          if isinstance(e.get("value"), list)
                          and any(child is element for child in e["value"]))
            parent["value"].append(second)
    report = _run(tmp_path, environment)
    assert not [f for f in report.findings if f.rule.kind == "template"
                and f.severity == Severity.ERROR], report.as_dict()


@pytest.mark.parametrize("identifier", [IP, CONTACT + "/IPCommunication/", CONTACT + "/"])
def test_both_current_and_previous_ip_spellings_open_the_required_children(
        tmp_path, identifier):
    environment = contact_env()
    link = _named(environment, "IPCommunication01")
    _set_sid(link, identifier)
    link["value"] = [e for e in link["value"]
                     if e.get("idShort") != "AddressOfAdditionalLink"]
    report = _run(tmp_path, environment)
    [finding] = [f for f in report.findings if f.id == "CI-E22"]
    assert identifier in finding.violation.detail, finding.violation



def test_the_submodel_s_own_identifier_does_not_open_ip_communication(tmp_path):
    """No published 02002 edition gives IPCommunication the submodel's own
    identifier, `.../ContactInformations` without a trailing slash: 1.0
    wrote `.../ContactInformations/`, 1.0.1 `.../IPCommunication/`, and
    the slashless value is only ever the submodel's. It was an alias all
    the same, so an element inside a contact carrying the submodel's
    identifier was judged as IPCommunication. The earlier spellings kept
    are the published ones, and this is not one of them."""
    environment = contact_env()
    link = _named(environment, "IPCommunication01")
    _set_sid(link, CONTACT)
    link["value"] = [e for e in link["value"]
                     if e.get("idShort") != "AddressOfAdditionalLink"]
    report = _run(tmp_path, environment).as_dict()
    assert not [f for f in report["findings"] if f["rule"] == "CI-E22"], report["findings"]
    # Named instead as what it is: an element no row claims, near the 1.0
    # spelling, with the rules beneath it not asked.
    [unmatched] = report["summary"]["unmatchedElements"]
    assert unmatched["seen"] == CONTACT and unmatched["resembles"] == CONTACT + "/", unmatched
    assert "CI-E22" in unmatched["rulesNotAskedHere"], unmatched
    assert "CIL1" in [f["rule"] for f in report["findings"]], report["findings"]

def test_software_configuration_uses_its_own_identifier_and_string_type(tmp_path):
    environment = sn_env()
    _set_sid(_named(environment, "ConfigurationURI"),
             SOFTWARE + "SoftwareNameplateInstance/ConfigurationURI")
    kind = _named(environment, "ConfigurationType")
    kind["valueType"], kind["value"] = "xs:string", "initial configuration"
    report = _run(tmp_path, environment)
    assert not [f for f in report.findings if f.severity == Severity.ERROR], report.as_dict()


@pytest.mark.parametrize("identifier", [
    SOFTWARE + "SoftwareNameplateInstance/ConfigurationURI",
    SOFTWARE + "SoftwareNameplateInstance/ConfigurationPath",
])
def test_both_configuration_uri_spellings_still_judge_the_element(tmp_path, identifier):
    environment = sn_env()
    uri = _named(environment, "ConfigurationURI")
    _set_sid(uri, identifier)
    uri["valueType"] = "xs:string"
    report = _run(tmp_path, environment)
    [finding] = [f for f in report.findings if f.id == "SN-E35"]
    assert "must carry valueType xs:anyURI" in finding.violation.message
    assert identifier in finding.violation.detail


@pytest.mark.parametrize("builder,rule", [(contact_env, "CI-E23"), (sn_env, "SN-E60")])
@pytest.mark.parametrize("prefix", [CONTACT, CONTACT.replace("/ContactInformations", "/ ContactInformations")])
def test_type_of_communication_keeps_the_spaced_and_repaired_spellings(
        tmp_path, builder, rule, prefix):
    environment = builder()
    element = _named(environment, "TypeOfCommunication")
    identifier = prefix + "/ContactInformation/IPCommunication/TypeOfCommunication"
    _set_sid(element, identifier)
    element["valueType"] = "xs:integer"
    element["value"] = "1"
    report = _run(tmp_path, environment)
    [finding] = [f for f in report.findings if f.id == rule]
    assert identifier in finding.violation.detail


@pytest.mark.parametrize("identifier", [IP, CONTACT + "/IPCommunication/", CONTACT + "/"])
def test_software_contact_keeps_the_previous_and_repaired_ip_spellings(tmp_path, identifier):
    environment = sn_env()
    element = _named(environment, "IPCommunication01")
    _set_sid(element, identifier)
    element["value"] = [e for e in element["value"]
                        if e.get("idShort") != "AddressOfAdditionalLink"]
    report = _run(tmp_path, environment)
    [finding] = [f for f in report.findings if f.id == "SN-E59"]
    assert identifier in finding.violation.detail
