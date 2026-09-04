"""What `xs:date` means, asked of this predicate and of the metamodel.

`valid_xs_date` decides HD-D8 and TD-D1, and everything that reached it
was thirteen distinct values, eight of them date-shaped: one January,
February, two March. No December, no `Z`, neither edge of the offset, no
month 00 or 13. Every constant in the predicate could be moved and the
suite stayed green.

The oracle is `aas_core3.verification.is_xs_date`, because that is the
layer this project delegates the metamodel to. Where the two agree there
is nothing to say. Where they differ, one of them is wrong, and the
ledger below names every difference and its direction -- an unnamed one
is the finding.

The two directions are not symmetric, and that is what the ledger is
for. *Over-acceptance* is caught by something: a value this predicate
lets through and aas-core3 rejects still draws META, measured below --
though only as a warning, so the run still exits 0 and "caught" means a
line on the screen rather than a verdict. *Over-rejection* is caught by
nothing: a conformant value refused here draws a MUST finding against a
file the metamodel channel is happy with, and the run exits 1.

The predicate used to differ in both directions, twenty-two of them
over-rejections. It differs in one direction now.
"""
from __future__ import annotations

import copy
import json

import pytest
from aas_core3.verification import is_xs_date

from aas_submodel_validate import runner
from aas_submodel_validate.rules.values import valid_xs_date
from builders import hd_env

#: Built from parts rather than typed out, because the parts are what the
#: predicate branches on: the year decides the leap rule, the month
#: indexes the day table, the day is compared against it, and the offset
#: is bounded on both sides.
YEARS = ("2025", "2024", "2000", "1900", "0001", "0000", "-0000", "9999",
         "10000", "012345", "-0001", "-0002", "-0004", "-0005", "-2020",
         "-2021", "-0100", "-0400", "999", "20255")
MONTHS = tuple("%02d" % m for m in range(0, 14)) + ("1", "99", "003")
DAYS = ("01", "28", "29", "30", "31", "00", "32", "1", "99", "0031")
#: Crossed against every year, not against one date. The ledger's own
#: reading of a value used to be positional, and a positional reading is
#: right only while nothing follows the day -- so the axis that would
#: have shown that has to be crossed, not sampled.
OFFSETS = ("", "Z", "z", "+00:00", "-00:00", "+14:00", "-14:00", "+14:01",
           "-14:01", "+13:59", "+13:60", "+00:60", "+99:00", "+1:00",
           "+01:0", "1:00", "+1400", "+0014:00", "+14:000")

#: Everything an XML Schema processor folds away before matching, and a
#: few shapes it does not.
WHITESPACE = ("\n", " ", "\t", "\r\n", "\n\n")
MALFORMED = ("", " ", "06.02.2020", "2025/03/15", "2025-03-15T00:00:00",
             "٢٠٢٥-٠٣-١٥", "2025-03-15+00:00Z", "--2025-03-15", "2025--03-15",
             "2025-03-15\x00")


def _corpus():
    for year in YEARS:
        for month in MONTHS:
            for day in DAYS:
                yield "%s-%s-%s" % (year, month, day)
        for offset in OFFSETS:
            yield "%s-02-29%s" % (year, offset)
            yield "%s-03-15%s" % (year, offset)
    for pad in WHITESPACE:
        yield "2025-03-15" + pad
        yield pad + "2025-03-15"
        yield pad + "2025-03-15" + pad
    yield from MALFORMED


CORPUS = tuple(sorted(set(_corpus())))


#: The one place the two readings differ, named, with its direction.
#:
#: `xs:date` carries `whiteSpace="collapse" fixed="true"` in the schema
#: W3C publishes for the built-in types, so a conforming processor folds
#: tabs, newlines and runs of spaces and trims the ends before the value
#: is matched. This predicate does; aas-core3 does not, and its pattern
#: ends with `$`, which admits a trailing newline and refuses a leading
#: one -- an asymmetry that is neither reading, just what `$` does in
#: Python.
#:
#: The direction is the safe one. Every value here is one XML Schema
#: calls conformant, so refusing it would be the failure this file exists
#: to prevent; accepting it where aas-core3 would not is an
#: over-acceptance, and META has the second opinion.
def _accounted_for(value, ours, theirs):
    return value != " ".join(value.split()) and ours and not theirs


def test_this_reading_and_the_metamodels_agree_or_are_accounted_for():
    """Every value in the corpus, against the reader this project
    delegates the metamodel to. An unaccounted difference is the finding.

    One test over the whole corpus rather than one per value: what a
    reader needs when this goes red is the shape of the disagreement, not
    its alphabetically smallest member."""
    unaccounted = []
    for value in CORPUS:
        ours, theirs = valid_xs_date(value), is_xs_date(value)
        if ours != theirs and not _accounted_for(value, ours, theirs):
            unaccounted.append((value, ours, theirs))
    assert not unaccounted, (
        "no recorded difference covers these: %r" % unaccounted[:20])


