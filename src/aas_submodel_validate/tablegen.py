"""Rows from a template document — the half of the generator that reads.

Split out of `tools/extract_smt_rules.py` and moved here for one reason:
`tools/` is not installed, and must not be. No member of a built wheel
sits under `tools/`, and putting one there would install two more
top-level names into everybody's site-packages, which
`tools/check_distributions.py` refuses in writing and CI runs on every
push. So while the row builder lived there, an installed copy of this
package could not build a table from a template, and neither could the
single-file build, which copies exactly this directory.

That matters because a mode that reads a template a caller supplies has
to give the same verdict from every entrance. The library, the command
line and the single file are the same engine or they are not one engine,
and the entrance that cannot reach the generator is the one that answers
differently.

What stayed behind is the part that writes: the pack list, the Python
source it renders, and the `--check` that proves a table matches its
generator byte for byte. Those are build-time and belong to the build.

The functions below are the ones that were here, unchanged, so that the
vendored tables regenerate to the same bytes. The one difference is
`DuplicateLabel`: the generator used to raise `SystemExit` with a
sentence, which is a build tool's way of leaving by 1, and a run-time
caller owes 2 — "could not judge the input" — instead. The exception
carries the sentence and each entrance decides its own code.
"""
from __future__ import annotations

import re
from collections import Counter

from .semantics import normalize

#: How many rows a template may declare. Not a byte bound: a template of
#: 46 MiB sits inside the 64 MiB this reader advertises for a document,
#: and what the generator spends is decided by rows, not by weight.
#: Chosen far above anything published -- the widest template vendored
#: here builds thirty-eight rows, the same number whether a caller
#: supplies it or the pack is generated from it, because both readers
#: skip the same open content -- and far below where a generated table
#: stops being something a person could read a finding out of.
MAX_TEMPLATE_ROWS = 10_000

#: The identifiers a published template uses to say "a section may hold
#: content I do not describe". No rule is generated from an element
#: wearing one: the template states no obligation there, so a
#: manufacturer's own property passes without comment
#: (`docs/divergences.md` #19).
#:
#: One set, read by both readers of a template. It was written per pack
#: in the generator and left empty for a table built at run time, so the
#: same file read the two ways described different obligations: handed
#: this project's own 02003 template, `--template` built 54 rows against
#: the pack's 26 and faulted a manufacturer's element for being the
#: wrong kind -- which is the failure #19 names in advance.
#:
#: The first two are the two IDTA publishes: *How to Create a Submodel
#: Template Specification* V1.1 (June 2025), Table 11 "Marking arbitrary
#: content in SubmodelElement data", which names `Arbitrary` and
#: `IntentionallyEmpty` and nothing else. The three typed spellings
#: after them are not in that table; they are what IDTA 02006 3.0's own
#: template uses, and they are here because a template that uses them
#: exists. Collecting the per-pack lists gave the first and the three
#: typed ones -- those were what the vendored six happened to use -- and
#: `IntentionallyEmpty` was in no pack and so in no list, which is why a
#: template marking content that way generated rules from the
#: placeholder and faulted a manufacturer's element against it.
OPEN_CONTENT_MARKERS = frozenset((
    "https://admin-shell.io/SMT/General/Arbitrary",
    "https://admin-shell.io/SMT/General/IntentionallyEmpty",
    "https://admin-shell.io/SMT/General/ArbitraryProp",
    "https://admin-shell.io/SMT/General/ArbitraryMLP",
    "https://admin-shell.io/SMT/General/ArbitraryFile",
))


class TemplateRefused(Exception):
    """This is not a template this reader will build a table from.

    Raised rather than exited on, for the same reason `DuplicateLabel`
    is: the code belongs to the entrance. A build tool leaves by 1 and a
    reader handed a file by somebody else owes 2 -- "could not judge the
    input" -- which is what every other unreadable input here gets.
    """


