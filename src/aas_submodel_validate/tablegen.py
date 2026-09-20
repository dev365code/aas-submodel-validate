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

#: How many rows a template may declare. Not a byte bound: a template of
#: 46 MiB sits inside the 64 MiB this reader advertises for a document,
#: and what the generator spends is decided by rows, not by weight.
#: Chosen far above anything published -- the widest template vendored
#: here has thirty-eight rows -- and far below where a generated table
#: stops being something a person could read a finding out of.
MAX_TEMPLATE_ROWS = 10_000


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
    # Counted here, before anything walks the tree twice. Put after the
    # duplicate-label backstop it would be free: that backstop is the
    # expensive path and the bound exists to keep a caller's file from
    # reaching it at any size.
    if counter[0] > MAX_TEMPLATE_ROWS:
        raise TemplateRefused(
            "this template declares %d rows, above the %d this reader builds "
            "a table from" % (counter[0], MAX_TEMPLATE_ROWS))
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
                 "TREE", "ROWS", "BY_ID", "BY_LABEL")

    def __init__(self, name, citation, semantic_id, sid_type, supplemental, tree):
        self.__name__ = name
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

    return [Rule(id=row["id"], kind="template", prio="MUST",
                 title=_title_of(row),
                 spec="%s, SMT/Cardinality qualifier" % table.TEMPLATE_CITATION,
                 fn=check_for(row["id"]), fix=row["fix"])
            for row in table.ROWS]
