"""A generated rule says where its requirement lives, and that includes the
qualifier the template stated it with -- as the template wrote it.

Every pack's rules said "SMT/Cardinality qualifier" (two said
"Multiplicity") whatever the element carried. Of IDTA 02035-4's forty-six
elements, forty-one state their cardinality with a bare `Cardinality`, four
with `SMT/Cardinality` and one with no qualifier at all; 02035-1 states one
with a bare `Cardinality`: the generator reads all three spellings alike
(docs/divergences.md #50), and the clause a finding cited named a qualifier
type the template does not write -- the same semanticId, spelled otherwise.
The counts below are the vendored templates', read off them, for every pack:
one that cites a fixed spelling again changes its count here.
"""
from __future__ import annotations

import importlib
import json

import pytest

from aas_submodel_validate import (
    registry,
    rules,  # noqa: F401 - importing registers
    runner,
    tablegen,
)
from aas_submodel_validate.registry import all_rules
from aas_submodel_validate.rules import (
    contact,
    contact_tables,
    dbp,
    dbp1,
    dbp1_tables,
    dbp4,
    dbp4_tables,
    dbp5,
    dbp5_tables,
    dbp7,
    dbp7_tables,
    dbp_tables,
    dn,
    dn_tables,
    hd,
    hd_tables,
    hs,
    hs_tables,
    pcf,
    pcf_tables,
    sn,
    sn_tables,
    td,
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
    assert _said(td_tables) == {"SMT/Cardinality": 22, None: 4}
    assert _said(pcf_tables) == {"SMT/Cardinality": 24, None: 2}
    assert _said(hd_tables) == {"SMT/Cardinality": 38}
    assert _said(dn_tables) == {"SMT/Cardinality": 30}
    assert _said(hs_tables) == {"SMT/Cardinality": 11}
    assert _said(dbp_tables) == {"SMT/Cardinality": 22}
    assert _said(dbp5_tables) == {"SMT/Cardinality": 49}
    assert _said(dbp7_tables) == {"SMT/Cardinality": 37}


#: Every vendored pack, beside the table it builds its rules from.
_PACKS = {"hd": (hd, hd_tables), "td": (td, td_tables), "dbp": (dbp, dbp_tables),
          "dn": (dn, dn_tables), "pcf": (pcf, pcf_tables),
          "contact": (contact, contact_tables), "hs": (hs, hs_tables),
          "sn": (sn, sn_tables), "dbp5": (dbp5, dbp5_tables), "dbp1": (dbp1, dbp1_tables),
          "dbp4": (dbp4, dbp4_tables), "dbp7": (dbp7, dbp7_tables)}


def _built_from(module, tables, rows):
    """The rules `module` registers when its table holds `rows`, in a
    registry of their own. The module is then built once more from its own
    rows, into a registry that is thrown away, so nothing it keeps goes on
    holding the changed ones, and the session's registry is put back."""
    kept_rows, kept_registry = tables.ROWS, registry._registry
    try:
        tables.ROWS, registry._registry = rows, {}
        importlib.reload(module)
        return registry._registry
    finally:
        tables.ROWS, registry._registry = kept_rows, {}
        importlib.reload(module)
        registry._registry = kept_registry


@pytest.mark.parametrize("name", sorted(_PACKS))
def test_a_pack_reads_the_qualifier_off_the_row_where_every_row_agrees_too(name):
    """The counts above hold a pack whose template mixes its spellings. One
    whose rows all say the same thing reads alike through a fixed string,
    and would go on saying it of a template re-vendored with another
    spelling: 02035-7's pack carried such a string in from before the
    clause was read off the row, and every row there says
    `SMT/Cardinality`. So one row is given another spelling and the pack
    is built again from it."""
    module, tables = _PACKS[name]
    row = dict(tables.ROWS[0])
    other = ("Cardinality" if row.get("card_qualifier", "SMT/Cardinality") == "Multiplicity"
             else "Multiplicity")
    row["card_qualifier"] = other
    built = _built_from(module, tables, (row,) + tuple(tables.ROWS[1:]))
    assert built[row["id"]].spec == "%s, %s qualifier" % (tables.TEMPLATE_CITATION, other), (
        "the pack cites a spelling its row does not carry: %r" % built[row["id"]].spec)


def test_02003_s_unqualified_items_say_where_their_0_to_many_comes_from():
    # The PDF's element tables give the four list items 0..*; the clause
    # says so inside the parenthesis it explains, not after it, where it
    # read as the PDF giving them no qualifier.
    unqualified = [_SPECS[row["id"]] for row in td_tables.ROWS
                   if row.get("card_qualifier", "") is None]
    assert unqualified == [td_tables.TEMPLATE_CITATION + ", no cardinality qualifier "
                           "(read as 0..*, as the PDF's element tables give it)"] * 4


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
