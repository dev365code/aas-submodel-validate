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
BatteryPass-Ready Data Attribute Longlist v1.3 or the Commission's
data-point guidance marks the same attribute mandatory under Regulation
(EU) 2023/1542. `BAT-R8` says both halves in the finding's own words.
The full name of the longlist is used deliberately: the short one
belongs to an earlier, non-commercially licensed series, and this index
is built from v1.3 only.

It reads none of the nine unless the file settles its own battery
category. One appeared to be required of every category and was not:
Annex IV Part A (4) reads "Where applicable, energy round trip
efficiency and its fade", and it was on this project's front page (#37).
The rest turn on the category and the file has to answer: remaining
capacity is required for light means of transport and *not to be
filled* for electric vehicles, and the capacity threshold for exhaustion
inverts. A finding that ignored the category would tell an LMT
manufacturer to add a field their own guidance forbids, which is
over-refusal wearing the shape of diligence. The coverage note counts
what was not asked, so the silence is stated rather than merely kept.

Where the clause a row cites states itself conditionally -- "where
possible", "where appropriate" -- the finding says so. The guidance can
mark an attribute mandatory for a category while the provision behind it
is qualified; both are printed, because settling that between two
published documents is not this tool's to do.

A warning and not an error, for a second reason: two published readings
of applicability exist and this pack cannot yet be told which to answer
for.

Neither rule needs a template table, which is what lets them run at all:
a row carries the submodel identifier, the element identifier, what the
template said, who says otherwise, and the provision. `battery_tables.py`
is generated from the indexes under `data/battery-passport/`.
"""
from __future__ import annotations

import re

from ..model import Violation
from ..registry import rule
from ..semantics import candidate_values, element_candidate_values
from . import battery_tables, detect
from .detect import instances

R2_ID = "BAT-R2"
R8_ID = "BAT-R8"

#: The element a battery passport states its own category in. IDTA
#: 02035-4 makes it cardinality `One` and names its vocabulary in the
#: element's own description: "lmt", "ev", "industrial", "stationary".
CATEGORY_ELEMENT = ("urn:samm:io.admin-shell.idta.batterypass."
                    "technical_data:1.0.0#batteryCategory")

#: The template's vocabulary, and the guidance column each one settles.
#:
#: Two of the four are deliberately absent. `industrial` and
#: `stationary` reach only columns the guidance names *above 2 kWh*, and
#: the category value states a category, not a capacity. The provision
#: that would close the gap -- which batteries need a passport at all --
#: is Article 77(1), which this repository does not index (the annex
#: index says so in its own note), so the inference that an industrial
#: battery carrying a passport is above the threshold has no source
#: here. Those two stay unanswered and the coverage note counts them.
CATEGORY_COLUMNS = {"ev": "EV", "lmt": "LMT"}

#: The readings that make an element required. The guidance writes two
#: spellings and the longlist a third; anything else -- `voluntary`,
#: `not-to-be-filled`, `not-stated`, `certain-cases` -- is not a
#: requirement and must not draw a finding. `not-to-be-filled` is the
#: one that matters: the capacity threshold for exhaustion is required
#: for an electric vehicle and forbidden for light means of transport,
#: so a rule that ignored the category would tell an LMT manufacturer to
#: add a field their own guidance refuses.
REQUIRED_READINGS = ("required", "required-by-batteries-regulation")


def declared_categories(submodels) -> tuple:
    """Every distinct category the file states, lower-cased.

    Over every submodel rather than the one being judged: the element
    lives in Technical Data and four of the eight rows it settles belong
    to other parts of the passport.
    """
    found = []
    for submodel in submodels:
        pending = list(getattr(submodel, "submodel_elements", None) or [])
        while pending:
            element = pending.pop()
            if CATEGORY_ELEMENT in element_candidate_values(element):
                value = getattr(element, "value", None)
                if isinstance(value, str) and value.strip():
                    word = value.strip().lower()
                    if word not in found:
                        found.append(word)
            for attribute in ("value", "statements", "annotations"):
                children = getattr(element, attribute, None)
                if isinstance(children, list):
                    pending.extend(c for c in children if hasattr(c, "semantic_id"))
    return tuple(found)


def declared_category(submodels) -> str:
    """The one category the file states, or "" -- for none, or for more
    than one.

    Two Technical Data submodels stating different categories used to be
    settled by whichever was walked first: `ev` then `lmt` reported six
    findings, all EV rows, and the same file with the two reversed
    reported ten, all LMT rows. Nothing said a choice had been made.

    Returning "" is the conservative direction and the one the table's
    own comment argues for. The capacity threshold for exhaustion is
    required for an electric vehicle and forbidden for light means of
    transport, so a run that guesses tells one of those two readers to
    add a field their own guidance refuses. A file that names two
    categories has not settled the question, and this says so rather
    than picking.
    """
    found = declared_categories(submodels)
    return found[0] if len(found) == 1 else ""


def _rows_the_category_settles(submodels):
    """The conditional rows this file's own category makes required."""
    column = CATEGORY_COLUMNS.get(declared_category(submodels))
    if column is None:
        return []
    return [row for row in battery_tables.CONDITIONAL_ON_CATEGORY
            if dict(row["categories"]).get(column) in REQUIRED_READINGS]

