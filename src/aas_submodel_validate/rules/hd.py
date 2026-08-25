"""IDTA 02004 Handover Documentation: the pack.

The structural layer is generated from the vendored template, one rule
per row. The hand-written layer -- what a template file cannot express,
from the mandatory VDI 2770 classification to files that exist in the
container -- is installed from `handover.py`, which a second template
sharing this submodel identifier installs from too.

Whether a Handover submodel is present at all is *not* here: that
question belongs to the tool rather than to this template, and it is
asked once for every template in `rules/detect.py`.
"""
from __future__ import annotations

from ..registry import rule
from . import handover, hd_tables
from .engine import analyze, matched_submodels

#: The template's own identity — one authority, the generated table.
TEMPLATE_SEMANTIC_ID = hd_tables.TEMPLATE_SEMANTIC_ID


# -- the generated structural layer ------------------------------------------
#
# One registered rule per template row, each reading its slice of the
# single cached walk. The table is generated from the vendored official
# template (tools/extract_smt_rules.py); the walk lives in engine.

def _row_check(row_id: str):
    def check(ctx):
        if not matched_submodels(ctx, hd_tables):
            return  # SMT-D1's finding; empty scopes would double-report it
        yield from analyze(ctx, hd_tables)["violations"].get(row_id, ())
    return check


for _row in hd_tables.ROWS:
    rule(_row["id"], kind="template", prio="MUST",
         title="'%s' as the template declares it (%s)"
               % (_row["label"], _row["sid"] or "by structure"),
         spec="IDTA 02004-2-0-1 template, SMT/Cardinality qualifier",
         fix=_row["fix"])(_row_check(_row["id"]))


# -- the hand rules: what a template file cannot express ---------------------
#
# The bodies live in `handover.py`, because IDTA 02035-2 publishes this
# same submodel identifier over the same elements and asks the same
# unwritten questions of them (docs/divergences.md #26). Installing them
# here is what says 02004 answers all fourteen: a table that could not
# would be refused at import rather than crash on a missing label.

handover.install("HD", hd_tables)
