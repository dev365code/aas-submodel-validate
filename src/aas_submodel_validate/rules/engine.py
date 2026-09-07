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


def analyze(ctx, tables) -> Dict:
    """The walk for one template, computed once per input.

    Cached per table rather than per context: an environment may carry a
    Handover submodel and a Technical Data submodel at once, and one
    cache slot would hand the second pack the first pack's answers."""
    cache = ctx.__dict__.setdefault("_smt_analysis", {})
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
    """
    from .detect import instances
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
               "idshort_drift": [], "reftype_drift": [], "lost_candidates": []}
        if reference is not None and expected and reference.type.value != expected:
            per["reftype_drift"].append((root, reference.type.value, expected))
        _scope(tables.TREE, submodel.submodel_elements or [], root, per,
               in_list=False)
        asked_here = set(per["instances"])
        per["lost_candidates"] = [rule_id for rule_id in per["lost_candidates"]
                                  if rule_id not in asked_here]
        for key in ("violations", "instances"):
            for row_id, entries in per[key].items():
                result[key].setdefault(row_id, []).extend(entries)
        for key in ("near_misses", "idshort_drift", "reftype_drift",
                    "lost_candidates"):
            result[key].extend(per[key])
    return result



def _descendant_ids(row) -> List[str]:
    """Every rule id beneath a row, which is what leaves the run with it."""
    out = []
    for child in row["children"]:
        out.append(child["id"])
        out.extend(_descendant_ids(child))
    return out


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
    order = {row["id"]: index for index, row in enumerate(_all_rows(analysed))}
    return sorted(set(missed), key=lambda rid: order.get(rid, len(order)))


def _all_rows(analysed) -> List:
    rows = []
    for module_name in analysed:
        tables = sys.modules.get(module_name)
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


def _subject(path: str, element, index: int) -> str:
    return "%s/%s" % (path, element.id_short or "[%d]" % index)


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


def _scope(rows, elements, path: str, result, in_list: bool) -> None:
    indexed = [(index, element, element_candidate_values(element),
                not candidate_values(element.semantic_id))
               for index, element in enumerate(elements)]
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

        # Only kind-matching elements are navigable, so only they go into
        # `instances`: a Property wearing a collection's id is a kind
        # violation (reported below), not something the hand rules should
        # try to walk into and crash on.
        result["instances"].setdefault(row["id"], []).extend(
            (_subject(path, element, index), element)
            for index, element in matched if type(element).__name__ == row["kind"])

        low, high = row["card"]
        count = len(matched)
        if count < low or (high is not None and count > high):
            result["violations"].setdefault(row["id"], []).append(Violation(
                "the template expects %s '%s' here; found %d"
                % (_KIND_WORDS.get((low, high), _UNCOUNTED), row["label"], count),
                subject=path,
                detail=("elements: %s" % ", ".join(
                    _subject(path, e, i) for i, e in matched)) if matched else None))
            # No `continue`: a wrong count must not silence the per-element
            # checks or the recursion. A misplaced element hiding a whole
            # subtree's real findings is the failure this validator exists
            # to prevent, not to commit.

        for index, element in matched:
            subject = _subject(path, element, index)
            actual = type(element).__name__
            if actual != row["kind"]:
                # Its own remedy. A generated row's rule is about how
                # many of an element there are, and its prescription
                # says to provide one -- which, inherited here, tells
                # the reader to add a second copy of the element they
                # are looking at, and that is the cardinality finding
                # this rule really is about.
                result["violations"].setdefault(row["id"], []).append(Violation(
                    "'%s' must be a %s" % (row["label"], row["kind"]),
                    subject=subject, detail="found a %s" % actual,
                    fix="Change this element from a %s to a %s. It is the "
                        "right element -- the semanticId matched -- so "
                        "adding another would be a second finding, not a "
                        "fix for this one." % (actual, row["kind"])))
                # Reported, and not recursed into -- so everything
                # below this row left the run with it, and nothing said
                # so. Twenty-one rules on the measured case, nine of
                # them mandatory, behind one `Property` wearing a list's
                # identifier.
                result["lost_candidates"].extend(_descendant_ids(row))
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
            # Only a disagreement. `typeValueListElement` is optional in
            # the metamodel and a file that says nothing is not a file
            # that says something wrong.
            listed = getattr(element, "type_value_list_element", None)
            if row["list_type"] and listed is not None and listed.value != row["list_type"]:
                result["violations"].setdefault(row["id"], []).append(Violation(
                    "'%s' is declared to hold %s; the template holds %s"
                    % (row["label"], listed.value, row["list_type"]),
                    subject=subject, detail="typeValueListElement is %s" % listed.value,
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
                _scope(row["children"], getattr(element, "value", None) or [],
                       subject, result,
                       in_list=(row["kind"] == "SubmodelElementList"))

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
    near_misses_here = len(result["near_misses"])
    for index, element, candidates, _main_empty in indexed:
        if index in claimed or not candidates:
            continue
        subject = _subject(path, element, index)
        for row in rows:
            near = _near_miss(candidates, row["match"])
            if near:
                result["near_misses"].append((subject,) + near)
                break

    if near_misses_here < len(result["near_misses"]):
        for row in rows:
            if row["children"] and not claimed_by.get(row["id"]):
                result["lost_candidates"].extend(_descendant_ids(row))


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
                if (seen_head and seen_head == exp_head
                        and edit_distance(seen_tail, exp_tail)
                        <= max(3, len(exp_tail) // 4)):
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
    value = getattr(element, "value", None)
    if not isinstance(value, list):
        return None
    for child in value:
        if _child_matches(child, row, parent_is_list):
            return child
    return None


def children_of(element, label: str, tables):
    row = tables.BY_LABEL[label]
    parent_is_list = type(element).__name__ == "SubmodelElementList"
    value = getattr(element, "value", None)
    if not isinstance(value, list):
        return []
    return [child for child in value if _child_matches(child, row, parent_is_list)]


def property_value(element, label: str, tables):
    """The string value of `element`'s child property matching `label`,
    or None when absent (cardinality is the generated rules' finding,
    not the hand rules')."""
    child = child_of(element, label, tables)
    value = getattr(child, "value", None) if child is not None else None
    return value if isinstance(value, str) else None