#: The note `BAT-R8` leaves when it looked at something. Not a finding:
#: it says what this run could examine, and a run examines nothing when
#: the input holds no submodel the table names.
#: Shared tail. "Floor" is not decoration -- see `coverage_note`.
COVERAGE_TAIL = (
    " Read from %s. Both figures are a "
    "floor, not a measurement: the templates cite no provision of the "
    "law, so the join behind the table matched attributes by name, and "
    "name matching misses every element whose label differs from the "
    "prose, and reaches a nested one only when its label happens to "
    "match.")
COVERAGE_NOTE = (
    "%s reported %d of the %d elements this table holds; %d of them turn "
    "on a battery category this file does not settle, so whether a "
    "published reading of the law requires those is a question this run "
    "did not ask.%s" + COVERAGE_TAIL)
#: A file can fail to settle the category by naming none or by naming
#: several, and those are not the same thing to fix. The first reads as
#: an omission; the second is a contradiction inside the file, and a run
#: that reported it the first way told a reader to add something they
#: had already written down twice.
COVERAGE_NOTE_DISPUTED = (
    "%s reported %d of the %d elements this table holds; %d of them turn "
    "on a battery category, and this file states %s, so this run did not "
    "choose between them -- whether a published reading of the law "
    "requires those is a question it did not ask.%s" + COVERAGE_TAIL)
#: The other reason an element goes unasked, which this note said with
#: the first one's words. A file that states `ev` has settled the
#: question; the six elements EV's guidance does not require were not
#: skipped for want of a category -- they were asked and the reading
#: says no. Telling that reader their file "does not settle" a category
#: it had just declared is the note contradicting the finding beside it.
COVERAGE_NOTE_SETTLED = (
    "%s reported %d of the %d elements this table holds; this file "
    "declares battery category '%s', and the reading recorded here does "
    "not require %d of the table's conditional elements for it, so those "
    "were not asked.%s" + COVERAGE_TAIL)


#: The third reason an element goes unasked, and the one that kept the
#: sentence from adding up: its submodel is not in this file at all. A
#: Technical Data file on its own read "reported 1 of the 9 ... does not
#: require 2 of the table's conditional elements", leaving six
#: unaccounted for -- a reader who did the arithmetic the note invites
#: got 3.
ELSEWHERE = (" A further %d belong%s to submodels this file does not carry, "
             "so nothing here could look for %s.")


def _elsewhere(submodels) -> int:
    """The rows whose submodel never arrived, said rather than left over."""
    here = set()
    for submodel in submodels:
        here |= _declared(submodel)
    rows = (battery_tables.LAW_REQUIRES_TEMPLATE_OPTIONAL
            + battery_tables.CONDITIONAL_ON_CATEGORY)
    return len({row["element"] for row in rows
                if row["submodel_semantic_id"] not in here})


