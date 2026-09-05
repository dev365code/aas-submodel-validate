# -*- coding: utf-8 -*-
"""Derive a requirement index from Annex XIII of the batteries regulation
(EUR-Lex consolidated HTML).

Annex XIII is the list of what a battery passport must contain. It is written
as four numbered blocks, each opening with a sentence that says who may see the
block's contents, followed by lettered points and, under some points, dashed
sub-items. That layout is the structure this reads: block number, the opening
sentence verbatim, the point letter, the point text.

Two derivations happen here, and only these two -- both from wording the annex
itself uses, both recorded on the record so they can be checked:

  1. Access class comes from the block's own heading: "PUBLICLY ACCESSIBLE",
     "LEGITIMATE INTEREST", "NOTIFIED BODIES ... MARKET SURVEILLANCE
     AUTHORITIES". The heading is kept verbatim next to the class.
  2. Whether an item is required comes from the block's opening sentence, which
     reads "A battery passport shall include the following information". So a
     point is "yes" unless its own text narrows it: a point that says "only for
     ..." is "conditional", and a point carrying a softer qualifier ("when
     relevant", "where applicable", "if available") is left "unclear" with the
     qualifying phrase recorded. Nothing here guesses which reading is right;
     the unclear ones are counted so they can be settled deliberately.

A consolidated text carries amendment markers in the flow -- "B" for the text as
originally adopted, "M" and "C" markers for text that an amendment or a
corrigendum replaced. A marker applies from where it appears until the next one,
so each point records which marker it fell under rather than being silently
flattened: a point whose wording arrived by corrigendum is a point whose wording
has a date attached to it.

Usage:
    python3 tools/extract_annex_xiii.py \
        --html sources/eurlex/02023R1542-20250731_EN.html \
        --out requirements-annex-xiii.json
"""

import argparse
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common  # noqa: E402

SOURCE = "annex-xiii"
START = "ANNEX XIII"
END = "ANNEX XIV"

ACCESS_BY_HEADING = (
    ("PUBLICLY ACCESSIBLE", "public"),
    ("NOTIFIED BODIES", "authorities"),
    ("LEGITIMATE INTEREST", "legitimate-interest"),
)

# Both kinds of qualifier narrow an obligation that the chapeau has
# already imposed; neither leaves it unstated. Annex XIII opens "A
# battery passport SHALL include the following information", so a point
# under it is required -- what a qualifier does is say when, or to what.
# Reading a soft qualifier as `unclear` said the annex does not state
# whether the thing is required, which is what `unclear` means in the
# README beside this file, and it is not true of anything here: 1(h) and
# 1(i) require voltage outright and attach "when relevant" only to the
# temperature ranges that follow. They were the only two points it hit,
# and they sat in the published summary table as the annex declining to
# say whether voltage must be given.
NARROWING = re.compile(r"\(?only for [^;.)]+\)?", re.I)
SOFT_QUALIFIER = re.compile(
    r"(when relevant|where relevant|where applicable|if available|when applicable"
    r"|as far as|to the extent)", re.I
)

BLOCK_HEADING = re.compile(r"^([1-4])\.\s+([A-Z][A-Z ,\-']+)$")
POINT = re.compile(r"^\(([a-z])\)$")
AMENDMENT_MARKER = re.compile(r"^[\u25b2\u25bc]([A-Z]\d*)?$")
DASH = "—"


