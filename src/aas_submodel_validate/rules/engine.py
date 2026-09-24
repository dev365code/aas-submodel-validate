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
from dataclasses import replace
from typing import Dict, List

from ..model import Violation
from ..semantics import (
    candidate_values,
    edit_distance,
    element_candidate_values,
    key_values,
    submodel_declares,
    version_stem,
)

#: How many of the elements sitting in an unopened scope one record names;
#: `unclaimedHereCount` says how many there were. Every unentered row of a
#: kind names every unplaced element of that kind beside it, so unbounded
#: the list grows as rows times elements -- measured, a supplied template of
#: a thousand optional rows against a thousand vendor containers wrote a
#: 50 MB report where the same report without the lists is half a megabyte.
UNCLAIMED_NAMED = 5


def _identifier(element):
    """The identifier an unplaced element carries, as this reader matches
    it (normalised): its own `semanticId`, keys joined as the matching
    joins them; failing that the first of its supplemental ones in the
    order the file gives them. Not the first spelling in sorted order,
    which is what this was -- a supplemental that sorted early stood in
    for the element's own. Empty key values are not an identifier."""
    for reference in ([element.semantic_id]
                      + list(getattr(element, "supplemental_semantic_ids", None) or [])):
        values = [value for value in key_values(reference) if value]
        if values:
            return "/".join(values)
    return None


def _sitting_order(pair):
    """Path order for (subject, identifier), total: these are sorted out of
    sets, and a key under which two pairs tie leaves their order to the
    process's string hashing -- the same file wrote a different report in
    each process. No identifier sorts first rather than failing."""
    subject, seen = pair
    return (_in_path_order((subject, seen or "")), subject, seen or "")

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


#: What repairing a File value takes, by how many parts of the package
#: carry the file name it ends in (`model.FIXABILITY`). The first version
#: graded by branch -- "not a part name" 2, "no part at this value" 5 --
#: and neither branch had looked: a value naming `/aasx/documents/` for a
#: file the package holds in `/aasx/files/` was told its bytes were not in
#: the input, and a value climbing out to a file nothing carries was told
#: the package was there to confirm its spelling against.
_FILE_GRADES = {
    "directory": (4, "the value names a directory and no file; which file it "
                     "means is for someone who knows the document to say"),
    "one": (2, "one part of this package carries the file name this value ends "
               "in; the corrected value is determined once that part is "
               "confirmed to be the file meant"),
    "several": (3, "several parts of this package carry the file name this "
                   "value ends in; which one is meant is a person's choice"),
    # Several parts, one file: the same bytes stored under two folders
    # were graded a choice, and there is nothing to choose between -- any
    # of them is the file meant once one is confirmed to be.
    "alike": (2, "several parts of this package carry the file name this "
                 "value ends in, and the archive records the same size and "
                 "checksum for each; the corrected value is determined once "
                 "one of them is confirmed to be the file meant"),
    "none": (5, "no part of this package carries the file name this value ends "
                "in; the file has to be supplied, or someone who knows the "
                "document has to say which part it is"),
}


def _file_grade(container, value):
    from ..container import file_name
    if not file_name(value):
        return _FILE_GRADES["directory"]
    carrying = container.carrying(value)
    if len(carrying) > 1 and container.alike(carrying):
        return _FILE_GRADES["alike"]
    found = len(carrying)
    return _FILE_GRADES["none" if not found else "one" if found == 1 else "several"]


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
        grade, why = _file_grade(container, folded)
        yield Violation(
            "this File's value is not a part name",
            subject=subject,
            fixability=grade, fixability_why=why,
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
        grade, why = _file_grade(container, value)
        yield Violation("the container holds no part at this File's value",
                        subject=subject, detail=value,
                        fixability=grade, fixability_why=why)


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
              "relationship for it is X4's question, not this one's.)",
          # The File element, as HD-D7's: the part it names is in
          # `detail`, and the subject is where the value was written.
          path=("document", "submodel", "element"))
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


