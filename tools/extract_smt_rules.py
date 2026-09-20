#!/usr/bin/env python3
"""Generate the structural rule tables from the vendored official templates.

Every element in an IDTA submodel template carries its own machine-readable
constraints -- an SMT/Cardinality qualifier, a semanticId, a valueType,
sometimes an AllowedIdShort pattern -- so the structural rule layer is
extracted, not hand-written: hand-copying 142 rows is how one of them
silently goes stale. That number is pinned in `tests/test_readme_front.py`
along with the rest, because it said sixty-four for as long as there were
two tables and went on saying it through a third -- this sentence was an
instance of the thing it warns about. `--check` regenerates and
byte-compares, the same contract the sibling validators use for their
generated files.

One generator, one row shape, one table per template (PACKS below).

What is deliberately interpreted rather than copied:

- **Match values.** A list item's identity is one key whose value joins
  the list IRDI and the item IRDI with "/" (e.g.
  `0173-1#02-ABI500#003/0173-1#01-AHF579#003`) -- a single key, the same
  in the template and the official example. A row matches on the union of
  that whole value, its supplemental spellings (ECLASS-CDP URLs
  normalised to IRDIs, `~N` cardinality suffixes admitted bare), and the
  "/"-join of any genuinely multi-key reference. The composite is kept
  whole -- not split into its components (docs/divergences.md #8).
- **AllowedIdShort.** The template writes `RefersTo[\\d{2,3}]`, which as
  a regular expression is a character class matching "RefersTo" plus one
  character. The evident intent `^RefersTo(?:\\d{2,3})?$` is what lands in
  the table -- the digits are the multiple-instance suffix and so optional
  (docs/divergences.md #5) -- and it is only ever an informational lint
  (Annex A lets any unique idShort stand).
- **Open content is not a rule.** 02003 §3.5 says "the set of suitable
  semanticIds is not restricted": its thirty-six placeholder elements
  describe what a manufacturer *may* add. Generating rules from them would
  demand the unconstrained, and all thirty-six carry the same identifier
  -- six of them siblings in one scope -- so the first row would claim
  every arbitrary element the walk met. `skip_sids`
  drops the subtree before it is numbered.
- **A missing cardinality is 0..\\*, not an error and not One.** 02004
  qualified every element; 02003 leaves four list items unqualified, and
  its PDF element tables give each of them 0..*. Assuming One there would
  invent an obligation the standard does not state.
- **Several example values, one remedy.** 02003 gives one element four
  ExampleValue qualifiers, one per classification system. Keeping the
  first would tell a reader ECLASS is the answer when the template offers
  four, so they are joined in template order.
- **A list child that carries an idShort.** AASd-120 forbids one on a
  direct child of a SubmodelElementList, which is the whole reason
  `item_names` exists. 02035-2 breaks it on four of its six list
  children, so those four rows are labelled with the name the artefact
  itself carries. Each pack names all of its list items anyway, using
  02004's word where the element is 02004's, so an upstream repair of
  that defect would rename nothing -- a row suddenly called
  "DocumentsItem" would announce a divergence where none had appeared.
"""
from __future__ import annotations

import argparse
import json
import pathlib as _pathlib
import re
import sys
import sys as _sys
from collections import Counter
from pathlib import Path

# The package, from wherever this script is. `make` exports
# PYTHONPATH and the lint job installs the package first, but
# CI's wheel job installs nothing and an unpacked sdist has no
# install at all -- and `MANIFEST.in` grafts this directory for
# exactly that reader. Two scripts here already did this; the
# import added to all eight assumed the other six were as
# lucky.
_TOOLS_SRC = str(_pathlib.Path(__file__).resolve().parent.parent / "src")
if _TOOLS_SRC not in _sys.path:
    _sys.path.insert(0, _TOOLS_SRC)

from aas_submodel_validate._terminal import survive  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aas_submodel_validate.semantics import normalize  # noqa: E402