class DuplicateLabel(TemplateRefused):
    """Two rows of one template claim the same label.

    The hand rules navigate by label and `BY_LABEL` is a dict, so two
    rows sharing one would make the second silently unreachable. Raised
    rather than exited on, because who exits and with what code belongs
    to the caller: the build tool leaves by 1 the way build tools do,
    and a reader handed the file by somebody else owes the code that
    means "could not judge this input".
    """


CARDINALITY = {"One": (1, 1), "ZeroToOne": (0, 1),
               "OneToMany": (1, None), "ZeroToMany": (0, None)}


#: The qualifier types this generator reads a cardinality from, in order
#: of precedence. `SMT/Cardinality` is the current SMT spelling; older
#: templates (02002, 02007) state the identical vocabulary as
#: `Multiplicity`; `Cardinality` is a third seen spelling. The battery
#: index's own extractor lists the same three.
_CARDINALITY_TYPES = ("SMT/Cardinality", "Multiplicity", "Cardinality")


_ALLOWED = re.compile(r"^(.*)\[(\\d\{\d(?:,\d)?\})\]$")


def _intended_pattern(raw):
    """`RefersTo[\\d{2,3}]` -> `^RefersTo(?:\\d{2,3})?$`, and anything
    else the name it spells.

    The digits are the numbering suffix for multiple instances, so they
    are optional: the template's *own* idShort for the single case
    ("PreviewFile") must not fail the template's own qualifier.

    Everything else is a name, not a program. Passed through as a
    pattern, a qualifier reading `Doc(1)` matched `Doc1` and not the
    element the template names, and one reading `A[` did not compile at
    all -- so every row of that table raised at walk time and the funnel
    reported each as "the rule itself could not run", under a remedy
    saying the defect is this validator's. Measured across the six
    vendored templates, every `AllowedIdShort` uses the bracket
    spelling above, so escaping the rest moves no pack.

    Returns `None` where the value cannot be read at all: one that
    claims the bracket spelling and gets it wrong (`A[\\d{3,2}]` asks for
    a repeat of at least three and at most two), or one that is not a
    string (`Qualifier.value` is optional in the metamodel, so a
    qualifier declaring this type and no value is a legal file). The
    caller says so and carries on.

    Not refused with the template, which is what the first repair did.
    This value feeds one rule, `info`, whose own remedy reads "Any
    unique idShort is legal; this is tidiness, not conformance" -- and a
    run-time table registers no lints at all, so under `--template`
    nothing reads it. Refusing threw away every MUST verdict on the file
    over a suggestion, while an unreadable `SMT/Cardinality` -- which
    decides whether an element is required -- quietly defaults to `0..*`
    ten lines above. The proportion was upside down.
    """
    if not isinstance(raw, str):
        return None
    matched = _ALLOWED.match(raw)
    if matched:
        # The name is escaped here too. The first repair reached the
        # branch below and left this one, where the *suffix* is IDTA's
        # and the part before it is still the caller's: `A[[\d{2}]`
        # matched this pattern and produced `^A[(?:\d{2})?$`, which
        # does not compile, so every row of that table raised and the
        # funnel reported each as a defect in this validator. Both
        # halves of the defect lived on in one of its two branches.
        pattern = "^%s(?:%s)?$" % (re.escape(matched.group(1)),
                                   matched.group(2))
        try:
            # What the walk does, brought forward to where the value is
            # still identifiable. Escaping cannot reach the suffix --
            # the suffix has to stay a program, that is what this branch
            # is for -- so the only answer to "is this one Python can
            # run" is to run it. Asking here rather than pattern-matching
            # the bounds also answers it for a spelling nobody
            # anticipated, which is the half the two repairs before this
            # one each left standing.
            re.compile(pattern)
        except re.error:
            return None
        return pattern
    return "^%s$" % re.escape(raw)


