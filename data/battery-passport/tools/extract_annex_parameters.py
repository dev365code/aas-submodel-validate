# -*- coding: utf-8 -*-
"""Derive an index of the parameter annexes from the batteries regulation
(EUR-Lex consolidated HTML): Annex IV Parts A and B, Annex VII Parts A and B.

Annex XIII is what a passport must *contain*, and `extract_annex_xiii.py`
indexes it. These are what the parameters *are* -- the numbered lists the
battery rule's rows cite when they say a published reading expects an element.
Nothing indexed them, so the one fact that decides whether a row may be
reported at all -- does the provision it cites carry a qualifier -- lived only
in the reader's head, and a row whose provision opens "Where applicable" was
carried as required of every battery category and put on the project's front
page. See `docs/divergences.md` #37.

Two shapes, because the annexes are typeset differently and a parser written
for one silently reads nothing from the other:

  Annex IV numbers and text share a line -- "4. Where applicable, energy round
  trip efficiency and its fade (in %)." Annex VII puts the number on its own
  line and the text beneath it.

Annex VII Part A also carries a chapeau naming who each list is for: "For
electric vehicle batteries:" and "For stationary battery energy storage systems
and LMT batteries:". That sentence is the evidence for which categories a
citation reaches, so it is recorded verbatim on every item under it rather than
summarised -- the battery rule reports a row for `lmt`, and the reason it may
is this line.

The obligation reading is the same one Annex XIII gets and is imported from
that module rather than restated: a point carrying a soft qualifier ("where
applicable", "where possible", "where appropriate") is `conditional` with the
qualifying phrase recorded. Two indexes disagreeing about what "where possible"
means would be worse than either of them being wrong.

Usage:
    python3 tools/extract_annex_parameters.py \
        --html sources/eurlex/02023R1542-20250731_EN.html \
        --out requirements-annex-parameters.json
"""

import argparse
import importlib.util
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common  # noqa: E402


def _annex_xiii():
    """The sibling extractor, loaded by path.

    `to_lines` and `read_obligation` are shared rather than copied: the
    first decides what counts as a line of the document and the second
    decides what a qualifier means, and two indexes of one text that
    answer either differently are worse than one of them being wrong.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "extract_annex_xiii.py")
    spec = importlib.util.spec_from_file_location("extract_annex_xiii", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: The annexes this reads, and where each one ends. Named rather than
#: discovered: an annex that stops being found must fail loudly, and a
#: heading that moved is exactly the kind of drift a pinned source is
#: pinned against.
ANNEXES = (
    ("IV", "ANNEX IV", "ANNEX V"),
    ("VII", "ANNEX VII", "ANNEX VIII"),
)

PART = re.compile(r"^Part ([AB])$")
#: Annex IV's shape: number and text on one line.
INLINE_ITEM = re.compile(r"^(\d+)\.\s+(.+)$")
#: Annex VII's shape: the number alone, its text on the next line.
LONE_NUMBER = re.compile(r"^(\d+)\.$")
#: Who a list is for, in the annex's own words. Ends in a colon and names
#: batteries; the parameters follow it.
CHAPEAU = re.compile(r"^For .*batteries.*:$", re.I)


def items_of(lines, annex):
    """Every numbered parameter under a Part, with the chapeau over it."""
    part, chapeau, found = None, "", []
    index = 0
    while index < len(lines):
        line = lines[index]
        heading = PART.match(line)
        if heading:
            # A new Part starts a new list, and the chapeau does not carry
            # across: Annex VII Part B has none, and inheriting Part A's
            # would say its items are for electric vehicles.
            part, chapeau = heading.group(1), ""
            index += 1
            continue
        if CHAPEAU.match(line):
            chapeau = line
            index += 1
            continue
        if part is None:
            index += 1
            continue
        inline = INLINE_ITEM.match(line)
        if inline:
            found.append((part, inline.group(1), inline.group(2), chapeau))
            index += 1
            continue
        lone = LONE_NUMBER.match(line)
        if lone and index + 1 < len(lines):
            found.append((part, lone.group(1), lines[index + 1], chapeau))
            index += 2
            continue
        index += 1
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--html", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    sibling = _annex_xiii()
    with open(args.html, encoding="utf-8", errors="replace") as handle:
        lines = sibling.to_lines(handle.read())

    records, notes = [], []
    for annex, start, end in ANNEXES:
        try:
            first = lines.index(start)
        except ValueError:
            raise SystemExit("%r not found -- is this the consolidated text?" % start)
        try:
            last = lines.index(end, first + 1)
        except ValueError:
            last = len(lines)
        body = lines[first:last]
        found = items_of(body, annex)
        if not found:
            raise SystemExit("%s: no numbered parameter found" % start)
        for part, number, text, chapeau in found:
            mandatory, condition = sibling.read_obligation(text)
            records.append(_common.record(
                "annex-%s-%s:%s" % (annex.lower(), part.lower(), number),
                "parameter",
                "Annex %s Part %s (%s)" % (annex, part, number),
                text, mandatory=mandatory, condition=condition,
                annex=annex, part=part, number=number,
                # Verbatim. This sentence is the whole evidence for which
                # batteries a citation reaches, and a summary of it would
                # be this project deciding that question rather than
                # reading it.
                chapeau=chapeau))
        notes.append("%s: %d parameters" % (start, len(found)))

    doc = _common.write_index(
        args.out,
        {"title": "Regulation (EU) 2023/1542, Annexes IV and VII",
         "edition": "CELEX 02023R1542-20250731 (consolidated as at 2025-07-31)"},
        records,
        [{"file": _common.provenance_path(args.html),
          "sha256": _common.sha256_file(args.html),
          "version": "consolidated text 02023R1542-20250731",
          "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/"
                 "?uri=CELEX:02023R1542-20250731"}],
        counts={"by_mandatory": _common.tally(records, "mandatory"),
                "by_annex": _common.tally(records, "annex"),
                "by_part": _common.tally(records, "part")},
        notes=notes)
    _common.report(doc, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