def install_near_miss_lint(rule_id: str, tables):
    """Register, for `tables`, the near-miss lint 02004's and 02003's packs
    have registered by hand from the start (`HDL2`, `TDL1`).

    Five packs never asked it. In them an identifier one version suffix or
    one last segment off took rows out of the run with nothing among the
    findings naming the element that did it: the one trace was a record in
    `summary.unmatchedElements`, which a pipeline reading findings never
    sees, and a drifted element with no rows beneath its own -- a
    property, a file -- left not even that (`docs/divergences.md` #23). Same title, clause and remedy as `TDL1`,
    so the finding reads alike whichever pack drew it."""
    from ..registry import rule

    @rule(rule_id, kind="lint", prio="SHOULD",
          path=("document", "submodel", "element"),
          title="near-miss semantic identifiers are diagnosed, not ignored",
          spec="matching policy, docs/divergences.md",
          fix="Correct the semanticId to the template's spelling; a near-miss "
              "matches nothing, and every rule that would have applied to the "
              "element silently stops applying.")
    def check(ctx):
        yield from near_miss_violations(ctx, tables)
    return check


def reftype_violations(ctx, tables):
    """The reference-type lint, for whichever pack asks. Same pair."""
    from ..model import Violation
    for subject, seen, expected, route in analyze(ctx, tables)["reftype_drift"]:
        yield Violation(
            "the reference type differs from the template's",
            subject=subject, path=route,
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
        #: (subject, seen type, template type, route) -- the route
        #: because the submodel's own reference is one of these, named
        #: by the submodel's idShort, and the rest name elements.
        "reftype_drift": [],
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
    #: The idShorts that repeat among the submodels this table answers
    #: for. A submodel's identity is its `id`; `idShort` is a label and
    #: two submodels may legally carry one -- AASd-022 is about
    #: referables that are *not* identifiable, so such a file draws no
    #: finding and no warning. The record below is keyed by a path whose
    #: first segment is that label, so two documents that each lost a
    #: scope were reported as one and the number a reader acts on came
    #: back halved, silently, on a legal file. Same policy as `_subject`
    #: uses for siblings: a name that is its own keeps the path it had.
    #: Counted over the label each submodel would be printed under, so
    #: several unnamed ones are told apart as readily as several sharing
    #: a name -- and a lone unnamed one keeps the `submodel` it has
    #: always had, which a test pins.
    named = Counter(submodel.id_short or "submodel"
                    for submodel in matched_submodels(ctx, tables))
    repeated = {name for name, count in named.items() if count > 1}
    for seat, submodel in enumerate(matched_submodels(ctx, tables)):
        root = submodel.id_short or "submodel"
        if root in repeated:
            root = "%s[%d]" % (root, seat)
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
               "unmatched": [], "not_entered": [], "not_examined": [],
               "reached": set()}
        if reference is not None and expected and reference.type.value != expected:
            per["reftype_drift"].append((root, reference.type.value, expected,
                                         ("document", "submodel")))
        _scope(tables.TREE, submodel.submodel_elements or [], root, per,
               in_list=False, citation=tables.TEMPLATE_CITATION, top=True)
        # Copies of a self-containing element the walk did not reach, inside
        # an element it judged. Where the template puts one -- a Node
        # directly inside a Node -- the walk gives it the copied element's
        # rows; one sitting anywhere else inside what the run judged, in a
        # container no row describes or beneath a copy of the wrong kind or
        # one whose identifier drifted, was reached by nothing, and saying
        # so is what keeps the reach of the check on the page (#48).
        copied = {row["recurses"] for row in tables.ROWS if row.get("recurses")}
        if copied:
            per["not_entered"] = _copies_not_reached(
                submodel.submodel_elements or [], root, copied, per["reached"])
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
        # And the same again for the scopes. A list walks its rows once
        # per item, so a row missed in the second item was entered in
        # the first: without this the report named twenty-seven rules as
        # scopes it never examined, twenty-two of which it had asked,
        # while `rulesNotAsked` on the same report was empty. Two keys
        # contradicting each other about one run.
        #
        # Only where nothing sat there, though. A place with an element of
        # the row's kind beside the unopened row is a fact about that place
        # whatever a sibling did: subtracting there too hid a drifted list
        # in one Document behind the same list, correctly identified, in
        # the next -- the report was byte for byte the one without it.
        examined = []
        for path, row_id, label, unasked, because, *sat in per["not_examined"]:
            kept = tuple(rule_id for rule_id in unasked
                         if because != "absent" or rule_id not in asked_here)
            if kept:
                examined.append((path, row_id, label, kept, because, *sat))
        per["not_examined"] = examined
        for key in ("violations", "instances"):
            for row_id, entries in per[key].items():
                result[key].setdefault(row_id, []).extend(entries)
        for key in ("near_misses", "idshort_drift", "reftype_drift",
                    "lost_candidates", "unmatched", "not_entered",
                    "not_examined"):
            result[key].extend(per[key])
    return result