def _values_of(reference):
    """Every match value one reference contributes: each key, the join of
    multi-key references, and the `~N`-stripped spelling of each. IRDI
    composites are kept whole -- not split into components -- to match
    candidate_values on the instance side (docs/divergences.md #8)."""
    keys = [normalize(key["value"]) for key in reference.get("keys", [])]
    out = set(keys)
    if len(keys) > 1:
        out.add("/".join(keys))
    for value in tuple(out):
        stripped = re.sub(r"~\d+", "", value)
        if stripped != value:
            out.add(stripped)
    return out


def _declared_values(element):
    """Every identifier the template gives this element, folded.

    What a row answers to is drawn from this, and so is half of the
    open-content question. The other half reads the element's own
    semanticId alone, which is a different question and is asked
    separately in `_is_open_content`.
    """
    values = set()
    if element.get("semanticId"):
        values |= _values_of(element["semanticId"])
    for supplemental in element.get("supplementalSemanticIds", []):
        values |= _values_of(supplemental)
    return values


def _is_open_content(element, markers):
    """Whether the template has left this place to the supplier.

    Two questions, not one, and reading only either of them was measured
    wrong in a different direction.

    The first is what the template calls the element. Its *own*
    semanticId being a marker is the template saying "anything may go
    here", and what it carries beside that describes the placeholder --
    a unit, a preferred type -- without turning the place into a
    requirement. Read as "every identifier must be a marker", a
    placeholder that named a unit alongside became a mandatory row, and
    the supplier's own element sitting in that place was reported
    missing: `found 0` about a file that is fine, which is the outcome
    `docs/divergences.md` #19 exists to prevent.

    A marker anywhere *else* -- in a supplemental, with no semanticId of
    the element's own -- does not reach this. It used to: the rule read
    "every identifier this element declares is a marker", and a
    container written that way was dropped with everything under it.
    Measured on a template whose unnamed `Box` held a mandatory `Inner`:
    a file missing `Inner` went from an error to `ok` at exit 0, because
    the row that would have asked for it was never built. A conformance
    reader going quiet is the one direction with no second opinion, and
    no sentence here or in the published pages said the subtree went
    too.

    Such an element is still not an obligation -- markers are not
    identities, `_match_set` removes them, and nothing can answer a row
    with an empty match set. That is settled where every other
    unanswerable row is settled, by dropping the obligation and saying
    so, which keeps the rows underneath in the table and the reason on
    the page.

    Folded: `_values_of` folds every other reference in this file, and
    unfolded, a marker written with a trailing space was not skipped
    while the same value matched on the instance side. Joined first,
    because a marker spelled across two keys is one identifier.
    """
    keys = [normalize(key["value"])
            for key in element.get("semanticId", {}).get("keys", [])]
    return "/".join(keys) in markers


def _match_set(element, skip_sids):
    """The identifiers a row answers to: what the template declares,
    less the pack's open-content markers.

    The argument is the pack's own list and not the module constant, so
    that the two questions asked of that list -- is this place open, and
    what does its row answer to -- cannot be asked of two different
    lists. Named for what arrives rather than for what it holds: a pack
    that put a real identifier in its skip list would have that
    identifier disappear from every match set, and a parameter called
    `markers` hides that from anyone reading the call.

    A marker says a place is open, not what belongs in it. Left in, it
    was an identity like any other: an element that carried a real
    identifier and marked itself open content beside it kept its row and
    also answered to the marker, so the supplier's own element under
    that marker satisfied a mandatory row it has nothing to do with.
    Measured -- a template requiring one `urn:test:real`, a file holding
    only the supplier's element: `ok` true, no findings, the required
    element absent.

    0 of the 156 rows across the packs carried one, because all 43
    markers in the six vendored templates are an element's own
    semanticId and those elements never reach here. This is about what a
    caller's template can do.
    """
    return tuple(sorted(_declared_values(element) - skip_sids))


def _primary_sid(element):
    keys = [key["value"] for key in element.get("semanticId", {}).get("keys", [])]
    return "/".join(keys)