def to_lines(raw_html):
    """Block-level tags become line breaks; everything else becomes text."""
    text = re.sub(r"<(p|div|tr|li|h\d|br)[^>]*>", "\n", raw_html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return [_common.squeeze(line) for line in text.split("\n") if _common.squeeze(line)]


def slice_annex(lines):
    try:
        start = lines.index(START)
    except ValueError:
        raise SystemExit("%r not found -- is this the consolidated text?" % START)
    for i in range(start + 1, len(lines)):
        if lines[i] == END:
            return lines[start:i]
    return lines[start:]


def classify_access(heading):
    upper = heading.upper()
    for needle, value in ACCESS_BY_HEADING:
        if needle in upper:
            return value
    return "n/a"


def read_obligation(text):
    """Return (mandatory, condition) from the point's own wording."""
    narrowed = NARROWING.search(text)
    if narrowed:
        return "conditional", narrowed.group(0).strip("()")
    soft = SOFT_QUALIFIER.search(text)
    if soft:
        return "conditional", soft.group(0)
    return "yes", ""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html", required=True)
    ap.add_argument("--out", default="requirements-annex-xiii.json")
    args = ap.parse_args(argv)

    with open(args.html, encoding="utf-8", errors="replace") as fh:
        lines = to_lines(fh.read())
    annex = slice_annex(lines)

    records, notes = [], []
    block_number = block_heading = block_chapeau = ""
    access = "n/a"
    pending_letter = None
    marker = ""
    sub_index = 0
    last_point_id = None

    for line in annex[1:]:
        found_marker = AMENDMENT_MARKER.match(line)
        if found_marker:
            marker = found_marker.group(1) or ""
            continue

        heading = BLOCK_HEADING.match(line)
        if heading:
            block_number, block_heading = heading.group(1), _common.squeeze(heading.group(2))
            access = classify_access(block_heading)
            block_chapeau = ""
            pending_letter = None
            last_point_id = None
            sub_index = 0
            if access == "n/a":
                notes.append(
                    "block %s: heading names no access class -- %r"
                    % (block_number, block_heading)
                )
            continue

        if not block_number:
            continue

        point = POINT.match(line)
        if point:
            pending_letter = point.group(1)
            sub_index = 0
            continue

        if line == DASH:
            pending_letter = pending_letter or DASH
            continue

        if not block_chapeau and line.lower().startswith("a battery passport shall include"):
            block_chapeau = line
            continue

        if pending_letter is None:
            continue

        mandatory, condition = read_obligation(line)
        if pending_letter == DASH:
            sub_index += 1
            parent = last_point_id or ("%s:%s" % (SOURCE, block_number))
            record_id = "%s.%d" % (parent, sub_index)
            section = "Annex XIII, point %s, sub-item %d" % (block_number, sub_index)
            if last_point_id:
                section = "Annex XIII, point %s, %s, sub-item %d" % (
                    block_number,
                    last_point_id.rsplit(".", 1)[-1],
                    sub_index,
                )
        else:
            record_id = "%s:%s.%s" % (SOURCE, block_number, pending_letter)
            section = "Annex XIII, point %s, (%s)" % (block_number, pending_letter)
            last_point_id = record_id
            sub_index = 0

        records.append(
            _common.record(
                id=record_id,
                kind="sentence",
                section=section,
                text=line,
                mandatory=mandatory,
                condition=condition,
                access=access,
                applies_to=[],
                joins=[],
                block=block_number,
                block_heading=block_heading,
                chapeau=block_chapeau,
                access_as_written=block_heading,
                consolidation_marker=marker,
                amended_in_consolidation=bool(marker) and not marker.startswith("B"),
            )
        )
        if pending_letter != DASH:
            pending_letter = None

    blocks = sorted({r["block"] for r in records})
    if blocks != ["1", "2", "3", "4"]:
        notes.append("expected four blocks, parsed %s" % blocks)
    missing_chapeau = sorted({r["block"] for r in records if not r["chapeau"]})
    if missing_chapeau:
        notes.append(
            "blocks %s carry no opening sentence, so what makes their points "
            "required is not recorded on them" % ", ".join(missing_chapeau)
        )
    notes.append(
        "Annex XIII itself names no battery category; which batteries need a "
        "passport is stated in Article 77(1), which is not part of this annex "
        "and so is not indexed here"
    )

    doc = _common.write_index(
        args.out,
        SOURCE,
        records,
        [
            {
                "file": _common.provenance_path(args.html),
                "sha256": _common.sha256_file(args.html),
                "version": "consolidated text 02023R1542-20250731",
                "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02023R1542-20250731",
            }
        ],
        counts={
            "by_block": _common.tally(records, "block"),
            "by_consolidation_marker": _common.tally(records, "consolidation_marker"),
            "amended_in_consolidation": sum(
                1 for r in records if r["amended_in_consolidation"]
            ),
        },
        notes=notes,
    )
    _common.report(doc, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
