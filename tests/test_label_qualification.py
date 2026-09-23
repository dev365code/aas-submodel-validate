"""Minimal-suffix label qualification in the generator.

A published template may repeat a named sub-structure in two scopes --
02023 carries `PcfCalculationMethods` under both its product and its
product-or-sector sections, same semanticId, different place. The
generator keys rows by label in one flat namespace (`BY_LABEL`), so two
rows wearing one label would make one of them unreachable; it qualifies a
colliding label by the shortest ancestor suffix that tells its collision
group apart -- the immediate parent where that alone distinguishes it,
one ancestor further where the immediate parents coincide, the full path
as a last resort. A template with no such repeat is left byte-for-byte
the same (the `--check` gate in `make check` proves that half).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pytest  # noqa: E402,F401  (kept for future xfail markers)

# Both halves, because this file asks both: the emitter still renders a
# module (`g.generate`) and still holds the pack list, while the row
# building moved into the package so an installed copy and the
# single-file build can reach it.
import extract_smt_rules as g  # noqa: E402
from aas_submodel_validate import tablegen  # noqa: E402

TEMPLATE = ROOT / "src/aas_submodel_validate/data/smt/02023/1.0/template.json"


def _pack(skip):
    return {"template": TEMPLATE,
            "output": ROOT / "src/aas_submodel_validate/rules/pcf_tables.py",
            "prefix": "PCF-E", "source": "x", "citation": "x",
            "item_names": g.PCF_ITEM_NAMES, "example_types": (), "skip_sids": skip}


def test_a_repeated_substructure_gets_unique_labels_by_immediate_parent():
    """With the product-or-sector section included, `PcfCalculationMethods`
    is claimed in two scopes. Generation must succeed and give each copy a
    label the other does not wear, so `BY_LABEL` keeps both. Their
    immediate parents differ (`ProductCarbonFootprint` vs
    `ProductOrSectorSpecificCarbonFootprint`), so one ancestor -- k=1 -- is
    enough, and no further ancestor is added."""
    text = g.generate(_pack(frozenset()))  # no skip -> the repeat is present
    assert "PcfCalculationMethods (ProductCarbonFootprint)" in text
    assert "PcfCalculationMethods (ProductOrSectorSpecificCarbonFootprint)" in text
    # k=1 only: the scope-root the interim scheme used is not appended.
    assert "(ProductCarbonFootprints)" not in text


def test_repeated_labels_are_qualified_by_minimal_ancestor_suffix():
    """The scheme, in full: the shortest ancestor suffix that makes a
    collision group unique -- the immediate parent where that
    distinguishes it, one ancestor further where it does not.

    In 02023 the two `PcfCalculationMethods` differ at the immediate parent
    (`ProductCarbonFootprint` vs `ProductOrSectorSpecificCarbonFootprint`),
    so k=1; the two `PcfCalculationMethod` share that parent
    (`PcfCalculationMethods`), so k=2 -- the grandparent that tells them
    apart, written from the top down. The suffix is read off the *raw*
    ancestor labels, so the shared parent contributes its bare
    `PcfCalculationMethods`, not its own k=1 qualifier."""
    text = g.generate(_pack(frozenset()))  # 02023 with both scopes present
    # k=1 for the outer repeat
    assert "PcfCalculationMethods (ProductCarbonFootprint)" in text
    assert "PcfCalculationMethods (ProductOrSectorSpecificCarbonFootprint)" in text
    # k=2 for the repeat nested under it: same immediate parent -> grandparent
    assert "PcfCalculationMethod (ProductCarbonFootprint/PcfCalculationMethods)" in text
    assert ("PcfCalculationMethod (ProductOrSectorSpecificCarbonFootprint/"
            "PcfCalculationMethods)" in text)


def test_a_non_colliding_label_is_not_qualified():
    """Only a colliding label is touched. With the product-or-sector
    section skipped there is no repeat, so no qualifier appears at all --
    the same guarantee that keeps the four packs without a repeat
    byte-identical (the `--check` gate proves that half)."""
    no_repeat = frozenset(("https://admin-shell.io/idta/CarbonFootprint/"
                           "ProductOrSectorSpecificCarbonFootprints/1/0",))
    text = g.generate(_pack(no_repeat))
    assert "(ProductCarbonFootprint)" not in text
    assert "(ProductOrSectorSpecificCarbonFootprint)" not in text
    # and the bare labels are still there, unqualified
    assert "'PcfCalculationMethods'" in text or '"PcfCalculationMethods"' in text


def test_by_label_keeps_both_repeats_and_drops_the_bare_label():
    """The consumer contract. After qualification `BY_LABEL` holds each
    scope's row under its qualified key and the bare colliding label is
    gone -- so a lookup by the bare label (`child_of`, `instances_of`,
    which index `BY_LABEL` directly) raises `KeyError` rather than
    silently returning one scope's row as if it were the only one."""
    namespace = {}
    exec(g.generate(_pack(frozenset())), namespace)
    by_label = namespace["BY_LABEL"]
    assert "PcfCalculationMethod (ProductCarbonFootprint/PcfCalculationMethods)" in by_label
    assert ("PcfCalculationMethod (ProductOrSectorSpecificCarbonFootprint/"
            "PcfCalculationMethods)" in by_label)
    assert "PcfCalculationMethod" not in by_label       # bare label -> KeyError


def test_a_top_level_repeat_keeps_its_bare_label_not_an_empty_qualifier():
    """A row with no ancestor cannot take an ancestor suffix. When a
    top-level label also appears nested, the nested copy is qualified and
    the top-level one keeps its bare label -- not `Label ()` with an empty
    parenthetical. Two top-level rows of one label stay identical and the
    downstream backstop reports them. Unreachable in the five shipped packs;
    it guards the arbitrary-template path, where a top-level idShort may
    collide with a nested one."""
    tree = [{"label": "A", "children": ()},
            {"label": "B", "children": ({"label": "A", "children": ()},)}]
    tablegen._qualify_repeats(tree)
    labels = tablegen._labels(tree, [])
    assert "A" in labels                 # top-level keeps its bare label
    assert "A (B)" in labels             # the nested copy is qualified
    assert "A ()" not in labels          # never an empty parenthetical