#: Item labels for elements a template leaves unnamed (AASd-120 forbids a
#: list child an idShort; 02004 obeys it, 02035-2 does not -- see the
#: module docstring). These labels are chosen to be
#: readable in a finding; most match the PDF's element names, a few
#: (LanguageCode, EntityForDocumentation) are our own where the PDF uses a
#: different word. Without one, a row would be called "DocumentsItem".
HD_ITEM_NAMES = {
    "Documents": "Document",
    "DocumentIds": "DocumentId",
    "DocumentClassifications": "DocumentClassification",
    "DocumentVersions": "DocumentVersion",
    "Language": "LanguageCode",
    "RefersToEntities": "RefersTo",
    "BasedOnReferences": "BasedOn",
    "TranslationOfEntities": "TranslationOf",
    "DigitalFiles": "DigitalFile",
    "DocumentedEntities": "DocumentedEntity",
    "Entities": "EntityForDocumentation",
}

#: 02003's four unnamed list items. Three of these are the PDF's own word
#: for the item (Tables 3, 7 and 11); ProductClassification is ours -- the
#: PDF writes that one in the plural in both the list row and the item's
#: own table, and a row called "ProductClassifications" twice over would
#: be unreadable in a finding.
TD_ITEM_NAMES = {
    "ProductImages": "ProductImage",
    "ProductClassifications": "ProductClassification",
    "TechnicalPropertyAreas": "TechnicalPropertyArea",
    "SpecificDescriptions": "SpecificDescription",
}

#: 02035-2's six list items, in 02004's words -- it is a profile of that
#: template and every one of its elements is one of 02004's. Only two are
#: read today: the published file gives the other four an idShort, which
#: AASd-120 forbids and which therefore wins. They are named anyway so
#: that repairing that defect upstream renames nothing here.
DBP_ITEM_NAMES = {
    "Documents": "Document",
    "DocumentClassifications": "DocumentClassification",
    "DocumentIds": "DocumentId",
    "DocumentVersions": "DocumentVersion",
    "Language": "LanguageCode",
    "DigitalFiles": "DigitalFile",
}

#: 02006's two list items (Markings, GuidelineSpecificProperties).
DN_ITEM_NAMES = {
    "Markings": "Marking",
    "GuidelineSpecificProperties": "GuidelineSpecificProperty",
}

#: The open-content placeholders of 02003 §3.5 -- see the module docstring.
ARBITRARY = "https://admin-shell.io/SMT/General/Arbitrary"

#: 02006's open-content placeholders -- a manufacturer's arbitrary
#: additions under AssetSpecificProperties and GuidelineSpecificProperties,
#: three of them, distinct from 02003's single ARBITRARY.
#: 02023's ProductOrSectorSpecificCarbonFootprints repeats the named
#: PcfCalculationMethods sub-structure that ProductCarbonFootprints
#: already carries (same semanticId, different scope). The generator
#: qualifies a label repeated across scopes by the shortest ancestor
#: suffix that distinguishes the copies (`_qualify_repeats`), so both
#: sections are judged. What is left out is
#: the open-content placeholder inside PcfInformation: an `ArbitraryContent`
#: property wearing the SMT/General/Arbitrary marker, which stands for
#: content the template does not define -- the same treatment 02006 gives
#: its Arbitrary* elements (docs/divergences.md).
PCF_SKIP = frozenset((
    "https://admin-shell.io/SMT/General/Arbitrary",
))

PCF_ITEM_NAMES = {
    "ProductCarbonFootprints": "ProductCarbonFootprint",
    "PcfCalculationMethods": "PcfCalculationMethod",
    "LifeCyclePhases": "LifeCyclePhase",
    "ProductOrSectorSpecificCarbonFootprints": "ProductOrSectorSpecificCarbonFootprint",
}

DN_ARBITRARY = frozenset((
    "https://admin-shell.io/SMT/General/ArbitraryProp",
    "https://admin-shell.io/SMT/General/ArbitraryMLP",
    "https://admin-shell.io/SMT/General/ArbitraryFile",
))

