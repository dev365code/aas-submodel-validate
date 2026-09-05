"""Write `rules/battery_tables.py` from the published requirements indexes.

Two tables, both facts about documents rather than readings of them:

`SHARED_SUBMODEL_IDS` -- every submodel semanticId that more than one
published template claims. Two today: `0173-1#01-AHF578#003` (IDTA 02004
and 02035-2, the pair this project has tables for) and one
CarbonFootprint identifier (IDTA 02023 and 02035-3, neither of which it
has). The collision is what makes `--profile` necessary, and it is read
off the templates rather than asserted.

`LAW_REQUIRES_TEMPLATE_OPTIONAL` -- every element the template marks
`ZeroToOne` that a legal reading marks mandatory **for every battery
category the source names**. The join beside the indexes computed the
disagreement; this reads its result and carries across only what a
finding has to say.

`CONDITIONAL_ON_CATEGORY` -- the rest of that disagreement, and no rule
reads it. Eight of the nine elements are required for some categories
and not others: remaining capacity is required for light means of
transport and voluntary for electric vehicles, and the capacity
threshold for exhaustion inverts -- required for EVs, and the
Commission's guidance marks it *not to be filled* for anything else.
Reporting those without knowing the battery's category would tell an LMT
manufacturer to add a field their guidance forbids. Knowing the category
is a separate rule that does not exist yet; until it does, these rows
are carried so the coverage note can count what it is not saying.

Run with `--check` to compare what this would write against what is on
disk. The indexes it reads are not shipped in an sdist, so `--check`
there reports that there is nothing to compare and passes: the table is
committed, and regenerating it needs the checkout.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "battery-passport"
OUT = ROOT / "src" / "aas_submodel_validate" / "rules" / "battery_tables.py"

#: The templates whose elements this pack reads. 02035-2 is excluded on
#: purpose: this project has a generated table for it already, and a
#: second opinion about the same elements from a different source is two
#: places for one answer to be right.
PACK_TEMPLATES = ("IDTA 02035-1", "IDTA 02035-3", "IDTA 02035-4",
                  "IDTA 02035-5", "IDTA 02035-6", "IDTA 02035-7")

HEADER = '''"""Generated from the battery-passport requirements indexes. Do not edit.

