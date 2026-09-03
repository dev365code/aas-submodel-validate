"""What the battery-passport templates permit and the regulation does not.

Two questions, and the second is the one no other tool asks.

**Which template is this?** IDTA publishes two collisions -- one submodel
identifier claimed by two templates. This project has generated tables
for both sides of the first (02004 and 02035-2) and `SMT-D2` owns it: the
choice rides on the `Selection` the walk reads, so the verdict cannot
move without the sentence that explains it. It has a table for neither
side of the second, and there the report used to say only that nothing
matched a template it knows -- the one thing that is not true about such
a file. `BAT-R2` says what it is, twice over, and `--profile` settles it.
Reporting the first collision here as well would be two rules answering
one question, and the second would be the one with no table behind it.

**Is a template-conformant file conformant to the law?** Nine elements
are `ZeroToOne` in their template -- absence is allowed -- while the
Battery Pass long list or the Commission's data-point guidance marks the
same attribute mandatory under Regulation (EU) 2023/1542. `BAT-R8` reads
those nine and says both halves in the finding's own words. It is a
warning, not an error: two published readings of applicability exist and
this pack cannot yet be told which one to answer for
(docs/divergences.md #37).

Neither rule needs a template table, which is what lets them run at all:
a row carries the submodel identifier, the element identifier, what the
template said, who says otherwise, and the provision. `battery_tables.py`
is generated from the indexes under `data/battery-passport/`.
"""
from __future__ import annotations

from ..model import Violation
from ..registry import rule
from ..semantics import candidate_values
from . import battery_tables

R2_ID = "BAT-R2"
R8_ID = "BAT-R8"

#: The note `BAT-R8` leaves when it looked at something. Not a finding:
#: it says what this run could examine, and a run examines nothing when
#: the input holds no submodel the table names.
COVERAGE_NOTE = (
    "%s read %d of the %d elements this pack knows the regulation to "
    "require and the template to permit absent (%s). That figure is a "
    "floor, not a measurement: the templates cite no provision of the "
    "law, so the join behind the table matched attributes by name, and "
    "name matching misses every element whose label differs from the "
    "prose and every nested one it cannot reach.")


def coverage_note(submodels) -> str:
    """What this run could examine, or None when it examined nothing.

    Computed here, from the table, at the moment of the run. A sentence
    with the number typed into it is a sentence that stops being true the
    day the indexes move, and this project has already shipped that
    mistake in prose more than once (LESSONS B).

    The word "floor" is not decoration. The templates carry no citation
    of the regulation, so the join behind the table had to match template
    elements to legal attributes by name, and name matching misses every
    element whose label differs from the prose and every nested one it
    cannot reach at all. What comes out is a lower bound on the
    disagreement, never a measurement of it.
    """
    total = len(battery_tables.LAW_REQUIRES_TEMPLATE_OPTIONAL)
    read = sum(len(_rows_for(submodel)) for submodel in submodels)
    if not read:
        return None
    return COVERAGE_NOTE % (R8_ID, read, total, battery_tables.SOURCE_EDITION)


def _declared(submodel) -> frozenset:
    return candidate_values(getattr(submodel, "semantic_id", None))


def _rows_for(submodel):
    """The table rows whose submodel this one declares itself to be."""
    declared = _declared(submodel)
    return [row for row in battery_tables.LAW_REQUIRES_TEMPLATE_OPTIONAL
            if row["submodel_semantic_id"] in declared]


def _carries(submodel, row) -> bool:
    """Whether the element the row names is present, by semanticId.

    By identifier and not by idShort, for the reason the roof of this
    project is built on: IDTA 02004 Annex A says a different idShort
    might be chosen. The idShort in the row is what a finding quotes, not
    what it matches on.
    """
    wanted = row["element_semantic_id"]
    for element in getattr(submodel, "submodel_elements", None) or []:
        if wanted in candidate_values(getattr(element, "semantic_id", None)):
            return True
    return False


