"""IDTA 02035-7 Circularity, the Digital Battery Passport's part 7: the
pack.

The structural layer is generated from the vendored template, one rule
per row -- the cardinalities and semanticIds the template file itself
declares. All thirty-seven of its elements state their cardinality with
the `SMT/Cardinality` qualifier.

Whether a Battery Circularity submodel is present is *not* here: that
question belongs to the tool rather than to this template, and it is
asked once for every template in `rules/detect.py`.

Every one of its identifiers is a SAMM URN: its own namespace's for the
circularity elements, the Handover Documentation one for the document
identifiers its five document lists hold, and a contact information
namespace for a spare-part supplier's name and addresses
(docs/divergences.md #61).

This pack is generated rows and nothing else: the template declares no
File row, so there is no file for a package to hold, and no value is
checked for what it says. The battery-data layer does not read this part.
`docs/scope.md` says so too.

It registers the near-miss lint every pack has (`DBP7L1`).
"""
from __future__ import annotations

from ..registry import rule
from . import dbp7_tables
from .engine import analyze, install_near_miss_lint, matched_submodels

#: The template's own identity -- one authority, the generated table.
TEMPLATE_SEMANTIC_ID = dbp7_tables.TEMPLATE_SEMANTIC_ID


# -- the generated structural layer ------------------------------------------
#
# One registered rule per template row, each reading its slice of the
# single cached walk. The table is generated from the vendored official
# template (tools/extract_smt_rules.py); the walk lives in engine.

def _row_check(row_id: str):
    def check(ctx):
        if not matched_submodels(ctx, dbp7_tables):
            return  # SMT-D1's finding; empty scopes would double-report it
        yield from analyze(ctx, dbp7_tables)["violations"].get(row_id, ())
    return check


for _row in dbp7_tables.ROWS:
    rule(_row["id"], kind="template", prio="MUST",
         title="'%s' as the template declares it (%s)"
               % (_row["label"], _row["sid"] or "by structure"),
         spec="%s, SMT/Cardinality qualifier" % dbp7_tables.TEMPLATE_CITATION,
         fix=_row["fix"],
         # A generated row always speaks about an element inside a
         # submodel of this document, so the route is the same for every
         # one of them; a count at the top of the walk says otherwise
         # where it is produced.
         path=("document", "submodel", "element"),
         )(_row_check(_row["id"]))


#: The element whose identifier nearly matches a row, named among the
#: findings (docs/divergences.md #23).
install_near_miss_lint("DBP7L1", dbp7_tables)
