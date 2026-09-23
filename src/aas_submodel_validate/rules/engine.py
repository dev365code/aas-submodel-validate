"""One walk over the instance, every structural answer collected.

A generated table says what its template expects; this engine says what
one instance actually holds. It runs once per template per validation
and caches on the context -- every generated rule and every hand rule of
a pack reads from the same walk, because walking the tree once per rule
is how a validator gets quadratic, and walking it differently per rule
is how two rules disagree about what they saw.

The table is an argument, and never an optional one. It had a default,
which is a way of guessing: a rule that forgot the argument read the
first template's table. `KeyError` would have made that loud, but the
tables share a label, so forgetting is silent and the rule reports on an
element the author never wrote.

Matching policy (docs/divergences.md #1--#5, #8): an instance element
belongs to a template row when its semanticId candidate spellings
(semantics.candidate_values) intersect the row's match set. idShort is
never consulted. Elements matching no row are allowed -- the template
states a minimum, not a whitelist ("a Document might have multiple
classifications in multiple systems") -- but an unmatched element whose
identifier is *nearly* a row's (an ECLASS version drift, an IRI
differing in its last segment) is recorded for the near-miss lint,
because silently not-matching a typo is how the official example's
singular/plural mix-up would sail through.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from typing import Dict, List

from ..model import Violation
from ..semantics import (
    candidate_values,
    edit_distance,
    element_candidate_values,
    submodel_declares,
    version_stem,
)

#: How a cardinality is said. The generator has its own copy of these
#: words for the remedy; the two are compared row by row in
#: `test_generated_rules.py`, and they disagreed about the fourth shape
#: until both were made to say `any number of`.
#:
#: That fourth shape is not here, and cannot be: `(0, None)` is
#: unbounded and not required, so `count < 0` never holds and there is no
#: upper test to fail. The fallback below is what a shape outside this
#: table would get, and no shape outside it can produce a message --
#: which `test_the_walk_has_a_word_for_every_count_it_can_report` is
#: what keeps true, since a fifth cardinality in a future template would
#: otherwise arrive here silently.
_KIND_WORDS = {(1, 1): "exactly one", (0, 1): "at most one", (1, None): "one or more"}
_UNCOUNTED = "any number of"


def _shared_identifier_item(row, actual):
    """The row's own item, when the template gives the two one identifier.

    Five Handover rows do (docs/divergences.md #39): `DigitalFiles` and
    its `DigitalFile` are both `0173-1#02-ABK126#002`, and so are
    Language/LanguageCode, RefersToEntities/RefersTo,
    BasedOnReferences/BasedOn and TranslationOfEntities/TranslationOf.
    An element written as the item alone therefore matches the *list's*
    row, and it is not the wrong kind of element -- it is the right
    element with no list around it.

    Read off the table rather than listed here, so a template that stops
    sharing an identifier stops taking this branch without anyone having
    to remember to come back. `sid` must be truthy: a structural row and
    a structural child both carry `None`, and two nothings are not the
    same identifier.
    """
    return next((child for child in row["children"]
                 if row["sid"] and child["sid"] == row["sid"]
                 and child["kind"] == actual), None)


def analyze(ctx, tables) -> Dict:
    """The walk for one template, computed once per input.

    Cached per table rather than per context: an environment may carry a
    Handover submodel and a Technical Data submodel at once, and one
    cache slot would hand the second pack the first pack's answers."""
    cache = ctx.__dict__.setdefault("_smt_analysis", {})
    # The table beside its name. `rows_not_reached` used to recover it
    # by looking the name up in `sys.modules`, which answers for the six
    # vendored packs and cannot answer for a table built at run time --
    # its name is a digest. Keeping the object is how a `Table` gets
    # ordered by what it declares rather than by how its ids are spelt.
    ctx.__dict__.setdefault("_smt_tables", {})[tables.__name__] = tables
    cached = cache.get(tables.__name__)
    if cached is None:
        cached = cache[tables.__name__] = _analyze(ctx, tables)
    return cached


def file_part_violations(container, subject, value):
    """The two findings a File value can draw, for whichever rule asks.

    `HD-D7` and `TD-D2` were verbatim twins -- same three branches, same
    three sentences -- and the repair that replaced the substring test
    reached one of them. So one rule reported a defect the other stayed
    silent about, in both directions, and both are MUST. A copy is a
    fork that looks like agreement; there is one body.

    The value is folded once, here, and every branch reads the folded
    one. Folding it for two of the three questions and not the third
    left a part that is in the archive drawing a MUST because its value
    carried a leading space.
    """
    from ..container import has_scheme, part_name_problem
    from ..model import Violation

    if not isinstance(value, str):
        return
    folded = value.strip()
    if not folded or has_scheme(folded):
        return              # empty names nothing; a scheme is somewhere else's
    problem = part_name_problem(folded)
    if problem is not None:
        yield Violation(
            "this File's value is not a part name",
            subject=subject,
            # Which reason, not the stock one. Every value that failed
            # here was told it climbed out of the package -- including
            # `/aasx/files/`, which climbs nowhere and names a directory,
            # and which then got a remedy for a defect it did not have.
            detail="%s: %s" % (value, problem),
            # And its own remedy. The rule's says to add the file under
            # the name this value gives, which is right when a part is
            # missing and wrong here: no entry added under this spelling
            # is a part, and for a value that climbs out of the package
            # adding one is the last thing to do.
            fix="Correct the value so it names a part of this package. A "
                "part name is absolute, uses `/` as its only separator, "
                "and percent-encodes anything outside the unreserved and "
                "sub-delimiter characters. Adding a file under this "
                "spelling will not answer the finding -- no part can "
                "carry this name.")
    # The value as written, not the folded spelling: `part` does the
    # folding now, after it has tried what the archive actually holds.
    # Asking about a string this rule invented, and then reporting the
    # string the file carries, is how the report came to disagree with
    # the container it read.
    elif container.part(value) is None:
        yield Violation("the container holds no part at this File's value",
                        subject=subject, detail=value)


def install_file_rule(rule_id: str, tables, citation: str, only=None):
    """Register, for `tables`, the question `file_part_violations` answers.

    The body has been one since two packs' copies of it diverged in the
    field. What stayed per pack was the *call*: 02004's family installs
    it with the rest of its hand rules, and a pack outside that family
    got it only if somebody remembered. Four tables declare File rows and
    two asked, so a Digital Nameplate naming two images its package does
    not carry was judged clean -- not because the rule was missing but
    because nobody asked it on that pack's behalf.

    The labels come from the table (`row["kind"] == "File"`), so a pack
    whose template gains a File row gains the question with it.

    `only` narrows that, because a File row is not always a file the
    supplier packs. 02023 declares two and its own vendored description
    calls one of them an "Online PCF calculation methodology reference"
    -- a pointer to somebody else's published method. Asked of that row,
    this rule made it a MUST that a standards body's PDF be inside the
    supplier's package, and said so in a remedy borrowed from a pack
    where it is true (`docs/divergences.md` #55). A pack that means
    fewer than all of its File rows names the ones it means; a name that
    is not a File row of that table is a mistake and says so here rather
    than quietly asking nothing.
    """
    from ..registry import rule

    declared = tuple(row["label"] for row in tables.ROWS
                     if row["kind"] == "File")
    if not declared:
        raise ValueError(
            "%s: this table declares no File row, so there is nothing for "
            "this rule to navigate" % rule_id)
    if only is None:
        labels = declared
    else:
        unknown = [label for label in only if label not in declared]
        if unknown:
            raise ValueError(
                "%s: %s is not a File row of this table, so narrowing the "
                "rule to it would ask about nothing"
                % (rule_id, ", ".join(unknown)))
        labels = tuple(label for label in declared if label in only)

    @rule(rule_id, kind="template", prio="MUST",
          title="files named by %s exist in the container"
                % ", ".join(labels),
          # Which of a template's File rows are files the supplier packs
          # is a reading of that template and not of a clause -- IDTA
          # gives an attachment and a citation the same `modelType` --
          # so the reading is cited where this project keeps its
          # readings. `spec` promises "where the requirement lives", and
          # a template file alone does not say where this one lives.
          spec="%s; IDTA 01005 (AASX); docs/divergences.md #55" % citation,
          fix="Add the file to the .aasx under the name this File value "
              "gives, or correct the value's path. (Declaring an aas-suppl "
              "relationship for it is X4's question, not this one's.)")
    def check(ctx):
        """Only answerable when the input *is* a container; an environment
        JSON names files this rule cannot see, and silence there is
        honesty rather than laxity."""
        container = ctx.loaded.container
        if container is None:
            return
        for label in labels:
            for subject, element in instances_of(ctx, label, tables):
                yield from file_part_violations(container, subject,
                                                getattr(element, "value", None))

    return check


def near_miss_violations(ctx, tables):
    """The near-miss lint, for whichever pack asks.

    Written twice, word for word, in `handover.py` and `td.py`. A copy
    is a fork that looks like agreement, and this repository has now
    watched one of these pairs diverge in the field.
    """
    from ..model import Violation
    for subject, seen, expected in analyze(ctx, tables)["near_misses"]:
        yield Violation("semanticId almost matches the template",
                        subject=subject,
                        detail="%s, where the template says %s" % (seen, expected))


def reftype_violations(ctx, tables):
    """The reference-type lint, for whichever pack asks. Same pair."""
    from ..model import Violation
    for subject, seen, expected in analyze(ctx, tables)["reftype_drift"]:
        yield Violation(
            "the reference type differs from the template's",
            subject=subject,
            detail="%s, where the template uses %s" % (seen, expected),
            fix=reftype_remedy(expected))


def dangling_violation(subject, keys, label):
    """A reference that resolves to nothing, for whichever rule asks.

    This pair had already come apart: the handover rule carried
    `dangling_remedy(label)` -- a sentence written per label because the
    standing one told the author of a dangling `BasedOn` to add an
    Entity -- and the technical-data rule, saying the same words, did
    not.
    """
    from ..model import Violation
    from .handover import dangling_remedy
    return Violation(
        "the reference walks to nothing in this submodel",
        subject=subject,
        detail="no element at key path %s"
               % " / ".join(key.value for key in keys[1:]),
        fix=dangling_remedy(label))


def matched_submodels(ctx, tables) -> List:
    """The instances a table answers for.

    Two selectors used to decide what gets judged -- this one, and
    `detect.matched` for the count and the presence rule -- and only one
    of them learned that a submodel declaring `kind: Template` is a
    specification rather than an instance. The 02004 template stopped
    being judged and the other two went on being judged, which is the
    shape this project keeps meeting: a repair that reaches one of two
    siblings. `is_template` is asked here too, and it is the same
    function.

    Computed once per table, for the same reason and with the same key
    as `analyze`. Every generated rule opens by asking this, and the
    answer cannot differ between two rules of one table -- the input,
    the selection and the stand-down are all fixed for the life of a
    context. Asked per rule it is a scan of every submodel per rule,
    and both numbers are the caller's: measured at the row bound, a
    supplied table of 9,900 rows against 500 submodels spent 6.48 of
    the run's 9.53 seconds deciding the same thing over again.

    Nothing may mutate what comes back -- the list is shared, exactly
    as `analyze`'s record is.
    """
    cache = ctx.__dict__.setdefault("_smt_matched", {})
    cached = cache.get(tables.__name__)
    if cached is None:
        cached = cache[tables.__name__] = _matched_submodels(ctx, tables)
    return cached


def _matched_submodels(ctx, tables) -> List:
    from .detect import instances
    # A table the caller supplied takes an identifier over, and a pack
    # that also answers for it stands down -- reported, never silent.
    # `getattr` because a context built before this existed has no such
    # field and a table with no identifier of its own cannot be taken
    # over anyway.
    taken = getattr(ctx, "taken_over", frozenset())
    if taken and tables.TEMPLATE_SEMANTIC_ID in taken \
            and not getattr(tables, "_supplied", False):
        return []
    return [submodel for submodel in instances(ctx.loaded)
            if submodel_declares(submodel, tables.TEMPLATE_SEMANTIC_ID)
            and ctx.selection.answers(submodel, tables)]


def _analyze(ctx, tables) -> Dict:
    result = {
        "violations": {},      # row id -> [Violation]
        "instances": {},       # row id -> [(subject path, element)]
        "near_misses": [],     # (subject path, seen value, expected value)
        "idshort_drift": [],   # (subject, id_short, pattern, is a list child)
        "reftype_drift": [],   # (subject path, seen type, template type)
        #: Rule ids that were below a scope this walk did not enter,
        #: *proposed*. Not an answer on its own: the same row is walked
        #: once per item of a list, so a row missed in one item and
        #: asked in another lands here and is subtracted afterwards
        #: against `instances`. Reporting this list directly said
        #: twenty-six rules went unasked when twenty-two of them ran.
        "lost_candidates": [],
        #: (subject, seen identifier, unasked rule ids, resembles-or-None)
        #: for each element this walk could not place. Same standing as
        #: `lost_candidates` and subtracted the same way.
        "unmatched": [],
        #: (subject, identifier) for each nested copy of a self-containing
        #: row that this walk did not enter. Same standing as the two
        #: above: a statement about the run, not about the file.
        "not_entered": [],
        #: (where, row id, label, unasked ids, reason) per row whose
        #: scope this walk never opened. See `model.NotExamined`.
        "not_examined": [],
    }
    for submodel in matched_submodels(ctx, tables):
        root = submodel.id_short or "submodel"
        reference = submodel.semantic_id
        expected = tables.TEMPLATE_SUBMODEL_SID_TYPE
        # One record per submodel, merged after. The walk used to write
        # into a single one, and the subtraction that takes a proposed
        # loss back off -- "some other scope asked this row" -- then
        # reached across submodels: a rule asked of one document erased
        # the claim that another document never asked it. Measured on
        # the Handover fixture, a drifted submodel reports thirty-six
        # rules unasked on its own and five with an intact copy of
        # itself beside it, about the drifted one either way.
        #
        # Within a submodel the subtraction is right and stays: a list
        # walks the same rows once per item, and a row missed in the
        # second item was entered in the first.
        per = {"violations": {}, "instances": {}, "near_misses": [],
               "idshort_drift": [], "reftype_drift": [], "lost_candidates": [],
               "unmatched": [], "not_entered": [], "not_examined": []}
        if reference is not None and expected and reference.type.value != expected:
            per["reftype_drift"].append((root, reference.type.value, expected))
        _scope(tables.TREE, submodel.submodel_elements or [], root, per,
               in_list=False, citation=tables.TEMPLATE_CITATION)
        asked_here = set(per["instances"])
        per["lost_candidates"] = [rule_id for rule_id in per["lost_candidates"]
                                  if rule_id not in asked_here]
        # The same subtraction, per element, and a record whose loss is
        # entirely taken back is not reported at all: that is what keeps a
        # conformant file carrying an extra element silent (#19).
        survived = []
        for subject, seen, unasked, resembles in per["unmatched"]:
            kept = tuple(r for r in unasked if r not in asked_here)
            if kept:
                survived.append((subject, seen, kept, resembles))
        per["unmatched"] = survived
        for key in ("violations", "instances"):
            for row_id, entries in per[key].items():
                result[key].setdefault(row_id, []).extend(entries)
        for key in ("near_misses", "idshort_drift", "reftype_drift",
                    "lost_candidates", "unmatched", "not_entered",
                    "not_examined"):
            result[key].extend(per[key])
    return result



def _descendant_ids(row) -> List[str]:
    """Every rule id beneath a row, which is what leaves the run with it."""
    out = []
    for child in row["children"]:
        out.append(child["id"])
        out.extend(_descendant_ids(child))
    return out


def unmatched_elements(ctx) -> List:
    """The elements this run could not place, with what each one cost.

    `rows_not_reached` answers "how many rules went unasked"; this answers
    "which element left them unasked", which is the question a reader has
    when the count is not zero. Same standing: a statement about the run,
    not about the file, and it moves no verdict (`docs/divergences.md`
    #19, #23).

    Deduplicated by element, keeping the largest loss recorded for it: the
    same element is walked once per item of a list.
    """
    from ..model import UnmatchedElement

    analysed = ctx.__dict__.get("_smt_analysis") or {}
    best = {}
    for analysis in analysed.values():
        for subject, seen, unasked, resembles in analysis.get("unmatched", ()):
            previous = best.get((subject, seen))
            if previous is None or len(unasked) > len(previous[0]):
                best[(subject, seen)] = (unasked, resembles)
    return [UnmatchedElement(subject=subject, seen=seen,
                             unasked=unasked, resembles=resembles)
            for (subject, seen), (unasked, resembles) in sorted(best.items())]


def scope_not_examined(ctx) -> List:
    """One record per row whose scope no walk in this run opened.

    Deduplicated by (where, row): a row is walked once per item of a
    list, and a reader counting the list would read three items as three
    times the loss. Where the same row is `absent` in one scope and has
    a stranger beside it in another, the stranger wins -- it is the more
    specific fact and the one a reader can act on.
    """
    from ..model import NotExamined

    analysed = ctx.__dict__.get("_smt_analysis") or {}
    best = {}
    for analysis in analysed.values():
        for where, rule, label, unasked, because in analysis.get("not_examined", ()):
            key = (where, rule)
            if key not in best or because == "unclaimed-element-present":
                best[key] = (label, unasked, because)
    return [NotExamined(where=where, rule=rule, label=label,
                        unasked=unasked, because=because)
            for (where, rule), (label, unasked, because) in sorted(best.items())]


def repeats_not_entered(ctx) -> List:
    """(subject, identifier) for every nested copy of a self-containing
    row this run did not walk into, deduplicated and in path order."""
    analysed = ctx.__dict__.get("_smt_analysis") or {}
    seen = set()
    for analysis in analysed.values():
        seen.update(analysis.get("not_entered", ()))
    return sorted(seen)


def rows_not_reached(ctx) -> List[str]:
    """Rule ids this run never put, in the order the tables declare them.

    Two steps, and the second is the one the first version of this
    skipped. `_scope` proposes the rows below a scope it did not enter;
    those proposals are per scope, and the same rows are walked once per
    item of a list. So every proposal is checked against `instances` --
    the walk's own record of the rows it looked at, anywhere -- and a
    row some other scope asked is taken back off. Without that
    subtraction a two-item list reported twenty-six rules unasked with
    twenty-two of them run, and one of the twenty-two printed as an
    error in the same report.

    A row is proposed only where the reader has already reported
    something that explains the loss: a near-miss in that scope, or an
    element of the wrong kind claiming the row. There is no way to tell
    a supplier's own element from a template element with a typo by
    looking at it, and the template states a minimum rather than a
    whitelist (docs/divergences.md #19), so guessing was what made a
    conformant file with one extra property report a rule unasked.
    """
    analysed = ctx.__dict__.get("_smt_analysis") or {}
    missed = []
    for result in analysed.values():
        # Already subtracted, and subtracted per submodel: `_analyze`
        # takes each document's proposals against the rows that document
        # asked. Doing it here instead made the unit the whole run, so a
        # rule asked of one submodel erased the claim that another never
        # asked it.
        missed.extend(result["lost_candidates"])
    # Ordered by the tables, deduplicated: one unrecognised element in a
    # list of three strands the same rows three times, and a reader
    # counting the list would read that as three times the loss.
    order = {row["id"]: index
             for index, row in enumerate(_all_rows(ctx, analysed))}
    # The id breaks the tie. Everything the tables do not place shares one
    # position, `sorted` is stable, and what it is stable *over* is a set
    # -- whose iteration order is string-hash order and is randomised per
    # process. Measured on that shape: five interpreters, five orders,
    # same input. A fallback that is only correct while nothing takes it
    # is not correct.
    #
    # This one said it was unreachable "because every analysed table is
    # an imported module", and named the moment that would stop being
    # true. `--template` was that moment: a `Table` is not in
    # `sys.modules`, so every run-time id landed here and came back
    # sorted by its own spelling -- which past ninety-nine rows is not
    # the template's order at all, ids being padded to two digits. The
    # tables are kept beside their names now, so the fallback is back to
    # holding nothing and is still here for when it does.
    return sorted(set(missed), key=lambda rid: (order.get(rid, len(order)), rid))


def _all_rows(ctx, analysed) -> List:
    """Every row of every table this run analysed, in their order.

    The tables are taken from the context, where `analyze` puts each one
    beside the name it caches under. `sys.modules` stood here and
    answered for the six vendored packs only; a table built from a
    caller's file has a digest for a name and was silently contributing
    no rows at all.
    """
    kept = ctx.__dict__.get("_smt_tables") or {}
    rows = []
    for name in analysed:
        tables = kept.get(name) or sys.modules.get(name)
        if tables is not None:
            rows.extend(tables.ROWS)
    return rows


def idshort_remedy(in_list: bool, pattern: str) -> str:
    """Two sentences, because the lint reads two situations and only one
    of them is about tidiness.

    Five of the six rows that carry an idShort pattern sit directly
    inside a SubmodelElementList, where AASd-120 forbids an idShort
    outright -- measured: aas-core3 raises it, six times, on a fixture
    that is otherwise clean. On those rows this lint can only fire on a
    file that already breaks the metamodel, and the one sentence it used
    to ship told the author to *rename* what must not be there. Following
    it left the violation in place.
    """
    if in_list:
        return ("Remove this idShort. A submodel element directly inside "
                "a SubmodelElementList must not carry one (AASd-120), so "
                "renaming it to the template's suggestion leaves a "
                "metamodel violation the file already has.")
    return ("Rename to the template's suggested pattern (%s). Any unique "
            "idShort is legal here; this is tidiness, not conformance."
            % pattern)


def reftype_remedy(expected: str) -> str:
    """The sentence a reference-type lint ships, in one place.

    Three packs raise this lint and two of them had a copy of the
    sentence. The copies drifted: one grew `.upper()` and a tuple so that
    an empty type would not read "an " -- `"" in "AEIOU"` is True -- and
    the other kept the arithmetic that was fixed. Neither drift was
    reachable and both would have shipped the moment it became so, which
    is what a second copy is for.
    """
    article = "an" if expected[:1].upper() in tuple("AEIOU") else "a"
    return ("Use %s %s here, as the template does; the value matched, "
            "so this is interoperability polish, not a failure."
            % (article, expected))


def _subject(path: str, element, index: int, shared=()) -> str:
    """Where an element sits, as a reader reads it.

    An index is appended in two cases and neither is decoration. An
    element with no idShort has no name to print. And an element whose
    idShort a sibling also carries has a name that does not identify it:
    the metamodel forbids that, this project relays the violation as a
    warning rather than refusing the file, so such a file is judged and
    what it is judged to have done has to be attributable. Before this,
    two elements produced the same string and the record keyed on it
    merged them -- one record for what two elements did
    (`docs/divergences.md` #53).

    `shared` is the idShorts that repeat in this element's own scope, so
    an element whose name is its own keeps the subject it always had.
    Disambiguating everything would have changed the subject of every
    finding this project prints, which is a wider change than the defect.
    """
    name = element.id_short or "[%d]" % index
    if element.id_short and element.id_short in shared:
        name = "%s[%d]" % (name, index)
    return "%s/%s" % (path, name)


def _matches_row(candidates, main_empty: bool, kind_name: str, row, in_list: bool) -> bool:
    """Whether an element belongs to `row`. Its candidate spellings
    (semanticId and supplementals) intersect the row's match set -- or,
    inside a list, a child with no *main* semanticId of its own counts for
    the sole child row when its element kind agrees. The fallback keys on
    the main semanticId being absent, not on having no identifiers at all:
    the official example's list children carry supplemental language-code
    ids yet are still the list's own items (counting them absent failed
    the reference material). idShort is never consulted."""
    if candidates & set(row["match"]):
        return True
    return in_list and main_empty and kind_name == row["kind"]


def _repeats_below(element, sid, subject):
    """Every descendant of `element` carrying `sid`, with where it sits.

    The whole chain and not the immediate children: the walk does not
    enter the first copy, so it would never meet the second. Measured on
    a file three deep, counting only the immediate ones reported one
    copy of two.
    """
    found = []
    stack = [(child, subject) for child in _sub_elements(element)]
    while stack:
        child, where = stack.pop()
        here = "%s/%s" % (where, child.id_short or "?")
        if sid in element_candidate_values(child):
            found.append((here, sid))
        stack.extend((below, here) for below in _sub_elements(child))
    return found


def _sub_elements(element):
    """The submodel elements a container holds: a
    SubmodelElementCollection or List keeps them in `value`, an Entity in
    `statements` (aas-core3). The generator descends the same two, so the
    walk and the table agree on what a scope contains. A Property's `value`
    is its string, not a list of elements, and is excluded here; a kind
    that carries neither yields nothing.

    A MultiLanguageProperty's `value` *is* a list -- of language strings,
    not of elements -- so what is gathered is filtered to what carries a
    `semantic_id`, which is the first thing every caller reads. The
    generator draws the same line from the other side, taking a child only
    where a modelType is declared, and without this the two disagreed:
    navigating an MLP raised `AttributeError` and was reported as the rule
    failing to run, about a file that is fine."""
    items = []
    for attribute in ("value", "statements"):
        got = getattr(element, attribute, None)
        if isinstance(got, list):
            items.extend(x for x in got if hasattr(x, "semantic_id"))
    return items


def _scope(rows, elements, path: str, result, in_list: bool,
           citation: str) -> None:
    indexed = [(index, element, element_candidate_values(element),
                not candidate_values(element.semantic_id))
               for index, element in enumerate(elements)]
    #: idShorts more than one child of this scope carries. Counted once
    #: here rather than asked per element, and read by every `_subject`
    #: call below, so the four of them cannot disagree about which
    #: element a finding is about.
    names = Counter(element.id_short for element in elements if element.id_short)
    shared = {name for name, count in names.items() if count > 1}
    claimed = set()
    #: Per scope, not per run: the same row id appears in every item of a
    #: list, and a row that matched in one item has been entered.
    claimed_by = {}

    for row in rows:
        # One element belongs to at most one row: the first row it matches
        # claims it. Without this a shared identifier would be counted
        # under two rows and both cardinalities would be wrong. (Sibling
        # rows in this template share no match value, so order is not load
        # bearing today; the guard is what keeps a future template honest.)
        matched = [(index, element) for index, element, candidates, main_empty in indexed
                   if index not in claimed
                   and _matches_row(candidates, main_empty, type(element).__name__,
                                    row, in_list)]
        claimed.update(index for index, _ in matched)
        if matched:
            claimed_by[row["id"]] = True

        # Only kind-matching elements go into `instances`: a Property
        # wearing a File's id is a kind violation (reported below), not a
        # file. The child lookups already tolerate the wrong kind, so what
        # this stops is not a crash but a misreading -- handed on, HD-D7
        # looked the Property's string up as a part name and reported the
        # archive missing a file nobody declared.
        result["instances"].setdefault(row["id"], []).extend(
            (_subject(path, element, index, shared), element)
            for index, element in matched if type(element).__name__ == row["kind"])

        low, high = row["card"]
        count = len(matched)
        if count < low or (high is not None and count > high):
            result["violations"].setdefault(row["id"], []).append(Violation(
                "the template expects %s '%s' here; found %d"
                % (_KIND_WORDS.get((low, high), _UNCOUNTED), row["label"], count),
                subject=path,
                detail=("elements: %s" % ", ".join(
                    _subject(path, e, i, shared) for i, e in matched)) if matched else None))
            # No `continue`: a wrong count must not silence the per-element
            # checks or the recursion. A misplaced element hiding a whole
            # subtree's real findings is the failure this validator exists
            # to prevent, not to commit.

        for index, element in matched:
            subject = _subject(path, element, index, shared)
            actual = type(element).__name__
            if actual != row["kind"]:
                # Its own remedy. A generated row's rule is about how
                # many of an element there are, and its prescription
                # says to provide one -- which, inherited here, tells
                # the reader to add a second copy of the element they
                # are looking at, and that is the cardinality finding
                # this rule really is about.
                # The remedy has to survive being followed. Where the
                # template gives a list and its item one identifier,
                # "change this into a list" is advice to delete the
                # content: the reader ends with an empty list and the
                # next run reports the item missing instead.
                item = _shared_identifier_item(row, actual)
                if item is not None:
                    remedy = ("Wrap this element in a %s named '%s' and "
                              "leave it inside as the list's item. The "
                              "template gives the list and its item the "
                              "same semanticId, so this element matched "
                              "the list's row -- changing it into a %s "
                              "would empty it and report '%s' missing "
                              "instead." % (row["kind"], row["label"],
                                            row["kind"], item["label"]))
                else:
                    remedy = ("Change this element from a %s to a %s. It is "
                              "the right element -- the semanticId matched "
                              "-- so adding another would be a second "
                              "finding, not a fix for this one."
                              % (actual, row["kind"]))
                result["violations"].setdefault(row["id"], []).append(Violation(
                    "'%s' must be a %s" % (row["label"], row["kind"]),
                    subject=subject, detail="found a %s" % actual,
                    spec="%s, the element's declared modelType" % citation,
                    fix=remedy))
                # Reported, and not recursed into -- so everything
                # below this row left the run with it, and nothing said
                # so. Twenty-one rules on the measured case, nine of
                # them mandatory, behind one `Property` wearing a list's
                # identifier.
                lost = tuple(_descendant_ids(row))
                result["lost_candidates"].extend(lost)
                # And which element did it, which here needs no guessing at
                # all: this one claimed the row, and the finding just above
                # already prints its subject. This was the only trigger with
                # no record, so the terminal fell back to "their element is
                # not one the template describes" about an element it could
                # name exactly -- worse evidence than the near miss it did
                # report for.
                if lost:
                    result["unmatched"].append(
                        (subject, sorted(element_candidate_values(element))[0]
                         if element_candidate_values(element) else row["sid"],
                         lost, row["sid"]))
                continue
            # What a list says it will hold, against what the template
            # says it holds. The metamodel asks whether the items agree
            # with the list's own declaration (AASd-108) and whether a
            # value type is present where one is needed (AASd-109); both
            # are relayed and neither compares the declaration to the
            # template, which is not a question the metamodel can ask.
            #
            # Everywhere else the item row catches this first: an item
            # row of `1..*` cannot be satisfied by an empty list. Four
            # rows are `0..*`, and there a list that declares the wrong
            # item type and carries none is metamodel-clean, satisfies
            # every row, and said nothing at all.
            #
            # Only a disagreement -- but not for the reason this comment
            # used to give. It said `typeValueListElement` is optional in
            # the metamodel, and it is not: `aas_core3` takes it as a
            # required argument and both JSON and XML deserialisation
            # refuse a file without one, before any rule here runs. The
            # optional field is `valueTypeListElement`, one letter-order
            # away and a different thing. So `listed is not None` cannot
            # fire, and neither can its twin below on `valueType`; both
            # stay as the kind of guard that costs nothing and would
            # turn a relaxed metamodel into a finding rather than an
            # `AttributeError`. `test_engine_seam` pins that, so the day
            # either field becomes optional the guards stop being
            # unreachable and somebody is told.
            listed = getattr(element, "type_value_list_element", None)
            if row["list_type"] and listed is not None and listed.value != row["list_type"]:
                result["violations"].setdefault(row["id"], []).append(Violation(
                    "'%s' is declared to hold %s; the template holds %s"
                    % (row["label"], listed.value, row["list_type"]),
                    subject=subject, detail="typeValueListElement is %s" % listed.value,
                    spec="%s, the list's declared typeValueListElement" % citation,
                    fix="Change this list's typeValueListElement from %s to "
                        "%s. This is about what the list says it will hold, "
                        "not about what is in it -- an empty list declaring "
                        "the wrong item type is the case nothing else here "
                        "reports." % (listed.value, row["list_type"])))
            declared = getattr(element, "value_type", None)
            if row["value_type"] and declared is not None and declared.value != row["value_type"]:
                result["violations"].setdefault(row["id"], []).append(Violation(
                    "'%s' must carry valueType %s" % (row["label"], row["value_type"]),
                    subject=subject, detail="found %s" % declared.value,
                    spec="%s, the element's declared valueType" % citation,
                    fix="Change this element's valueType from %s to %s. "
                        "The element itself is the right one; only the "
                        "type it declares for its value is not."
                        % (declared.value, row["value_type"])))
            # A required element that carries nothing. Cardinality is
            # the generated rules' question and content is the hand
            # rules', and this fell between them: every hand rule guards
            # on `value is not None` -- correctly, since an absent value
            # is not theirs to report -- and the count was satisfied by
            # the element being there. A Technical Data file with the
            # value deleted from all nine of its required properties drew
            # nothing at all and left by 0.
            #
            # The count is satisfied in form and the requirement is not.
            # It is the tool's own promise that goes false here: "the
            # template requires this element" answered yes about an
            # element holding nothing, which is the shape of pass this
            # project treats as worst.
            #
            # Absent, not empty. `value: ""` is the empty string, which
            # *is* a value of that type, and calling it nothing is a
            # reading about content rather than about presence -- the
            # metamodel draws the same line. Measured and left alone
            # deliberately; `docs/divergences.md` #40.
            #
            # MUST, and measured against what the standards body
            # publishes before raising it there: across IDTA's own 02004
            # example and the three 02003 samples, all 102 properties
            # carry a value and none is absent, so this costs nothing on
            # published material.
            if (low >= 1 and row["kind"] == "Property"
                    and getattr(element, "value", None) is None):
                result["violations"].setdefault(row["id"], []).append(Violation(
                    "'%s' is required here and carries no value" % row["label"],
                    subject=subject,
                    detail="the element is present and its value is absent",
                    fix="Give this '%s' a value. The element is the right "
                        "one and it is in the right place -- do not add "
                        "another, which is what the count's own advice "
                        "would tell you and would leave two of them "
                        "empty." % row["label"]))
            if row["allowed_idshort"] and element.id_short \
                    and not re.match(row["allowed_idshort"], element.id_short):
                result["idshort_drift"].append(
                    (subject, element.id_short, row["allowed_idshort"], in_list))
            reference = element.semantic_id
            if row["sid_type"] and reference is not None \
                    and reference.type.value != row["sid_type"]:
                result["reftype_drift"].append(
                    (subject, reference.type.value, row["sid_type"]))
            if row["children"]:
                _scope(row["children"], _sub_elements(element),
                       subject, result,
                       in_list=(row["kind"] == "SubmodelElementList"),
                       citation=citation)
            # A row the table marked as containing itself. The repeating
            # child was left unexpanded so the table stays finite
            # (docs/divergences.md #48), and nothing here read the
            # marker -- so an instance's nested copies were walked by
            # nobody and the report said nothing at all. How to re-apply
            # the scope is what #48 defers to the first vendored
            # self-containing template; what cannot wait for that is
            # saying the copies were not entered.
            if row.get("recurses"):
                result["not_entered"].extend(
                    _repeats_below(element, row["recurses"], subject))

    # What this scope did not enter, and only where the reader has
    # already said something is wrong.
    #
    # The first version asked whether any element here went unclaimed
    # and had a truthy `value`. That is not a test for children -- a
    # `Property`'s value is its string -- so a manufacturer's own
    # property tripped it, and `docs/divergences.md` #19 promises those
    # pass without comment. It also missed an empty collection, which
    # genuinely could have opened a subtree. Both directions wrong, on a
    # guess about what an unidentified element was meant to be.
    #
    # There is no way to tell a supplier's own element from a template
    # element with a typo by looking at it; that is the policy question
    # #23 names and it is still open. So this claims a loss only where
    # the reader has already reported a defect that explains it: the
    # near-miss lint fired here, or a row matched an element of the
    # wrong kind and the walk therefore did not recurse.
    #: How many near misses stood before *this* scope looked for one.
    #:
    #: Taken here rather than at the top of the function, which is where
    #: it was: the recursion into children happens inside the row loop
    #: above, between the two lines, so the count grew from every
    #: descendant and each ancestor read that as "a near miss was found
    #: here". Measured on the Handover fixture -- dropping
    #: `DocumentVersions` reported no unasked rule, and dropping it *and*
    #: drifting `ClassId` in another branch reported twenty-three, all of
    #: them about `DocumentVersions`. `docs/divergences.md` #23 says the
    #: claim is about the scope the near miss was found in.
    #: (subject, seen, row) for each element a near miss fired on, taken
    #: here rather than re-derived afterwards, which is also what tells
    #: this scope a near miss fired *in it*: the list is per scope, and the
    #: claim #23 makes is about the scope the near miss was found in.
    #: Re-deriving membership afterwards by asking
    #: which elements *carry* one of the identifiers a near miss named
    #: caught bystanders: an element whose own identifier matched nothing
    #: but which carried the drifted one as a supplemental was handed the
    #: neighbour's loss, and being first alphabetically it was the element
    #: the terminal named.
    near_here = []
    for index, element, candidates, _main_empty in indexed:
        if index in claimed or not candidates:
            continue
        subject = _subject(path, element, index, shared)
        for row in rows:
            near = _near_miss(candidates, row["match"])
            if near:
                result["near_misses"].append((subject,) + near)
                near_here.append((subject, near[0], near[1], row))
                break

    # What this scope did not enter, and which element left it unentered.
    #
    # This used to be claimed only where a near miss had already explained
    # the loss, because the template states a minimum and not a whitelist
    # (#19) and guessing made a conformant file with one extra property
    # report rules unasked. The guess is gone rather than widened: what is
    # recorded is not that the element is wrong but that this run did not
    # look inside a row, and an element with nothing unasked beneath it
    # produces no record at all -- so the conformant-plus-extension case
    # still says nothing, without anyone having to guess about it.
    unentered = []
    for row in rows:
        if row["children"] and not claimed_by.get(row["id"]):
            unentered.extend(_descendant_ids(row))
    # The same rows, reported whether or not anything explains them.
    # `lost_candidates` below is claimed only where the reader has
    # already said something is wrong, and that restriction is right for
    # a claim about *who* -- but it took the scope down with the blame,
    # so a container wearing an identifier the template does not name
    # passed with every published number identical to a clean run.
    # `because` is a fact about the same scope and not a cause: an
    # element no row claimed may be a legitimate extension (#19) and
    # nothing here says which.
    strangers = sorted(
        _subject(path, element, index, shared)
        for index, element, candidates, _empty in indexed
        if index not in claimed and candidates)
    for row in rows:
        if not row["children"] or claimed_by.get(row["id"]):
            continue
        lost = tuple(_descendant_ids(row))
        if not lost:
            continue
        result["not_examined"].append(
            (path, row["id"], row["label"], lost,
             "unclaimed-element-present" if strangers else "absent"))
    # A loss is claimed only where something explains it, and that guard
    # stays: a row left unclaimed because the file legitimately does not
    # carry an optional element is not a loss anyone caused, and blaming a
    # supplier's own element for it is the noise #19 and #23 warn about.
    # What this adds is *who*, not a new reason to claim a loss. The
    # comparison still requires the whole head of an identifier to match, so
    # a typo inside an earlier segment -- and a whole segment added or
    # dropped, which is how 02002's specification differs from its template
    # (#51) -- explains nothing and stays unreported (#22), deliberately:
    # #23 measures why no bound can separate those from a real neighbour.
    # Attributed to the element the near-miss lint already named, and to no
    # other: this adds *who* to a loss the reader was already told about, and
    # invents no new reason to claim one. Widening the trigger to structural
    # similarity is the half of #23 deliberately not built -- seventeen of the
    # eighteen rows a middle-segment typo silences are ECLASS IRDIs, whose
    # adjacent codes are different real properties, so no bound separates a
    # typo from a legitimate neighbour without a dictionary this project does
    # not carry (`test_the_rows_a_middle_typo_silences_are_identifiers_
    # nothing_can_separate` keeps that argument loud).
    if unentered and near_here:
        # A row's subtree is that row's loss, counted once. Handing every
        # unplaceable element the whole scope's loss made each answer for
        # the others (two drifted siblings each got the other's children,
        # and the per-element counts summed to twice what was lost); and
        # handing it to each element that resembles the *same* row -- which
        # is what a version bump on every item of a list produces, the most
        # likely real cause -- brought the double count straight back. So
        # the group is keyed by the row and the identifier that drifted, and
        # the first element of a group speaks for it: those siblings carry
        # one drift between them, not one each. Counting a loss twice is the
        # over-attribution #23 records an earlier version making.
        grouped = {}
        for subject, seen, expected, row in near_here:
            if claimed_by.get(row["id"]) or not row["children"]:
                continue
            grouped.setdefault((row["id"], seen), (row, expected, subject))
        for (_row_id, seen), (row, expected, subject) in grouped.items():
            lost = tuple(_descendant_ids(row))
            if lost:
                result["unmatched"].append((subject, seen, lost, expected))
        result["lost_candidates"].extend(unentered)


def _near_miss(candidates, match_values):
    """(seen, expected) when a candidate almost matches a row value: same
    ECLASS stem with a different version suffix, or the same IRI namespace
    with a *similar* last segment. Similarity is bounded (a small edit
    distance) so a genuine singular/plural typo is caught while an
    unrelated neighbour that merely shares a directory is not."""
    for seen in sorted(candidates):
        for expected in match_values:
            seen_stem, expected_stem = version_stem(seen), version_stem(expected)
            if seen_stem and seen_stem == expected_stem and seen != expected:
                return (seen, expected)
            if "://" in seen and "://" in expected and seen != expected:
                seen_head, _, seen_tail = seen.rstrip("/").rpartition("/")
                exp_head, _, exp_tail = expected.rstrip("/").rpartition("/")
                # Counted as far as the bound. `edit_distance` stops at
                # `cap` and answers `cap + 1`, and at its default of 6 a
                # bound of 7 or more -- a last segment of 28 characters --
                # was met by any pair at all (docs/divergences.md #43).
                bound = max(3, len(exp_tail) // 4)
                if (seen_head and seen_head == exp_head
                        and edit_distance(seen_tail, exp_tail, cap=bound) <= bound):
                    return (seen, expected)
    return None


# -- navigation for the hand rules ------------------------------------------
def resolve_in_submodel(submodel, keys) -> bool:
    """Can a ModelReference's key path be walked inside `submodel`?

    Children are found by idShort -- or by position when the containing
    element is a SubmodelElementList, whose children the metamodel
    addresses by index. Index resolution must work even when a list child
    carries an (illegal) idShort: the official example does exactly that,
    and the idShort is its AASd-120 violation, not the reference's.
    """
    scope = submodel.submodel_elements or []
    in_list = False
    steps = keys[1:]
    for position_in_path, key in enumerate(steps):
        found = None
        for position, element in enumerate(scope):
            if element.id_short == key.value or (in_list and str(position) == key.value):
                found = element
                break
        if found is None:
            return False
        if position_in_path == len(steps) - 1:
            return True                        # the last key resolved to an element
        value = getattr(found, "value", None)
        if not isinstance(value, list):
            return False                       # more keys, but this element is a leaf
        in_list = type(found).__name__ == "SubmodelElementList"
        scope = value
    return True



def instances_of(ctx, label: str, tables):
    """(subject path, element) pairs the walk matched to the row named
    `label` (template idShort, or the PDF's item name for unnamed rows)."""
    return analyze(ctx, tables)["instances"].get(tables.BY_LABEL[label]["id"], [])


def _child_matches(child, row, parent_is_list: bool) -> bool:
    return _matches_row(element_candidate_values(child),
                        not candidate_values(child.semantic_id),
                        type(child).__name__, row, parent_is_list)


def child_of(element, label: str, tables):
    """The first direct child of `element` matching the row `label`, or
    None. Uses the same matching as the walk -- including the in-list
    kind fallback -- so a hand rule and the generated layer never
    disagree about which child is which (docs/divergences.md #11)."""
    row = tables.BY_LABEL[label]
    parent_is_list = type(element).__name__ == "SubmodelElementList"
    # The same guard `children_of` has had since it was written. An
    # element declared as the wrong kind has a `value` that is a string,
    # or none at all: a `Property` where a collection belongs gives one,
    # a `Range` or a `Capability` has no `value` attribute. Iterating the
    # first yields characters and the second raises, and either way the
    # rule was reported as having crashed -- "a defect in the validator,
    # not in your file" -- about a defect in the file that the generated
    # rule beside it names exactly. Absence is what this returns for any
    # child it cannot find, and a child of the wrong kind is one of
    # those; the generated cardinality and kind rules are what speak.
    for child in _sub_elements(element):
        if _child_matches(child, row, parent_is_list):
            return child
    return None


def children_of(element, label: str, tables):
    row = tables.BY_LABEL[label]
    parent_is_list = type(element).__name__ == "SubmodelElementList"
    return [child for child in _sub_elements(element)
            if _child_matches(child, row, parent_is_list)]


def property_value(element, label: str, tables):
    """The string value of `element`'s child property matching `label`,
    or None when absent (cardinality is the generated rules' finding,
    not the hand rules')."""
    child = child_of(element, label, tables)
    value = getattr(child, "value", None) if child is not None else None
    return value if isinstance(value, str) else None
