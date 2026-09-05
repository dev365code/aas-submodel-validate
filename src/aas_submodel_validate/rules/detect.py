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


def is_template(submodel) -> bool:
    """Whether this submodel says it is a specification, not an instance.

    `ModellingKind.TEMPLATE` is "specification of the common features
    ... that such an instance can be instantiated using it". Every rule
    in this project is a requirement on an instance -- a cardinality
    says how many of a thing an instance must carry -- so asking a
    template to satisfy one is a category error, and the tool asked.
    Pointed at the published 02004 template, which is where its own
    rules are generated from, it reported that the template has no VDI
    2770 classification and told the reader to add one. No flag escaped
    it.

    Read through aas-core3's own default rather than compared to a
    string: `kind` is optional and the metamodel says what an absent
    one means.
    """
    kind = getattr(submodel, "kind_or_default", None)
    kind = kind() if callable(kind) else getattr(submodel, "kind", None)
    return getattr(kind, "name", str(kind or "")).upper() == "TEMPLATE"


def matched(ctx):
    """Every (pack, submodel) pair the input actually brought, instances
    only -- see `is_template` for why a specification is not one."""
    return [(pack, submodel)
            for submodel in ctx.loaded.submodels
            if not is_template(submodel)
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
                return ("a submodel is *named* %s but its semanticId is %s -- "
                        "matching goes by semanticId, never by name"
                        % (submodel.id_short,
                           ", ".join(key_values(submodel.semantic_id)) or "absent"))
    if seen:
        return "semanticId value(s): %s" % ", ".join(sorted(set(seen))[:3])
    return "no submodel in the input declares any semanticId"


#: The remedy, and the sentence that keeps it from being wrong.
#:
#: It used to end at the list of identifiers, which reads as "relabel
#: your file as one of these". For a battery-passport submodel that is
#: advice to mislabel a correct document -- and it printed one line above
#: a `BAT-R8` finding naming that document's real template. The message
#: was corrected first and the remedy was not, which is the half a reader
#: acts on.
_REMEDY = ("If the submodel means one of the templates this tool has a table "
           "for, give it that template's semanticId: "
           + "; ".join("%s for %s" % (pack.semantic_id, pack.name) for pack in PACKS)
           + ". If it means a template this tool has no table for, leave the "
             "identifier alone -- it is doing its job, and this finding only "
             "says nothing here judged the submodel against a template.")


@rule(RULE_ID, kind="template", prio="MUST",
      title="the input must contain a submodel this tool knows",
      spec="IDTA 02004-2-0 §2.4, Table 2; IDTA 02003-2-0-1 §2",
      fix=_REMEDY)
def smt_d1_a_known_submodel_is_present(ctx):
    """No findings is also what a perfect package looks like, so a run
    that validated nothing must say so loudly (the sibling validators'
    silent-pass lesson, applied from day one). Unreadable inputs are the
    X rules' finding — piling this on top of those would be noise."""
    if ctx.loaded.nothing_was_judged:
        return
    if matched(ctx):
        return
    # A file of nothing but specifications is not a file that failed to
    # declare a known identifier -- it declares one and is not an
    # instance. The note the runner adds says that; this saying the
    # other thing on top of it would be two answers to one question.
    if ctx.loaded.submodels and all(is_template(submodel)
                                    for submodel in ctx.loaded.submodels):
        return
    # "recognises" was true until the battery pack landed. That pack
    # knows identifiers this one has no template table for, and reports
    # on them (BAT-R2, BAT-R8), so a sentence claiming the tool does not
    # recognise them contradicts a finding two lines further down the
    # same report.
    yield Violation("no submodel declares a semanticId this tool has a "
                    "template table for",
                    detail=_nearest_miss(ctx.loaded.submodels))