def _cardinality_words(card):
    low, high = card
    if (low, high) == (1, 1):
        return "exactly one"
    if (low, high) == (0, 1):
        return "at most one"
    if high is None and low == 1:
        return "one or more"
    # Unbounded and not required. The walk cannot report a count for this
    # shape -- `count < 0` never holds and there is no upper test -- so
    # this word reaches a remedy and never a message. It still has to be
    # a sentence: it shipped as "Provide any number 'ProductImage'
    # element(s)", which is not one.
    return "any number of"


def _rows(element, parent_label, parent_id, counter, pack, in_list=False,
          repeats=None):
    """One row, and its children's rows -- or None where the template
    describes open content rather than an obligation (see `skip_sids`).
    The check comes before the counter so skipped subtrees leave no gap in
    the numbering and no trace in a sibling template's table."""
    if _is_open_content(element, pack["skip_sids"]):
        return None
    label = element.get("idShort") \
        or pack["item_names"].get(parent_label, parent_label + "Item")
    counter[0] += 1
    if counter[0] > MAX_TEMPLATE_ROWS:
        # Here, not after the walk. Checked afterwards the bound stopped
        # the *second* pass and let the first build every row first:
        # measured, 300,000 rows were materialised in 2.2 seconds and 282
        # MiB before the refusal -- which on a container with a memory
        # limit is a kill rather than an exit code. And 300,000 is not
        # the ceiling: an element this builds a row from needs only a
        # `modelType` and an `idShort`, 42 bytes of it measured, so about
        # 1.58 million rows fit inside the 64 MiB of template this reader
        # takes in. `SECURITY.md` says a template above the row
        # limit is refused at the row that crosses it, and that sentence
        # is only true from here.
        raise TemplateRefused(
            "this template declares more than the %d rows this reader "
            "builds a table from" % MAX_TEMPLATE_ROWS)
    row_id = "%s%02d" % (pack["prefix"], counter[0])
    qualifiers = {q.get("type"): q.get("value") for q in element.get("qualifiers", [])}
    # Absent means 0..*: see the module docstring. Read in one of three
    # spellings -- SMT/Cardinality, or the older Multiplicity, or a bare
    # Cardinality -- the same set the battery index's extractor already
    # treats as cardinality (data/battery-passport/tools/extract_idta_smt.py),
    # so a template that states its obligations only in the older spelling
    # is read rather than defaulted to 0..* (docs/divergences.md #50). The
    # first spelling present wins; absent all three is 0..*.
    card = (0, None)
    for _card_type in _CARDINALITY_TYPES:
        if _card_type in qualifiers:
            card = CARDINALITY.get(qualifiers[_card_type], (0, None))
            break
    # A copy the template makes mandatory makes every copy need one of its
    # own, and no finite file has that many: a tree three deep with
    # everything in place drew an error at the bottom, for the file. The
    # lower bound is dropped before the remedy is written from it, and the
    # template's defect is said instead, the way a mandatory row nothing
    # can answer is.
    endless = card[0] if repeats and card[0] > 0 else None
    if endless:
        card = (0, card[1])
    examples = [value for key, value in qualifiers.items()
                if key in pack["example_types"]]
    example = " | ".join(examples) if examples else None
    fix = ("Provide %s '%s' element(s)%s with semanticId %s%s."
           % (_cardinality_words(card), label,
              " under %s" % parent_label if parent_label else "",
              _primary_sid(element) or "(as the template declares)",
              "; example value: %r" % example if example else ""))
    # A SubmodelElementCollection or List holds its children in `value`;
    # an Entity holds them in `statements` (aas-core3). Descend whichever
    # the element carries -- a kind populates only one -- so an Entity's
    # rows are generated rather than every instance of it looking empty.
    # A MultiLanguageProperty's `value` is a list of language entries, not
    # of elements; only what declares a modelType is a child here.
    my_sid = _primary_sid(element)
    sub_elements = []
    # A nested copy is not expanded: the walk gives it the rows of the
    # element it copies, at whatever depth it sits (`repeats`, below).
    for _container in (() if repeats else ("value", "statements")):
        _items = element.get(_container)
        if isinstance(_items, list):
            sub_elements.extend(_items)
    # A self-containing element -- an Entity or SubmodelElementCollection
    # whose own child repeats its semanticId (02011's Node holds a Node) --
    # gives that child a row of its own, as the template gives it an
    # element of its own: its cardinality is the template's, which 02011
    # makes 0..* inside a Node where the Node itself is 1..* inside the
    # entry. The child's row is marked `recurses` and not expanded, so the
    # table stays finite and the walk re-applies the copied element's rows
    # to it at any depth (docs/divergences.md #48). Only these two kinds,
    # the shapes the standard nests: a SubmodelElementList and its item
    # share one identifier by design (#39) but are a list with one item
    # kind, not self-containment, and no other kind reaches a child
    # through `value`/`statements`. Direct self-containment only; indirect
    # (A in B in A) is out of scope.
    children = []
    for child in sub_elements:
        if not (isinstance(child, dict) and "modelType" in child):
            continue
        # Written empty, too. A repeat the template writes with content of
        # its own is that content, spelled out at that level: a nested
        # `Node` declaring `Extra` asks for `Extra` there and not for what
        # the outer `Node` holds. Given the outer rows instead, it was told
        # to carry the outer `Name` and never asked for the `Extra` it
        # declares. Only a repeat written with nothing inside it -- which
        # is how 02011 writes one -- leaves the template's shape to be
        # carried down.
        copies = (my_sid and _primary_sid(child) == my_sid
                  and child["modelType"] == element["modelType"]
                  and element["modelType"] in ("Entity", "SubmodelElementCollection")
                  and not any(isinstance(item, dict) and "modelType" in item
                              for key in ("value", "statements")
                              for item in (child.get(key) if isinstance(child.get(key), list)
                                           else ())))
        child_row = _rows(child, label, row_id, counter, pack,
                          in_list=element["modelType"] == "SubmodelElementList",
                          repeats=my_sid if copies else None)
        if child_row is not None:
            children.append(child_row)
    #: What this row answers to. An element the template identifies with
    #: nothing has none, and matching never consults idShort -- so
    #: outside a list, where a sole item row is matched by its kind
    #: instead, no element can ever answer this row. A mandatory one was
    #: then an error no file could clear: measured, a file carrying an
    #: element of exactly the name the template writes was told
    #: `found 0`, under a remedy ending "with semanticId " and nothing,
    #: because there was nothing to name. The obligation is dropped and
    #: the template's defect is said instead -- the file is not the
    #: thing that is wrong.
    match = _match_set(element, pack["skip_sids"])
    unidentified = not match and not in_list
    if unidentified:
        card = (0, None)
    #: Read before the row is built so the row can carry the fact. A
    #: value that cannot be read leaves the pattern unset and the raw
    #: text on the row, where the caller who supplied the template is
    #: told about it once. `in` rather than truth: `Qualifier.value` is
    #: optional, so a qualifier of this type with no value at all is a
    #: legal file and is a value this cannot read, not an absence.
    declares_idshort = "AllowedIdShort" in qualifiers
    allowed_idshort = (_intended_pattern(qualifiers["AllowedIdShort"])
                       if declares_idshort else None)
    row = {
        "id": row_id,
        "label": label,
        "parent": parent_id,
        "kind": element["modelType"],
        # The same set the skip above read, so a pack cannot skip
        # through one list and match through another.
        "match": match,
        "sid": my_sid,
        "sid_type": element.get("semanticId", {}).get("type"),
        "card": card,
        "value_type": element.get("valueType"),
        "list_type": element.get("typeValueListElement"),
        "allowed_idshort": allowed_idshort,
        "example": example,
        "fix": fix,
        "children": tuple(children),
    }
    if repeats:
        row["recurses"] = repeats
    if endless:
        row["endless"] = endless
    if unidentified:
        row["unidentified"] = True
    if declares_idshort and allowed_idshort is None:
        # Present only where there is something to say, so a row built
        # from a template that reads cleanly is the row it always was --
        # which is what lets the generated tables and the run-time ones
        # be compared key for key.
        row["allowed_idshort_unreadable"] = qualifiers["AllowedIdShort"]
    return row


