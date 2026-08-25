#!/usr/bin/env python3
"""Generate the structural rule table from the vendored official template.

Every element in the IDTA 02004 template carries its own machine-readable
constraints -- an SMT/Cardinality qualifier, a semanticId, a valueType,
sometimes an AllowedIdShort pattern -- so the structural rule layer is
extracted, not hand-written: hand-copying 38 rows is how one of them
silently goes stale. `--check` regenerates and byte-compares, the same
contract the sibling validators use for their generated files.

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

TEMPLATE = ROOT / "src/aas_submodel_validate/data/smt/02004/2.0.1/template.json"
OUTPUT = ROOT / "src/aas_submodel_validate/rules/hd_tables.py"

#: Item labels for elements the template leaves unnamed (list children
#: carry no idShort -- the metamodel forbids it). These labels are chosen
#: to be readable in a finding; several match the PDF's element names, a
#: few (LanguageCode, EntityForDocumentation) are our own where the PDF
#: uses a different word.
ITEM_NAMES = {
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


def _rows(element, parent_label, parent_id, counter):
    label = element.get("idShort") or ITEM_NAMES.get(parent_label, parent_label + "Item")
    counter[0] += 1
    row_id = "HD-E%02d" % counter[0]
    qualifiers = {q.get("type"): q.get("value") for q in element.get("qualifiers", [])}
    card = CARDINALITY[qualifiers["SMT/Cardinality"]]
    example = qualifiers.get("ExampleValue")
    fix = ("Provide %s '%s' element(s)%s with semanticId %s%s."
           % (_cardinality_words(card), label,
              " under %s" % parent_label if parent_label else "",
              _primary_sid(element) or "(as the template declares)",
              "; example value: %r" % example if example else ""))
    children = [
        _rows(child, label, row_id, counter)
        for child in (element.get("value") or [])
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


def generate() -> str:
    document = json.loads(TEMPLATE.read_text("utf-8-sig"))
    submodel = document["submodels"][0]
    counter = [0]
    tree = tuple(_rows(element, "", None, counter)
                 for element in submodel["submodelElements"])
    submodel_sid = "/".join(k["value"] for k in submodel["semanticId"]["keys"])
    submodel_sid_type = submodel["semanticId"].get("type")

    lines = [
        '"""GENERATED by tools/extract_smt_rules.py from the vendored official',
        "template -- edit the generator, regenerate, never this file.",
        "",
        "Source: IDTA 02004-2-0-1 template.json (CC BY 4.0, (c) IDTA and",
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
    text = generate()
    if args.check:
        if OUTPUT.read_text("utf-8") != text:
            print("rules/hd_tables.py is stale: run tools/extract_smt_rules.py",
                  file=sys.stderr)
            return 1
        print("hd_tables.py matches its generator (%d rows)" % text.count("'id':"))
        return 0
    OUTPUT.write_text(text, "utf-8")
    print("wrote %s" % OUTPUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
