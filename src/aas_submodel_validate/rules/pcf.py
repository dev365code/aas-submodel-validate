"""IDTA 02023 Carbon Footprint: the pack.

The structural layer is generated from the vendored template, one rule
per row -- the cardinalities and semanticIds the template file itself
declares.

Whether a Carbon Footprint submodel is present at all is *not* here:
that question belongs to the tool rather than to this template, and it
is asked once for every template in `rules/detect.py`.

Only the core `ProductCarbonFootprints` section is generated. The
optional `ProductOrSectorSpecificCarbonFootprints` section repeats the
named `PcfCalculationMethods` sub-structure that
`ProductCarbonFootprints` already carries (same semanticId, a second
scope), and neither the generator's one-label-per-row namespace nor the
per-scope walk can emit two identically-labelled rows for one repeated
structure yet -- so that section is left unjudged for now
(docs/divergences.md). `PCF-D1` below makes that gap visible rather than
silent.
"""
from __future__ import annotations

from ..model import Violation
from ..registry import rule
from ..semantics import candidate_values
from . import pcf_tables
from .engine import analyze, matched_submodels

#: The template's own identity -- one authority, the generated table.
TEMPLATE_SEMANTIC_ID = pcf_tables.TEMPLATE_SEMANTIC_ID

#: The one top-level section this pack does not generate rules from -- the
#: repeated sub-structure the generator cannot place in two scopes yet.
#: `PCF-D1` reads it so a file that carries it is not passed in silence.
_UNJUDGED_SECTION_SID = ("https://admin-shell.io/idta/CarbonFootprint/"
                         "ProductOrSectorSpecificCarbonFootprints/1/0")


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


# -- the honest-coverage note ------------------------------------------------
#
# The one thing a partial pack must not do is let the part it does not
# judge come back clean. This says, at info, that the section is present
# and unjudged -- without faulting the file, because the gap is the
# tool's, not the document's.

@rule("PCF-D1", kind="template", prio="MAY",
      title="the ProductOrSectorSpecificCarbonFootprints section is not judged",
      spec="IDTA 02023 1.0 template; docs/divergences.md",
      fix="This tool version judges the core ProductCarbonFootprints "
          "section only. ProductOrSectorSpecificCarbonFootprints repeats a "
          "sub-structure the generator cannot yet place in two scopes, so it "
          "is left unjudged -- nothing here is a verdict on that section. "
          "Judge it by hand until a later version reads it.")
def pcf_d1_product_or_sector_specific_is_not_judged(ctx):
    """Silence would read as a pass: a file carrying the skipped section
    would come back clean though nothing looked at it. Reported at info,
    once per section, on the section's own semanticId."""
    for submodel in matched_submodels(ctx, pcf_tables):
        for element in submodel.submodel_elements or []:
            if _UNJUDGED_SECTION_SID in candidate_values(
                    getattr(element, "semantic_id", None)):
                yield Violation(
                    "ProductOrSectorSpecificCarbonFootprints is present but "
                    "this tool version does not judge it",
                    subject=getattr(element, "id_short", None)
                    or "ProductOrSectorSpecificCarbonFootprints")