def _labels(rows, out):
    for row in rows:
        out.append(row["label"])
        _labels(row["children"], out)
    return out


def _qualify_repeats(tree):
    """Where a label is claimed by rows in more than one scope, qualify
    each by the shortest ancestor suffix that tells its collision group
    apart: the immediate parent where that alone distinguishes it, one
    ancestor further where the immediate parents coincide, the full path
    from the top as a last resort. A template with no such repeat leaves
    this a no-op, so its generated table stays byte-for-byte the same.
    Only the label is touched: it is the row's identity for the walk and
    for the hand rules that navigate by it, while `fix` keeps the
    element's own idShort, which is what a reader is told to provide.

    The suffix is read off the *raw* ancestor labels, before any of them
    is itself qualified, so a repeat nested under a repeat (02023's
    `PcfCalculationMethod` under a repeated `PcfCalculationMethods`) reads
    its parent's bare label, not the parent's own qualifier. The tree a
    recursion point (`recurses`) leaves behind is finite -- its
    self-similar subtree is not re-expanded -- so the suffix a descendant
    of one takes does not grow with depth: `Node (EntryNode)` at the
    entry, `Node (Node)` at the recursion, and so at every level.

    The duplicate-label check downstream still runs: if even the full path
    does not tell two same-labelled rows apart, it aborts there rather
    than emit a table that hides a row.
    """
    labels = _labels(tree, [])
    # Counted once, not once per label. `labels.count(label)` inside this
    # comprehension walked the whole list for every entry in it, so the
    # work went as the square of the template's width -- and it sat in
    # front of the early return, so a template with no repeated label at
    # all paid it in full. Measured before the change: 2,000 rows in
    # 0.023s, 8,000 in 0.51s, 32,000 in 9.2s. Every vendored table is
    # byte-for-byte what it was.
    seen = Counter(labels)
    clashing = {label for label, count in seen.items() if count > 1}
    if not clashing:
        return

    # Each row's raw ancestor labels, immediate parent first, snapshotted
    # before any label is qualified so a nested repeat reads bare labels.
    ancestors = {}

    def record(rows, chain):
        for row in rows:
            ancestors[id(row)] = chain
            record(row["children"], [row["label"]] + chain)
    record(tree, [])

    # The colliding rows, grouped by their (raw) label.
    groups = {}

    def collect(rows):
        for row in rows:
            if row["label"] in clashing:
                groups.setdefault(row["label"], []).append(row)
            collect(row["children"])
    collect(tree)

    def suffix(row, k):
        # the k nearest ancestors, written from the top down (path order)
        return "/".join(reversed(ancestors[id(row)][:k]))

    for rows in groups.values():
        deepest = max(len(ancestors[id(row)]) for row in rows)
        k = 1
        while k < deepest and len({suffix(row, k) for row in rows}) < len(rows):
            k += 1
        for row in rows:
            appendix = suffix(row, k)
            if appendix:
                row["label"] = "%s (%s)" % (row["label"], appendix)


