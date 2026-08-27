# -*- coding: utf-8 -*-
"""Derive a requirement index from the Commission guidance table
"Digital Batteries Passport - data points by category" (PDF).

The guidance is one wide table, continued across pages: a data point number, the
data point name, the provision it comes from, and then one column each for
electric vehicle, light means of transport and industrial batteries saying
whether that data point applies to them.

Reading a table out of a PDF is where indexes usually go quietly wrong: text
extraction returns a stream of words, and a wrapped cell looks exactly like the
next cell. So this does not read the text stream. It reads the ruling lines the
page actually draws, turns them into a grid, and assigns every word to the cell
whose rectangle contains it. If a page's grid is not the expected six columns,
the page is reported rather than parsed on a guess.

The table repeats its header on every page and lets a row run over a page break,
so a row that carries no data point number is not a row: it is the tail of the
previous one, and its cells are appended to it. A numberless row with nothing
before it would be a parse that has lost its place, and is reported as such.

Text the page prints outside the ruled table is not thrown away either. Apart
from the page number, what sits outside the grid is a footnote, and a footnote is
where a table explains what one of its own words means -- so footnotes are kept
alongside the records that carry the marker.

The applicability wording is kept verbatim and also mapped to a single value,
using the vocabulary the guidance sets out for itself: mandatory, optional,
applicable only in certain cases, or not to be filled as of the date it names.
Any wording outside that vocabulary is left "unclear" and listed.

Usage:
    python3 tools/extract_ec_datapoints.py \
        --pdf "sources/ec-dg-grow/digital-batteries-passport-data-point-by-category_v2.0.pdf" \
        --out requirements-ec-datapoints.json
"""

import argparse
import os
import re
import sys

import fitz  # PyMuPDF

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common  # noqa: E402

SOURCE = "ec-datapoints"
VERSION = "Version 2.0"
EXPECTED_COLUMNS = 6
COLUMN_NAMES = ("number", "name", "legal_source", "ev", "lmt", "industrial")
CATEGORY_COLUMNS = (("EV", "ev"), ("LMT", "lmt"), ("industrial-above-2kWh", "industrial"))

# The guidance's own vocabulary, page 3: "whether a data point is mandatory,
# optional, applicable only in certain cases, or does not have to be
# filled/displayed as of February 2027".
APPLICABILITY = (
    (re.compile(r"^mandatory\b", re.I), "yes", "required"),
    (re.compile(r"^optional\b", re.I), "no", "optional"),
    (re.compile(r"only in certain cases|only applicable|only if|if applicable"
                r"|where applicable|applicable\d* if", re.I),
     "conditional", "certain-cases"),
    (re.compile(r"does not have to be (filled|displayed)|not to be (filled|displayed)"
                r"|no need to (fill|display)", re.I), "no", "not-to-be-filled"),
    (re.compile(r"^(n/?a|-|–|—)$", re.I), "unclear", "not-stated"),
)
STRONGEST = ("yes", "conditional", "no", "unclear")


def cluster(values, tolerance=6.0):
    grouped = []
    for v in sorted(values):
        if grouped and v - grouped[-1][-1] <= tolerance:
            grouped[-1].append(v)
        else:
            grouped.append([v])
    return [sum(g) / len(g) for g in grouped]


def page_grid(page):
    """The x and y positions of the lines the page draws, as boundaries."""
    xs, ys = set(), set()
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l":
                a, b = item[1], item[2]
                if abs(a.x - b.x) < 1 and abs(a.y - b.y) > 5:
                    xs.add(a.x)
                if abs(a.y - b.y) < 1 and abs(a.x - b.x) > 5:
                    ys.add(a.y)
            elif item[0] == "re":
                r = item[1]
                if r.width < 2:
                    xs.add((r.x0 + r.x1) / 2)
                if r.height < 2:
                    ys.add((r.y0 + r.y1) / 2)
    return cluster(xs), cluster(ys)


def cells_of(page, x_bounds, y_bounds):
    """One string per (row, column) rectangle, in reading order.

    Returns the cells and the words that fell outside the grid. A word outside
    the grid is a word the index would have lost, so the caller reports it
    instead of quietly producing a shorter table.
    """
    grid, outside = {}, []
    for x0, y0, x1, y1, word, _b, _l, _w in page.get_text("words"):
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        col = row = None
        for i in range(len(x_bounds) - 1):
            if x_bounds[i] <= cx < x_bounds[i + 1]:
                col = i
                break
        for j in range(len(y_bounds) - 1):
            if y_bounds[j] <= cy < y_bounds[j + 1]:
                row = j
                break
        if col is None or row is None:
            outside.append(word)
            continue
        grid.setdefault((row, col), []).append((round(y0, 1), x0, word))
    out = {}
    for key, words in grid.items():
        out[key] = _common.squeeze(" ".join(w for _y, _x, w in sorted(words)))
    return out, outside