def test_the_ledger_excuses_exactly_the_differences_and_no_more():
    """The test above is only as strong as the ledger is narrow, and
    nothing measured how narrow. Replacing the ledger with `return True`
    passed: a sentence that excuses everything excuses the regression it
    was written to catch."""
    differing = {v for v in CORPUS if valid_xs_date(v) != is_xs_date(v)}
    excused = {v for v in CORPUS
               if _accounted_for(v, valid_xs_date(v), is_xs_date(v))}
    assert excused == differing
    assert differing, "the corpus stopped reaching the recorded difference"
    assert all(v != " ".join(v.split()) for v in differing)


def test_the_corpus_keeps_its_shape():
    """A corpus that shrank would pass everything above while measuring
    nothing: most of its values could be deleted one at a time without a
    test noticing, and a tiny stand-in passed both guards while proving
    far less. What cannot shrink is asserted here."""
    assert len(CORPUS) >= 2000
    months = {v.split("-")[1] for v in CORPUS if v.startswith("2025-")}
    assert months >= {"%02d" % m for m in range(1, 13)}
    assert {True, False} == {valid_xs_date(v) for v in CORPUS}
    for edge in ("+14:00", "+14:01", "-14:00", "Z"):
        assert any(v.endswith(edge) for v in CORPUS), edge
    # Fields longer than the grammar allows, which is where a pattern
    # that counts "two or more" instead of "exactly two" shows.
    for wide in ("003", "0031", "+1400", "+0014:00"):
        assert any(wide in v for v in CORPUS), wide


@pytest.mark.parametrize("value", (
    "2025-01-31", "2025-03-31", "2025-04-30", "2025-05-31", "2025-06-30",
    "2025-07-31", "2025-08-31", "2025-09-30", "2025-10-31", "2025-11-30",
    "2025-12-31", "2024-02-29", "2000-02-29", "2025-03-15Z",
    "2025-03-15+14:00", "2025-03-15-14:00", "2025-03-15+00:00",
    "-0001-01-01", "-0001-02-29", "-0005-02-29", "2025-03-15\n",
    "0001-01-01", "10000-01-01",
))
def test_a_conformant_date_is_accepted(value):
    """Fixed points, held independently of the oracle. Where the two
    readings agree they are allowed to be wrong together, and an oracle
    that moves takes the comparison with it; these do not move.

    All of them are the direction with no second opinion: a value refused
    here draws a MUST finding against a file aas-core3 is happy with. The
    last three used to be refused."""
    assert valid_xs_date(value)


@pytest.mark.parametrize("value", (
    "2025-04-31", "2025-06-31", "2025-09-31", "2025-11-31", "2025-02-29",
    "1900-02-29", "2025-00-15", "2025-13-15", "2025-03-00", "2025-03-32",
    "2025-03-15+14:01", "2025-03-15-14:01", "2025-03-15+13:60",
    "2025-03-15+00:60", "2025-3-15", "2025-03-5", "0000-01-01",
    "-0000-01-01", "012345-01-01", "-0004-02-29", "2025-003-01",
    "2025-01-0031", "2025-01-01+1400", "2025-01-01+14:000",
))
def test_a_value_outside_the_lexical_space_is_refused(value):
    """The other edge of each branch. Thirty days hath September, 1900 is
    not a leap year, the offset is bounded at fourteen hours, there is no
    year zero, a year past four digits carries no leading zero, and a
    field is exactly as wide as the grammar says."""
    assert not valid_xs_date(value)


#: A few changes to the predicate survive everything above, all of
#: them equivalent -- named so the next reader does not spend an
#: afternoon on them, and because some of them *became* equivalent here.
#:
#: `^` removed and `match` swapped for `search`: `match` anchors already,
#: and `^` anchors already, so either alone does the job. `\Z` swapped for
#: `$`: the collapse strips the trailing newline before the pattern sees
#: it, so the distinction those two used to make is no longer reachable.
#: `re.ASCII` removed: the year alternation spells `[1-9]` and `0` as
#: literals, so a year in Arabic-Indic digits fails there before any
#: `\d` is asked.
#:
#: They all stay. Each is redundant only while the thing beside it holds,
#: and the thing beside it is one edit away from not holding.


def _with_status_set_date(value):
    env = copy.deepcopy(hd_env())

    def walk(element):
        if element.get("idShort") == "StatusSetDate":
            yield element
        children = element.get("value")
        if isinstance(children, list):
            for child in children:
                yield from walk(child)

    node = next(found for element in env["submodels"][0]["submodelElements"]
                for found in walk(element))
    node["value"] = value
    return env


@pytest.mark.parametrize("value", ("0000-01-01", "012345-01-01", "-0004-02-29"))
def test_a_value_this_reading_used_to_admit_is_now_refused_by_both(tmp_path, value):
    """The three the predicate accepted and aas-core3 did not, which a
    ledger recorded as "over-acceptance, backstopped by META".

    The backstop was real and weaker than the word carries: META is the
    relayed channel at `SHOULD`, so the report came back `ok` and the run
    exited 0. Somebody reading the screen was told; a gate reading the
    exit code was not. Measured rather than asserted, because the claim
    lived in a docstring and the measurement lived nowhere.

    Both channels refuse them now, and the run exits 1."""
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(_with_status_set_date(value)).encode("utf-8"))
    report = runner.run(path)
    assert "HD-D8" in {f.id for f in report.findings}
    assert [f for f in report.findings if f.id == "META"], "the second opinion went away"
    assert not report.ok