@rule(R2_ID, kind="template", prio="SHOULD",
      title="a submodel identifier two published templates claim is named, not dismissed",
      spec="IDTA 02023 and IDTA 02035-3 publish one CarbonFootprint "
           "submodel semanticId; docs/divergences.md #36",
      fix="Run --profile with the document number of the template you "
          "mean. This tool has a table for neither side of this "
          "collision, so the profile settles which template the file "
          "claims to be and no more -- nothing here judges it against "
          "either one.")
def bat_r2_shared_identifier_without_a_table(ctx):
    """Silent where `SMT-D2` speaks. That rule owns the collision this
    project has tables for, and owning it means carrying the choice on
    the object the walk reads; this one owns the collision it has no
    table for, where there is no choice to carry and the alternative is
    a report that calls a known template unknown."""
    forced = getattr(ctx.selection, "forced", None)
    for submodel in ctx.loaded.submodels:
        for identifier in sorted(_declared(submodel)):
            claimants = battery_tables.SHARED_SUBMODEL_IDS.get(identifier)
            if claimants is None:
                continue
            if any(claimant in _KNOWN_TO_THE_WALK for claimant in claimants):
                continue          # SMT-D2's collision, and its sentence
            if forced in _KEYS_OF.get(identifier, ()):
                continue          # somebody said which one they meant
            yield Violation(
                "this submodel's semanticId is claimed by %s, and nothing "
                "here can tell them apart" % " and ".join(claimants),
                subject=getattr(submodel, "id_short", None) or "submodel",
                detail="%s; no table for either, so this submodel was not "
                       "judged against a template" % identifier)


@rule(R8_ID, kind="template", prio="SHOULD",
      title="elements the template permits absent that the regulation requires",
      spec="Regulation (EU) 2023/1542 Annex VII; "
           "docs/divergences.md #37 for which reading this answers for",
      fix="Provide the element, or record that this battery is outside "
          "the provision that requires it. The template will not ask for "
          "it -- that is the point of the finding.")
def bat_r8_template_optional_but_law_requires(ctx):
    """Every row whose submodel is here, in table order, and the walk
    reads every element rather than the first: an absence past the first
    element is the same absence."""
    for submodel in ctx.loaded.submodels:
        for row in _rows_for(submodel):
            if _carries(submodel, row):
                continue
            yield Violation(
                "conformant to the template and not to the regulation: "
                "'%s' is absent" % row["element_id_short"],
                subject="%s/%s" % (getattr(submodel, "id_short", None)
                                   or "submodel", row["element_id_short"]),
                detail="%s %s makes it %s; %s requires it (%s)"
                       % (row["template"], row["template_version"],
                          row["cardinality"], ", ".join(row["citations"]),
                          ", ".join(row["says_mandatory"])))


#: The document numbers `engine.matched_submodels` can actually answer
#: for. Written here rather than imported from `profiles`, which imports
#: the two generated tables and would make this module depend on them for
#: a fact about names.
_KNOWN_TO_THE_WALK = frozenset(("IDTA 02004", "IDTA 02003", "IDTA 02035-2"))

#: What `--profile` is spelled with, per collision: the document numbers
#: of the two templates that claim the identifier.
_KEYS_OF = {
    identifier: tuple(name.replace("IDTA ", "") for name in claimants)
    for identifier, claimants in battery_tables.SHARED_SUBMODEL_IDS.items()
}

#: The document numbers that settle a collision this tool has no table
#: for. `profiles.KEYS` is deliberately the other thing -- the numbers
#: that choose a table, derived so `--help` cannot name a template this
#: tool cannot judge by. These are named separately for the same reason:
#: they choose nothing, they only say which template the file claims to
#: be, and a flag that pretends otherwise would be worse than no flag.
#:
#: Both lists reach the parser, because `BAT-R2`'s remedy tells the
#: reader to use one of these and a remedy naming a value the parser
#: refuses is worse than silence. Measured: it did, for one commit.
SETTLES_ONLY = tuple(sorted(
    key for identifier, keys in _KEYS_OF.items() for key in keys
    if not any(claimant in _KNOWN_TO_THE_WALK
               for claimant in battery_tables.SHARED_SUBMODEL_IDS[identifier])))
