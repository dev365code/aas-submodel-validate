"""The bundle's public first screen, re-derived rather than trusted.

`data/battery-passport/` is linked to readers who know the sources
better than this project does. Its README and `divergences-public.md`
make numeric claims about indexes sitting in the same directory, and
every one of them is a claim a reader can check in a minute with `jq`.
The ones here were checked once by hand; without this file that is all
they ever were.

Two of these are not pins but properties, and they are the reason this
file exists rather than a list of numbers:

- **coverage is a floor.** The README and the join both say every
  coverage figure is a lower bound. A count that credits an annex point
  to a document that does not cite it is not a lower bound -- it is a
  number in the wrong direction, and the promise is the one thing a
  reader will test.
- **a divergence rests on what was read.** `divergences-public.md`
  opens by saying each entry states what was read and in which bytes.
  An entry that lists a record which does not cite the provision it is
  filed under fails that sentence, whatever the count says.

An sdist carries no `data/`, so everything here skips where the
directory is absent -- the same rule `tools/battery_data_check.py`
follows, for the same reason.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "data" / "battery-passport"

pytestmark = pytest.mark.skipif(
    not DATA.is_dir(), reason="no data/battery-passport in this tree (sdist)"
)


def _squeezed(name):
    """Line wrapping is a layout choice these assertions must not have an
    opinion about: a reflow is not a changed claim."""
    return re.sub(r"\s+", " ", (DATA / name).read_text("utf-8"))


def _index(name):
    return json.loads((DATA / name).read_text("utf-8"))


def _join_tool():
    """The join's own citation parser, so this asks the question the
    generator answered rather than a second guess at it."""
    spec = importlib.util.spec_from_file_location(
        "_join_under_test", DATA / "tools" / "join_requirements.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def join():
    return _index("requirements-join.json")


@pytest.fixture(scope="module")
def names():
    """`names(record_id, point)` -- does that record's own citation
    identify that annex point, and only it?

    Built from the annex index's list of point ids, not from the join,
    so the join could be rewritten from scratch and this would still be
    asking the same question. A citation identifies a point when it is
    the point, or when it is a block with exactly that one point
    beneath it -- `Annex XIII 3` is a single unlettered sentence that
    the index numbers `3.1`, and naming the block names the sentence.
    A block with more than one point beneath it identifies none of
    them: expanding it would be the join inventing statements, one per
    point, out of a single citation.
    """
    points = {r["id"] for r in _index("requirements-annex-xiii.json")["records"]}

    def beneath(citation):
        return {p for p in points if p.startswith(citation + ".")}

    def names_it(record_citations, point):
        for citation in record_citations:
            if citation == point:
                return True
            if beneath(citation) == {point}:
                return True
        return False

    return names_it


@pytest.fixture(scope="module")
def cites():
    """id -> the citations that record makes in its own words."""
    tool = _join_tool()
    out = {}
    for filename, field in (
        ("requirements-ec-datapoints.json", "legal_source"),
        ("requirements-longlist.json", "legal_reference"),
    ):
        for record in _index(filename)["records"]:
            out[record["id"]] = set(tool.citations(record.get(field, "")))
    return out


# -- the two properties -----------------------------------------------------


def test_a_differing_reading_rests_only_on_records_that_cite_the_provision(join, cites, names):
    """`divergences-public.md` entry 7 names ten provisions the guidance
    and the longlist read differently, and says of each that it lists
    what was read. A record reaches that list through its citation, so a
    record that does not carry the citation is evidence of nothing about
    that provision -- and two longlist rows about expected lifetime,
    which name the whole of Annex XIII point 1 in passing, were being
    read as a statement about every lettered point beneath it."""
    wrong = []
    for entry in join["readings_that_differ_by_citation"]:
        citation = entry["citation"]
        for reading, ids in entry["readings"].items():
            for rid in ids:
                # `names`, not string equality: a citation of a block whose
                # only content is one point identifies that point, and this
                # file says so ten lines up. Asking the question two ways in
                # one test file is how a suite comes to contradict itself.
                if not names(cites.get(rid, ()), citation):
                    wrong.append("%s: %s (%s) does not cite it" % (citation, rid, reading))
    assert not wrong, "readings filed under a provision the record never cites:\n" + "\n".join(wrong)


def test_annex_coverage_counts_are_a_floor_and_not_above_it(join, cites, names):
    """Every coverage figure in the join is published as a lower bound.
    A point credited to a document that never identified it is credited
    *above* the floor, which is the one direction the promise cannot
    absorb: a reader who checks a floor and finds it is a ceiling has
    found the document arguing against itself."""
    counted = {"guidance": 0, "longlist": 0}
    for point in join["annex_coverage"]:
        key = point["annex_point"]
        if any(names(cites.get(rid, ()), key) for rid in point["ec_datapoints"]):
            counted["guidance"] += 1
        if any(names(cites.get(rid, ()), key) for rid in point["longlist_rows"]):
            counted["longlist"] += 1
    counts = join["counts"]
    assert counts["annex_points_with_a_guidance_data_point"] == counted["guidance"]
    assert counts["annex_points_with_a_longlist_row"] == counted["longlist"]


def test_every_credited_record_identified_the_point_it_is_credited_to(join, cites, names):
    """The per-row form of the count above, and the one a reader checks
    first: open the table, pick a row, look up the record. Row 83 of the
    longlist is "expected lifetime in calendar years"; it appeared
    against responsible sourcing, marking, due diligence and sixteen
    other provisions because it names the block those sit in."""
    stray = [
        "%s <- %s" % (point["annex_point"], rid)
        for point in join["annex_coverage"]
        for rid in point["ec_datapoints"] + point["longlist_rows"]
        if not names(cites.get(rid, ()), point["annex_point"])
    ]
    assert not stray, "credited to a point their citation does not identify:\n" + "\n".join(stray)


def test_a_credit_that_was_dropped_is_still_shown_somewhere(join, cites, names):
    """Demoting a credit must move it where a reader can see it, not
    delete it. Every record that reaches a point through a broader
    citation stays listed against that point, in the column that says
    it was reached without being named."""
    for point in join["annex_coverage"]:
        for rid in point["reached_by_a_broader_citation"]["ec_datapoints"]:
            assert not names(cites.get(rid, ()), point["annex_point"])
        for rid in point["reached_by_a_broader_citation"]["longlist_rows"]:
            assert not names(cites.get(rid, ()), point["annex_point"])
    reached = sum(
        1
        for point in join["annex_coverage"]
        if point["reached_by_a_broader_citation"]["ec_datapoints"]
        or point["reached_by_a_broader_citation"]["longlist_rows"]
    )
    assert join["counts"]["annex_points_a_broader_citation_reaches_without_naming"] == reached
    assert reached, "the block citation this whole property exists for has vanished"


# -- the README's numbers ---------------------------------------------------


def test_the_readme_counts_the_rows_it_says_it_counts():
    readme = _squeezed("README.md")
    assert "the guidance table has 71 rows and this carries 71 records" in readme
    assert len(_index("requirements-ec-datapoints.json")["records"]) == 71
    assert "the longlist has 100 rows and this carries 100 records" in readme
    assert len(_index("requirements-longlist.json")["records"]) == 100


def test_the_longest_longlist_quotation_is_about_what_the_readme_says():
    longest = max(
        len(value)
        for record in _index("requirements-longlist.json")["records"]
        for value in record.values()
        if isinstance(value, str)
    )
    assert 1250 <= longest < 1350, longest


def test_the_annex_index_carries_no_unclear_as_the_readme_says():
    """The README explains why: Annex XIII opens by requiring everything
    under it, so a qualifier narrows a duty rather than creating a
    doubt. One `unclear` in this index makes that paragraph false."""
    records = _index("requirements-annex-xiii.json")["records"]
    assert [r["id"] for r in records if r.get("mandatory") == "unclear"] == []


def test_the_templates_carry_no_citation_of_the_law():
    """The load-bearing sentence under every coverage figure: name
    matching is all there is *because* the templates cite nothing. One
    citation appearing upstream would make the floor argument obsolete
    rather than wrong, and this is where that would be noticed."""
    blob = json.dumps(_index("requirements-idta.json"), ensure_ascii=False)
    assert not re.findall(r"2023/1542|Annex\s*XIII", blob)


def test_the_ledger_has_the_line_count_the_regenerate_steps_expect():
    lines = [
        line
        for line in (DATA / "sources.sha256").read_text("utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    steps = (DATA / "tools" / "REGENERATE.txt").read_text("utf-8")
    assert "expect: %d lines, all OK" % len(lines) in steps


def test_regenerate_holds_the_commands_the_readme_promises():
    """The page names a number of commands and the file holds them.

    Counted rather than fixed at five: an extractor landed -- the
    parameter annexes, so the rule table can say when a clause it cites
    states itself "where possible" -- and the number in the sentence is
    what goes stale, not the list."""
    steps = (DATA / "tools" / "REGENERATE.txt").read_text("utf-8")
    commands = re.findall(r"(?m)^ {4}python3 tools/\w+\.py", steps)
    assert len(commands) == 6, commands
    assert "the six commands in `tools/REGENERATE.txt`" in _squeezed("README.md")


# -- the divergence numbers -------------------------------------------------


def test_entry_nine_adds_up(join):
    counts = join["counts"]
    assert counts["template_elements"] == 221
    assert counts["template_elements_matched_by_name"] == 43
    assert counts["template_elements_matched_by_nothing"] == 178
    assert counts["template_elements_matched_by_name"] + counts[
        "template_elements_matched_by_nothing"
    ] == counts["template_elements"]
    assert counts["guidance_data_points_unmatched"] == 59
    assert counts["longlist_rows_unmatched"] == 63
    # Summed, not compared to a number written here twice. The 63 in
    # this line used to be the guidance's unmatched count and stopped
    # being it, while the line above went on asserting the real one --
    # two facts about the same total, one of them stale, and the test
    # green until the other moved.
    assert (counts["guidance_data_points_matched_by_name"]
            + counts["guidance_data_points_unmatched"]) == 71


def test_entry_six_names_the_only_citation_that_does_not_resolve(join):
    dangling = join["citations_without_a_matching_annex_point"]
    assert [d["citation"] for d in dangling] == ["annex-xiii:1.t"]
    assert dangling[0]["cited_by"] == "ec-datapoints:44"
    points = [r["id"] for r in _index("requirements-annex-xiii.json")["records"]]
    assert [p for p in points if p.startswith("annex-xiii:1.")][-1] == "annex-xiii:1.s"


def test_entry_seven_names_the_provisions_the_join_found(join):
    """The prose and the data drifted once already, in the direction
    that flatters: the entry claimed ten provisions because the join
    handed it ten. Both are pinned here so a change to either has to
    move the other."""
    entry = _squeezed("divergences-public.md")
    found = [e["citation"] for e in join["readings_that_differ_by_citation"]]
    assert len(found) == 8
    assert "read eight provisions differently" in entry
    assert "For eight provisions, the two restatements differ" in entry

    spelled = {
        "annex-vi-a:1": "Annex VI A (1)",
        "annex-xiii:1.b": "1(b)",
        "annex-xiii:1.c": "1(c)",
        "annex-xiii:1.e": "1(e)",
        "annex-xiii:1.g": "1(g)",
        "annex-xiii:1.m": "1(m)",
        "annex-xiii:4.a": "4(a)",
        "annex-xiii:4.d": "4(d)",
    }
    assert sorted(spelled) == sorted(found), "the join moved and the entry did not"
    for citation, as_written in spelled.items():
        assert as_written in entry, citation
    for gone in ("1(d)", "1(q)"):
        head = entry.split("**How this was counted")[0]
        assert gone not in head.split("## 7.")[1], "%s is back on the disagreement list" % gone


def test_the_join_table_still_shows_the_citations_it_stopped_counting(join):
    """Demotion is not deletion. The public markdown has to carry the
    block-reached records, or the correction has traded one wrong number
    for a missing fact."""
    table = (DATA / "requirements-join.md").read_text("utf-8")
    assert "reached without being named" in table

    # Per row and per cell. The first version asked `rid in table` with
    # `rid` a two-character number, which a sha256 fragment in the source
    # listing satisfies: every mention of 83 and 84 could be deleted from
    # the table and the assertion still passed. A substring search over a
    # whole document is not a test of a column.
    rows = {}
    for line in table.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 7 and cells[0].startswith("`annex-xiii:"):
            rows[cells[0].strip("`")] = {c for c in cells[5].split(",") if c.strip() != "-"}
    assert rows, "no coverage rows parsed out of the table"

    shown_somewhere = False
    for point in join["annex_coverage"]:
        broader = point["reached_by_a_broader_citation"]
        expected = {
            rid.split(":")[-1]
            for rid in broader["ec_datapoints"] + broader["longlist_rows"]
        }
        cell = {c.strip() for c in rows[point["annex_point"]]}
        assert expected == cell, (point["annex_point"], sorted(expected), sorted(cell))
        shown_somewhere = shown_somewhere or bool(expected)
    assert shown_somewhere, "nothing is being reported as reached-without-being-named"


def test_the_join_says_how_many_names_its_matched_elements_actually_reach(join):
    """`43 of 221 elements match` is true and reads as more than it is.

    Four of the forty-two are the value child of another of the
    forty-two -- `RemainingCapacity` and `RemainingCapacityValue` both
    match longlist row 60, because `value` is a stopword and the two
    labels reduce to one bag. A fifth pair is two elements in two
    different templates on one attribute. The count is not wrong; the
    reading it invites is, and the reader who spots it has spotted it in
    the table on the same page. So the join states both numbers."""
    counts = join["counts"]
    assert counts["template_elements_matched_by_name"] == len(join["name_matches"]) == 43
    named = counts["distinct_attribute_names_those_elements_reach"]
    assert named == 38, named
    assert len(join["name_matches"]) - named == 5

    # The pairs that make the difference, so the number cannot drift into
    # agreement by accident: each is one element and its own value child.
    ids = {m["element"] for m in join["name_matches"]}
    children = {
        i
        for i in ids
        if i.endswith("Value") and i.rsplit("/", 1)[0] in ids
    }
    assert len(children) == 4, sorted(children)


# -- claims that went stale once, and the gates that stop them ---------------


def test_every_hash_the_divergences_cite_is_in_the_ledger():
    """`divergences-public.md` opens by saying every file was read at the
    hash recorded in `sources.sha256`. It cited `a90c0055` for the
    consolidated text for a day after the source was re-pinned to
    `cbca54f9` -- the indexes and the ledger all moved and the prose did
    not. Any short digest in that file has to be a real one."""
    text = (DATA / "divergences-public.md").read_text("utf-8")
    ledger = (DATA / "sources.sha256").read_text("utf-8")
    cited = set(re.findall(r"`([0-9a-f]{8,40})`", text))
    assert cited, "no digests found -- this gate is measuring nothing"
    unknown = sorted(d for d in cited if d not in ledger)
    assert not unknown, "cited but not in sources.sha256: %s" % unknown


def test_the_readme_and_the_notice_count_the_cc_by_sources_the_same_way():
    """Each said a different number for a while, and `NOTICE.md`
    contradicted itself: its opening said three of four and all four of
    its source sections state CC BY 4.0 terms."""
    notice = (DATA / "NOTICE.md").read_text("utf-8")
    sources = [
        section
        for section in notice.split("\n## ")[1:]
        if "`requirements-" in section.split("\n")[0]
    ]
    assert len(sources) == 4, [s.split("\n")[0] for s in sources]
    for section in sources:
        squeezed = re.sub(r"\s+", " ", section)
        assert "Creative Commons Attribution 4.0" in squeezed or "CC BY Licence" in squeezed
        assert "creativecommons.org/licenses/by/4.0" in squeezed
    assert "All four sources carry Creative Commons Attribution 4.0" in re.sub(
        r"\s+", " ", notice
    )
    assert "all four sources carry Creative Commons Attribution 4.0 terms" in _squeezed(
        "README.md"
    )


def test_the_column_the_prose_says_is_not_copied_is_described_as_it_is_read():
    """The extractor reads the column attributed to a separate
    specification and writes one boolean from it. Two documents said it
    does not read the column at all, which is a different and false
    statement -- and a licence-adjacent one, since the column is the
    reason the field exists."""
    records = _index("requirements-longlist.json")["records"]
    flags = [r["separate_spec_has_requirement_text"] for r in records]
    assert len(flags) == 100 and sum(1 for f in flags if f is True) == 99
    source = (DATA / "tools" / "extract_longlist.py").read_text("utf-8")
    assert 'bool(cell(row, "requirement_spec"))' in source
    assert "PUBLIC_PROFILE_OMITS = ()" in source, "the profile now omits something; say so"
    # Both documents have to name the field and keep the sentence that
    # says what the old wording got wrong. Trying to detect the false
    # claim by searching for its words was the first version of this and
    # it was too clever by half: any rewording walked straight past it.
    for document, correction in (
        ("README.md", "An earlier version of this sentence said the extractor does not read"),
        ("NOTICE.md", "This paragraph said the extractor does not read the column"),
    ):
        squeezed = _squeezed(document)
        assert "separate_spec_has_requirement_text" in squeezed, document
        assert correction in squeezed, document


def test_the_readme_points_at_readings_that_are_really_there():
    """The paragraph names four places where wording becomes a
    `mandatory` value, after a version of it claimed a convention the
    code does not follow. Every name in it has to resolve."""
    readme = _squeezed("README.md")
    for filename, symbols in (
        ("extract_annex_xiii.py", ("read_obligation", "NARROWING", "SOFT_QUALIFIER")),
        ("extract_ec_datapoints.py", ("classify", "combine", "APPLICABILITY", "STRONGEST")),
        ("extract_longlist.py", ("MARK_MEANING",)),
        ("extract_idta_smt.py", ("MANDATORY_BY_CARDINALITY",)),
    ):
        source = (DATA / "tools" / filename).read_text("utf-8")
        assert filename in readme, filename
        for symbol in symbols:
            assert symbol in readme, "%s is not named in the README" % symbol
            assert re.search(r"(?m)^(def %s\(|%s = )" % (symbol, symbol), source), (
                "%s is named in the README and not defined in %s" % (symbol, filename)
            )


def test_the_only_non_uri_claim_states_which_templates_it_is_about():
    """`counts.templates` holds twelve templates and the entry spoke
    about seven, so three further non-URI values sat in the field a
    reader was pointed at."""
    templates = _index("requirements-idta.json")["counts"]["templates"]
    uri = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:\S*$")
    not_uri = sorted(k for k, v in templates.items() if not uri.match(v["template_id"]))
    assert len(templates) == 12
    assert len(not_uri) == 4, not_uri
    parts = [k for k in not_uri if re.search(r"02035-\d", k)]
    assert parts == ["IDTA 02035-4 V1.0.1"], parts
    entry = _squeezed("divergences-public.md")
    assert "Among the seven parts, Part 4's value is also the only one that is not a URI" in entry
    assert "holds twelve templates, not seven" in entry


def test_every_annex_point_records_the_amendment_marker_it_falls_under():
    """A consolidated text marks its passages: `B` for the text as
    adopted, `M`/`C` for what an amendment or a corrigendum replaced. The
    extractor's own docstring says a marker applies from where it appears
    until the next one, and that each point records which one it fell
    under "rather than being silently" dropped.

    Sixteen of the thirty-four recorded no marker at all. Not because
    they fall outside one -- the marker governing them is `▼B`, and it is
    stated before Annex XIII begins, so slicing the annex out of the
    document left it on the other side of the cut. A reader asking which
    of these obligations are original text and which arrived by amendment
    got an empty string for the first sixteen, and an empty string reads
    as "not amended" exactly where the answer was never looked up."""
    records = _index("requirements-annex-xiii.json")["records"]
    unmarked = [r["id"] for r in records if not r["consolidation_marker"]]
    assert not unmarked, "%d points carry no marker: %s" % (len(unmarked), unmarked)

    tally = _index("requirements-annex-xiii.json")["counts"]["by_consolidation_marker"]
    assert "" not in tally, tally
    assert sum(tally.values()) == len(records) == 34
    # `amended_in_consolidation` is derived from the marker, so a missing
    # marker made it false. It must now be true exactly for the non-`B`.
    for record in records:
        expected = not record["consolidation_marker"].startswith("B")
        assert record["amended_in_consolidation"] is expected, record["id"]


def test_the_join_says_how_much_of_the_citing_it_actually_checked(join, cites):
    """`citations_unresolved_in_consolidated_text` is 1, and its name
    claims a scope the code does not have: only Annex XIII citations are
    resolved against anything, because nothing here indexes Annex VI or
    the articles. Of the 168 citations the two restatements make, 115 are
    checked and 53 are not, and a count of one unresolved reads very
    differently once you know which."""
    instances = [c for ids in cites.values() for c in ids]
    checked = [c for c in instances if c.startswith("annex-xiii:")]
    counts = join["counts"]
    assert counts["citations_checked_against_the_annex"] == len(checked) == 115
    assert counts["citations_no_index_here_can_resolve"] == len(instances) - len(checked) == 53
    assert counts["citations_checked_against_the_annex"] + counts[
        "citations_no_index_here_can_resolve"
    ] == len(instances) == 168


def test_the_two_counts_that_always_show_the_same_number_say_why(join):
    """`annex points with neither` and `annex points named only through
    their parent` both read 6, and they are the same six points. The
    second is a subset of the first by construction -- a point reached
    only through its parent has nothing of its own -- so two adjacent
    rows of the table can never disagree in the direction a reader might
    expect, and looking at 6 and 6 it is natural to think twelve points
    are involved. Where they are equal it means something worth saying:
    every point no restatement names has a parent that is named."""
    neither = {
        a["annex_point"]
        for a in join["annex_coverage"]
        if not a["ec_datapoints"] and not a["longlist_rows"]
    }
    through_parent = {
        a["annex_point"] for a in join["annex_coverage"] if a["cited_only_through_its_parent"]
    }
    assert through_parent <= neither, sorted(through_parent - neither)
    table = (DATA / "requirements-join.md").read_text("utf-8")
    assert "is a subset of" in table
    if through_parent == neither:
        assert "every point no restatement names has a parent that is" in table


# -- what the demotion mechanism owes, found by attacking it ----------------


def test_a_citation_of_a_point_that_has_sub_items_reports_reaching_them(join, cites, names):
    """The first version of the demotion split the same relation in two
    by an accident, and then fixed only half of it.

    `Annex XIII 2 (c)` is cited by `ec-datapoints:48` and `longlist:44`,
    and 2(c) has six sub-items. Because 2(c) has a row of its own in the
    annex index, the code returned early and never looked at them -- so
    six points reached by a broader citation were reported as reached by
    nothing, three lines under a new paragraph saying such a record "is
    shown against each and counted against none". The accident that used
    to decide the counts was still deciding the reporting."""
    reached = {}
    for point in join["annex_coverage"]:
        key = point["annex_point"]
        parent = key.rsplit(".", 1)[0] if "." in key else None
        if parent is None:
            continue
        for rid, citations in cites.items():
            if parent in citations and not names(citations, key):
                reached.setdefault(key, set()).add(rid)

    for key, expected in reached.items():
        entry = next(a for a in join["annex_coverage"] if a["annex_point"] == key)
        shown = set(
            entry["reached_by_a_broader_citation"]["ec_datapoints"]
            + entry["reached_by_a_broader_citation"]["longlist_rows"]
        )
        assert expected <= shown, (key, sorted(expected - shown))
    assert "annex-xiii:2.c.1" in reached, "the case this test exists for has gone"


def test_the_two_ways_of_saying_reached_but_not_named_cannot_disagree(join):
    """`cited_only_through_its_parent` and the demotion column describe
    one relation. Held apart, one row could say a point is named through
    its parent while the column beside it says the same citation reaches
    it without naming it."""
    for point in join["annex_coverage"]:
        broader = point["reached_by_a_broader_citation"]
        has_broader = bool(broader["ec_datapoints"] or broader["longlist_rows"])
        direct = bool(point["ec_datapoints"] or point["longlist_rows"])
        assert point["cited_only_through_its_parent"] == (has_broader and not direct), (
            point["annex_point"],
            point["cited_only_through_its_parent"],
            has_broader,
            direct,
        )


def test_a_block_that_is_not_a_provision_is_not_published_as_one(join):
    """`readings_that_differ_by_citation` walks every key the join
    collected, and a block citation puts its own key in there --
    `annex-xiii:1`, which the change declares names nothing and which has
    no row in the coverage table. One guidance row citing the block the
    way the two lifetime rows do would publish it under "where two
    restatements of the same provision disagree", which is the same
    one-citation-many-provisions error the change removed."""
    points = {r["id"] for r in _index("requirements-annex-xiii.json")["records"]}
    for entry in join["readings_that_differ_by_citation"]:
        citation = entry["citation"]
        if not citation.startswith("annex-xiii:"):
            continue
        assert citation in points, "%s is a block, not a provision" % citation


def test_everything_a_citation_names_is_credited_to_it(join, cites, names):
    """The mirror of the floor property, which only checked one way.
    Every test written for the demotion verified that a credited record
    names its point; none verified that a naming record is credited, so
    a change that dropped credits was green."""
    for point in join["annex_coverage"]:
        key = point["annex_point"]
        expected = {rid for rid, citations in cites.items() if names(citations, key)}
        shown = set(point["ec_datapoints"] + point["longlist_rows"])
        assert expected <= shown, (key, sorted(expected - shown))


def test_the_citation_parser_reads_these_strings_the_way_a_person_does():
    """Every other property in this file builds its ground truth by
    calling the generator's own parser, so a change to that parser moves
    both sides of the comparison and the suite stays green while the
    published counts move. Measured: widening one character class in
    `ANNEX_XIII` drops 1(f) -- restated word for word by two documents --
    to restated by neither, with 1096 tests passing.

    This is the one place the parser is asked against an answer written
    by hand. The strings are copied out of the two indexes; the keys are
    what a reader of Annex XIII would say they name."""
    tool = _join_tool()
    for written, expected in (
        ("BR Annex XIII 1 (f)", ["annex-xiii:1.f"]),
        ("Annex XIII (1f)", ["annex-xiii:1.f"]),
        ("Annex XIII 1(n)", ["annex-xiii:1.n"]),
        ("Annex XIII (2c);", ["annex-xiii:2.c"]),
        ("BR Annex XIII 2 (c)", ["annex-xiii:2.c"]),
        ("Annex XIII 3", ["annex-xiii:3"]),
        ("Annex XIII (1)", ["annex-xiii:1"]),
        ("BR Annex XIII 1 (t)", ["annex-xiii:1.t"]),
        ("Annex XIII 4 (a)", ["annex-xiii:4.a"]),
    ):
        assert tool.citations(written) == expected, written

    # And the letters really are distinguished, one from another. The
    # mutation above survived because nothing asked.
    letters = {
        chr(code): tool.citations("Annex XIII 1 (%s)" % chr(code))
        for code in range(ord("a"), ord("t") + 1)
    }
    assert all(v == ["annex-xiii:1.%s" % k] for k, v in letters.items()), letters


def test_the_longlist_is_named_by_the_edition_that_is_cc_by():
    """The short name belongs to a different, non-commercially licensed
    series.

    `data/battery-passport/NOTICE.md` says so, and said the full name was
    used in "the file, the ledger line and the extractor that reads it --
    the three places a reader arrives from". A reader also arrives from
    the front page and from the docstring of the pack that ships, and
    both said "Battery Pass long list". A licensing note asserting where
    a name is used is worth exactly as much as the assertion.

    Asked of the whole tree rather than of the three places, because the
    fourth place is how this was missed."""
    import pathlib
    import re as _re
    root = pathlib.Path(__file__).resolve().parents[1]
    short = _re.compile(r"Battery\s+Pass\s+long\s?list", _re.I)
    #: The one place the short name belongs: the sentence explaining that
    #: it belongs somewhere else. Recognised by what the line says, not
    #: by which file it is in.
    disclaims = _re.compile(r"belongs to (the )?earlier|earlier series|"
                            r"non-commercial", _re.I)
    offenders = []
    for path in sorted(root.rglob("*")):
        if path.is_dir() or path.suffix not in (".py", ".md", ".toml", ".txt", ""):
            continue
        if any(part in (".git", "build", "dist", "__pycache__", ".venv")
               for part in path.parts):
            continue
        # A build artefact is a stale copy of the front page, and this
        # file is where the pattern is written down. Neither is somebody
        # using the name.
        if path.suffix == "" and path.name != "NOTICE":
            continue
        if ".egg-info" in str(path) or path.resolve() == pathlib.Path(__file__).resolve():
            continue
        try:
            text = path.read_text("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if short.search(line) and not disclaims.search(line):
                window = "\n".join(text.splitlines()[max(0, number - 3):number + 2])
                if disclaims.search(window):
                    continue
                offenders.append("%s:%d" % (path.relative_to(root), number))
    assert not offenders, (
        "the short name names an earlier, non-commercially licensed "
        "series and is used here: %s" % ", ".join(offenders))