def build(document, pack):
    """The table a template document describes, without rendering it.

    `pack` carries what the reader cannot know from the document alone --
    the rule-id prefix, the citation, the identifiers to skip, the names
    to give unnamed list items, and which value spellings are examples
    rather than fixed values. `tools/extract_smt_rules.py` holds one per
    vendored template; a caller supplying their own passes the same
    shape.

    Returns the tree and the three facts a table carries about the
    submodel itself. Rendering them into a module is the caller's, and
    for the vendored packs it is still the build tool's.
    """
    submodels = (document or {}).get("submodels") if isinstance(document, dict) else None
    if not submodels:
        raise TemplateRefused(
            "this file declares no submodels, so there is no template in it "
            "to build a table from")
    submodel = submodels[0]
    if "semanticId" not in submodel or not submodel.get("submodelElements"):
        raise TemplateRefused(
            "the first submodel declares no semanticId or no elements; a "
            "template states what it identifies and what it requires")
    counter = [0]
    tree = tuple(row for row in
                 (_rows(element, "", None, counter, pack)
                  for element in submodel["submodelElements"])
                 if row is not None)
    # `_rows` refuses while it walks, so reaching here means the count
    # held. Kept as a second reading of the same number because the two
    # are reached by different paths -- a template of exactly the bound
    # passes the first and is checked again here, and a change that moves
    # the counting has to get past both.
    if counter[0] > MAX_TEMPLATE_ROWS:
        raise TemplateRefused(
            "this template declares %d rows, above the %d this reader builds "
            "a table from" % (counter[0], MAX_TEMPLATE_ROWS))
    # Normalised, like every value on the instance side and like the
    # supplementals four lines below. Read raw, a template written in the
    # ECLASS-CDP spelling built rows that could match nothing, failed to
    # take its identifier over so a pack answered instead, and left the
    # report saying the caller's template decided a run it took no part
    # in -- three wrong answers from one missing call.
    # Each key, then the join -- the order `_values_of` uses for every
    # other reference in this file, and for the instance-side candidates
    # these are compared against. Joined first and normalised once, a
    # reference stacking two ECLASS-CDP URLs stayed a URL pair while
    # every row and every candidate carried the IRDI form, so the
    # template took its identifier over from nobody, a pack answered
    # instead, and the report named a joined URL as what the caller's
    # file claims. The single-key case was repaired; this is the same
    # call, still missing one reader along.
    submodel_sid = "/".join(
        normalize(k["value"]) for k in submodel["semanticId"]["keys"])
    submodel_sid_type = submodel["semanticId"].get("type")
    # What the submodel says about itself *besides* its identifier. Two
    # templates can declare the same semanticId -- 02004 and 02035-2 do --
    # and then this is the only thing in either published file that tells
    # an instance of one from an instance of the other. Normalised like
    # every other match value, so the ECLASS-CDP spelling folds onto the
    # IRDI it means and contributes nothing where that is all there is.
    supplemental = set()
    for reference in submodel.get("supplementalSemanticIds", []):
        supplemental |= _values_of(reference)

    # A label repeated across scopes is qualified by the shortest ancestor
    # suffix that tells the copies apart, so a template that reuses a named
    # sub-structure (02023 does) still gets one BY_LABEL entry per row; a
    # template that does not is left untouched.
    _qualify_repeats(tree)
    labels = _labels(tree, [])
    seen = Counter(labels)
    if len(seen) != len(labels):
        duplicates = sorted(label for label, count in seen.items() if count > 1)
        raise DuplicateLabel(
            "two rows share a label (%s); give the item a name in the "
            "pack's item_names" % ", ".join(duplicates))

    return {"tree": tree, "submodel_sid": submodel_sid,
            "submodel_sid_type": submodel_sid_type, "supplemental": supplemental}


