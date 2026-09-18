"""IDTA 02023 Carbon Footprint: the pack.

The structural layer is generated from the vendored template, one rule
per row -- the cardinalities and semanticIds the template file itself
declares.

Whether a Carbon Footprint submodel is present at all is *not* here:
that question belongs to the tool rather than to this template, and it
is asked once for every template in `rules/detect.py`.

Both the core `ProductCarbonFootprints` section and the
`ProductOrSectorSpecificCarbonFootprints` section are generated. The
latter repeats the named `PcfCalculationMethods` sub-structure the former
carries (same semanticId, a second scope); the generator tells the two
apart by qualifying a repeated label with its scope-root, so each row is
judged in its own place (docs/divergences.md). The one part left
unjudged is the open-content `ArbitraryContent` placeholder inside
`PcfInformation`, which stands for content the template does not define
-- the same treatment 02006 gives its Arbitrary* elements.
"""
from __future__ import annotations

from ..registry import rule
from . import pcf_tables
from .engine import analyze, matched_submodels

#: The template's own identity -- one authority, the generated table.
TEMPLATE_SEMANTIC_ID = pcf_tables.TEMPLATE_SEMANTIC_ID


# -- the generated structural layer ------------------------------------------
#
# One registered rule per template row, each reading its slice of the
# single cached walk. The table is generated from the vendored official
# template (tools/extract_smt_rules.py); the walk lives in engine.

def _row_check(row_id: str):
    def check(ctx):
        if not matched_submodels(ctx, pcf_tables):
            return  # SMT-D1's finding; empty scopes would double-report it
        yield from analyze(ctx, pcf_tables)["violations"].get(row_id, ())
    return check


for _row in pcf_tables.ROWS:
    rule(_row["id"], kind="template", prio="MUST",
         title="'%s' as the template declares it (%s)"
               % (_row["label"], _row["sid"] or "by structure"),
         spec="%s, SMT/Cardinality qualifier" % pcf_tables.TEMPLATE_CITATION,
         fix=_row["fix"])(_row_check(_row["id"]))
