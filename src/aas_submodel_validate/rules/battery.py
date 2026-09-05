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
same attribute mandatory under Regulation (EU) 2023/1542. `BAT-R8` says
both halves in the finding's own words.

It reads one of the nine. The other eight depend on the battery's
category and nothing here can read one: remaining capacity is required
for light means of transport and voluntary for electric vehicles, and
the capacity threshold for exhaustion inverts -- required for EVs, and
the guidance marks it *not to be filled* for anything else. A finding
that ignored the category would tell an LMT manufacturer to add a field
their own guidance forbids, which is over-refusal wearing the shape of
diligence. They are in `CONDITIONAL_ON_CATEGORY`, read by nothing, and
the coverage note counts them so the silence is stated rather than
merely kept (docs/divergences.md #37).

A warning and not an error, for a second reason: two published readings
of applicability exist and this pack cannot yet be told which to answer
for.

Neither rule needs a template table, which is what lets them run at all:
a row carries the submodel identifier, the element identifier, what the
template said, who says otherwise, and the provision. `battery_tables.py`
is generated from the indexes under `data/battery-passport/`.
"""
from __future__ import annotations

from ..model import Violation
from ..registry import rule
from ..semantics import candidate_values, element_candidate_values
from . import battery_tables
from .detect import instances

R2_ID = "BAT-R2"
R8_ID = "BAT-R8"

#: The note `BAT-R8` leaves when it looked at something. Not a finding:
#: it says what this run could examine, and a run examines nothing when
#: the input holds no submodel the table names.
COVERAGE_NOTE = (
    "%s reported %d of the %d elements this table holds; %d of them need "
    "a battery category no rule here reads yet, so whether the law "
    "requires those is a question this run did not ask. Read from %s. Both figures are a "
    "floor, not a measurement: the templates cite no provision of the "
    "law, so the join behind the table matched attributes by name, and "
    "name matching misses every element whose label differs from the "
    "prose, and reaches a nested one only when its label happens to "
    "match.")


def coverage_note(submodels) -> str:
    """What this run could examine, or None when it examined nothing.

    Computed here, from the table, at the moment of the run. A sentence
    with the number typed into it is a sentence that stops being true the
    day the indexes move, and this project has already shipped that
    mistake in prose more than once.

    The word "floor" is not decoration. The templates carry no citation
    of the regulation, so the join behind the table had to match template
    elements to legal attributes by name, and name matching misses every
    element whose label differs from the prose and every nested one it
    cannot reach at all. What comes out is a lower bound on the
    disagreement, never a measurement of it.
    """
    withheld = len(battery_tables.CONDITIONAL_ON_CATEGORY)
    # Every row the table holds, the withheld ones included. Counting
    # against the reportable rows alone made the sentence "1 of the 1",
    # which is a number divided by itself wearing the look of complete
    # coverage -- and the eight it does not ask about are named in the
    # same breath, so they belong in the denominator that frames them.
    total = len(battery_tables.LAW_REQUIRES_TEMPLATE_OPTIONAL) + withheld
    # Distinct rows, not a sum over submodels: two ProductCondition
    # submodels in one file -- two battery modules, an ordinary shape --
    # made this say "10 of the 9".
    read = len({row["element"] for submodel in submodels
                for row in _rows_for(submodel)})
    if not read:
        return None
    return COVERAGE_NOTE % (R8_ID, read, total, withheld,
                            battery_tables.SOURCE_EDITION)


def _declared(submodel) -> frozenset:
    return candidate_values(getattr(submodel, "semantic_id", None))


def _rows_for(submodel):
    """The table rows whose submodel this one declares itself to be."""
    declared = _declared(submodel)
    return [row for row in battery_tables.LAW_REQUIRES_TEMPLATE_OPTIONAL
            if row["submodel_semantic_id"] in declared]


def _carries(submodel, row) -> bool:
    """Whether the element the row names is present anywhere below the
    submodel, by semanticId.

    By identifier and not by idShort, for the reason the roof of this
    project is built on: IDTA 02004 Annex A says a different idShort
    might be chosen. The idShort in the row is what a finding quotes, not
    what it matches on.

    Through `element_candidate_values`, which reads supplementals too.
    The walk has read them since `test_decisions_are_pinned` recorded
    why -- an instance may carry a vendor identifier as its main one and
    declare the template's in a supplemental, and a reader that looks
    only at the main one turns that conformant file into a failing one.
    Reading `semantic_id` alone here reproduced that exactly.

    At any depth, because the one element this rule reads today sits two
    collections down -- a walk over the top level alone reports it absent
    from a file that carries it, which is the direction this project
    treats as worst. The row says the submodel must carry the element;
    it does not say where, and the template's own nesting is not a thing
    the law speaks about.
    """
    wanted = row["element_semantic_id"]
    pending = list(getattr(submodel, "submodel_elements", None) or [])
    while pending:
        element = pending.pop()
        if wanted in element_candidate_values(element):
            return True
        for attribute in ("value", "statements", "submodel_element_list",
                          "annotations"):
            children = getattr(element, attribute, None)
            if isinstance(children, list):
                pending.extend(c for c in children if hasattr(c, "semantic_id"))
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
    for submodel in instances(ctx.loaded):
        for identifier in sorted(_declared(submodel)):
            claimants = battery_tables.SHARED_SUBMODEL_IDS.get(identifier)
            if claimants is None:
                continue
            if any(claimant in _known_to_the_walk() for claimant in claimants):
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
      title="elements the template permits absent that a published "
            "reading of the regulation requires",
      spec="Regulation (EU) 2023/1542; each finding names the provision "
           "its own row cites, and docs/divergences.md #37 records whose "
           "reading of it this answers for",
      fix="Provide the element, or record that this battery is outside "
          "the provision read as requiring it. The template will not ask "
          "for it -- that is the point of the finding.")
def bat_r8_template_optional_but_law_requires(ctx):
    """Every row whose submodel is here, in table order, and the walk
    reads every element rather than the first: an absence past the first
    element is the same absence."""
    for submodel in instances(ctx.loaded):
        for row in _rows_for(submodel):
            if _carries(submodel, row):
                continue
            clauses = ", ".join(row["citations"])
            yield Violation(
                "conformant to the template and not to the regulation: "
                "'%s' is absent" % row["element_id_short"],
                # The element's name, not a path. This used to synthesise
                # `<submodel>/<element>`, which is a place the walk never
                # went -- the element sits two collections down where it
                # is present at all -- so the finding pointed at one
                # location and accepted the identifier at any other.
                subject=row["element_id_short"],
                # Whose reading, and of what. The row's own citations,
                # because a table joined from several sources cites a
                # different provision on every line; and `read ... as
                # requiring`, because the authority behind this row is a
                # published reading of that provision and not the
                # provision speaking. `docs/divergences.md` #37 has said
                # so since the rule landed -- the document was careful
                # and the sentence a reader sees was not.
                # The rule's own `spec` is unreachable now that every
                # violation carries one, and it was where the pointer to
                # the divergence lived -- so a reader lost the one line
                # that says whose reading this is answering for. It
                # travels with the clause instead.
                spec="Regulation (EU) 2023/1542 %s; docs/divergences.md "
                     "#37 for whose reading of it this answers"
                     % clauses,
                detail="%s %s makes it %s; %s is read as requiring it, for "
                       "every battery category the source names. Asked "
                       "anywhere under the submodel: this rule is about "
                       "the data being present, not about where the "
                       "template puts it"
                       % (row["template"], row["template_version"],
                          row["cardinality"], clauses))


def _known_to_the_walk() -> frozenset:
    """The templates this tool has a rule table for, read from the two
    registries that hold them.

    Written out by hand first, which made it a second place for one
    answer to be right: a pack landing or leaving moved one list and not
    the other, and a stale entry here makes `BAT-R2` say "no table for
    either" about a collision that has just acquired one. Imported
    lazily because `detect` and `profiles` register rules at import and
    this module is imported alongside them.
    """
    from . import detect, profiles
    named = {pack.name for pack in detect.PACKS}
    for profile in profiles.PROFILES:
        named |= {profile.default_name, profile.name}
    # The registries spell a pack "Handover Documentation (IDTA 02004)";
    # a collision is spelled by document number alone.
    return frozenset(name.split(" (")[-1].rstrip(")") for name in named)

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
def _settles_only() -> tuple:
    return tuple(sorted(
        key for identifier, keys in _KEYS_OF.items() for key in keys
        if not any(claimant in _known_to_the_walk()
                   for claimant in battery_tables.SHARED_SUBMODEL_IDS[identifier])))