def _id_short_of(row) -> str:
    """The idShort a row's element carries: its label, less the qualifier
    `docs/divergences.md` #48 adds where two rows share one -- `Node
    (EntryNode)`, `AddressOfAdditionalLink (IPCommunication__00__)`. Asked
    against the label itself, an element carrying the row's own idShort
    beside such a row was never recognised, and the missing element was
    graded 5 with a reason saying nothing here resembled it. An idShort
    holds no space, so the qualifier is everything from the first ` (`."""
    return row["label"].split(" (", 1)[0]


def _descendant_ids(row) -> List[str]:
    """Every rule id beneath a row, which is what leaves the run with it."""
    out = []
    for child in row["children"]:
        out.append(child["id"])
        out.extend(_descendant_ids(child))
    return out


def _asked_inside(row, element, copied=None) -> List[str]:
    """The rule ids a walk entering `element` as `row` would ask: every
    row directly beneath it, since entering a scope asks each of its rows,
    and beneath each of those only what `element` holds for it, matched
    the way the walk matches.

    The way the walk goes, too. An element of the wrong kind is not
    entered, and the walk charges one carrying the row's identifier
    outright with everything beneath its row; one whose identifier also
    drifted is charged the same. Charged nothing, such an element in a pack
    registering no near-miss lint left no trace at all -- a report the same
    as a clean file's, and one defect quieter than the file with only the
    identifier corrected. Each element goes to the first row it matches,
    as the walk hands them out: entered under every row it matched, one
    element answered for two sibling rows sharing an identifier. And a row
    that copies an element above it is followed with that element's rows
    (`copied`, as `_scope` carries them): it used to be asked and not
    followed, on the reasoning that its rows were counted already, which
    held one level down -- the sections a nested copy holds were never
    counted at its own depth."""
    if type(element).__name__ != row["kind"]:
        return _descendant_ids(row)
    inside = dict(copied or {})
    if row["sid"] and not row.get("recurses"):
        inside[row["sid"]] = row["children"]
    rows = inside.get(row["recurses"], ()) if row.get("recurses") else row["children"]
    out = [child["id"] for child in rows]
    in_list = type(element).__name__ == "SubmodelElementList"
    for sub in _sub_elements(element):
        for child in rows:
            if _child_matches(sub, child, in_list):
                if child["children"] or child.get("recurses"):
                    out.extend(_asked_inside(child, sub, inside))
                break
    return out


def unmatched_elements(ctx) -> List:
    """The elements this run could not place, with what each one cost.

    `rows_not_reached` answers "how many rules went unasked"; this answers
    "which element left them unasked", which is the question a reader has
    when the count is not zero. Same standing: a statement about the run,
    not about the file, and it moves no verdict (`docs/divergences.md`
    #19, #23).

    One record per element, holding every rule any table recorded it
    losing. This kept the largest record and dropped the rest, which is
    right only while one table walks the element: a submodel two tables
    answer for -- a pack's identifier and a supplied template's, both on
    it -- was charged with one table's rules, and the other's stayed in
    `rulesNotAsked` with no element to look them up by. The row it
    resembles is the one the largest record names.
    """
    from ..model import UnmatchedElement

    analysed = ctx.__dict__.get("_smt_analysis") or {}
    # In the tables' order, as `rows_not_reached` lists the same rules.
    # Collected the way a walk into the element meets them -- the rows
    # directly beneath it first, then what it holds -- a record listed the
    # rules beneath a section after that section's siblings, and one set
    # of rules came out in two orders in one report.
    order = {row["id"]: index for index, row in enumerate(_all_rows(ctx, analysed))}
    lost, resembled = {}, {}
    for analysis in analysed.values():
        for subject, seen, unasked, resembles in analysis.get("unmatched", ()):
            key = (subject, seen)
            if key not in lost or len(unasked) > resembled[key][0]:
                resembled[key] = (len(unasked), resembles)
            held = lost.setdefault(key, [])
            for rule in unasked:
                if rule not in held:
                    held.append(rule)
    return [UnmatchedElement(subject=key[0], seen=key[1],
                             unasked=tuple(sorted(lost[key], key=lambda rid: (
                                 order.get(rid, len(order)), rid))),
                             resembles=resembled[key][1])
            for key in sorted(lost)]


