# -*- coding: utf-8 -*-
"""Derive a requirement index from IDTA submodel template files (AAS JSON).

What the source states, and this reads:
  * the element tree, by idShort path;
  * the SMT/Cardinality qualifier on each element -- One, ZeroToOne, OneToMany,
    ZeroToMany -- which is where a template says what must be present;
  * the semanticId of the submodel and of every element, which is the only thing
    a conformance check may match on (an idShort is a label, not an identity);
  * the declared model type and value type.

What it does not do: decide anything the file does not state. An element with no
cardinality qualifier is recorded as "unclear", not as optional.

Example values are ignored. Where a part also ships a *_without_examplevalues
file, that file is read as a cross-check on the element tree, not as a second
source of records.

Usage:
    python3 tools/extract_idta_smt.py \
        --sources-dir sources/idta --out requirements-idta.json
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common  # noqa: E402

SOURCE = "idta-smt"

# https://admin-shell.io/SubmodelTemplates/Cardinality/1/0
CARDINALITY_TYPES = ("SMT/Cardinality", "Multiplicity", "Cardinality")
MANDATORY_BY_CARDINALITY = {
    "One": "yes",
    "OneToMany": "yes",
    "ZeroToOne": "no",
    "ZeroToMany": "no",
}
# Only these carry children; a Property's "value" is a value, not a subtree.
CONTAINERS = ("SubmodelElementCollection", "SubmodelElementList", "Entity")

# Which template each directory holds, and how it was pinned. Directory names
# carry the version because the files themselves do not always: see the notes.
TEMPLATES = {
    "02035-1_v1.0": ("IDTA 02035-1", "V1.0", True),
    "02035-2_v1.0": ("IDTA 02035-2", "V1.0", True),
    "02035-3_v1.0": ("IDTA 02035-3", "V1.0", True),
    "02035-4_v1.0.1": ("IDTA 02035-4", "V1.0.1", True),
    "02035-5_v1.0.2": ("IDTA 02035-5", "V1.0.2", True),
    "02035-6_v1.0.1": ("IDTA 02035-6", "V1.0.1", True),
    "02035-7_v1.0.1": ("IDTA 02035-7", "V1.0.1", True),
    "02099-1_v1.0.1": ("IDTA 02099-1", "V1.0.1", True),
    # Read for comparison only -- these are the base templates the battery
    # passport parts were derived from, not part of the battery passport index.
    "02035-5_v1.0.1": ("IDTA 02035-5", "V1.0.1", False),
    "02099-1_v1.0.0": ("IDTA 02099-1", "V1.0", False),
    "_base_02004_v2.0": ("IDTA 02004", "V2.0", False),
    "_base_02023_v1.0": ("IDTA 02023", "V1.0", False),
}


def first_key_value(ref):
    """A semanticId is a reference; the identity is the first key's value."""
    if not isinstance(ref, dict):
        return ""
    keys = ref.get("keys") or []
    if not keys:
        return ""
    return keys[0].get("value", "") or ""


def cardinality_of(element):
    for q in element.get("qualifiers") or []:
        if q.get("type") in CARDINALITY_TYPES:
            return q.get("value", "") or ""
    return ""


def text_of(element):
    for field in ("displayName", "description"):
        for entry in element.get(field) or []:
            if entry.get("text"):
                return entry["text"]
    return element.get("idShort", "") or ""


def walk(element, prefix, out, depth=0):
    """Depth-first over the element tree, recording one row per element."""
    id_short = element.get("idShort") or "[%d]" % len(out)
    path = prefix + "/" + id_short if prefix else id_short
    card = cardinality_of(element)
    out.append(
        {
            "path": path,
            "id_short": id_short,
            "text": text_of(element),
            "semantic_id": first_key_value(element.get("semanticId")),
            "cardinality": card,
            "model_type": element.get("modelType", "") or "",
            "value_type": element.get("valueType", "") or "",
            "depth": depth,
        }
    )
    if element.get("modelType") in CONTAINERS and isinstance(element.get("value"), list):
        for child in element["value"]:
            if isinstance(child, dict):
                walk(child, path, out, depth + 1)


def read_submodel_file(path):
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    out = []
    for submodel in doc.get("submodels") or []:
        rows = []
        for child in submodel.get("submodelElements") or []:
            walk(child, submodel.get("idShort", "") or "", rows)
        admin = submodel.get("administration") or {}
        out.append(
            {
                "id_short": submodel.get("idShort", "") or "",
                "submodel_id": submodel.get("id", "") or "",
                "semantic_id": first_key_value(submodel.get("semanticId")),
                "administration_version": "%s.%s"
                % (admin.get("version", "?"), admin.get("revision", "?")),
                "template_id": admin.get("templateId", "") or "",
                "kind": submodel.get("kind", "") or "",
                "elements": rows,
            }
        )
    return out