def _flatten(rows, out):
    for row in rows:
        out.append(row)
        _flatten(row["children"], out)
    return out


class Table:
    """A rule table that is not a module.

    The walk takes a table as an argument and reads eight names off it,
    plus `__name__` to key its per-context cache. A generated pack is a
    module and answers all nine; a table built from a template a caller
    supplied has to answer the same nine or it is a second reader wearing
    one name.

    `__name__` is not decoration. `engine.analyze` caches its walk under
    it, so two tables sharing a name silently share one walk — which is
    the failure the table argument was given no default to prevent. A
    run-time table is named for the digest of the document it was built
    from, so two different templates cannot collide and the same template
    twice is the same name.
    """

    __slots__ = ("__name__", "TEMPLATE_CITATION", "TEMPLATE_SEMANTIC_ID",
                 "TEMPLATE_SUBMODEL_SID_TYPE", "TEMPLATE_SUPPLEMENTAL_SEMANTIC_IDS",
                 "TREE", "ROWS", "BY_ID", "BY_LABEL", "_supplied")

    def __init__(self, name, citation, semantic_id, sid_type, supplemental, tree):
        self.__name__ = name
        #: This table came from a caller, so it is the one that
        #: stands when a pack claims the same identifier.
        self._supplied = True
        self.TEMPLATE_CITATION = citation
        self.TEMPLATE_SEMANTIC_ID = semantic_id
        self.TEMPLATE_SUBMODEL_SID_TYPE = sid_type
        self.TEMPLATE_SUPPLEMENTAL_SEMANTIC_IDS = supplemental
        self.TREE = tree
        self.ROWS = tuple(_flatten(tree, []))
        self.BY_ID = {row["id"]: row for row in self.ROWS}
        self.BY_LABEL = {row["label"]: row for row in self.ROWS}

    def __repr__(self):                 # pragma: no cover - diagnostics
        return "<Table %s, %d rows>" % (self.__name__, len(self.ROWS))