#: Digits inside a subject sort by value, not by spelling.
_RUN_OF_DIGITS = re.compile(r"(\d+)")

#: How much of a subject the path order reads. A key is one tuple per run
#: of digits, and every subject carries its whole path: measured, a root
#: idShort alternating letters and digits cost about 9 MB per element
#: sorted, so a half-megabyte file would outgrow a 16 GB machine. Past
#: this the whole subject breaks the tie, as a string.
_PATH_KEY_CHARACTERS = 2000


def _in_path_order(record):
    """A sort key that reads `[2]` as two rather than as the text "2".

    Positions are how an unnamed element is addressed, so a scope of
    twelve sorts `[0] [10] [11] [1] ...` by string. The caller prints
    the first few of these as a place to start looking, and the first
    few were the wrong few.

    Compared as digits, never converted: `int()` refuses a run of more
    than 4,300 digits on every interpreter CI runs (3.10.7 onwards), and an
    idShort is the file's to write -- measured, one such submodel name
    turned two rules into "the rule itself could not run". Shorter runs are
    smaller, then digit by digit, then the spelling (`1` before `01`), so
    no two different names compare equal.
    """
    subject, identifier = record
    parts = _RUN_OF_DIGITS.split(subject[:_PATH_KEY_CHARACTERS])
    return ([(len(part.lstrip("0")), part.lstrip("0"), part) if index % 2
             else (-1, part, "") for index, part in enumerate(parts)],
            identifier, subject)


def scope_not_examined(ctx) -> List:
    """One record per place a row was not entered, where its rules were
    not put anywhere else in that submodel either.

    Per place: `where` carries a list item's index, so each item of a list
    is its own place and its own record. Two records share a key only when
    two places print the same way -- an idShort spelled like a position,
    `[1]`, beside the unnamed item at index 1 -- and then the one with a
    stranger beside it wins, as the more specific fact, carrying both
    places' strangers.
    """
    from ..model import NotExamined

    analysed = ctx.__dict__.get("_smt_analysis") or {}
    best = {}
    sat = {}
    for analysis in analysed.values():
        for (where, rule, label, unasked, because, sitting,
             count) in analysis.get("not_examined", ()):
            key = (where, rule)
            if key not in best or because == "unclaimed-element-present":
                best[key] = (label, unasked, because)
            names, total = sat.get(key, ((), 0))
            sat[key] = (set(names) | set(sitting), max(total, count))
    out = []
    for (where, rule), (label, unasked, because) in sorted(best.items()):
        names, total = sat[(where, rule)]
        names = sorted(names, key=_sitting_order)
        out.append(NotExamined(where=where, rule=rule, label=label,
                               unasked=unasked, because=because,
                               unclaimed=tuple(names[:UNCLAIMED_NAMED]),
                               unclaimed_count=max(total, len(names))))
    return out


def repeats_not_entered(ctx) -> List:
    """(subject, identifier) for every copy of a self-containing row this
    run did not walk into, inside an element it judged, deduplicated and
    in path order."""
    analysed = ctx.__dict__.get("_smt_analysis") or {}
    seen = set()
    for analysis in analysed.values():
        seen.update(analysis.get("not_entered", ()))
    return sorted(seen, key=_in_path_order)


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
    answered for the vendored packs only; a table built from a
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


