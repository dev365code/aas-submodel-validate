"""IDTA 02003 Technical Data: the generated structural layer.

One registered rule per template row, each reading its slice of a walk
that runs once for this table. The engine is the same one 02004 uses;
only the table differs, which is the whole point of generating tables
rather than writing rules.

Whether a Technical Data submodel is present at all belongs to
`rules/detect.py` — that question is the tool's, not this template's.

What a template file cannot say about 02003 is not here yet: dates that
are dates, files that exist in the container, references that resolve.
Those arrive with their own fixtures.
"""
from __future__ import annotations

from ..registry import rule
from . import td_tables
from .hd_engine import analyze, matched_submodels


def _row_check(row_id: str):
    def check(ctx):
        if not matched_submodels(ctx, td_tables):
            return  # SMT-D1's finding; empty scopes would double-report it
        yield from analyze(ctx, td_tables)["violations"].get(row_id, ())
    return check


for _row in td_tables.ROWS:
    rule(_row["id"], kind="template", prio="MUST",
         title="'%s' as the template declares it (%s)"
               % (_row["label"], _row["sid"] or "by structure"),
         # The four unnamed list items carry no qualifier at all; the
         # PDF's element tables are what give them 0..*.
         spec="IDTA 02003-2-0-1 template, SMT/Cardinality qualifier "
              "(unnamed list items: 0..* per the PDF's element tables)",
         fix=_row["fix"])(_row_check(_row["id"]))