def table_from(document, pack, name=None):
    """The table a template describes, as an object the walk can take.

    The same `build` the emitter uses, presented the way a generated
    module presents itself -- so the run-time path and the build-time
    path are one code path with two renderings, and a test can put the
    two side by side and compare rows.

    `name` defaults to a digest of the document, because the walk caches
    on it and a name that repeats is a walk that is reused for a
    different table.
    """
    import hashlib
    import json as _json

    built = build(document, pack)
    if name is None:
        digest = hashlib.sha256(
            _json.dumps(document, sort_keys=True,
                        separators=(",", ":")).encode("utf-8")).hexdigest()
        name = "<template %s>" % digest[:16]
    return Table(name, pack["citation"], built["submodel_sid"],
                 built["submodel_sid_type"],
                 tuple(sorted(built["supplemental"])), built["tree"])


#: What a row's rule says about itself. The same two sentences the
#: generated packs build, kept here so a run-time rule and a built-in one
#: read alike -- a reader should not be able to tell which door a finding
#: came through by its wording.
def _title_of(row):
    return "'%s' as the template declares it (%s)" % (
        row["label"], row["sid"] or "by structure")


def rules_for(table, pack):
    """One `Rule` per row, not registered with anybody.

    Not registered on purpose. `docs/rule-coverage.json` lists every id
    this project publishes and `make exercised` compares the ids that
    fired against it, so an id that exists because somebody passed a file
    would fail a gate about this project's own rules. `runner._meta_rule`
    is the precedent: a `Rule` the run puts without the registry having
    heard of it.

    They go to `runner.execute` like any other rule, which is the only
    place here where a rule that raises becomes a finding rather than a
    traceback. A rule built from a stranger's template is the last kind
    that should be able to take the process down.
    """
    from .model import Rule
    from .rules.engine import analyze, matched_submodels

    def check_for(row_id):
        def check(ctx):
            if not matched_submodels(ctx, table):
                return      # nothing here claims this template
            yield from analyze(ctx, table)["violations"].get(row_id, ())
        return check

    # The route every vendored pack's generated rows declare: a row names
    # an element, or -- for a count at the top of the walk -- the
    # submodel, which the finding itself says. Built without one, every
    # finding a supplied template drew carried `path: []` beside the same
    # row's `["document", "submodel", "element"]` from a vendored pack.
    return [Rule(id=row["id"], kind="template", prio="MUST",
                 title=_title_of(row),
                 spec="%s, SMT/Cardinality qualifier" % table.TEMPLATE_CITATION,
                 fn=check_for(row["id"]), fix=row["fix"],
                 path=("document", "submodel", "element"))
            for row in table.ROWS]
