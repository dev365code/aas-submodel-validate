"""IDTA 02006 Digital Nameplate: the pack.

The structural layer is generated from the vendored template, one rule
per row -- the cardinalities and semanticIds the template file itself
declares.

Whether a Nameplate submodel is present at all is *not* here: that
question belongs to the tool rather than to this template, and it is
asked once for every template in `rules/detect.py`.
"""
from __future__ import annotations

from ..registry import rule
from . import dn_tables
from .engine import analyze, matched_submodels

#: The template's own identity -- one authority, the generated table.
TEMPLATE_SEMANTIC_ID = dn_tables.TEMPLATE_SEMANTIC_ID


# -- the generated structural layer ------------------------------------------
#
# One registered rule per template row, each reading its slice of the
# single cached walk. The table is generated from the vendored official
# template (tools/extract_smt_rules.py); the walk lives in engine.

def _row_check(row_id: str):
    def check(ctx):
        if not matched_submodels(ctx, dn_tables):
            return  # SMT-D1's finding; empty scopes would double-report it
        yield from analyze(ctx, dn_tables)["violations"].get(row_id, ())
    return check


for _row in dn_tables.ROWS:
    rule(_row["id"], kind="template", prio="MUST",
         title="'%s' as the template declares it (%s)"
               % (_row["label"], _row["sid"] or "by structure"),
         spec="%s, SMT/Cardinality qualifier" % dn_tables.TEMPLATE_CITATION,
         fix=_row["fix"])(_row_check(_row["id"]))