SAMM_VERSION = re.compile(r":(\d+\.\d+\.\d+)#")


def namespace_version(semantic_id):
    """The version a semanticId carries in itself, when it carries one."""
    m = SAMM_VERSION.search(semantic_id or "")
    if m:
        return m.group(1)
    m = re.search(r"/(\d+)/(\d+)/", semantic_id or "")
    if m:
        return "%s.%s" % (m.group(1), m.group(2))
    return ""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sources-dir", default="sources/idta")
    ap.add_argument("--out", default="requirements-idta.json")
    args = ap.parse_args(argv)

    provenance, records, notes = [], [], []
    comparison = {}
    seen_semantic_ids = {}

    for directory in sorted(os.listdir(args.sources_dir)):
        full = os.path.join(args.sources_dir, directory)
        if not os.path.isdir(full) or directory not in TEMPLATES:
            continue
        template, version, indexed = TEMPLATES[directory]
        files = sorted(f for f in os.listdir(full) if f.endswith(".json"))
        primary = [f for f in files if "_without_examplevalues" not in f]
        crosscheck = [f for f in files if "_without_examplevalues" in f]
        if not primary:
            notes.append("%s %s: no template file with example values" % (template, version))
            continue

        path = os.path.join(full, primary[0])
        submodels = read_submodel_file(path)
        digest = _common.sha256_file(path)
        provenance.append(
            {
                "file": _common.provenance_path(path, keep=3),
                "sha256": digest,
                "version": "%s %s" % (template, version),
                "role": "indexed" if indexed else "comparison",
            }
        )

        for submodel in submodels:
            key = "%s %s" % (template, version)
            comparison[key] = {
                "submodel_id_short": submodel["id_short"],
                "submodel_semantic_id": submodel["semantic_id"],
                "administration_version": submodel["administration_version"],
                "template_id": submodel["template_id"],
                "elements": len(submodel["elements"]),
                "semantic_id_version": namespace_version(submodel["semantic_id"]),
                "element_semantic_id_versions": sorted(
                    {
                        namespace_version(e["semantic_id"])
                        for e in submodel["elements"]
                        if namespace_version(e["semantic_id"])
                    }
                ),
                "sha256": digest,
            }
            seen_semantic_ids.setdefault(submodel["semantic_id"], []).append(key)

            if crosscheck:
                other = read_submodel_file(os.path.join(full, crosscheck[0]))
                a = [e["path"] for e in submodel["elements"]]
                b = [e["path"] for sm in other for e in sm["elements"]]
                if a != b:
                    notes.append(
                        "%s: element tree differs between the file with example "
                        "values (%d elements) and the one without (%d)"
                        % (key, len(a), len(b))
                    )
            elif indexed:
                notes.append(
                    "%s: ships no file without example values, so the element "
                    "tree has no second reading to be checked against" % key
                )

            if not indexed:
                continue

            slug = template.replace(" ", "-").lower()
            for element in submodel["elements"]:
                card = element["cardinality"]
                records.append(
                    _common.record(
                        id="%s:%s:%s" % (SOURCE, slug, element["path"]),
                        kind="element",
                        section="%s %s / %s" % (template, version, element["path"]),
                        text=element["text"],
                        mandatory=MANDATORY_BY_CARDINALITY.get(card, "unclear"),
                        condition="",
                        access="n/a",
                        applies_to=[],
                        joins=[],
                        template=template,
                        template_version=version,
                        id_short=element["id_short"],
                        semantic_id=element["semantic_id"],
                        cardinality=card or "(none)",
                        model_type=element["model_type"],
                        value_type=element["value_type"],
                        depth=element["depth"],
                    )
                )

    for semantic_id, holders in sorted(seen_semantic_ids.items()):
        if len(holders) > 1:
            notes.append(
                "submodel semanticId %s is used by more than one template: %s"
                % (semantic_id, ", ".join(holders))
            )

    doc = _common.write_index(
        args.out,
        SOURCE,
        records,
        provenance,
        counts={
            "by_template": _common.tally(records, "template"),
            "by_cardinality": _common.tally(records, "cardinality"),
            "templates": comparison,
        },
        notes=notes,
    )
    _common.report(doc, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
