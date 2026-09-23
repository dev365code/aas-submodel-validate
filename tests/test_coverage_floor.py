"""What this project covers, and what it deliberately does not.

Seven templates are given rule tables. The generator reads a cardinality
in any of three spellings -- `SMT/Cardinality`, the older `Multiplicity`,
or a bare `Cardinality` (docs/divergences.md #20, #50) -- so a template
written in the older spelling is judgeable once vendored. IDTA 02002
Contact Information is the first vendored that way; IDTA 02007 Software
Nameplate is written the same way and is still not vendored, and
docs/scope.md names it. These tests hold the tool and the prose to each
other.
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

#: The identifier docs/scope.md names as not covered, from the pinned
#: upstream: the template states cardinality with Multiplicity only.
SOFTWARE_NAMEPLATE = "https://admin-shell.io/idta/SoftwareNameplate/1/0"               # 02007

#: The identifiers of the templates that DO have a table -- the converse
#: guard, so a stale or typo'd "uncovered" constant cannot pass merely by
#: being trivially absent from the covered set.
COVERED = {
    "0173-1#01-AHF578#003",                                             # 02004 (02035-2 shares it)
    "0173-1#01-AHX837#002",                                             # 02003
    "https://admin-shell.io/idta/nameplate/3/0/Nameplate",             # 02006
    "https://admin-shell.io/idta/CarbonFootprint/CarbonFootprint/1/0",  # 02023
    "https://admin-shell.io/zvei/nameplate/1/0/ContactInformations",    # 02002
    "https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel",  # 02011
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
    assert SOFTWARE_NAMEPLATE not in claimed


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


def test_scope_md_puts_each_template_on_the_side_the_tool_puts_it():
    """The prose a reader relies on, anchored to its context and to which
    *side* each name sits on -- not merely present somewhere in the file,
    which is how this test would pass with the meaning inverted.

    02002 is vendored now, so it must appear among the templates given
    tables; 02007 is not, so it must appear with the not-yet-vendored
    reason. Both halves are asserted, because asserting only the absent
    one stays green for a stale constant that has stopped guarding
    anything."""
    scope = " ".join((ROOT / "docs" / "scope.md").read_text("utf-8").split())
    _, _, section = scope.partition("Which templates it covers")
    assert section, "the coverage section is gone"
    assert "SMT-D1" in section
    assert "Multiplicity" in section
    covered, _, not_covered = section.partition("still not vendored")
    assert not_covered, "the not-yet-vendored sentence is gone"
    # Bound the window at the next heading: without this, the "02002 is not
    # on the not-covered side" check below forbids the string anywhere in
    # the rest of the file, and would fire on an unrelated later mention.
    not_covered = not_covered.partition("## ")[0]
    assert "02002 Contact Information" in covered
    assert "02007 Software Nameplate" in not_covered
    assert "02002" not in not_covered
