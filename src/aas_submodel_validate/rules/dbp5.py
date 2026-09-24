"""IDTA 02035-5 Product Condition, the Digital Battery Passport's part 5:
the pack.

The structural layer is generated from the vendored template, one rule
per row -- the cardinalities and semanticIds the template file itself
declares, each with the `SMT/Cardinality` qualifier.

Whether a Product Condition submodel is present is *not* here: that
question belongs to the tool rather than to this template, and it is
asked once for every template in `rules/detect.py`.

Every identifier in the template is a SAMM URN,
`urn:samm:io.admin-shell.idta.batterypass.product_condition:1.0.2#...`,
with an ECLASS identifier beside most of them as a supplemental, and the
version inside it moved with each release: 1.0 wrote `1.0.0`, 1.0.1 a
mix of `1.0.0` and `1.0.1`, 1.0.2 `1.0.2` throughout (its Annex B says
so). A submodel written to an earlier release matches no row, and
SMT-D1 says which template it means and that only the version differs;
an element of an earlier release inside a 1.0.2 submodel is a near miss
(docs/divergences.md #58).

Four collections are mandatory -- `StateOfCharge`, `NumberOfFullCycles`,
`InformationOnAccidents` and `TemperatureInformation` -- and each of the
twelve dynamic ones holds a `LastUpdate` under one shared identifier,
which the table tells apart by its parent's name.

This pack is generated rows only: cardinality, element kind, `valueType`
and the semanticId at every level. No value is checked for what it says
-- a state of charge above 100 or a `LastUpdate` in the future draws
nothing here -- and the battery-data layer (`BAT-R8`) reads what it
reads of this part on its own terms. `docs/scope.md` says so too.

It registers the near-miss lint every pack has (`DBP5L1`).
"""
from __future__ import annotations

from ..registry import rule
from . import dbp5_tables
from .engine import analyze, install_near_miss_lint, matched_submodels

#: The template's own identity -- one authority, the generated table.
TEMPLATE_SEMANTIC_ID = dbp5_tables.TEMPLATE_SEMANTIC_ID


# -- the generated structural layer ------------------------------------------
#
# One registered rule per template row, each reading its slice of the
# single cached walk. The table is generated from the vendored official
# template (tools/extract_smt_rules.py); the walk lives in engine.

def _row_check(row_id: str):
    def check(ctx):
        if not matched_submodels(ctx, dbp5_tables):
            return  # SMT-D1's finding; empty scopes would double-report it
        yield from analyze(ctx, dbp5_tables)["violations"].get(row_id, ())
    return check


for _row in dbp5_tables.ROWS:
    rule(_row["id"], kind="template", prio="MUST",
         title="'%s' as the template declares it (%s)"
               % (_row["label"], _row["sid"] or "by structure"),
         spec="%s, SMT/Cardinality qualifier" % dbp5_tables.TEMPLATE_CITATION,
         fix=_row["fix"],
         # A generated row always speaks about an element inside a
         # submodel of this document, so the route is the same for every
         # one of them; a count at the top of the walk says otherwise
         # where it is produced.
         path=("document", "submodel", "element"),
         )(_row_check(_row["id"]))


#: The element whose identifier nearly matches a row, named among the
#: findings (docs/divergences.md #23).
install_near_miss_lint("DBP5L1", dbp5_tables)
