"""IDTA 02002 Contact Information: the pack.

The structural layer is generated from the vendored template, one rule
per row -- the cardinalities and semanticIds the template file itself
declares. Every one of its thirty-six elements states its cardinality
with the older `Multiplicity` qualifier and none with `SMT/Cardinality`
(docs/divergences.md #50), which is what makes it judgeable here at all.

Whether a Contact Information submodel is present is *not* here: that
question belongs to the tool rather than to this template, and it is
asked once for every template in `rules/detect.py`.

The edition is 1.0.1 because it is the current release, not because it
fixes anything here: 1.0 gives `IPCommunication` the submodel's own
identifier, 1.0.1 gives it `.../ContactInformations/IPCommunication/`, and
the published specification gives it `.../ContactInformation/IPCommunication/`
-- three spellings, no two alike. A file built to the specification
therefore matches no row at either edition, and since that collection is
`0..*` the mandatory `AddressOfAdditionalLink` beneath it is never asked
for and nothing says so (docs/divergences.md #51). 1.0.1 also carries a
space inside `TypeOfCommunication`'s identifier, so that row is dead
against a specification-conformant file and live against one that mirrors
the template.

This pack is generated rows only. What that covers is real -- cardinality,
element kind, `valueType`, and the semanticId at every level, though a
`0..*` row can only ever be proved wrong by kind and never by count -- and
what it does not cover is worth naming, because
twenty-one of the thirty-six rows are `MultiLanguageProperty`: a required
MLP carrying no language at all draws nothing structural here (the
empty-value check is a Property's, docs/divergences.md #40), and neither
an email, a telephone number, a URL, a time zone nor a language code is
checked for shape. `docs/scope.md` says so too.

It registers the near-miss lint every pack has had since 0.8.0
(`CIL1`), so an identifier one version suffix or one last segment off
is named among the findings; a drift elsewhere in an identifier is
not (docs/divergences.md #23).
"""
from __future__ import annotations

from ..registry import rule
from . import contact_tables
from .engine import analyze, install_near_miss_lint, matched_submodels

#: The template's own identity -- one authority, the generated table.
TEMPLATE_SEMANTIC_ID = contact_tables.TEMPLATE_SEMANTIC_ID


# -- the generated structural layer ------------------------------------------
#
# One registered rule per template row, each reading its slice of the
# single cached walk. The table is generated from the vendored official
# template (tools/extract_smt_rules.py); the walk lives in engine.

def _row_check(row_id: str):
    def check(ctx):
        if not matched_submodels(ctx, contact_tables):
            return  # SMT-D1's finding; empty scopes would double-report it
        yield from analyze(ctx, contact_tables)["violations"].get(row_id, ())
    return check


for _row in contact_tables.ROWS:
    rule(_row["id"], kind="template", prio="MUST",
         title="'%s' as the template declares it (%s)"
               % (_row["label"], _row["sid"] or "by structure"),
         spec="%s, Multiplicity qualifier" % contact_tables.TEMPLATE_CITATION,
         fix=_row["fix"],
         # A generated row always speaks about an element inside a
         # submodel of this document, so the route is the same for
         # every one of them. The grade is not: one row reports a
         # count, a kind, a list's item type, a valueType and a
         # present element with no value, and those are not equally
         # repairable, so each is graded where it is produced.
         path=("document", "submodel", "element"),
         )(_row_check(_row["id"]))


#: The element whose identifier nearly matches a row, named among the
#: findings (docs/divergences.md #23).
install_near_miss_lint("CIL1", contact_tables)
