"""Scope-root label qualification in the generator.

A published template may repeat a named sub-structure in two scopes --
02023 carries `PcfCalculationMethods` under both its product and its
product-or-sector sections, same semanticId, different place. The
generator keys rows by label in one flat namespace (`BY_LABEL`), so two
rows wearing one label would make one of them unreachable; it used to
abort. It now qualifies a colliding label by its scope-root -- the
top-level element its scope descends from -- so both are kept, and a
template with no such repeat is left byte-for-byte the same (the
`--check` gate in `make check` proves that half).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import extract_smt_rules as g  # noqa: E402

TEMPLATE = ROOT / "src/aas_submodel_validate/data/smt/02023/1.0/template.json"


def _pack(skip):
    return {"template": TEMPLATE,
            "output": ROOT / "src/aas_submodel_validate/rules/pcf_tables.py",
            "prefix": "PCF-E", "source": "x", "citation": "x",
            "item_names": g.PCF_ITEM_NAMES, "example_types": (), "skip_sids": skip}


def test_a_repeated_substructure_gets_unique_labels_by_scope_root():
    """With the product-or-sector section included, `PcfCalculationMethods`
    and its item are claimed in two scopes. Generation must succeed and
    give each colliding label its scope-root, so `BY_LABEL` keeps both."""
    text = g.generate(_pack(frozenset()))  # no skip -> the repeat is present
    assert "PcfCalculationMethods (ProductCarbonFootprints)" in text
    assert "PcfCalculationMethods (ProductOrSectorSpecificCarbonFootprints)" in text
    assert "PcfCalculationMethod (ProductCarbonFootprints)" in text
    assert "PcfCalculationMethod (ProductOrSectorSpecificCarbonFootprints)" in text


def test_a_non_colliding_label_is_not_qualified():
    """Only a colliding label is touched. With the product-or-sector
    section skipped there is no repeat, so no scope-root qualifier appears
    -- the same guarantee that keeps the four packs without a repeat
    byte-identical (the `--check` gate proves that half)."""
    no_repeat = frozenset(("https://admin-shell.io/idta/CarbonFootprint/"
                           "ProductOrSectorSpecificCarbonFootprints/1/0",))
    text = g.generate(_pack(no_repeat))
    assert "(ProductCarbonFootprints)" not in text
    assert "(ProductOrSectorSpecificCarbonFootprints)" not in text
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
    assert "PcfCalculationMethod (ProductCarbonFootprints)" in by_label
    assert "PcfCalculationMethod (ProductOrSectorSpecificCarbonFootprints)" in by_label
    assert "PcfCalculationMethod" not in by_label       # bare label -> KeyError
