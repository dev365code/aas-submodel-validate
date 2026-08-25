#!/usr/bin/env python3
"""Generate the structural rule tables from the vendored official templates.

Every element in an IDTA submodel template carries its own machine-readable
constraints -- an SMT/Cardinality qualifier, a semanticId, a valueType,
sometimes an AllowedIdShort pattern -- so the structural rule layer is
extracted, not hand-written: hand-copying sixty-four rows is how one of
them silently goes stale. `--check` regenerates and byte-compares, the
same contract the sibling validators use for their generated files.

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
import re
import sys
from pathlib import Path

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

#: The open-content placeholders of 02003 §3.5 -- see the module docstring.
ARBITRARY = "https://admin-shell.io/SMT/General/Arbitrary"

#: One entry per vendored template. `source` names the file in the header
#: of the generated module, so a reader lands on the right upstream
#: artefact; `prefix` is the rule-id namespace the registry keeps unique.
PACKS = (
    {
        "template": ROOT / "src/aas_submodel_validate/data/smt/02004/2.0.1/template.json",
        "output": ROOT / "src/aas_submodel_validate/rules/hd_tables.py",
        "prefix": "HD-E",
        "source": "IDTA 02004-2-0-1 template.json",
        "item_names": HD_ITEM_NAMES,
        "example_types": ("ExampleValue",),
        "skip_sids": frozenset(),
    },
    {
        "template": ROOT / "src/aas_submodel_validate/data/smt/02003/2.0.1/template.json",
        "output": ROOT / "src/aas_submodel_validate/rules/td_tables.py",
        "prefix": "TD-E",
        "source": "IDTA 02003_2-0-1 template.json",
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
        "prefix": "DBP-E",
        "source": "IDTA 02035-2_DBP-Part-2_HandoverDocumentation.json",
        "item_names": DBP_ITEM_NAMES,
        "example_types": ("ExampleValue",),
        "skip_sids": frozenset(),
    },
)

CARDINALITY = {"One": (1, 1), "ZeroToOne": (0, 1),
               "OneToMany": (1, None), "ZeroToMany": (0, None)}

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
    return "any number"


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
    # Absent means 0..*: see the module docstring. A dict comprehension
    # keeps the template's own order, which is the order examples join in.
    card = CARDINALITY.get(qualifiers.get("SMT/Cardinality"), (0, None))
    examples = [value for key, value in qualifiers.items()
                if key in pack["example_types"]]
    example = " | ".join(examples) if examples else None
    fix = ("Provide %s '%s' element(s)%s with semanticId %s%s."
           % (_cardinality_words(card), label,
              " under %s" % parent_label if parent_label else "",
              _primary_sid(element) or "(as the template declares)",
              "; example value: %r" % example if example else ""))
    # A MultiLanguageProperty's `value` is a list of language entries, not
    # of elements; only what declares a modelType is a child here.
    children = [
        row for row in (
            _rows(child, label, row_id, counter, pack)
            for child in (element.get("value") or [])
            if isinstance(child, dict) and "modelType" in child)
        if row is not None
    ] if isinstance(element.get("value"), list) else []
    return {
        "id": row_id,
        "label": label,
        "parent": parent_id,
        "kind": element["modelType"],
        "match": _match_set(element),
        "sid": _primary_sid(element),
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


def _labels(rows, out):
    for row in rows:
        out.append(row["label"])
        _labels(row["children"], out)
    return out


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

    # The hand rules navigate by label, and BY_LABEL is a dict: two rows
    # sharing a label would make one of them silently unreachable. Fail
    # here, where a person can name the second one, rather than there.
    labels = _labels(tree, [])
    if len(set(labels)) != len(labels):
        duplicates = sorted({label for label in labels if labels.count(label) > 1})
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
        "TEMPLATE_SEMANTIC_ID = %r" % submodel_sid,
        "TEMPLATE_SUBMODEL_SID_TYPE = %r" % submodel_sid_type,
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
