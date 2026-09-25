"""A generated rule says where its requirement lives, and that includes the
qualifier the template stated it with -- as the template wrote it.

Every pack's rules said "SMT/Cardinality qualifier" (two said
"Multiplicity") whatever the element carried. IDTA 02035-4 states forty-one
of its forty-six cardinalities with a bare `Cardinality` and one with none at
all, 02035-1 one with a bare `Cardinality`: the generator reads all three
spellings alike (docs/divergences.md #50), and the clause a finding cited
named a qualifier the file of the template does not contain. The counts
below are the vendored templates', read off them.
"""
from __future__ import annotations

import json

from aas_submodel_validate import (
    rules,  # noqa: F401 - importing registers
    runner,
    tablegen,
)
from aas_submodel_validate.registry import all_rules
from aas_submodel_validate.rules import (
    contact_tables,
    dbp1_tables,
    dbp4_tables,
    hd_tables,
    sn_tables,
    td_tables,
)

_SPECS = {rule.id: rule.spec for rule in all_rules()}


def _said(tables):
    counts = {}
    for row in tables.ROWS:
        spec = _SPECS[row["id"]]
        if "no cardinality qualifier" in spec:
            key = None
        else:
            key = spec.split(", ")[-1].split(" qualifier")[0]
        counts[key] = counts.get(key, 0) + 1
    return counts


def test_each_pack_s_rules_name_the_qualifier_as_its_template_wrote_it():
    assert _said(dbp4_tables) == {"Cardinality": 41, "SMT/Cardinality": 4, None: 1}
    assert _said(dbp1_tables) == {"SMT/Cardinality": 21, "Cardinality": 1}
    assert _said(contact_tables) == {"Multiplicity": 36}
    assert _said(sn_tables) == {"Multiplicity": 73}
    assert _said(hd_tables) == {"SMT/Cardinality": 38}
    said = _said(td_tables)
    assert set(said) == {"SMT/Cardinality", None} and said[None] == 4, said


def test_the_warranty_that_states_no_cardinality_says_so():
    [row] = [row for row in dbp4_tables.ROWS if row["label"] == "WarrantyInformation"]
    assert "no cardinality qualifier" in _SPECS[row["id"]]
    assert "0..*" in _SPECS[row["id"]]


def test_a_caller_s_template_is_cited_the_same_way(tmp_path):
    def ref(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}
    identifier = "urn:example:qualifiers"
    elements = []
    for n, written in enumerate(("SMT/Cardinality", "Multiplicity", "Cardinality", None)):
        element = {"modelType": "Property", "idShort": "P%d" % n, "valueType": "xs:string",
                   "semanticId": ref("%s/p%d" % (identifier, n))}
        if written:
            element["qualifiers"] = [{"type": written, "valueType": "xs:string",
                                      "value": "One"}]
        elements.append(element)
    template = tmp_path / "t.json"
    template.write_text(json.dumps({"submodels": [{
        "kind": "Template", "idShort": "Q", "id": "urn:t", "semanticId": ref(identifier),
        "submodelElements": elements}]}), encoding="utf-8")
    supplied = runner._supplied_table(str(template))
    cited = [rule.spec.split(", ", 1)[1]
             for rule in tablegen.rules_for(supplied["table"], supplied["pack"])]
    assert cited == ["SMT/Cardinality qualifier", "Multiplicity qualifier",
                     "Cardinality qualifier", "no cardinality qualifier (read as 0..*)"], cited