#: One entry per vendored template. `source` names the file in the header
#: of the generated module, so a reader lands on the right upstream
#: artefact; `prefix` is the rule-id namespace the registry keeps unique.
#: `citation` is how a finding's `per` line names this template to a
#: reader who has to argue with it -- the document, without the file
#: extension, spelled the way the standard is cited rather than the way
#: the file is named. It was written out by hand in each rule module
#: until a finding needed to cite the same template for something other
#: than the cardinality qualifier, and two copies of a citation are two
#: chances to cite different documents for one reading.
PACKS = (
    {
        "template": ROOT / "src/aas_submodel_validate/data/smt/02004/2.0.1/template.json",
        "output": ROOT / "src/aas_submodel_validate/rules/hd_tables.py",
        "prefix": "HD-E",
        "source": "IDTA 02004-2-0-1 template.json",
        "citation": "IDTA 02004-2-0-1 template",
        "item_names": HD_ITEM_NAMES,
        "example_types": ("ExampleValue",),
        "skip_sids": frozenset(),
    },
    {
        "template": ROOT / "src/aas_submodel_validate/data/smt/02003/2.0.1/template.json",
        "output": ROOT / "src/aas_submodel_validate/rules/td_tables.py",
        "prefix": "TD-E",
        "source": "IDTA 02003_2-0-1 template.json",
        "citation": "IDTA 02003-2-0-1 template",
        "item_names": TD_ITEM_NAMES,
        "example_types": ("SMT/ExampleValue/ECLASS", "SMT/ExampleValue/CDD",
                          "SMT/ExampleValue/UNSPSC", "SMT/ExampleValue/CustomerSpecific"),
        "skip_sids": frozenset((ARBITRARY,)),
    },
    # The Digital Battery Passport's part 2 is a second Handover
    # Documentation template and declares 02004's submodel semanticId
    # exactly, so its rows need their own id namespace and their own
    # table: one row cannot carry two remedy sentences. Its qualifier
    # vocabulary is 02004's -- bare `ExampleValue`, `SMT/Cardinality` on
    # every element, no open content -- so none of the readings 02003
    # forced apply here.
    {
        "template": ROOT / "src/aas_submodel_validate/data/smt/02035-2/1.0/template.json",
        "output": ROOT / "src/aas_submodel_validate/rules/dbp_tables.py",
        "prefix": "DBP2-E",
        "source": "IDTA 02035-2_DBP-Part-2_HandoverDocumentation.json",
        "citation": "IDTA 02035-2 1.0 template",
        "item_names": DBP_ITEM_NAMES,
        "example_types": ("ExampleValue",),
        "skip_sids": frozenset(),
    },
    {
        "template": ROOT / "src/aas_submodel_validate/data/smt/02006/3.0/template.json",
        "output": ROOT / "src/aas_submodel_validate/rules/dn_tables.py",
        "prefix": "DN-E",
        "source": "IDTA 02006-3-0_Template_Digital Nameplate.json",
        "citation": "IDTA 02006-3-0 template",
        "item_names": DN_ITEM_NAMES,
        "example_types": (),
        "skip_sids": DN_ARBITRARY,
    },
    {
        "template": ROOT / "src/aas_submodel_validate/data/smt/02023/1.0/template.json",
        "output": ROOT / "src/aas_submodel_validate/rules/pcf_tables.py",
        "prefix": "PCF-E",
        "source": "IDTA 02023 _Template_CarbonFootprint.json",
        "citation": "IDTA 02023 1.0 template",
        "item_names": PCF_ITEM_NAMES,
        "example_types": (),
        "skip_sids": PCF_SKIP,
    },
    # IDTA 02002 Contact Information 1.0.1 -- the edition this project
    # reads; 1.0 gives `IPCommunication` the submodel's own identifier,
    # which 1.0.1 repairs (docs/divergences.md). Every one of its
    # thirty-six elements states its cardinality with the older
    # `Multiplicity` qualifier and none with `SMT/Cardinality` (#50). It
    # holds no SubmodelElementList and no open content: repetition rides on
    # a collection's own cardinality instead, so there are no item names to
    # supply and nothing to skip.
    {
        "template": ROOT / "src/aas_submodel_validate/data/smt/02002/1.0.1/template.json",
        "output": ROOT / "src/aas_submodel_validate/rules/contact_tables.py",
        "prefix": "CI-E",
        "source": "IDTA 02002-1-0-1_Template_ContactInformation.json",
        "citation": "IDTA 02002-1-0-1 template",
        "item_names": {},
        "example_types": (),
        "skip_sids": frozenset(),
    },
)

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
            # A row with no ancestor (top level) has no suffix to qualify
            # by, so it keeps its bare label rather than becoming `Label ()`.
            # Two such rows sharing a label stay identical and the backstop
            # reports them.