def _elsewhere_said(missing) -> str:
    if not missing:
        return ""
    return ELSEWHERE % (missing, "s" if missing == 1 else "",
                        "it" if missing == 1 else "them")


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
    submodels = list(submodels)
    # What was withheld *from this file*, not from the table. A passport
    # that states `ev` or `lmt` has answered the question the conditional
    # rows were waiting on, and a sentence that keeps saying eight after
    # seven of them were asked is a number typed into prose -- which the
    # paragraph below already warns about. Counted as what is left once
    # the read rows and the absent submodels are taken out, rather than
    # from the settled set directly: the two overlap, and adding three
    # independently counted numbers made the note account for fifteen of
    # nine.
    # The table, and nothing about this file. It was
    # `unconditional + withheld`, and `withheld` falls as the file
    # settles rows -- so the numerator rose while the denominator fell
    # from the same fact, and an LMT passport read "reported 8 of the 2
    # elements this table holds". Every fixture this note had been
    # measured on declared no category, which is the one case where the
    # two formulas agree.
    #
    # The denominator still carries the elements this run did not ask
    # about. Counting against the reportable rows alone made the sentence
    # "1 of the 1", a number divided by itself wearing the look of
    # complete coverage -- and the ones it does not ask about are named
    # in the same breath, so they belong in the frame.
    total = (len(battery_tables.LAW_REQUIRES_TEMPLATE_OPTIONAL)
             + len(battery_tables.CONDITIONAL_ON_CATEGORY))
    # Distinct rows, not a sum over submodels: two ProductCondition
    # submodels in one file -- two battery modules, an ordinary shape --
    # made this say "10 of the 9".
    settled_rows = _rows_the_category_settles(submodels)
    read = len({row["element"] for submodel in submodels
                for row in _rows_for(submodel, settled=settled_rows)})
    elsewhere = _elsewhere(submodels)
    # Whether the table knows any submodel here, not whether it read a
    # row of one. Those were the same question while one row was
    # required of every category -- every battery file read at least
    # that one -- and they came apart the day that row turned out to
    # cite a provision saying "where applicable". A passport that
    # declares no category now reads none of the nine, and `not read`
    # returned None for it: the file this note has the most to say about
    # got silence, and a reader was told nothing about the nine
    # questions the run did not ask.
    if not any(_declared(submodel) & detect.PACK_ONLY_SEMANTIC_IDS
               for submodel in submodels):
        return None
    # Whether the file settled the question, not whether it said
    # something. A category this tool has no column for settles nothing,
    # so it takes the sentence for a file that named none -- which is
    # what the run actually did with it.
    stated = declared_category(submodels)
    if CATEGORY_COLUMNS.get(stated) is None:
        # A partition, not three counts that happen to be near each
        # other. Every row is read, or belongs to a submodel that never
        # arrived, or is left waiting on the category -- and the third
        # is what remains once the first two are taken out. Counted as
        # three independent numbers, the first version said the note
        # accounted for fifteen of nine.
        disputed = declared_categories(submodels)
        if len(disputed) > 1:
            return COVERAGE_NOTE_DISPUTED % (
                R8_ID, read, total, total - read - elsewhere,
                # Sorted: the walk's order is exactly what this change
                # stopped letting decide anything, and a note that
                # printed it would put it back in the report.
                " and ".join("'%s'" % word for word in sorted(disputed)),
                _elsewhere_said(elsewhere), battery_tables.SOURCE_EDITION)
        return COVERAGE_NOTE % (R8_ID, read, total,
                                total - read - elsewhere,
                                _elsewhere_said(elsewhere),
                                battery_tables.SOURCE_EDITION)
    return COVERAGE_NOTE_SETTLED % (
        R8_ID, read, total, stated, total - read - elsewhere,
        _elsewhere_said(elsewhere),
        battery_tables.SOURCE_EDITION)


def _declared(submodel) -> frozenset:
    return candidate_values(getattr(submodel, "semantic_id", None))


