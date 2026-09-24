"""What this project covers, and what it deliberately does not.

Eight templates are given rule tables. The generator reads a cardinality
in any of three spellings -- `SMT/Cardinality`, the older `Multiplicity`,
or a bare `Cardinality` (docs/divergences.md #20, #50) -- so a template
written in the older spelling is judgeable once vendored. IDTA 02002
Contact Information and IDTA 02007 Software Nameplate are both vendored
that way. These tests hold the tool and the prose to each other.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
# The row builder moved into the package (`tablegen`) so an installed
# copy and the single-file build can reach it; what stayed in `tools/`
# is the emitter. These ask the builder, so they follow it.
from aas_submodel_validate import tablegen as g  # noqa: E402

#: The identifiers of the templates that have a table. 02007 stood beside
#: this set as the one docs/scope.md named as not yet vendored, with a
#: guard that the packs did not claim it; it has a pack now, and there is
#: no template left on that side of the page.
COVERED = {
    "0173-1#01-AHF578#003",                                             # 02004 (02035-2 shares it)
    "0173-1#01-AHX837#002",                                             # 02003
    "https://admin-shell.io/idta/nameplate/3/0/Nameplate",             # 02006
    "https://admin-shell.io/idta/CarbonFootprint/CarbonFootprint/1/0",  # 02023
    "https://admin-shell.io/zvei/nameplate/1/0/ContactInformations",    # 02002
    "https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel",  # 02011
    "https://admin-shell.io/idta/SoftwareNameplate/1/0",                # 02007
    "urn:samm:io.admin-shell.idta.batterypass.product_condition:1.0.2"
    "#ProductCondition",                                                # 02035-5
}


def test_the_covered_identifiers_are_the_ones_the_packs_claim():
    """Both directions, as one equality: every pack claims one of the
    covered identifiers, and every covered identifier has a pack."""
    import aas_submodel_validate.rules  # noqa: F401  (registers the packs)
    from aas_submodel_validate.rules import detect
    claimed = {pack.semantic_id for pack in detect.PACKS}
    assert claimed == COVERED


def test_the_generator_reads_all_three_cardinality_spellings():
    """The generator reads a cardinality in any of three spellings -- the
    current `SMT/Cardinality`, the older `Multiplicity` (02002/02007 use
    it), or a bare `Cardinality` -- the first present winning, and an
    element carrying none of them is 0..* (#20, #50). So a template written
    in the older spelling is judged, not passed as all-optional."""
    def card_of(qualifiers):
        element = {"idShort": "X", "modelType": "Property",
                   "valueType": "xs:string", "qualifiers": qualifiers,
                   "semanticId": {"type": "ExternalReference",
                                  "keys": [{"type": "GlobalReference",
                                            "value": "urn:x"}]}}
        pack = {"prefix": "X-E", "item_names": {}, "example_types": (),
                "skip_sids": frozenset()}
        return g._rows(element, "", None, [0], pack)["card"]

    assert card_of([{"type": "Multiplicity", "value": "One"}]) == (1, 1)
    assert card_of([{"type": "Cardinality", "value": "ZeroToOne"}]) == (0, 1)
    assert card_of([{"type": "SMT/Cardinality", "value": "One"}]) == (1, 1)
    # SMT/Cardinality wins when more than one spelling is present.
    assert card_of([{"type": "Multiplicity", "value": "ZeroToOne"},
                    {"type": "SMT/Cardinality", "value": "One"}]) == (1, 1)
    assert card_of([]) == (0, None)   # none of the three -> 0..*


def test_a_zero_to_many_row_still_obliges_kind_not_only_absence():
    """A 0..* row obliges kind, not presence -- the boundary of #20's
    reading. An element carrying no cardinality qualifier (in any of the
    three spellings) still fails its kind check when present as the wrong
    modelType, but its absence is never faulted. A guard on that boundary;
    not a statement about 02002/02007, whose Multiplicity the generator now
    reads."""
    row = g._rows({"idShort": "X", "modelType": "Property", "valueType": "xs:string",
                   "semanticId": {"type": "ExternalReference",
                                  "keys": [{"type": "GlobalReference",
                                            "value": "urn:x"}]}},
                  "", None, [0], {"prefix": "X-E", "item_names": {},
                                  "example_types": (), "skip_sids": frozenset()})
    assert row["card"] == (0, None)     # no presence/count obligation
    assert row["kind"] == "Property"    # but the kind is still recorded and checked


def test_scope_md_names_every_template_the_tool_has_a_table_for():
    """The prose a reader relies on, anchored to its context -- the
    sentence that says which templates are given tables -- and not merely
    present somewhere in the file, which is how a template could sit on
    the wrong side of the page and pass.

    Until 02007 was vendored this held a second side too: 02007 among the
    templates not yet vendored, and 02002 not there. That sentence is gone
    with nothing left to put in it, so what is held is that every
    template with a table is named where the tables are, under the number
    the page gives, and that nothing is still called unvendored."""
    scope = " ".join((ROOT / "docs" / "scope.md").read_text("utf-8").split())
    _, _, section = scope.partition("Which templates it covers")
    assert section, "the coverage section is gone"
    assert "SMT-D1" in section
    assert "Multiplicity" in section
    head, _, _ = section.partition("A submodel of any other template")
    assert "Nine official templates are given rule tables" in head, head[:200]
    for name in ("02004 Handover Documentation", "02003 Technical Data",
                 "02035-2 Digital Battery Passport", "02006 Digital Nameplate",
                 "02023 Carbon Footprint", "02002 Contact Information",
                 "02011 Hierarchical Structures", "02007 Software Nameplate",
                 "02035-5 Digital Battery Passport part 5"):
        assert name in head, name
    assert "still not vendored" not in section.partition("## ")[0]