def _copies_not_reached(elements, root, copied, reached):
    """Every element carrying one of the `copied` identifiers that the walk
    did not reach, inside an element it did, with where it sits.

    Inside an element a row claimed, a copy the walk missed is the reach
    of the check: it sits in a container no row describes, or beneath a
    copy of the wrong kind or one whose identifier drifted, and the run
    judged what is around it. Outside every such element it is not: a
    copy at the submodel's root, or anywhere beneath an element no row
    claimed from the top down, is inside nothing the run judged -- an
    element beside the template's own, silent the way any extra element
    is (`docs/divergences.md` #19), or a place the run already names in
    `scopeNotExamined`. Counting every element that carried the
    identifier called a Node at the root a nested copy and named the
    Nodes of a drifted entry node twice.

    Judged means claimed by any row, not by one of the copied identifier's.
    The first version of this asked whether the outermost element carrying
    the same identifier had been reached, and so counted a Node in a
    container no row describes when the container sat inside a judged
    Node, and not when it sat directly inside the judged entry node, which
    carries another identifier. One flag per path, carried down with it:
    a flag kept for a level instead let one sibling's reach stand for the
    next, and a stray Node at the root was counted after the entry node.

    The whole tree and not the immediate children: a copy the walk did
    not reach hides the copies inside it from the walk too. Measured on a
    file three deep, counting only the immediate ones reported one copy
    of two.

    Named by `_subject`, which is what names every other record in this
    module. Spelled `?` here instead, the children of a
    `SubmodelElementList` -- which the metamodel forbids an idShort, and
    which is where repeats actually sit -- all came out as one string,
    and `repeats_not_entered` deduplicates: three unentered subtrees
    were reported as one, at a place with no name. That is exactly the
    merge `docs/divergences.md` #53 names and `_subject` was written to
    stop, in a walk added beside it that did not call it.
    """
    found = []
    #: Whether a row claimed some element above this point, on this path.
    stack = [(elements, root, False)]
    while stack:
        children, where, judged = stack.pop()
        names = Counter(child.id_short for child in children if child.id_short)
        shared = {name for name, count in names.items() if count > 1}
        for index, child in enumerate(children):
            here = _subject(where, child, index, shared)
            carried = copied & element_candidate_values(child)
            claimed = id(child) in reached
            if carried and judged and not claimed:
                found.append((here, sorted(carried)[0]))
            stack.append((_sub_elements(child), here, judged or claimed))
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


#: What repairing a count finding takes (`model.FIXABILITY`). Each reason
#: says what the walk found at the place the finding names; the walk
#: does not look elsewhere, and where the element sits one level up the
#: repair is easier than the grade says.
_SURPLUS = (3, "every copy is present; which of them to keep is a person's "
               "choice")
_LIKE_ONE = (2, "one element here that no row claimed carries this row's idShort "
                "or an identifier close to its own; the correction is "
                "determined once it is confirmed to be the one meant")
_LIKE_SEVERAL = (3, "several elements here that no row claimed carry this row's "
                    "idShort or an identifier close to its own; which one is "
                    "meant is a person's choice")
_GIVEN_WHOLE = (2, "every row below this one is optional, so the template gives "
                   "all it must hold; adding it is determined once no copy of it "
                   "is confirmed to sit elsewhere in the file")
_MISSING = (5, "nothing else here resembles the missing element, and what it "
               "holds is content the template does not give")
_CONTAINERS = ("SubmodelElementCollection", "SubmodelElementList")


def _kind_grade(row, element, actual, item):
    """What moving an element into the kind the template gives takes.

    The template names the target kind; whether the content maps onto it
    is the question. It does, mechanically, in two cases this walk can
    see: an element of the kind the template gives a list's item, which
    matched the list's row because the two share an identifier, is
    wrapped; and a collection whose every child is of the list's item
    kind becomes that list. Anything else -- a Property holding free text
    where a MultiLanguageProperty belongs -- needs someone who knows what
    it says."""
    if item is not None:
        return (2, "this element is of the kind the template gives the list's "
                   "item, and the template gives the list around it; wrapping "
                   "it is determined once it is confirmed to be the item and not "
                   "the list")
    if (row["kind"] == "SubmodelElementList" and actual == "SubmodelElementCollection"
            and row.get("list_type")
            and all(type(child).__name__ == row["list_type"]
                    for child in _sub_elements(element))):
        return (2, "every element inside is of the kind the template gives the "
                   "list's items; the change is determined once they are "
                   "confirmed to be those items")
    return (4, "the template gives the kind and not how this element's content "
               "maps onto it; carrying it across needs someone who knows what it "
               "means")


