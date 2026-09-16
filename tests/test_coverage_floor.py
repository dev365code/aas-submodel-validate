"""What this project covers, and what it deliberately does not.

Five templates are given rule tables; a template that states no
cardinality on any element is not, because the reading that an absent
qualifier means 0..* (docs/divergences.md #20) would make its table
oblige nothing. docs/scope.md names the two published templates in that
state; this holds the tool and the prose to each other.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import extract_smt_rules as g  # noqa: E402

#: The identifiers docs/scope.md names as uncovered, measured from the
#: pinned upstream: each template carries no SMT/Cardinality qualifier.
CONTACT_INFORMATION = "https://admin-shell.io/zvei/nameplate/1/0/ContactInformations"  # 02002
SOFTWARE_NAMEPLATE = "https://admin-shell.io/idta/SoftwareNameplate/1/0"               # 02007


def test_the_uncovered_templates_are_not_claimed_by_a_pack():
    """Neither 02002 nor 02007 is claimed, so a submodel of either draws
    SMT-D1 rather than a table that would judge nothing."""
    import aas_submodel_validate.rules  # noqa: F401  (registers the packs)
    from aas_submodel_validate.rules import detect
    covered = {pack.semantic_id for pack in detect.PACKS}
    assert CONTACT_INFORMATION not in covered
    assert SOFTWARE_NAMEPLATE not in covered


def test_a_template_stating_no_cardinality_would_oblige_nothing():
    """The reason they are not tabled, reconciling #20 for a whole
    template: an element with no SMT/Cardinality qualifier generates a
    0..* row, which cannot be violated by count -- so a table with no
    qualifier anywhere requires nothing of any file."""
    element = {"idShort": "Anything", "modelType": "Property",
               "valueType": "xs:string",
               "semanticId": {"type": "ExternalReference",
                              "keys": [{"type": "GlobalReference",
                                        "value": "urn:x:anything"}]}}
    # No "qualifiers" key at all -- the whole-template case.
    pack = {"prefix": "X-E", "item_names": {}, "example_types": (),
            "skip_sids": frozenset()}
    row = g._rows(element, "", None, [0], pack)
    assert row["card"] == (0, None)   # #20: absent qualifier -> 0..*
    assert row["card"][0] == 0        # nothing required


def test_scope_md_names_the_two_uncovered_templates():
    """The prose a reader relies on. If the coverage statement drops one,
    this fails rather than letting the tool and the doc drift apart."""
    scope = " ".join((ROOT / "docs" / "scope.md").read_text("utf-8").split())
    assert "02002 Contact Information" in scope
    assert "02007 Software Nameplate" in scope