def classify(wording):
    for pattern, mandatory, label in APPLICABILITY:
        if pattern.search(wording or ""):
            return mandatory, label
    return "unclear", "unrecognised"


def combine(values):
    """A data point is required if it is required for any category the table
    covers; the per-category readings are kept alongside."""
    for level in STRONGEST:
        if level in values:
            return level
    return "unclear"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", default="requirements-ec-datapoints.json")
    args = ap.parse_args(argv)

    document = fitz.open(args.pdf)
    records, notes = [], []
    wording_seen, skipped_pages, dropped = {}, [], {}
    seen_numbers = set()

    rows = []  # (number, {column: text}) with page-break tails folded in
    for index in range(len(document)):
        page = document[index]
        x_bounds, y_bounds = page_grid(page)
        if len(x_bounds) - 1 != EXPECTED_COLUMNS or len(y_bounds) < 2:
            if len(x_bounds) > 1:
                skipped_pages.append(index + 1)
            continue
        cells, outside = cells_of(page, x_bounds, y_bounds)
        if outside:
            dropped[index + 1] = outside
        for row in range(len(y_bounds) - 1):
            values = {name: cells.get((row, i), "") for i, name in enumerate(COLUMN_NAMES)}
            number = values["number"].strip()
            if number.lower() == "number" or values["name"].lower() == "data point name":
                continue  # the header, repeated on every page
            if not any(v.strip() for v in values.values()):
                continue
            if re.fullmatch(r"\d+", number):
                rows.append([number, values, index + 1])
                continue
            if rows and not number:
                for name in COLUMN_NAMES[1:]:
                    if values[name]:
                        rows[-1][1][name] = _common.squeeze(
                            rows[-1][1][name] + " " + values[name]
                        )
                continue
            notes.append(
                "page %d row %d carries no data point number and nothing to "
                "attach it to: %r" % (index + 1, row, values["name"][:60])
            )

    for number, values, page_number in rows:
        if number in seen_numbers:
            notes.append("data point %s appears more than once" % number)
            continue
        seen_numbers.add(number)

        per_category, applies_to, readings = {}, [], []
        for label, key in CATEGORY_COLUMNS:
            wording = values[key]
            mandatory, tag = classify(wording)
            wording_seen[wording] = wording_seen.get(wording, 0) + 1
            per_category[label] = {"as_written": wording, "reading": tag}
            readings.append(mandatory)
            if mandatory in ("yes", "conditional"):
                applies_to.append(label)
            if tag == "unrecognised" and wording:
                notes.append(
                    "data point %s, %s: wording outside the guidance's own "
                    "vocabulary -- %r" % (number, label, wording[:80])
                )

        records.append(
            _common.record(
                id="%s:%s" % (SOURCE, number),
                kind="attribute",
                section="%s, data point %s" % (VERSION, number),
                text=values["name"],
                mandatory=combine(readings),
                condition="",
                access="n/a",
                applies_to=applies_to,
                joins=[],
                number=number,
                legal_source=values["legal_source"],
                applicability=per_category,
                page=page_number,
            )
        )

    document.close()
    footnotes = {}
    for page_number, words in sorted(dropped.items()):
        text = _common.squeeze(" ".join(words))
        # Every page prints its own number outside the table; that is not content.
        if text.startswith(str(page_number)):
            text = _common.squeeze(text[len(str(page_number)):])
        if text:
            footnotes[str(page_number)] = text
    if skipped_pages:
        notes.append(
            "pages %s draw a grid that is not the expected %d columns and were "
            "not parsed" % (skipped_pages, EXPECTED_COLUMNS)
        )
    numbers = sorted(int(r["number"]) for r in records)
    if numbers and numbers != list(range(numbers[0], numbers[-1] + 1)):
        gaps = sorted(set(range(numbers[0], numbers[-1] + 1)) - set(numbers))
        notes.append("data point numbers are not continuous; missing %s" % gaps)

    doc = _common.write_index(
        args.out,
        SOURCE,
        records,
        [
            {
                "file": _common.provenance_path(args.pdf),
                "sha256": _common.sha256_file(args.pdf),
                "version": VERSION,
                "url": "https://single-market-economy.ec.europa.eu/single-market/"
                       "digital-product-passport/batteries_en",
            }
        ],
        counts={
            "by_applicability_wording": dict(sorted(wording_seen.items())),
            "data_point_range": "%s-%s" % (numbers[0], numbers[-1]) if numbers else "",
            "words_outside_the_grid": sum(len(w) for w in dropped.values()),
            "footnotes": footnotes,
        },
        notes=notes,
    )
    _common.report(doc, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
