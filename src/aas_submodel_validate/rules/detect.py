"""Did the input bring a submodel this tool knows how to judge?

This is the one question that belongs to the tool rather than to any
template, and it has to be asked once. A presence rule per template
would contradict itself the moment a second template arrived: a
Technical Data file would fail Handover's rule and a Handover file would
fail Technical Data's, and both findings would be false. So the error is
"none of the templates matched", and the diagnosis names what was seen.

Everything else about a template lives with that template. This module
knows only each pack's anchor identifier, the name to call it by, and
the word an author is likely to have used as an idShort.
"""
from __future__ import annotations

from ..model import Violation
from ..registry import rule
from ..semantics import key_values, submodel_declares
from . import hd_tables, td_tables

#: The rule id. Referenced by the runner, which can demote this one
#: finding to a note, so the string lives here rather than in two places.
RULE_ID = "SMT-D1"


class Pack:
    """One template this tool can judge: what identifies it, what to call
    it, and the idShort an author reaches for when they mean it."""

    def __init__(self, name, tables, id_short_hint):
        self.name = name
        self.tables = tables
        self.id_short_hint = id_short_hint

    @property
    def semantic_id(self) -> str:
        return self.tables.TEMPLATE_SEMANTIC_ID

    @property
    def stem(self) -> str:
        """The identifier without its ECLASS version suffix."""
        return self.semantic_id.rpartition("#")[0]


PACKS = (
    Pack("Handover Documentation (IDTA 02004)", hd_tables, "handoverdocumentation"),
    Pack("Technical Data (IDTA 02003)", td_tables, "technicaldata"),
)


def matched(ctx):
    """Every (pack, submodel) pair the input actually brought."""
    return [(pack, submodel)
            for submodel in ctx.loaded.submodels
            for pack in PACKS
            if submodel_declares(submodel, pack.semantic_id)]


def _nearest_miss(submodels) -> str:
    """Why nothing matched, in the most useful words available."""
    seen = []
    for submodel in submodels:
        for value in key_values(submodel.semantic_id):
            seen.append(value)
            for pack in PACKS:
                if value.startswith(pack.stem) and value != pack.semantic_id:
                    return ("found %s, which differs from the %s template's %s "
                            "only in the ECLASS version suffix"
                            % (value, pack.name, pack.semantic_id))
        named = (getattr(submodel, "id_short", None) or "").lower()
        for pack in PACKS:
            if named == pack.id_short_hint:
                return ("a submodel is *named* %s but its semanticId is %s — "
                        "matching goes by semanticId, never by name"
                        % (submodel.id_short,
                           ", ".join(key_values(submodel.semantic_id)) or "absent"))
    if seen:
        return "semanticId value(s): %s" % ", ".join(sorted(set(seen))[:3])
    return "no submodel in the input declares any semanticId"


_REMEDY = ("Give the submodel the semanticId of the template it means to be: "
           + "; ".join("%s for %s" % (pack.semantic_id, pack.name) for pack in PACKS)
           + ".")


@rule(RULE_ID, kind="template", prio="MUST",
      title="the input must contain a submodel this tool knows",
      spec="IDTA 02004-2-0 §2.4, Table 2; IDTA 02003-2-0-1 §2",
      fix=_REMEDY)
def smt_d1_a_known_submodel_is_present(ctx):
    """No findings is also what a perfect package looks like, so a run
    that validated nothing must say so loudly (the sibling validators'
    silent-pass lesson, applied from day one). Unreadable inputs are the
    X rules' finding — piling this on top of those would be noise."""
    if ctx.loaded.errors and not ctx.loaded.submodels:
        return
    if matched(ctx):
        return
    yield Violation("no submodel declares a semanticId this tool recognises",
                    detail=_nearest_miss(ctx.loaded.submodels))
