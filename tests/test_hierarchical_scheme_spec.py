"""FAILING FIRST -- executable spec for the hierarchical-structures scheme
unit (02011), turned green by the generator and engine changes next.

Two behaviours the generator does not have today, each proved red via
`_rows` on a synthetic structure and marked xfail(strict) so the tree
stays green until the code lands:

* descending an Entity's `statements` -- an Entity holds its submodel
  elements there, not in `value` (aas-core3), so without this an Entity's
  rows are never generated and every instance of it looks empty;
* marking a self-containing element -- an Entity (or SMC) whose descendant
  repeats its own semanticId -- as a recursion point, rather than
  expanding it forever, so the walk can re-apply its rows at any depth.

Removing an xfail is that half of the scheme unit's done-signal.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import extract_smt_rules as g  # noqa: E402


def _sid(value):
    return {"type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": value}]}


def _row(element):
    pack = {"prefix": "X-E", "item_names": {}, "example_types": (),
            "skip_sids": frozenset()}
    return g._rows(element, "", None, [0], pack)


@pytest.mark.xfail(strict=True, reason="Entity statements-descent is part of "
                   "the hierarchical scheme unit; the generator descends "
                   "`value` only today")
def test_the_generator_descends_an_entitys_statements():
    """An Entity holds its submodel elements in `statements`, not `value`.
    The generator must descend them, or EntryNode's mandatory Node row is
    never emitted and every 02011 instance would look empty."""
    entry = {"idShort": "EntryNode", "modelType": "Entity",
             "semanticId": _sid("urn:x:EntryNode"),
             "statements": [{"idShort": "Node", "modelType": "Entity",
                             "semanticId": _sid("urn:x:Node"),
                             "qualifiers": [{"type": "SMT/Cardinality",
                                             "value": "OneToMany"}]}]}
    assert any(child["label"] == "Node" for child in _row(entry)["children"])


@pytest.mark.xfail(strict=True, reason="recursion marking is part of the "
                   "hierarchical scheme unit; the generator does not detect "
                   "self-containment today")
def test_a_self_containing_entity_is_marked_recurses():
    """A Node (Entity) whose statements hold a Node of the same semanticId
    is a recursion point: its row must carry a `recurses` marker naming the
    repeated identifier, so the walk re-applies the Node rows at any depth
    rather than the table expanding one level and stopping."""
    node = {"idShort": "Node", "modelType": "Entity",
            "semanticId": _sid("urn:x:Node"),
            "qualifiers": [{"type": "SMT/Cardinality", "value": "OneToMany"}],
            "statements": [{"idShort": "Node", "modelType": "Entity",
                            "semanticId": _sid("urn:x:Node"),
                            "qualifiers": [{"type": "SMT/Cardinality",
                                            "value": "ZeroToMany"}]}]}
    assert _row(node).get("recurses") == "urn:x:Node"


def test_shared_identifier_list_rows_are_never_marked_recurses():
    """The #1 guard for the recursion detector: a `SubmodelElementList`
    and its item share one identifier (docs/divergences.md #39) -- 02004
    has five such pairs (Language/LanguageCode, DigitalFiles/DigitalFile,
    and three ReferenceElement lists), 02035-2 two -- but that is a list
    with one item kind, not self-containment. If the detector marked them
    `recurses` it would rewrite their rows and break the byte-frozen packs.
    They carry no marker today and must carry none once the detector lands.
    """
    from aas_submodel_validate.rules import dbp_tables, hd_tables  # noqa: E402

    def rows_sharing_parent_sid(tables):
        found = []

        def walk(rows, parent):
            for row in rows:
                if parent is not None and row["sid"] and row["sid"] == parent["sid"]:
                    found.append(row)
                walk(row["children"], row)
        walk(tables.TREE, None)
        return found

    shared = rows_sharing_parent_sid(hd_tables) + rows_sharing_parent_sid(dbp_tables)
    assert len(shared) == 7, "the #39 shared-identifier rows moved: %d" % len(shared)
    for row in shared:
        assert not row.get("recurses"), (
            "%s shares its parent's identifier (a list and its item, #39); it "
            "is not a recursion point and must not be marked" % row["label"])