def _rows_for(submodel, submodels=None, settled=None):
    """The table rows whose submodel this one declares itself to be.

    Plus the conditional rows the file's own declared category settles,
    when it declares one. Those were withheld because their obligation
    depends on a category and nothing read one; the template makes the
    category mandatory and names its vocabulary, so a passport that
    states `ev` or `lmt` has answered the question the rows were waiting
    on. A passport that states neither is judged exactly as before.

    `settled` is those rows, already worked out. Which category the file
    states is one fact about the file, and this was deriving it again
    for every submodel -- each derivation walking every element of every
    submodel to find the one element that states it. N submodels made
    that N x N x their elements, on an input the byte ledger passes
    without complaint: "bounded by what it opens" held for bytes and not
    for time. Callers that walk more than one submodel work it out once
    and pass it; `submodels` stays for the callers that hold one.
    """
    declared = _declared(submodel)
    rows = list(battery_tables.LAW_REQUIRES_TEMPLATE_OPTIONAL)
    if settled is not None:
        rows += settled
    elif submodels is not None:
        rows += _rows_the_category_settles(submodels)
    return [row for row in rows if row["submodel_semantic_id"] in declared]


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


#: A clause reference, and nothing else on the line. A row's citations
#: come out of an index whose cells sometimes carry the analyst's working
#: note beside the reference -- `--> measurement at 80 % SoC and 20% SoC
#: required` travelled into `per`, which is the one line a reader copies
#: into a report of their own.
CLAUSE = re.compile(
    r"Art(?:icle)?\.?\s*\d+(?:\s*\(\d+\))?"
    r"|Annex\s+[IVX]+(?:\s+Part\s+[AB])?"
    # Two ways the sources number a point below an annex. The long list
    # parenthesises it -- `Annex IV (2)`, `Annex XIII (1k)` -- and the
    # Commission's guidance does not: `Annex XIII 4 (b)`. Only the first
    # was matched, so every guidance citation flattened to a bare
    # `Annex XIII`, which names a list of twenty-odd points and tells a
    # reader nothing about which one.
    r"(?:\s*\(\s*\d+\s*[a-z]?\s*\)|\s+\d+\s*\(\s*[a-z]\s*\))?", re.I)

#: How an index id is written for someone who has neither index. E6: the
#: long list is the "BatteryPass-Ready Data Attribute Longlist", which is
#: what its own file is called; the older series name this project's
#: NOTICE says it avoids is not this document.
SOURCE_NAMES = {
    "longlist": "BatteryPass-Ready Data Attribute Longlist v1.3 (draft) row %s",
    "ec-datapoints": ("European Commission guidance, Digital Batteries "
                      "Passport -- data point by category v2.0, data point %s"),
}


#: What a provision says about its own reach, when it says anything. The
#: per-category readings come from the guidance and the long list; this
#: is the clause's own wording, and the two differ: the Commission marks
#: the remaining power capability `Mandatory` for LMT while Annex VII
#: Part A (2) states it "where possible". Reporting the first without
#: the second is the mistake that put a "Where applicable" provision on
#: this project's front page, one layer down -- three findings an LMT
#: passport draws cite a qualified clause and said nothing about it.
#:
#: Said, not silenced. The guidance's "Mandatory for LMT" is a published
#: reading and dropping it would be this tool deciding the question
#: instead of reporting that two documents answer it differently.
QUALIFIED = (" %s, so whether it reaches this battery is not a question "
             "this tool answers.")


def _qualified(row) -> str:
    """One sentence however many clauses qualify the row.

    Two rows cite two qualified provisions each, and a sentence per
    clause said the same thing twice in a `saw` line already long enough
    to be skipped."""
    stated = ["%s states it '%s'" % (section, phrase.lower())
              for section, phrase in row.get("provision_conditions", ())]
    if not stated:
        return ""
    if len(stated) > 1:
        stated = [", ".join(stated[:-1]) + " and " + stated[-1]]
    return QUALIFIED % stated[0]


#: One point, written two ways. The long list parenthesises the point and
#: its letter together -- `Annex XIII (1k)` -- and the Commission writes
#: them apart -- `Annex XIII 1 (k)`. Both cite the same provision, and
#: with the guidance's citations joined in, `CapacityThresholdExhaustion`
#: printed both. Two spellings of one clause read as two clauses.
_JOINED_POINT = re.compile(r"^(Annex\s+[IVX]+)\s*\(\s*(\d+)\s*([a-z])\s*\)$", re.I)


