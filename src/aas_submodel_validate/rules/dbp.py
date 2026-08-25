"""IDTA 02035-2, the Digital Battery Passport's Handover Documentation.

A second published template answering to IDTA 02004's submodel
semanticId, over twenty-two of that template's thirty-eight rows, with
two of them relaxed and none made stricter (docs/divergences.md #26).
Because the identifier cannot say which of the two a file means, which
one answers is decided in `profiles.py` and reported by `SMT-D2`; this
module only says what is asked once 02035-2 is the answer.

The structural layer is generated, as 02004's and 02003's are. The hand
layer is 02004's, installed from `handover.py` minus the three rules
whose elements this template does not have -- and "minus three" is
refused unless the table agrees, in both directions.
"""
from __future__ import annotations

from ..registry import rule
from . import dbp_tables, handover
from .engine import analyze, matched_submodels

#: The template's own identity -- one authority, the generated table. It
#: is 02004's identifier, which is the whole reason this pack exists.
TEMPLATE_SEMANTIC_ID = dbp_tables.TEMPLATE_SEMANTIC_ID


def _row_check(row_id: str):
    def check(ctx):
        if not matched_submodels(ctx, dbp_tables):
            return  # SMT-D1's finding, or 02004 answered instead
        yield from analyze(ctx, dbp_tables)["violations"].get(row_id, ())
    return check


for _row in dbp_tables.ROWS:
    rule(_row["id"], kind="template", prio="MUST",
         title="'%s' as the template declares it (%s)"
               % (_row["label"], _row["sid"] or "by structure"),
         spec="IDTA 02035-2 1.0 template, SMT/Cardinality qualifier",
         fix=_row["fix"])(_row_check(_row["id"]))


#: D6 navigates StatusValue, D8 StatusSetDate, D9 the four reference
#: elements -- rows 02035-2 does not have. `install` refuses this list if
#: the table turns out to answer for any of them, so it cannot quietly
#: become a way to check less.
handover.install("DBP2", dbp_tables, omit=("-D6", "-D8", "-D9"),
                 inherits="IDTA 02035-2 1.0")
