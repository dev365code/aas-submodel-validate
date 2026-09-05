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
    }
    for submodel in matched_submodels(ctx, tables):
        root = submodel.id_short or "submodel"
        reference = submodel.semantic_id
        expected = tables.TEMPLATE_SUBMODEL_SID_TYPE
        if reference is not None and expected and reference.type.value != expected:
            result["reftype_drift"].append(
                (root, reference.type.value, expected))
        _scope(tables.TREE, submodel.submodel_elements or [], root, result,
               in_list=False)
    return result



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
                continue
            declared = getattr(element, "value_type", None)
            if row["value_type"] and declared is not None and declared.value != row["value_type"]:
                result["violations"].setdefault(row["id"], []).append(Violation(
                    "'%s' must carry valueType %s" % (row["label"], row["value_type"]),
                    subject=subject, detail="found %s" % declared.value,
                    fix="Change this element's valueType from %s to %s. "
                        "The element itself is the right one; only the "
                        "type it declares for its value is not."
                        % (declared.value, row["value_type"])))
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

    for index, element, candidates, _main_empty in indexed:
        if index in claimed or not candidates:
            continue
        subject = _subject(path, element, index)
        for row in rows:
            near = _near_miss(candidates, row["match"])
            if near:
                result["near_misses"].append((subject,) + near)
                break


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
