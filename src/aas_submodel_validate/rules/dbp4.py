"""IDTA 02035-4 Technical Data, the Digital Battery Passport's part 4: the
pack.

The structural layer is generated from the vendored template, one rule
per row -- the cardinalities and semanticIds the template file itself
declares. Forty-one of its forty-six elements state their cardinality
with a bare `Cardinality` qualifier and four with `SMT/Cardinality`,
which the generator reads as the same (docs/divergences.md #50);
`WarrantyInformation` states none, and reads 0..*.

Whether a Battery Technical Data submodel is present is *not* here: that
question belongs to the tool rather than to this template, and it is
asked once for every template in `rules/detect.py`. The submodel carries
02003's own identifier among its supplementals, and is matched by its
own (docs/divergences.md #28).

Its elements' own identifiers are ECLASS IRDIs and SAMM URNs in the part's
own namespace, whose version is 1.0.0 for most and 1.0.1 for the warranty
the 1.0.1 release added (docs/divergences.md #60).

This pack is generated rows, and one question every pack with a File row
asks: whether the file a logo or a product image names is in the package
(`DBP4-D1`). No value is checked for what it says -- not the battery
category, not a voltage -- and the battery-data layer (`BAT-R8`), which
reads the battery category from this part, reads it on its own terms.
`docs/scope.md` says so too.

It registers the near-miss lint every pack has (`DBP4L1`).
"""
from __future__ import annotations

from ..registry import rule
from . import dbp4_tables
from .engine import analyze, install_file_rule, install_near_miss_lint, matched_submodels

#: The template's own identity -- one authority, the generated table.
TEMPLATE_SEMANTIC_ID = dbp4_tables.TEMPLATE_SEMANTIC_ID


# -- the generated structural layer ------------------------------------------
#
# One registered rule per template row, each reading its slice of the
# single cached walk. The table is generated from the vendored official
# template (tools/extract_smt_rules.py); the walk lives in engine.

def _row_check(row_id: str):
    def check(ctx):
        if not matched_submodels(ctx, dbp4_tables):
            return  # SMT-D1's finding; empty scopes would double-report it
        yield from analyze(ctx, dbp4_tables)["violations"].get(row_id, ())
    return check


for _row in dbp4_tables.ROWS:
    rule(_row["id"], kind="template", prio="MUST",
         title="'%s' as the template declares it (%s)"
               % (_row["label"], _row["sid"] or "by structure"),
         spec="%s, SMT/Cardinality qualifier" % dbp4_tables.TEMPLATE_CITATION,
         fix=_row["fix"],
         # A generated row always speaks about an element inside a
         # submodel of this document, so the route is the same for every
         # one of them; a count at the top of the walk says otherwise
         # where it is produced.
         path=("document", "submodel", "element"),
         )(_row_check(_row["id"]))


# The one question here that is not a reading of this template: whether
# the file a logo or a product image names is in the package, asked as it
# is of every pack with a File row.
install_file_rule("DBP4-D1", dbp4_tables, dbp4_tables.TEMPLATE_CITATION)


#: The element whose identifier nearly matches a row, named among the
#: findings (docs/divergences.md #23).
install_near_miss_lint("DBP4L1", dbp4_tables)
