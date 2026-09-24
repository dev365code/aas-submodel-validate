"""Every generated 02007 Software Nameplate rule fires, and the golden
fixture fires nothing at all.

Same contract as the other generated suites: a required row is proved
live by removing it, a bounded optional by injecting past its maximum,
and an unbounded (0..*) row by putting an element of the wrong kind under
its identifier -- the other half of what the row says.

The rows are the template's, and the specification beside it disagrees
with the template in several places (docs/divergences.md #57). The tests
at the bottom hold what those disagreements do to a file built to the
specification, so that the page describing them cannot drift from what
the run says.
"""
from __future__ import annotations

import copy
import json

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.rules import sn_tables
from builders import SN, SN_CONTACT, inject, sn_env, strip_row, stub_of
from verdicts import by_id

#: What to put under a row's identifier so its kind check fires. A
#: Property is the odd one out: something has to differ from it.
_WRONG_KIND = {"Property": "MultiLanguageProperty"}


def _run(tmp_path, env: dict):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return runner.run(path)


def _ids(tmp_path, env: dict):
    return by_id(_run(tmp_path, env))


def _named(children, id_short):
    return next(child for child in children if child.get("idShort") == id_short)


def _instance(env):
    return _named(env["submodels"][0]["submodelElements"], "SoftwareNameplateInstance")


def test_the_golden_environment_fires_nothing(tmp_path):
    assert set(_ids(tmp_path, sn_env())) == set()


def test_the_golden_environment_is_metamodel_clean_too(tmp_path):
    assert [f for f in _run(tmp_path, sn_env()).findings if f.rule.kind == "meta"] == []


def _mismatched(row) -> dict:
    wrong = stub_of(row)
    kind = _WRONG_KIND.get(row["kind"], "Property")
    wrong["modelType"] = kind
    wrong.pop("typeValueListElement", None)
    if kind == "Property":
        wrong["valueType"] = "xs:string"
        wrong["value"] = "x"
    else:
        wrong.pop("valueType", None)
        wrong["value"] = [{"language": "en", "text": "x"}]
    return wrong


@pytest.mark.parametrize("row", sn_tables.ROWS, ids=[r["id"] for r in sn_tables.ROWS])
def test_every_generated_rule_fires(tmp_path, row):
    env = copy.deepcopy(sn_env())
    low, high = row["card"]
    parent = sn_tables.BY_ID.get(row["parent"])
    if low >= 1:
        strip_row(env, row, tables=sn_tables)
    elif high is not None:
        inject(env, parent, [stub_of(row), stub_of(row)], tables=sn_tables)
    else:
        inject(env, parent, [_mismatched(row)], tables=sn_tables)
    assert row["id"] in _ids(tmp_path, env)


def test_the_golden_fixture_carries_every_row(tmp_path):
    """Every row has a matched instance on the golden file, so the golden
    verdict is about a full instance and not a partial one (the reasoning
    is the Contact Information suite's)."""
    from aas_submodel_validate.loader import load
    from aas_submodel_validate.rules import engine, profiles

    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(sn_env()).encode("utf-8"))
    ctx = runner.Context(load(path), profiles.Selection(None))
    instances = engine.analyze(ctx, sn_tables)["instances"]
    missing = [row["id"] for row in sn_tables.ROWS if not instances.get(row["id"])]
    assert not missing, "the golden fixture no longer carries: %s" % missing


def test_a_submodel_holding_neither_collection_draws_nothing(tmp_path):
    """Both collections are 0..1 in the template, and every mandatory
    element sits beneath one of them: an empty Software Nameplate is, by
    the template, complete. What the run can say is that it examined
    neither place."""
    env = copy.deepcopy(sn_env())
    env["submodels"][0].pop("submodelElements")
    report = _run(tmp_path, env)
    assert report.findings == [], [(f.id, f.violation.subject) for f in report.findings]


# -- where the template and the specification disagree (#57) ----------------

