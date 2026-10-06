"""An IRDI written the way SAMM writes one is the IRDI it wraps.

IDTA's templates spell one ECLASS identifier two ways. Most write it bare,
`0173-1#02-AAO134#002`; the battery passport's parts 5 and 7, generated from
SAMM models, write it `urn:irdi:0173-1#02-AAO134#002` -- the synthetic URN
SAMM's modelling guideline uses for an IRDI, which is not a URI, and whose
second `#` that guideline writes `%23`. No URN namespace `irdi` is
registered; the prefix is a convention, around the same identifier.

Matching here is exact unless a reading says otherwise, as IDTA-01001's annex
on matching semantic identifiers makes exact matching the default. The same
annex lists, among the ways a reader may match more widely, treating two
syntaxes of one IRDI as one. This project already reads an ECLASS-CDP address
as its IRDI (docs/divergences.md #4); it reads this prefix and that escape the
same way, and nothing else: no other namespace, no other case, no other
escape.

Before it did, a spare part supplier identified the way 02002 Contact
Information identifies one -- by the bare ECLASS identifiers 02035-7 borrows
under the prefix -- matched no row of 02035-7, and six mandatory fields were
reported missing; a 02002 e-mail address written under the prefix was
missing from 02002; and a 02035-5 value known by the bare identifier the
template prefixes was missing from 02035-5.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.rules import (
    contact_tables,
    dbp1_tables,
    dbp4_tables,
    dbp5_tables,
    dbp7_tables,
    dbp_tables,
    dn_tables,
    hd_tables,
    hs_tables,
    pcf_tables,
    sn_tables,
    td_tables,
)
from aas_submodel_validate.semantics import normalize
from builders import (
    PC,
    contact_env,
    contact_prefixed_env,
    dbp5_bare_irdi_env,
    dbp5_env,
    dbp7_supplier_env,
    dn_env,
    hd_env,
    hs_env,
)


def _findings(tmp_path, env):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return sorted(f.id for f in runner.run(path).findings if f.rule.kind != "meta")


def _escaped(irdi):
    head, _, version = irdi.rpartition("#")
    return "urn:irdi:%s%%23%s" % (head, version)


@pytest.mark.parametrize("spell", [
    lambda irdi: irdi,
    lambda irdi: "urn:irdi:" + irdi,
    _escaped,
], ids=["bare, as 02002 writes them", "under the prefix, as 02035-7 writes them",
        "under the prefix with the escape SAMM's guideline writes"])
def test_a_spare_part_supplier_answers_02035_7_however_its_irdis_are_spelt(tmp_path, spell):
    assert _findings(tmp_path, dbp7_supplier_env(spell)) == []


def test_a_02002_e_mail_address_written_under_the_prefix_answers_its_row(tmp_path):
    assert _findings(tmp_path, contact_prefixed_env()) == []


def test_a_02035_5_value_known_by_the_bare_irdi_answers_its_row(tmp_path):
    assert _findings(tmp_path, dbp5_bare_irdi_env()) == []


@pytest.mark.parametrize("written, read", [
    ("urn:irdi:0173-1#02-AAO134#002", "0173-1#02-AAO134#002"),
    ("urn:irdi:0173-1#02-AAC895%23009", "0173-1#02-AAC895#009"),
    (" urn:irdi:0173-1#02-AAO134#002 ", "0173-1#02-AAO134#002"),
    # An IRDI that is not ECLASS's: IEC CDD's, under the same prefix.
    ("urn:irdi:0112/2///61360_4#AAA001#001", "0112/2///61360_4#AAA001#001"),
])
def test_the_prefix_and_its_escape_are_read_and_nothing_further(written, read):
    assert normalize(written) == read


@pytest.mark.parametrize("written", [
    "URN:IRDI:0173-1#02-AAO134#002",
    "urn:iridi:0173-1#02-ABL851#001",  # 02035-5's misspelling, docs/divergences.md #58
    "urn:idi:0173-1#02-ABL854#001",    # 02035-7's specification, #61
    "urn:irdi:",
    "0173-1#02-AAC895%23009",
    "urn:samm:io.admin-shell.idta.batterypass.circularity:1.0.0#Circularity",
    # The prefix stands before an IRDI and nothing else. Around anything
    # else -- an IRI, a SAMM URN, an open-content marker, a second prefix,
    # a CDP address, a value with one `#` -- it is left as written, so
    # what it wraps matches nothing it would not match unwrapped.
    "urn:irdi:https://admin-shell.io/idta/nameplate/3/0/Nameplate",
    "urn:irdi:urn:samm:io.admin-shell.idta.contact_information:1.0.0#emailAddress",
    "urn:irdi:https://admin-shell.io/SMT/General/Arbitrary",
    "urn:irdi:urn:irdi:0173-1#02-AAO134#002",
    "urn:irdi:https://api.eclass-cdp.com/0173-1-02-AAO134-002",
    "urn:irdi:0173-1#02-AAO134%2F002",
    "urn:irdi:0173-1%2302-AAO134%23002%23",
])
def test_no_other_spelling_is_read_away(written):
    assert normalize(written) == written


@pytest.mark.parametrize("tables", [
    hd_tables, td_tables, dbp_tables, dn_tables, pcf_tables, contact_tables, hs_tables,
    sn_tables, dbp5_tables, dbp1_tables, dbp4_tables, dbp7_tables,
], ids=lambda tables: tables.__name__.rsplit(".", 1)[-1])
def test_a_vendored_table_holds_what_the_comparison_reads(tables):
    """A generated table carries its rows' identifiers in comparison form,
    because it is generated through the same function a file's identifiers
    go through when it is read. Folding only at reading time would leave
    the two forms facing each other: a file written as the template writes
    it would stop matching."""
    held = [value for row in tables.ROWS for value in row["match"]
            if value.startswith("urn:irdi:")]
    assert held == [], held[:3]


def _ref(*values):
    return {"type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": value} for value in values]}


def _known(env, own):
    pending = list(env["submodels"][0]["submodelElements"])
    while pending:
        element = pending.pop(0)
        if element["semanticId"]["keys"][0]["value"] == own:
            return element
        value = element.get("value")
        if isinstance(value, list):
            pending.extend(child for child in value
                           if isinstance(child, dict) and "modelType" in child)
    raise AssertionError(own)


def test_a_submodel_naming_an_iri_under_the_prefix_is_not_taken_for_its_template(tmp_path):
    """The prefix wraps an IRDI. Wrapped around 02006's own IRI it read as
    that IRI, and a submodel saying `urn:irdi:https://...` was judged as a
    Digital Nameplate -- a match neither the annex nor SAMM writes."""
    env = dn_env()
    own = env["submodels"][0]["semanticId"]["keys"][0]["value"]
    env["submodels"][0]["semanticId"] = _ref("urn:irdi:" + own)
    assert "SMT-D1" in _findings(tmp_path, env)


def _caller(tmp_path, prefix):
    """A caller's template whose `B` is known by two keys and whose `A`
    carries those two beside its own, and a file written exactly as it."""
    a, b1, b2 = (prefix + "0173-1#02-ZZZ010#001", prefix + "0173-1#02-ZZZ020#001",
                 prefix + "0173-1#01-ZZZ030#001")
    one = [{"type": "SMT/Cardinality", "valueType": "xs:string", "value": "One"}]
    anchor = _ref("urn:example:caller:anchor")
    template = tmp_path / "template.json"
    template.write_text(json.dumps({"submodels": [{
        "kind": "Template", "idShort": "T", "id": "urn:t", "modelType": "Submodel",
        "semanticId": anchor, "submodelElements": [
            {"modelType": "Property", "idShort": "A", "valueType": "xs:string",
             "semanticId": _ref(a), "supplementalSemanticIds": [_ref(b1, b2)], "qualifiers": one},
            {"modelType": "Property", "idShort": "B", "valueType": "xs:string",
             "semanticId": _ref(b1, b2), "qualifiers": one}]}]}), encoding="utf-8")
    document = tmp_path / "document.json"
    document.write_text(json.dumps({"submodels": [{
        "id": "urn:i", "idShort": "I", "modelType": "Submodel", "semanticId": anchor,
        "submodelElements": [
            {"modelType": "Property", "idShort": "A", "valueType": "xs:string", "value": "a",
             "semanticId": _ref(a)},
            {"modelType": "Property", "idShort": "B", "valueType": "xs:string", "value": "b",
             "semanticId": _ref(b1, b2)}]}]}), encoding="utf-8")
    return runner.run(document, template=template)


@pytest.mark.parametrize("prefix", ["", "urn:irdi:"], ids=["bare", "under the prefix"])
def test_an_element_known_by_two_keys_keeps_its_own_row_however_they_are_spelt(tmp_path, prefix):
    """An element's own identifier settles which row it is
    (docs/divergences.md #60). A row's own identifier is two keys here,
    and the comparison form of two keys is each key read and the two
    joined -- read as one string, only the first key's prefix came off,
    the result was nobody's identifier, and `B` fell to `A`, whose
    supplemental holds the same pair: `found 2` and `found 0` about a file
    written exactly as its template."""
    report = _caller(tmp_path, prefix)
    assert [f.id for f in report.findings if f.rule.kind != "meta"] == []


_NODE = "https://admin-shell.io/idta/HierarchicalStructures/Node/1/0"


@pytest.mark.parametrize("node", [_NODE, "urn:irdi:0173-1#02-ZZZ100#001"],
                         ids=["as published", "an IRDI under the prefix"])
def test_a_copy_the_walk_did_not_reach_is_said_however_its_identifier_is_spelt(tmp_path, node):
    """A self-containing element's copies that the walk did not reach are
    named in a note (docs/divergences.md #48). That reading compared the
    template's identifier as written with the file's as read, so an
    identifier the comparison reads differently -- under the prefix --
    lost the note while everything else about the run stayed the same."""
    from aas_submodel_validate import tablegen
    vendored = (Path(tablegen.__file__).parent / "data" / "smt" / "02011" / "1.1.1"
                / "template.json").read_text(encoding="utf-8")
    assert vendored.count(_NODE) == 3
    template = tmp_path / "template.json"
    template.write_text(vendored.replace(_NODE, node), encoding="utf-8")
    env = hs_env()
    entry = env["submodels"][0]["submodelElements"][0]
    gearbox = next(e for e in entry["statements"] if e.get("idShort") == "Gearbox")
    shaft = next(e for e in gearbox["statements"] if e.get("idShort") == "Shaft")
    shaft["statements"].append({
        "idShort": "Bolt", "modelType": "SubmodelElementCollection", "semanticId": _ref(_NODE),
        "value": [{"idShort": "Washer", "modelType": "Entity", "semanticId": _ref(_NODE),
                   "entityType": "SelfManagedEntity", "globalAssetId": "urn:example:asset:washer"}]})
    document = tmp_path / "document.json"
    document.write_text(json.dumps(env).replace(_NODE, node), encoding="utf-8")
    report = runner.run(document, template=template)
    assert any("contains itself" in note for note in report.notes), report.notes


def test_an_element_that_matches_through_the_prefix_is_judged_like_any_other(tmp_path):
    """What moves the other way: an optional 02002 element written under
    the prefix matched no row and was judged by nothing; it matches now,
    and a `valueType` its row does not allow is reported."""
    env = contact_env()
    element = _known(env, "0173-1#02-AAO199#003")
    element["semanticId"] = _ref("urn:irdi:0173-1#02-AAO199#003")
    element["valueType"] = "xs:int"
    element["value"] = "1"
    assert "CI-E19" in _findings(tmp_path, env)


def test_a_submodel_identified_under_the_prefix_is_judged_by_its_template(tmp_path):
    env = hd_env()
    env["submodels"][0]["semanticId"] = _ref("urn:irdi:0173-1#01-AHF578#003")
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    report = runner.run(path)
    assert report.ok and "SMT-D1" not in [f.id for f in report.findings]


def test_a_near_miss_is_named_across_the_two_spellings(tmp_path):
    """One version off is a near miss whichever way the IRDI is spelt."""
    env = contact_env()
    _known(env, "0173-1#02-AAO198#002")["semanticId"] = _ref("urn:irdi:0173-1#02-AAO198#003")
    assert "CIL1" in _findings(tmp_path, env)
    env = dbp5_env()
    element = _known(env, PC + "stateOfChargeValue")
    element["semanticId"] = _ref("0173-1#02-ABL821#002")
    element.pop("supplementalSemanticIds", None)
    assert "DBP5L1" in _findings(tmp_path, env)
