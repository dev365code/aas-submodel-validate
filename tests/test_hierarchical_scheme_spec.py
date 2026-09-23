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

These tests encode the *two-row* model of a recursion point, settled
against 02011 Hierarchical Structures 1.1.1 once it was vendored
(docs/divergences.md #48): the template gives the repeating child an
element of its own with a cardinality of its own -- `Node` is 1..* inside
the entry and its nested `Node` 0..* inside a `Node` -- so the child gets a
row of its own, marked `recurses` and not expanded. The one-row model these
tests held before, the outer element marked and the child dropped, lost
that second cardinality: the walk would have had to assume one.
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


def test_a_self_containing_entity_gives_its_copy_a_marked_row():
    """A Node (Entity) whose statements hold a Node of the same semanticId
    is a recursion point. The nested Node gets a row of its own, at the
    cardinality the template gives it, marked `recurses` with the repeated
    identifier so the walk re-applies the outer Node's rows to it at any
    depth; the outer row carries no marker, and the copy is not expanded,
    so the table stays finite."""
    node = {"idShort": "Node", "modelType": "Entity",
            "semanticId": _sid("urn:x:Node"),
            "qualifiers": [{"type": "SMT/Cardinality", "value": "OneToMany"}],
            "statements": [{"idShort": "Node", "modelType": "Entity",
                            "semanticId": _sid("urn:x:Node"),
                            "qualifiers": [{"type": "SMT/Cardinality",
                                            "value": "ZeroToOne"}]}]}
    row = _row(node)
    assert not row.get("recurses")
    assert row["card"] == (1, None)
    [copy] = [child for child in row["children"] if child["sid"] == "urn:x:Node"]
    assert copy.get("recurses") == "urn:x:Node"
    # The template's, and not the 0..* an assumption would have given --
    # which is why the fixture says ZeroToOne: with ZeroToMany here the
    # assertion held for a generator that read nothing.
    assert copy["card"] == (0, 1)
    assert copy["children"] == ()             # not expanded


def test_a_repeat_written_with_content_is_that_content():
    """A nested Node the template writes with an element of its own asks
    for that element there, not for what the outer Node holds; it is an
    ordinary row, expanded as written, and not a copy."""
    node = {"idShort": "Node", "modelType": "Entity", "semanticId": _sid("urn:x:Node"),
            "statements": [
                {"idShort": "Name", "modelType": "Property", "semanticId": _sid("urn:x:Name"),
                 "qualifiers": [{"type": "SMT/Cardinality", "value": "One"}]},
                {"idShort": "Node", "modelType": "Entity", "semanticId": _sid("urn:x:Node"),
                 "statements": [{"idShort": "Extra", "modelType": "Property",
                                 "semanticId": _sid("urn:x:Extra"),
                                 "qualifiers": [{"type": "SMT/Cardinality",
                                                 "value": "One"}]}]}]}
    [inner] = [child for child in _row(node)["children"] if child["sid"] == "urn:x:Node"]
    assert not inner.get("recurses")
    assert [child["sid"] for child in inner["children"]] == ["urn:x:Extra"]


def test_a_mandatory_copy_is_judged_as_optional_and_marked():
    """Every copy needing a copy of its own is more copies than any file
    has. The lower bound goes, the upper stays, and the row says why."""
    node = {"idShort": "Node", "modelType": "Entity", "semanticId": _sid("urn:x:Node"),
            "statements": [{"idShort": "Node", "modelType": "Entity",
                            "semanticId": _sid("urn:x:Node"),
                            "qualifiers": [{"type": "SMT/Cardinality", "value": "One"}]}]}
    [copy] = _row(node)["children"]
    assert copy.get("recurses") == "urn:x:Node"
    assert copy["card"] == (0, 1) and copy.get("endless") == 1


def test_the_02011_table_is_one_row_per_template_element():
    """Measured on the vendored file: eleven elements, eleven rows. The
    nested Node is the only row marked, and it is the one at 0..*."""
    from aas_submodel_validate.rules import hs_tables  # noqa: E402

    marked = [row for row in hs_tables.ROWS if row.get("recurses")]
    assert len(hs_tables.ROWS) == 11
    assert [(row["label"], row["card"]) for row in marked] == [("Node (Node)", (0, None))]
    [outer] = [row for row in hs_tables.ROWS if row["label"] == "Node (EntryNode)"]
    assert outer["card"] == (1, None) and not outer.get("recurses")


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
        [copy] = g._rows(el, "", None, [0], pack)["children"]
        assert copy.get("recurses") == "urn:x:N", kind
    # Same identifier, another kind: an Entity holding a collection that
    # wears its identifier is not holding a copy of itself.
    mixed = {"idShort": "N", "modelType": "Entity", "semanticId": _sid("urn:x:N"),
             "statements": [{"idShort": "N", "modelType": "SubmodelElementCollection",
                             "semanticId": _sid("urn:x:N")}]}
    assert all(child.get("recurses") is None
               for child in g._rows(mixed, "", None, [0], pack)["children"])
    are = {"idShort": "R", "modelType": "AnnotatedRelationshipElement",
           "semanticId": _sid("urn:x:R"),
           "value": [{"idShort": "R", "modelType": "AnnotatedRelationshipElement",
                      "semanticId": _sid("urn:x:R")}]}
    outer = g._rows(are, "", None, [0], pack)
    assert outer.get("recurses") is None
    assert all(child.get("recurses") is None for child in outer["children"])