def _scope(rows, elements, path: str, result, in_list: bool,
           citation: str, top: bool = False, copied=None) -> None:
    """Judge `elements` against `rows`, and recurse.

    `copied` maps an identifier to the rows of the element that carries
    it, for every element this walk is inside: what a row marked
    `recurses` -- a nested copy of an element above it -- is given as its
    own rows, at whatever depth the copy sits (docs/divergences.md #48).
    The table stops one level down; an instance stops where it stops,
    and the walk follows the instance."""
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
    #: (row, position in its violation list) for each "too few" finding
    #: made here, graded once this scope knows what else sits in it --
    #: which is only after the near-miss walk below.
    short = []
    #: What a finding naming this scope's own path names: the submodel,
    #: at the top of the walk, and the element it has reached below.
    here = ("document", "submodel") if top else None

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
            result["reached"].update(id(element) for _, element in matched)

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
            found = result["violations"].setdefault(row["id"], [])
            found.append(Violation(
                "the template expects %s '%s' here; found %d"
                % (_KIND_WORDS.get((low, high), _UNCOUNTED), row["label"], count),
                subject=path, path=here,
                # Two defects wear one message and they are not equally
                # repairable. Too many: every copy is present and the
                # repair is choosing which to keep. Too few is graded
                # below, by what else this scope turns out to hold: the
                # first version called it a 5 -- the content is not in
                # this input -- on a file whose element sat right here
                # one version suffix off.
                fixability=_SURPLUS[0] if count >= low else _MISSING[0],
                fixability_why=_SURPLUS[1] if count >= low else _MISSING[1],
                detail=("elements: %s" % ", ".join(
                    _subject(path, e, i, shared) for i, e in matched)) if matched else None))
            if count < low:
                short.append((row, len(found) - 1))
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
                grade, why = _kind_grade(row, element, actual, item)
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
                    fixability=grade, fixability_why=why,
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
                    # The declaration disagrees with the template and
                    # the template's answer is on the page. Confirm the
                    # items really are that kind and the declaration
                    # follows; that premise is what makes it a 2.
                    fixability=2,
                    fixability_why=(
                        "the template states the item type; rewriting the "
                        "declaration is determined once the items are "
                        "confirmed to be of it"),
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
                    # Same shape as the row above: the template states
                    # the type, and the premise to confirm is that the
                    # value as written is representable in it.
                    fixability=2,
                    fixability_why=(
                        "the template states the valueType; the rewrite is "
                        "determined once the value is confirmed to fit it"),
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
                    # The element is here and the value is not, and the
                    # template does not say what it is.
                    fixability=5,
                    fixability_why=(
                        "the element is present and its value is not, and what "
                        "the value is is not something the template gives"),
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
                    (subject, reference.type.value, row["sid_type"], None))
            # A nested copy takes the rows of the element it copies. They
            # were walked by nobody until 02011 was vendored and settled
            # how (#48): the run said it had not entered the copies, which
            # was true and left everything inside them unjudged.
            below = (copied or {}).get(row["recurses"], ()) if row.get("recurses") \
                else row["children"]
            if below:
                inside = dict(copied or {})
                if row["sid"] and not row.get("recurses"):
                    inside[row["sid"]] = row["children"]
                _scope(below, _sub_elements(element),
                       subject, result,
                       in_list=(row["kind"] == "SubmodelElementList"),
                       citation=citation, copied=inside)

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
    #: What sat here unplaced, by kind: each element no row claimed that
    #: carries an identifier, as (subject, identifier). One carrying none is
    #: left out on purpose, and it costs something: a template container
    #: that lost its `semanticId` reads as a section the file does not
    #: carry. But a container with no identifier is also the commonest
    #: shape of a manufacturer's own, and counting it made conformant files
    #: speak, which `docs/divergences.md` #19 promises they do not.
    unplaced = {}
    for index, element, candidates, _main_empty in indexed:
        # A key that normalises to nothing is no identifier either.
        if index in claimed or not any(candidates):
            continue
        subject = _subject(path, element, index, shared)
        unplaced.setdefault(type(element).__name__, []).append(
            (subject, _identifier(element)))
        for row in rows:
            near = _near_miss(candidates, row["match"])
            if near:
                result["near_misses"].append((subject,) + near)
                near_here.append((subject, near[0], near[1], row, element))
                break

    # What each "too few" finding here would take to repair, now that the
    # scope is known. An element no row claimed that nearly carries the
    # row's identifier, or carries its idShort, is what the repair would
    # point at: one of them is a correction to confirm, several a choice.
    # With none, a section whose every row below is optional is given
    # whole by the template; anything else holds content it does not give.
    if short:
        loose = [(index, element) for index, element, _c, _m in indexed
                 if index not in claimed]
        for row, at in short:
            like = {subject for subject, _seen, _expected, near, _element in near_here
                    if near is row}
            like.update(_subject(path, element, index, shared)
                        for index, element in loose
                        if element.id_short and element.id_short == _id_short_of(row))
            if like:
                grade, why = _LIKE_ONE if len(like) == 1 else _LIKE_SEVERAL
            elif (row["kind"] in _CONTAINERS
                    and all(child["card"][0] == 0 for child in row["children"])):
                grade, why = _GIVEN_WHOLE
            else:
                grade, why = _MISSING
            found = result["violations"][row["id"]]
            found[at] = replace(found[at], fixability=grade, fixability_why=why)

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
    # Which *kinds* went unplaced here, asked once and read per row.
    # This was one boolean for the whole scope -- is anything here
    # unplaced -- and every unentered row beside it took that answer. So
    # one property the template never mentions flipped a row about a
    # section the file does not even have, and the terminal said the
    # file carried an element under a section that was not there. A
    # conformant file carrying a manufacturer's own element reports
    # nothing at all (`docs/divergences.md` #19) and that is the promise
    # it broke.
    #
    # An element can only be sitting in a row's place if it is the kind
    # that row asks for. Anything else is an extension, which is #19's
    # subject and not this one's. The elements come from the near-miss
    # walk above, which visits exactly this set with each subject already
    # built; an earlier version built them a second time here, sorted
    # them, and read the result as a truth value.
    #
    # And *which* elements, not only whether any. Two opposite situations
    # -- a row's own container under a drifted identifier, and a row the
    # file legitimately omits beside an unrelated container of the same
    # kind -- produced byte-identical records, and the one fact that tells
    # them apart is what was sitting there. Named; still not blamed.
    # Sorted once per kind, not once per row: every row of a kind reads
    # the same list.
    ordered = {kind: sorted(pairs, key=_sitting_order)
               for kind, pairs in unplaced.items()}
    for row in rows:
        if not row["children"] or claimed_by.get(row["id"]):
            continue
        lost = tuple(_descendant_ids(row))
        if not lost:
            continue
        sitting = ordered.get(row["kind"], ())
        result["not_examined"].append(
            (path, row["id"], row["label"], lost,
             "unclaimed-element-present" if sitting else "absent",
             tuple(sitting[:UNCLAIMED_NAMED]), len(sitting)))
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
    if near_here:
        # Asked whether or not this scope left a row unentered, and of a
        # row a sibling entered too. Both gates stood here while the loss
        # was the resembled row's whole subtree, and both were stand-ins:
        # an entered row's subtree is not lost -- but what a drifted copy
        # holds and its intact sibling does not is, and the subtraction
        # below takes back what any scope asked, which is the question
        # the two gates were answering by guess.
        #
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
        for subject, seen, expected, row, element in near_here:
            if not row["children"] and not row.get("recurses"):
                continue
            grouped.setdefault((row["id"], seen), (row, expected, subject, []))[3].append(element)
        # And the run-wide list takes the same rows and no others. It
        # took every row this scope left unentered, because one near miss
        # fired somewhere in it: a Nameplate whose serial number drifted
        # reported the three rules of a section the file simply omits as
        # rules the drift kept from being asked, and the screen said their
        # element was not one this reader recognised. The omitted section
        # is still recorded -- `not_examined`, above, says so of every
        # unentered row -- but as a place nothing explains, which is what
        # it is. A near miss explains the rows it resembles (#23).
        #
        # And of the rows it resembles, only what the element would have
        # had asked. Matched, it would have opened the row's scope, and
        # every row directly beneath is asked there; beneath those, only a
        # section the element carries is entered. A section it does not
        # carry would have been a place not examined all the same, so the
        # drift kept nothing of it from being asked -- charging its rules
        # to the element said otherwise, and the place is recorded, as
        # every unentered row is, in `not_examined`.
        for (_row_id, seen), (row, expected, subject, elements) in grouped.items():
            lost = []
            for element in elements:
                for rule_id in _asked_inside(row, element, copied):
                    if rule_id not in lost:
                        lost.append(rule_id)
            lost = tuple(lost)
            if lost:
                result["unmatched"].append((subject, seen, lost, expected))
                result["lost_candidates"].extend(lost)


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
