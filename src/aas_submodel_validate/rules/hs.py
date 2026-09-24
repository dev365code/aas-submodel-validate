"""IDTA 02011 Hierarchical Structures enabling Bills of Material: the pack.

The structural layer is generated from the vendored template, one rule
per row -- the cardinalities and semanticIds the template file itself
declares, every one of its eleven elements with `SMT/Cardinality`.

A `Node` holds `Node`s of its own identifier, to any depth: the bill of
material is a tree. The template writes that out one level down and
stops, and its nested `Node` is a row of its own at the cardinality the
template gives it -- 0..* inside a `Node`, where the outer one is 1..*
inside the entry -- marked as a copy of the element above it. The walk
gives each nested copy that element's rows, at whatever depth it sits,
so a defect five levels down is judged as one at the first
(docs/divergences.md #48).

Whether a Hierarchical Structures submodel is present is *not* here: that
question belongs to the tool rather than to this template, and it is
asked once for every template in `rules/detect.py`.

This pack is generated rows only. What that covers is real -- the
entry node and its nodes by count and kind at every depth, the three
relationships by kind, `BulkCount` and `ArcheType` by `valueType` -- and
what it does not cover is worth naming. A `RelationshipElement`'s two
ends are not read: the template gives both as
`https://admin-shell.io/SMT/General/IntentionallyEmpty`, which constrains
nothing, so whether `HasPart` points at a part, or at anything that
exists, is not checked (docs/divergences.md #56). `ArcheType` is not
checked against the three words the template's form offers. And whether
the tree the relationships draw agrees with the tree the nodes nest is a
question this pack does not ask.

It registers the near-miss lint every pack has had since 0.8.0
(`HSL1`), so an identifier one version suffix or one last segment off
is named among the findings; a drift elsewhere in an identifier is
not (docs/divergences.md #23).
"""
from __future__ import annotations

from ..registry import rule
from . import hs_tables
from .engine import analyze, install_near_miss_lint, matched_submodels

#: The template's own identity -- one authority, the generated table.
TEMPLATE_SEMANTIC_ID = hs_tables.TEMPLATE_SEMANTIC_ID


# -- the generated structural layer ------------------------------------------
#
# One registered rule per template row, each reading its slice of the
# single cached walk. The table is generated from the vendored official
# template (tools/extract_smt_rules.py); the walk lives in engine.

def _row_check(row_id: str):
    def check(ctx):
        if not matched_submodels(ctx, hs_tables):
            return  # SMT-D1's finding; empty scopes would double-report it
        yield from analyze(ctx, hs_tables)["violations"].get(row_id, ())
    return check


for _row in hs_tables.ROWS:
    rule(_row["id"], kind="template", prio="MUST",
         title="'%s' as the template declares it (%s)"
               % (_row["label"], _row["sid"] or "by structure"),
         spec="%s, SMT/Cardinality qualifier" % hs_tables.TEMPLATE_CITATION,
         fix=_row["fix"],
         # A generated row always speaks about an element inside a
         # submodel of this document, so the route is the same for every
         # one of them; a count at the top of the walk says otherwise
         # where it is produced.
         path=("document", "submodel", "element"),
         )(_row_check(_row["id"]))


#: The element whose identifier nearly matches a row, named among the
#: findings (docs/divergences.md #23).
install_near_miss_lint("HSL1", hs_tables)