def test_collections_spelled_as_the_specification_spells_them_are_not_examined(tmp_path):
    """The specification's Table 1 gives the two collections
    `.../SoftwareNameplate/1/0/SoftwareNameplateType` and
    `.../1/0/SoftwareNameplateInstance`; the template, and every child
    identifier in both documents, has a `SoftwareNameplate/` segment
    before them. Spelled the specification's way, neither collection
    matches a row, both rows are optional, and nothing inside is asked --
    a missing `Version` included. The verdict is silent and the run says
    where it did not look, naming the two collections it could not
    place."""
    env = copy.deepcopy(sn_env())
    spec = "https://admin-shell.io/idta/SoftwareNameplate/1/0/"
    for element in env["submodels"][0]["submodelElements"]:
        element["semanticId"]["keys"][0]["value"] = spec + element["idShort"]
    kind = env["submodels"][0]["submodelElements"][0]
    kind["value"] = [child for child in kind["value"] if child.get("idShort") != "Version"]
    report = _run(tmp_path, env)
    assert report.findings == [], [(f.id, f.violation.subject) for f in report.findings]
    places = {place["label"]: [e["subject"] for e in place["unclaimedHere"]]
              for place in report.as_dict()["summary"]["scopeNotExamined"]}
    both = ["SoftwareNameplate/SoftwareNameplateInstance",
            "SoftwareNameplate/SoftwareNameplateType"]
    assert places == {"SoftwareNameplateType": both,
                      "SoftwareNameplateInstance": both}, places


def test_a_configuration_uri_with_its_own_identifier_is_charged_to_the_file(tmp_path):
    """The template gives `ConfigurationURI` the identifier of the
    `ConfigurationPath` it sits in; the specification's Table 6 gives it
    `.../SoftwareNameplateInstance/ConfigurationURI`. A file that follows
    the specification is told its `ConfigurationURI` is missing, and the
    remedy names the parent's identifier -- the template's defect, handed
    to the file. Held here so the page that says so stays true."""
    env = copy.deepcopy(sn_env())
    path = _named(_named(_instance(env)["value"], "ConfigurationPaths")["value"],
                  "ConfigurationPath")
    uri = _named(path["value"], "ConfigurationURI")
    uri["semanticId"]["keys"][0]["value"] = SN + "SoftwareNameplateInstance/ConfigurationURI"
    report = _run(tmp_path, env)
    [finding] = [f for f in report.findings if f.id == "SN-E35"]
    assert finding.violation.subject.endswith("ConfigurationPaths/ConfigurationPath")
    assert (SN + "SoftwareNameplateInstance/ConfigurationPath") in finding.rule.fix


def test_a_configuration_type_given_as_text_is_charged_to_the_file(tmp_path):
    """The specification's Table 6 types `ConfigurationType` as a string
    and gives `initial configuration` as its example; its diagram, and the
    template, make it an integer. The template's reading is the one
    judged."""
    env = copy.deepcopy(sn_env())
    path = _named(_named(_instance(env)["value"], "ConfigurationPaths")["value"],
                  "ConfigurationPath")
    kind = _named(path["value"], "ConfigurationType")
    kind["valueType"], kind["value"] = "xs:string", "initial configuration"
    assert "SN-E36" in _ids(tmp_path, env)


def test_an_installation_file_written_as_a_blob_is_the_wrong_kind(tmp_path):
    """Figure 5 of the specification makes `InstallationFile` a `Blob`; the
    template writes a string Property, and the row judges the kind."""
    env = copy.deepcopy(sn_env())
    kind = env["submodels"][0]["submodelElements"][0]
    blob = _named(kind["value"], "InstallationFile")
    sid = blob["semanticId"]
    blob.clear()
    blob.update({"idShort": "InstallationFile", "modelType": "Blob", "semanticId": sid,
                 "contentType": "application/zip", "value": "UEsDBA=="})
    report = _run(tmp_path, env)
    [finding] = [f for f in report.findings if f.id == "SN-E17"]
    assert "must be a Property" in finding.violation.message


def test_a_second_contact_draws_nothing(tmp_path):
    """Table 3 allows one `Contact`; the template, with Figure 6, allows
    any number, and the template's bound is the one judged."""
    env = copy.deepcopy(sn_env())
    instance = _instance(env)
    second = copy.deepcopy(_named(instance["value"], "Contact"))
    second["idShort"] = "Contact02"
    instance["value"].append(second)
    assert set(_ids(tmp_path, env)) == set()


def test_an_ip_communication_with_the_contact_template_s_newer_identifier_is_not_asked(
        tmp_path):
    """`Contact` is 02002's collection copied in, with 02002 1.0's
    identifier for `IPCommunication` -- the Contact Information submodel's
    own. A file carrying 1.0.1's identifier instead matches no row, the
    collection is 0..*, and the mandatory `AddressOfAdditionalLink` inside
    it is never asked for (docs/divergences.md #51)."""
    env = copy.deepcopy(sn_env())
    contact = _named(_instance(env)["value"], "Contact")
    link = _named(contact["value"], "IPCommunication01")
    link["semanticId"]["keys"][0]["value"] = SN_CONTACT + "IPCommunication/"
    link["value"] = [child for child in link["value"]
                     if child.get("idShort") != "AddressOfAdditionalLink"]
    assert set(_ids(tmp_path, env)) == set()
