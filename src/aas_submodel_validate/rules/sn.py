"""IDTA 02007 Software Nameplate: the pack.

The structural layer is generated from the vendored template, one rule
per row -- the cardinalities and semanticIds the template file itself
declares. Every one of its seventy-three elements states its cardinality
with the older `Multiplicity` qualifier and none with `SMT/Cardinality`
(docs/divergences.md #50).

Whether a Software Nameplate submodel is present is *not* here: that
question belongs to the tool rather than to this template, and it is
asked once for every template in `rules/detect.py`.

The template's two collections, one for the software as a type and one
for an installed instance, are both 0..1, so every one of its fourteen
mandatory elements sits beneath an optional collection: a submodel
holding neither draws nothing here.

The rows are the template's, and in several places the template and the
specification beside it disagree (docs/divergences.md #57). The two
collections' own identifiers carry a `SoftwareNameplate/` segment the
specification's tables leave out, so a file spelling them as the
specification does has neither collection examined -- which the run says
in `scopeNotExamined`. `ConfigurationURI` carries the identifier of the
`ConfigurationPath` it sits in, so a file giving it the identifier the
specification prints draws an error for a missing `ConfigurationURI`.
Where the specification's diagram and its tables disagree -- whether
`InstallationDate` is mandatory, how many `InventoryTag`s there may be,
whether `ConfigurationType` is an integer -- the template sides with the
diagram and so does this pack. `Contact` is 02002's `ContactInformation`
copied in, carrying 02002's two identifier defects with it
(docs/divergences.md #51).

This pack is generated rows only. What that covers is real -- cardinality,
element kind, `valueType`, and the semanticId at every level, though a
`0..*` row can only ever be proved wrong by kind and never by count -- and
what it does not cover is worth naming: twenty-nine of the seventy-three
rows are `MultiLanguageProperty`, and a required one carrying no language
at all draws nothing structural here (docs/divergences.md #40); the
product URI is not checked for shape, as the Digital Nameplate's is; and
no version, checksum, date or path is checked for what it says.
`docs/scope.md` says so too.

Like the other generated-only packs it registers no near-miss lint, so a
drifted identifier here can take rules out of the run with nothing
naming the drift that did it (docs/divergences.md #23).
"""
from __future__ import annotations

from ..registry import rule
from . import sn_tables
from .engine import analyze, matched_submodels

#: The template's own identity -- one authority, the generated table.
TEMPLATE_SEMANTIC_ID = sn_tables.TEMPLATE_SEMANTIC_ID


# -- the generated structural layer ------------------------------------------
#
# One registered rule per template row, each reading its slice of the
# single cached walk. The table is generated from the vendored official
# template (tools/extract_smt_rules.py); the walk lives in engine.

def _row_check(row_id: str):
    def check(ctx):
        if not matched_submodels(ctx, sn_tables):
            return  # SMT-D1's finding; empty scopes would double-report it
        yield from analyze(ctx, sn_tables)["violations"].get(row_id, ())
    return check


for _row in sn_tables.ROWS:
    rule(_row["id"], kind="template", prio="MUST",
         title="'%s' as the template declares it (%s)"
               % (_row["label"], _row["sid"] or "by structure"),
         spec="%s, Multiplicity qualifier" % sn_tables.TEMPLATE_CITATION,
         fix=_row["fix"],
         # A generated row always speaks about an element inside a
         # submodel of this document, so the route is the same for every
         # one of them; a count at the top of the walk says otherwise
         # where it is produced.
         path=("document", "submodel", "element"),
         )(_row_check(_row["id"]))
