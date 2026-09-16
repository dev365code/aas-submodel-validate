"""What this project covers, and what it deliberately does not.

Five templates are given rule tables. Two published templates the
generator can read structurally are not: they state their cardinalities
with the older `Multiplicity` qualifier, and the generator reads only
`SMT/Cardinality` (docs/divergences.md #20, #50). Read as no cardinality,
every row would default to 0..*, and the table could not enforce the
presence those templates require. docs/scope.md names the two; these
tests hold the tool and the prose to each other.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import extract_smt_rules as g  # noqa: E402

#: The identifiers docs/scope.md names as not covered, from the pinned
#: upstream: each template states cardinality with Multiplicity only.
CONTACT_INFORMATION = "https://admin-shell.io/zvei/nameplate/1/0/ContactInformations"  # 02002
SOFTWARE_NAMEPLATE = "https://admin-shell.io/idta/SoftwareNameplate/1/0"               # 02007

#: The identifiers of the templates that DO have a table -- the converse
#: guard, so a stale or typo'd "uncovered" constant cannot pass merely by
#: being trivially absent from the covered set.
COVERED = {
    "0173-1#01-AHF578#003",                                             # 02004 (02035-2 shares it)
    "0173-1#01-AHX837#002",                                             # 02003
    "https://admin-shell.io/idta/nameplate/3/0/Nameplate",             # 02006
    "https://admin-shell.io/idta/CarbonFootprint/CarbonFootprint/1/0",  # 02023
}


def test_the_covered_and_uncovered_identifiers_are_what_the_docs_say():
    """Both directions. Every pack claims one of the covered identifiers,
    and neither uncovered template's identifier is claimed. The converse
    half is what makes it a guard: `X not in claimed` alone stays green
    for a stale constant that has quietly stopped guarding anything."""
    import aas_submodel_validate.rules  # noqa: F401  (registers the packs)
    from aas_submodel_validate.rules import detect
    claimed = {pack.semantic_id for pack in detect.PACKS}
    assert claimed == COVERED
    assert CONTACT_INFORMATION not in claimed
    assert SOFTWARE_NAMEPLATE not in claimed


def test_the_generator_reads_smt_cardinality_and_not_multiplicity():
    """The reason 02002/02007 are not tabled: their cardinality is stated
    with `Multiplicity`, and the generator reads only `SMT/Cardinality`.
    An element carrying `Multiplicity: One` (mandatory) but no
    `SMT/Cardinality` is still read as 0..* -- so a table built from such a
    template could not require the element the template makes mandatory.
    The difference is the spelling, not the concept (#20, #50)."""
    def card_of(qualifiers):
        element = {"idShort": "X", "modelType": "Property",
                   "valueType": "xs:string", "qualifiers": qualifiers,
                   "semanticId": {"type": "ExternalReference",
                                  "keys": [{"type": "GlobalReference",
                                            "value": "urn:x"}]}}
        pack = {"prefix": "X-E", "item_names": {}, "example_types": (),
                "skip_sids": frozenset()}
        return g._rows(element, "", None, [0], pack)["card"]

    assert card_of([{"type": "Multiplicity", "value": "One"}]) == (0, None), \
        "Multiplicity was read; the generator should ignore it"
    assert card_of([{"type": "SMT/Cardinality", "value": "One"}]) == (1, 1)
    assert card_of([]) == (0, None)   # #20: no qualifier at all -> 0..*


def test_a_zero_to_many_row_still_obliges_kind_not_only_absence():
    """The boundary of "not tabled": a 0..* row imposes no presence or
    count obligation, but it is not obligation-free -- a present element of
    the wrong modelType still fails its kind check. So an all-0..* table is
    not "passes every file"; it is "cannot require anything be present".
    This is why the reason 02002/02007 are set aside is the missing
    presence obligation, stated precisely rather than as "obliges
    nothing"."""
    row = g._rows({"idShort": "X", "modelType": "Property", "valueType": "xs:string",
                   "semanticId": {"type": "ExternalReference",
                                  "keys": [{"type": "GlobalReference",
                                            "value": "urn:x"}]}},
                  "", None, [0], {"prefix": "X-E", "item_names": {},
                                  "example_types": (), "skip_sids": frozenset()})
    assert row["card"] == (0, None)     # no presence/count obligation
    assert row["kind"] == "Property"    # but the kind is still recorded and checked


def test_scope_md_names_the_two_as_not_covered():
    """The prose a reader relies on, anchored to its context: the two
    names must appear in the coverage section, on the not-covered side,
    with the Multiplicity reason -- not merely somewhere in the file with
    the meaning inverted."""
    scope = " ".join((ROOT / "docs" / "scope.md").read_text("utf-8").split())
    _, _, section = scope.partition("Which templates it covers")
    assert section, "the coverage section is gone"
    assert "SMT-D1" in section
    assert "Multiplicity" in section
    assert "02002 Contact Information" in section
    assert "02007 Software Nameplate" in section