def generate(pack) -> str:
    document = json.loads(pack["template"].read_text("utf-8-sig"))
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
    # The hand rules navigate by label, and BY_LABEL is a dict: two rows
    # sharing a label would make one of them silently unreachable. Fail
    # here, where a person can name the second one, rather than there.
    labels = _labels(tree, [])
    # Counted, not re-counted. This is the same `labels.count(label)` in a
    # comprehension over `labels` that `_qualify_repeats` had, and the fix
    # there left it standing here -- where it is worse, because it runs
    # only when there are duplicates, so the path that got fast was the
    # one that already worked and the refusal stayed quadratic. Measured
    # end to end before this change: 4,000 elements refused in 0.11s,
    # 8,000 in 0.55s, 16,000 in 2.5s, 32,000 in 9.4s, on files of a few
    # megabytes.
    seen = Counter(labels)
    if len(seen) != len(labels):
        duplicates = sorted(label for label, count in seen.items() if count > 1)
        raise SystemExit("%s: two rows share a label (%s); give the item a name "
                         "in the pack's item_names"
                         % (pack["output"].name, ", ".join(duplicates)))

    lines = [
        '"""GENERATED by tools/extract_smt_rules.py from the vendored official',
        "template -- edit the generator, regenerate, never this file.",
        "",
        "Source: %s (CC BY 4.0, (c) IDTA and" % pack["source"],
        'contributors; pin and hashes in THIRD_PARTY.md)."""',
        "",
        "TEMPLATE_CITATION = %r" % pack["citation"],
        "TEMPLATE_SEMANTIC_ID = %r" % submodel_sid,
        "TEMPLATE_SUBMODEL_SID_TYPE = %r" % submodel_sid_type,
        "TEMPLATE_SUPPLEMENTAL_SEMANTIC_IDS = %r" % (tuple(sorted(supplemental)),),
        "",
        "TREE = %s" % _fmt(tree, 0),
        "",
        "",
        "def _flatten(rows, out):",
        "    for row in rows:",
        "        out.append(row)",
        "        _flatten(row[\"children\"], out)",
        "    return out",
        "",
        "",
        "ROWS = tuple(_flatten(TREE, []))",
        "BY_ID = {row[\"id\"]: row for row in ROWS}",
        "BY_LABEL = {row[\"label\"]: row for row in ROWS}",
        "",
    ]
    return "\n".join(lines)


def _fmt(value, depth):
    pad = "    " * depth
    if isinstance(value, tuple) and value and isinstance(value[0], dict):
        inner = ",\n".join(pad + "    " + _fmt(v, depth + 1) for v in value)
        return "(\n%s,\n%s)" % (inner, pad)
    if isinstance(value, dict):
        inner = ",\n".join('%s    %r: %s' % ("    " * depth, k, _fmt(v, depth + 1))
                           for k, v in value.items())
        return "{\n%s,\n%s}" % (inner, "    " * depth)
    return repr(value)


def main() -> int:
    survive()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    bad = 0
    for pack in PACKS:
        output = pack["output"]
        text = generate(pack)
        if args.check:
            if not output.exists() or output.read_text("utf-8") != text:
                print("rules/%s is stale: run tools/extract_smt_rules.py"
                      % output.name, file=sys.stderr)
                bad = 1
                continue
            print("%s matches its generator (%d rows)"
                  % (output.name, text.count("'id':")))
        else:
            output.write_text(text, "utf-8")
            print("wrote %s" % output)
    return bad


if __name__ == "__main__":
    sys.exit(main())
