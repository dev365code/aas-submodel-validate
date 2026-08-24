"""IDTA 02004 Handover Documentation: the hand-written rules.

The generated structural layer (cardinality, types, per-element
semanticIds) arrives with the vendored template; what lives here is what
a template file cannot express. First of them: is the submodel this tool
was pointed at even claiming to be Handover Documentation?
"""
from __future__ import annotations

from ..model import Violation
from ..registry import rule
from ..semantics import key_values

#: The template's own identity, from the published 02004 2.0.1 template.
TEMPLATE_SEMANTIC_ID = "0173-1#01-AHF578#003"
_TEMPLATE_STEM = "0173-1#01-AHF578"


def matched_submodels(ctx):
    return [submodel for submodel in ctx.loaded.submodels
            if TEMPLATE_SEMANTIC_ID in key_values(submodel.semantic_id)]


def _nearest_miss(submodels):
    """Why nothing matched, in the most useful words available."""
    seen = []
    for submodel in submodels:
        for value in key_values(submodel.semantic_id):
            seen.append(value)
            if value.startswith(_TEMPLATE_STEM) and value != TEMPLATE_SEMANTIC_ID:
                return ("found %s, which differs from the template's %s only in the "
                        "ECLASS version suffix" % (value, TEMPLATE_SEMANTIC_ID))
        if (getattr(submodel, "id_short", None) or "").lower() == "handoverdocumentation":
            return ("a submodel is *named* HandoverDocumentation but its semanticId "
                    "is %s — matching goes by semanticId, never by name"
                    % (", ".join(key_values(submodel.semantic_id)) or "absent"))
    if seen:
        return "saw semanticId value(s): %s" % ", ".join(sorted(set(seen))[:3])
    return "no submodel in the input declares any semanticId"


@rule("HD-D1", kind="template", prio="MUST",
      title="the input must contain a Handover Documentation submodel",
      spec="IDTA 02004-2-0 §1.3",
      fix="Give the submodel a semanticId with key value %s "
          "(type ExternalReference / GlobalReference), as the published "
          "template declares it." % TEMPLATE_SEMANTIC_ID)
def hd_d1_submodel_present(ctx):
    """No findings is also what a perfect package looks like, so a run
    that validated nothing must say so loudly (the sibling validators'
    silent-pass lesson, applied from day one). Unreadable inputs are the
    X rules' finding — piling this on top of those would be noise."""
    if ctx.loaded.errors and not ctx.loaded.submodels:
        return
    if matched_submodels(ctx):
        return
    yield Violation("no submodel declares the Handover Documentation semanticId",
                    detail=_nearest_miss(ctx.loaded.submodels))
