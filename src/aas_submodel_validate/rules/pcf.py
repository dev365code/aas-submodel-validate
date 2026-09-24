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
apart by qualifying a repeated label with the shortest ancestor suffix
that distinguishes the copies, so each row is judged in its own place
(docs/divergences.md #48). The one part left
unjudged is the open-content `ArbitraryContent` placeholder inside
`PcfInformation`, which stands for content the template does not define
-- the same treatment 02006 gives its Arbitrary* elements.
"""
from __future__ import annotations

from ..registry import rule
from . import pcf_tables
from .engine import analyze, install_file_rule, install_near_miss_lint, matched_submodels

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
         fix=_row["fix"],
         # A generated row always speaks about an element inside a
         # submodel of this document, so the route is the same for
         # every one of them. The grade is not: one row reports a
         # count, a kind, a list's item type, a valueType and a
         # present element with no value, and those are not equally
         # repairable, so each is graded where it is produced.
         path=("document", "submodel", "element"),
         )(_row_check(_row["id"]))


# The one question in this file that is not a reading of this
# template: whether the files its File rows name are in the package.
# The body is shared and was called from 02004's family alone, so a
# package of this kind naming parts it does not hold was judged clean.
# `ExplanatoryStatement` only. The other File row this template declares
# is `PcfRuleOnlineReference`, which the vendored template describes as an
# "Online PCF calculation methodology reference" -- the published method a
# footprint was calculated by, which lives where its publisher put it. Asked
# whether it is in the container, this rule faulted conformant files for
# naming it the way such a reference is written (`docs/divergences.md` #55).
install_file_rule("PCF-D1", pcf_tables, pcf_tables.TEMPLATE_CITATION,
                  only=("ExplanatoryStatement",))


#: The element whose identifier nearly matches a row, named among the
#: findings (docs/divergences.md #23).
install_near_miss_lint("PCFL1", pcf_tables)
