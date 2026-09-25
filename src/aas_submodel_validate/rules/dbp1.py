"""IDTA 02035-1 Digital Nameplate, the Digital Battery Passport's part 1:
the pack.

The structural layer is generated from the vendored template, one rule
per row -- the cardinalities and semanticIds the template file itself
declares. Twenty-one of its twenty-two elements state their cardinality
with the `SMT/Cardinality` qualifier and `ManufacturerIdentifier` with a
bare `Cardinality`, which the generator reads as the same
(docs/divergences.md #50).

Whether a Battery Nameplate submodel is present is *not* here: that
question belongs to the tool rather than to this template, and it is
asked once for every template in `rules/detect.py`.

Its elements' own identifiers mix four schemes: IEC CDD for twelve, each
with an ECLASS and a SAMM identifier beside it as supplementals; an IRI
for `UniqueFacilityIdentifier` and for `AddressInformation`, which is
02002's collection dropped in and written empty, so nothing inside it is
asked here, though the specification's §3.2 requires four address
fields in it; ECLASS for `LifeCycleStage`; and SAMM URNs for the rest --
four in the battery passport's own namespace, `ManufacturerIdentifier`
in the technical data part's, and the two document lists' items in the
Handover Documentation one, an identifier the specification never
prints (docs/divergences.md #59).

This pack is generated rows, and one question every pack with a File
row asks: whether the file a marking names is in the package
(`DBP1-D1`). The product URI is not checked for
shape, as the Digital Nameplate's is; no date, identifier, life-cycle
stage or marking is checked for what it says; and the battery-data layer
(`BAT-R8`) reads what it reads of this part on its own terms.
`docs/scope.md` says so too.

It registers the near-miss lint every pack has (`DBP1L1`).
"""
from __future__ import annotations

from ..registry import rule
from ..tablegen import qualifier_said
from . import dbp1_tables
from .engine import analyze, install_file_rule, install_near_miss_lint, matched_submodels

#: The template's own identity -- one authority, the generated table.
TEMPLATE_SEMANTIC_ID = dbp1_tables.TEMPLATE_SEMANTIC_ID


# -- the generated structural layer ------------------------------------------
#
# One registered rule per template row, each reading its slice of the
# single cached walk. The table is generated from the vendored official
# template (tools/extract_smt_rules.py); the walk lives in engine.

def _row_check(row_id: str):
    def check(ctx):
        if not matched_submodels(ctx, dbp1_tables):
            return  # SMT-D1's finding; empty scopes would double-report it
        yield from analyze(ctx, dbp1_tables)["violations"].get(row_id, ())
    return check


for _row in dbp1_tables.ROWS:
    rule(_row["id"], kind="template", prio="MUST",
         title="'%s' as the template declares it (%s)"
               % (_row["label"], _row["sid"] or "by structure"),
         spec="%s, %s" % (dbp1_tables.TEMPLATE_CITATION, qualifier_said(_row)),
         fix=_row["fix"],
         # A generated row always speaks about an element inside a
         # submodel of this document, so the route is the same for every
         # one of them; a count at the top of the walk says otherwise
         # where it is produced.
         path=("document", "submodel", "element"),
         )(_row_check(_row["id"]))


# The one question here that is not a reading of this template: whether
# the file a marking names is in the package, asked as it is of every pack
# with a File row (`MarkingFile`, as 02006's).
install_file_rule("DBP1-D1", dbp1_tables, dbp1_tables.TEMPLATE_CITATION)


#: The element whose identifier nearly matches a row, named among the
#: findings (docs/divergences.md #23).
install_near_miss_lint("DBP1L1", dbp1_tables)
