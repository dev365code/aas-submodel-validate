"""Rows from a template document — the half of the generator that reads.

Split out of `tools/extract_smt_rules.py` and moved here for one reason:
`tools/` is not installed. It is not in the wheel (measured: a built
wheel has 56 members and none of them under `tools`), and putting it
there would install two more top-level names into everybody's
site-packages, which `tools/check_distributions.py` refuses in writing.
So an installed copy of this package could not build a table, and
neither could the single-file build, which copies exactly this directory.

That matters because a mode that reads a template a caller supplies has
to give the same verdict from every entrance. The command line, the
library, the single file and an action are the same engine or they are
not one engine, and the entrance that cannot reach the generator is the
one that answers differently.

What stayed behind is the part that writes: the pack list, the Python
source it renders, and the `--check` that proves a table matches its
generator byte for byte. Those are build-time and belong to the build.

The functions below are the ones that were here, unchanged, so that the
six vendored tables regenerate to the same bytes. The one difference is
`DuplicateLabel`: the generator used to raise `SystemExit` with a
sentence, which is a build tool's way of leaving by 1, and a run-time
caller owes 2 — "could not judge the input" — instead. The exception
carries the sentence and each entrance decides its own code.
"""
from __future__ import annotations

import re
from collections import Counter

from .semantics import normalize


class DuplicateLabel(Exception):
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
    """`RefersTo[\\d{2,3}]` -> `^RefersTo(?:\\d{2,3})?$`.

    The digits are the numbering suffix for multiple instances, so they
    are optional: the template's *own* idShort for the single case
    ("PreviewFile") must not fail the template's own qualifier.
    """
    matched = _ALLOWED.match(raw)
    if matched:
        return "^%s(?:%s)?$" % (matched.group(1), matched.group(2))
    return "^%s$" % raw


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


def _match_set(element):
    values = set()
    if element.get("semanticId"):
        values |= _values_of(element["semanticId"])
    for supplemental in element.get("supplementalSemanticIds", []):
        values |= _values_of(supplemental)
    return tuple(sorted(values))


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


def _rows(element, parent_label, parent_id, counter, pack):
    """One row, and its children's rows -- or None where the template
    describes open content rather than an obligation (see `skip_sids`).
    The check comes before the counter so skipped subtrees leave no gap in
    the numbering and no trace in a sibling template's table."""
    if _primary_sid(element) in pack["skip_sids"]:
        return None
    label = element.get("idShort") \
        or pack["item_names"].get(parent_label, parent_label + "Item")
    counter[0] += 1
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
    for _container in ("value", "statements"):
        _items = element.get(_container)
        if isinstance(_items, list):
            sub_elements.extend(_items)
    # A self-containing element -- an Entity or SubmodelElementCollection
    # whose own child repeats its semanticId (02011's Node holds a Node) --
    # is a recursion point: mark it and leave the repeating child
    # unexpanded, so the table stays finite (docs/divergences.md #48).
    # Only these two kinds, the shapes the standard nests: a
    # SubmodelElementList and its item share one identifier by design (#39)
    # but are a list with one item kind, not self-containment, and no other
    # kind reaches a child through `value`/`statements`. Direct
    # self-containment only; indirect (A in B in A) is out of scope.
    recurses = None
    children = []
    for child in sub_elements:
        if not (isinstance(child, dict) and "modelType" in child):
            continue
        if (my_sid and _primary_sid(child) == my_sid
                and child["modelType"] == element["modelType"]
                and element["modelType"] in ("Entity", "SubmodelElementCollection")):
            recurses = my_sid
            continue
        child_row = _rows(child, label, row_id, counter, pack)
        if child_row is not None:
            children.append(child_row)
    row = {
        "id": row_id,
        "label": label,
        "parent": parent_id,
        "kind": element["modelType"],
        "match": _match_set(element),
        "sid": my_sid,
        "sid_type": element.get("semanticId", {}).get("type"),
        "card": card,
        "value_type": element.get("valueType"),
        "list_type": element.get("typeValueListElement"),
        "allowed_idshort": (_intended_pattern(qualifiers["AllowedIdShort"])
                           if "AllowedIdShort" in qualifiers else None),
        "example": example,
        "fix": fix,
        "children": tuple(children),
    }
    if recurses is not None:
        row["recurses"] = recurses
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
    submodel = document["submodels"][0]
    counter = [0]
    tree = tuple(row for row in
                 (_rows(element, "", None, counter, pack)
                  for element in submodel["submodelElements"])
                 if row is not None)
    submodel_sid = "/".join(k["value"] for k in submodel["semanticId"]["keys"])
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
