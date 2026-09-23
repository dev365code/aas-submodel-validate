"""Executable spec for the hierarchical-structures scheme (02011).

Two behaviours the generator gained with the scheme, each proved on a
synthetic structure via `_rows`:

* descending an Entity's `statements` -- an Entity holds its submodel
  elements there, not in `value` (aas-core3), so without this an Entity's
  rows are never generated and every instance of it looks empty;
* marking a self-containing element -- an Entity (or SMC) whose descendant
  repeats its own semanticId -- as a recursion point, rather than
  expanding it forever, so the walk can re-apply its rows at any depth.

Written failing-first and kept as the scheme's regression guards, with
the #1 guard below: the generator must not mistake a `SubmodelElementList`
and its item -- which share one identifier by design (#39) -- for
self-containment.

These tests encode the *one-row* model of a recursion point: the element
whose own child repeats its semanticId carries the marker, and that child
is left unexpanded. The design's alternative -- two rows, an entry edge at
the outer cardinality and a recursion edge at `0..*`, with the marker on
the inner -- is not settled, because no template that recurses is vendored
and the two models cannot be told apart without one. When 02011
Hierarchical Structures is vendored, that model is settled against the real
file first, the basis recorded in docs/divergences.md #48, and these tests
rewritten to match whichever model wins.
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


def _sid(value):
    return {"type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": value}]}


def _row(element):
    pack = {"prefix": "X-E", "item_names": {}, "example_types": (),
            "skip_sids": frozenset()}
    return g._rows(element, "", None, [0], pack)


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


def test_a_self_containing_entity_is_marked_recurses():
    """A Node (Entity) whose statements hold a Node of the same semanticId
    is a recursion point: its row must carry a `recurses` marker naming the
    repeated identifier, so the walk re-applies the Node rows at any depth
    rather than the table expanding one level and stopping. The repeating
    child is left unexpanded, so the row's children do not carry it."""
    node = {"idShort": "Node", "modelType": "Entity",
            "semanticId": _sid("urn:x:Node"),
            "qualifiers": [{"type": "SMT/Cardinality", "value": "OneToMany"}],
            "statements": [{"idShort": "Node", "modelType": "Entity",
                            "semanticId": _sid("urn:x:Node"),
                            "qualifiers": [{"type": "SMT/Cardinality",
                                            "value": "ZeroToMany"}]}]}
    row = _row(node)
    assert row.get("recurses") == "urn:x:Node"
    # the repeating child is not expanded into a row
    assert all(child["label"] != "Node" for child in row["children"])


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


def test_02004_entity_is_the_consistency_case_for_statements_descent():
    """The 02004 guard, and the design's own limit (docs/divergences.md
    #48): 02004's only Entity (EntityForDocumentation) declares no
    statements in the template, so statements-descent finds nothing there.
    02004 proves the change is *consistent* -- its table stays byte-frozen
    and every corpus verdict is unmoved -- but not that statements-descent
    is *correct*, which needs a template whose Entity has statements
    (02011, not yet vendored). This guards the consistency half: the Entity
    row is present, holds no children, and is not a recursion point."""
    from aas_submodel_validate.rules import hd_tables  # noqa: E402

    entities = []

    def walk(rows):
        for row in rows:
            if row["kind"] == "Entity":
                entities.append(row)
            walk(row["children"])
    walk(hd_tables.TREE)

    assert len(entities) == 1, "02004's Entity count moved: %d" % len(entities)
    entity = entities[0]
    assert entity["label"] == "EntityForDocumentation"
    assert entity["children"] == ()          # template declares no statements
    assert not entity.get("recurses")        # not self-containing


def test_only_entity_and_collection_self_containment_is_marked():
    """The recursion detector marks an Entity or SubmodelElementCollection
    that repeats its own semanticId -- the shapes the standard nests -- and
    nothing else, even a same-kind same-sid pair reached through `value` on
    another element kind. A real template never nests a RelationshipElement's
    own identifier through `value` (its children live in annotations, which
    the generator does not descend), but the arbitrary-template path must not
    mark one if it did."""
    pack = {"prefix": "X", "item_names": {}, "example_types": (),
            "skip_sids": frozenset()}
    for kind in ("Entity", "SubmodelElementCollection"):
        container = "statements" if kind == "Entity" else "value"
        el = {"idShort": "N", "modelType": kind, "semanticId": _sid("urn:x:N"),
              container: [{"idShort": "N", "modelType": kind,
                           "semanticId": _sid("urn:x:N")}]}
        assert g._rows(el, "", None, [0], pack).get("recurses") == "urn:x:N", kind
    are = {"idShort": "R", "modelType": "AnnotatedRelationshipElement",
           "semanticId": _sid("urn:x:R"),
           "value": [{"idShort": "R", "modelType": "AnnotatedRelationshipElement",
                      "semanticId": _sid("urn:x:R")}]}
    assert g._rows(are, "", None, [0], pack).get("recurses") is None