def _canonical(clause) -> str:
    joined = _JOINED_POINT.match(clause)
    if joined:
        return "%s %s (%s)" % joined.groups()
    return clause


def _clauses(citations) -> str:
    """The clause identifiers a row cites, in the row's own order."""
    found = []
    for citation in citations:
        for hit in CLAUSE.findall(citation):
            hit = _canonical(" ".join(hit.split()).rstrip(".:,"))
            if hit not in found:
                found.append(hit)
    return ", ".join(found or list(citations))


def _sources(ids) -> str:
    """Which published document said so, named so a reader can go and
    look. The index ids resolve to files that ship in neither the wheel
    nor the source distribution, so they must not reach a reader."""
    named = []
    for identifier in ids:
        prefix, _, number = identifier.partition(":")
        pattern = SOURCE_NAMES.get(prefix)
        named.append(pattern % number if pattern else identifier)
    return "; ".join(named)


@rule(R8_ID, kind="template", prio="SHOULD",
      title="elements the template permits absent that a published "
            "reading of the regulation requires",
      # "its own row" stood here. A rule's `spec` is what a finding
      # prints when the violation carries none, so this is reader-facing
      # -- and `row` is this project's word for a line of its own table,
      # not an AAS word and not an IDTA one. A reader who went and
      # learned the standard would not find it.
      spec="Regulation (EU) 2023/1542; each finding names the provision "
           "it reads from, and docs/divergences.md #37 records whose "
           "reading of it this answers for",
      fix="Provide the element, or record that this battery is outside "
          "the provision read as requiring it. The template will not ask "
          "for it -- that is the point of the finding.")
def bat_r8_template_optional_but_law_requires(ctx):
    """Every row whose submodel is here, in table order, and the walk
    reads every element rather than the first: an absence past the first
    element is the same absence."""
    here = list(instances(ctx.loaded))
    # Which column settled the row, named in the finding. Every row this
    # rule reports is conditional on a category now, so a finding that
    # does not say which one is a claim about batteries in general --
    # and the row it used to report of every category was the one whose
    # provision reads "Where applicable".
    column = CATEGORY_COLUMNS.get(declared_category(here))
    settled_rows = _rows_the_category_settles(here)
    for submodel in here:
        for row in _rows_for(submodel, settled=settled_rows):
            if _carries(submodel, row):
                continue
            clauses = _clauses(row["citations"])
            yield Violation(
                # Not "and not to the regulation". That asserts the law
                # has been broken, which this tool cannot know: what it
                # has is a published reading of a provision, and #37 has
                # said so since the rule landed while the sentence a
                # reader sees said the other thing.
                "conformant to the template; a published reading of the "
                "regulation expects it%s: '%s' is absent"
                % (" for %s batteries" % column if column else "",
                   row["element_id_short"]),
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
                # Which document, which edition, which row, and for
                # which category. "for every battery category the source
                # names" stood here, over a row whose sources name three
                # categories and mark it required in one of them.
                detail="%s %s makes it %s. Read as expected%s by: %s.%s Asked "
                       "anywhere under the submodel: this rule is about "
                       "the data being present, not about where the "
                       "template puts it"
                       % (row["template"], row["template_version"],
                          row["cardinality"],
                          " for %s" % column if column else "",
                          _sources(row["says_mandatory"]),
                          _qualified(row)))


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
def settles_only() -> tuple:
    """The `--profile` keys that choose no table, only settle a claim.

    Public because it crosses a module boundary: `cli.py` builds the
    flag's `choices` and its help out of it, and two test modules read
    it. A leading underscore said the opposite and had said it since the
    flag existed.

    A key is in here when every template claiming its submodel
    identifier is one this project has no table for. `--profile` then
    records which template the author meant and silences `BAT-R2`; it
    cannot select a rule set, because there is none to select.
    """
    return tuple(sorted(
        key for identifier, keys in _KEYS_OF.items() for key in keys
        if not any(claimant in _known_to_the_walk()
                   for claimant in battery_tables.SHARED_SUBMODEL_IDS[identifier])))