Written by `tools/extract_battery_rules.py`; run it after the indexes
move. The source edition and the hashes it was built from are below, so
a finding can name the template it read: IDTA 02035-5 published 1.0.2 in
August 2026, and a table that does not say which edition it is stops
being true without saying so.
"""
'''


def _load(name):
    return json.loads((DATA / name).read_text("utf-8"))


def _shared_ids(idta) -> dict:
    claimed = collections.defaultdict(set)
    for edition, meta in idta["counts"]["templates"].items():
        claimed[meta["submodel_semantic_id"]].add(edition.split(" V")[0])
    return {sid: tuple(sorted(names))
            for sid, names in sorted(claimed.items()) if len(names) > 1}


def _every_category_required(record) -> bool:
    """Whether a source requires the attribute for every category it names.

    Two shapes: the long list writes a verdict per category, the
    guidance writes `{as_written, reading}`. A row qualifies only when
    every category in every citing source reads as required -- the
    direction this project errs in when it cannot tell.
    """
    applicability = record.get("applicability")
    if not isinstance(applicability, dict) or not applicability:
        return False
    for verdict in applicability.values():
        if isinstance(verdict, dict):
            verdict = verdict.get("reading")
        if verdict not in ("required", "required-by-batteries-regulation"):
            return False
    return True


def _law_rows(idta, join, indexes) -> list:
    elements = {record["id"]: record for record in idta["records"]}
    # Keyed by (document number, edition). Keyed by number alone the last
    # edition in the index wins, and two templates are pinned twice --
    # a row then carried one edition's version string beside another
    # edition's identifier and hash, which `--check` cannot see because
    # it compares bytes to bytes.
    submodel_of = {(edition.rsplit(" V", 1)[0], "V" + edition.rsplit(" V", 1)[1]): meta
                   for edition, meta in idta["counts"]["templates"].items()}
    rows = []
    for entry in join["readings_that_differ_by_name"]:
        element = elements[entry["element"]]
        if element["template"] not in PACK_TEMPLATES:
            continue
        if element["cardinality"] != "ZeroToOne":
            continue        # the disagreement this rule is about is that one
        citations, unconditional, categories = [], True, {}
        for source, reading in sorted(entry["readings"].items()):
            if reading != "yes" or source.startswith("template("):
                continue
            record = indexes.get(source)
            if record is None:
                continue
            for reference in record.get("legal_references") or []:
                if reference not in citations:
                    citations.append(reference)
            unconditional = unconditional and _every_category_required(record)
            for name, verdict in (record.get("applicability") or {}).items():
                if isinstance(verdict, dict):
                    verdict = verdict.get("reading")
                categories.setdefault(name, verdict)
        rows.append({
            "unconditional": unconditional,
            "categories": tuple(sorted(categories.items())),
            "element": entry["element"],
            "template": element["template"],
            "template_version": element["template_version"],
            "submodel_semantic_id": submodel_of[
                (element["template"], element["template_version"])]["submodel_semantic_id"],
            "submodel_sha256": submodel_of[
                (element["template"], element["template_version"])]["sha256"],
            "element_id_short": element["id_short"],
            "element_semantic_id": element["semantic_id"],
            "cardinality": element["cardinality"],
            "text": element["text"],
            "says_mandatory": tuple(sorted(
                source for source, reading in entry["readings"].items()
                if reading == "yes" and not source.startswith("template("))),
            "citations": tuple(citations),
        })
    return rows


def render() -> str:
    idta = _load("requirements-idta.json")
    join = _load("requirements-join.json")
    indexes = {}
    for name in ("requirements-longlist.json", "requirements-ec-datapoints.json"):
        for record in _load(name)["records"]:
            indexes[record["id"]] = record

    rows = _law_rows(idta, join, indexes)
    shared = _shared_ids(idta)
    # The editions the rows were actually read from, not every edition of
    # every template that contributed one: IDTA 02035-5 is pinned twice
    # (1.0.1 and 1.0.2) and only one of them is behind these elements.
    edition = ", ".join(sorted({"%s %s" % (row["template"], row["template_version"])
                                for row in rows}))

    lines = [HEADER, "",
             "#: The edition of every template a row below was read from.",
             "SOURCE_EDITION = %r" % edition, "",
             "#: Submodel identifiers more than one published template claims.",
             "SHARED_SUBMODEL_IDS = {"]
    for sid, names in shared.items():
        lines.append("    %r:" % sid)
        lines.append("        %r," % (names,))
    lines += ["}", ""]
    fields = ("element", "template", "template_version", "submodel_semantic_id",
              "submodel_sha256", "element_id_short", "element_semantic_id",
              "cardinality", "text", "says_mandatory", "citations", "categories")

    def emit(name, comment, chosen):
        out = lines
        out.extend(comment)
        out.append("%s = (" % name)
        for row in chosen:
            out.append("    {")
            for key in fields:
                out.append("        %r: %r," % (key, row[key]))
            out.append("    },")
        out += [")", ""]

    emit("LAW_REQUIRES_TEMPLATE_OPTIONAL",
         ["#: Elements the template allows to be absent that a legal reading",
          "#: requires **of every battery category the source names**. Every",
          "#: field here is one a finding has to say."],
         [row for row in rows if row["unconditional"]])
    emit("CONDITIONAL_ON_CATEGORY",
         ["#: The same disagreement where it depends on the battery's",
          "#: category, which no rule here can read yet. Reported by",
          "#: nothing: the capacity threshold for exhaustion is required",
          "#: for electric vehicles and marked *not to be filled* for",
          "#: everything else, so a finding that ignored the category",
          "#: would tell one manufacturer to add what another's guidance",
          "#: forbids. Carried so the coverage note can count what it is",
          "#: not saying."],
         [row for row in rows if not row["unconditional"]])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not DATA.is_dir():
        print("battery rules: no data/battery-passport in this tree "
              "(an sdist ships the table, not the indexes it came from)")
        return 0
    written = render()
    if not args.check:
        OUT.write_text(written, "utf-8")
        print("battery rules: wrote %s" % OUT.relative_to(ROOT))
        return 0
    if OUT.read_text("utf-8") != written:
        print("battery rules: %s is not what the generator would write; "
              "run tools/extract_battery_rules.py" % OUT.relative_to(ROOT),
              file=sys.stderr)
        return 1
    print("battery rules: the table matches its generator")
    return 0


if __name__ == "__main__":
    sys.exit(main())
