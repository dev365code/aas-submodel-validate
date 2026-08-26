"""What `xs:date` means, asked of this predicate and of the metamodel.

`valid_xs_date` decides HD-D8 and TD-D1, and it was reached by eight date
strings: February and one March, no December, no `Z`, no offset at either
edge, no month 00 or 13. A hundred and three mutations of it survived the
whole suite.

The oracle is `aas_core3.verification.is_xs_date`, because that is the
layer this project delegates the metamodel to. Where the two agree,
nothing needs saying. Where they differ, one of them is wrong, and this
file is where each difference is named and its direction accounted for --
because the two directions are not symmetric:

*Over-acceptance is backstopped.* A value this predicate lets through
that aas-core3 rejects still draws META ("Value must be consistent with
the value type"), so the file does not pass clean. Measured, not assumed.

*Over-rejection is not.* A conformant value this predicate refuses draws
HD-D8 against a file aas-core3 is perfectly happy with, and nothing else
in the run says otherwise. That is the direction with no second opinion,
and it is what the corpus below is wide for.
"""
from __future__ import annotations

import pytest
from aas_core3.verification import is_xs_date

from aas_submodel_validate.rules.values import valid_xs_date

#: Built from parts rather than typed out, because the parts are what the
#: predicate branches on: the year decides the leap rule, the month
#: indexes the day table, the day is compared against it.
YEARS = ("2025", "2024", "2000", "1900", "0001", "0000", "9999",
         "10000", "012345", "-0001", "-2020", "-2021", "-0004", "999", "20255")
MONTHS = ("01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12",
          "00", "13", "1", "99")
DAYS = ("01", "28", "29", "30", "31", "00", "32", "1", "99")
OFFSETS = ("", "Z", "z", "+00:00", "-00:00", "+14:00", "-14:00", "+14:01",
           "-14:01", "+13:59", "+13:60", "+00:60", "+99:00", "+1:00", "+01:0", "1:00")

MALFORMED = ("", " ", "2025-03-15\n", "\n2025-03-15", " 2025-03-15", "2025-03-15 ",
             "06.02.2020", "2025/03/15", "2025-03-15T00:00:00", "٢٠٢٥-٠٣-١٥",
             "2025-03-15+00:00Z", "--2025-03-15", "2025--03-15")


def _corpus():
    for year in YEARS:
        for month in MONTHS:
            for day in DAYS:
                yield "%s-%s-%s" % (year, month, day)
    for offset in OFFSETS:
        yield "2025-03-15" + offset
        yield "2024-02-29" + offset
    yield from MALFORMED


def _year_of(value):
    """The year as written, or None if the value has no four-digit year."""
    body = value[1:] if value.startswith("-") else value
    digits = body.split("-")[0]
    return ("-" if value.startswith("-") else "") + digits if digits.isdigit() else None


#: The three places the two readings differ, each named and each with the
#: direction it differs in. A difference that is not one of these is a
#: regression in this predicate or a change upstream, and either way it is
#: something somebody has to look at.
def _accounted_for(value, ours, theirs):
    year = _year_of(value)
    if year is not None and year.lstrip("-").lstrip("0") == "":
        # Year zero. XSD 1.0 has none -- 1 BCE is written `-0001` -- and
        # aas-core3 says so. This predicate checks the lexical space and
        # does not, which is an over-acceptance META catches.
        return ours and not theirs
    if year is not None and len(year.lstrip("-")) > 4 and year.lstrip("-")[0] == "0":
        # A year past four digits may not carry leading zeros. Same
        # direction, same backstop.
        return ours and not theirs
    if year is not None and year.startswith("-") and value[-5:-3] == "02":
        # The leap rule for years before the common era. There is no year
        # zero, so `-0001` is 1 BCE and the astronomical year is one
        # greater; this predicate divides the year as written. It differs
        # in *both* directions, which is why the assertion below allows
        # either -- and why the ledger says the metamodel channel is the
        # one to believe about a BCE date.
        return ours != theirs
    if value != value.rstrip("\n"):
        # A trailing newline. `$` in a Python pattern matches before a
        # final newline and aas-core3's ends with one, so it accepts a
        # value an XML Schema processor refuses. This predicate uses `\\Z`.
        # The stricter reading is the correct one and the difference is
        # upstream's (docs/divergences.md).
        return theirs and not ours
    return False


def test_this_reading_and_the_metamodels_agree_or_are_accounted_for():
    """Every value in the corpus, against the reader this project
    delegates the metamodel to. An unaccounted difference is the finding.

    One test over the whole corpus rather than one per value: a run that
    parametrises two thousand cases reports the first and hides the rest,
    and what a reader needs when this goes red is the shape of the
    disagreement, not its alphabetically smallest member."""
    unaccounted = []
    for value in sorted(set(_corpus())):
        ours, theirs = valid_xs_date(value), is_xs_date(value)
        if ours != theirs and not _accounted_for(value, ours, theirs):
            unaccounted.append((value, ours, theirs))
    assert not unaccounted, (
        "no recorded difference covers these: %r" % unaccounted[:20])


def test_the_corpus_reaches_both_answers_and_every_difference():
    """A corpus that only ever agreed would pass the test above with the
    predicate deleted. This is what makes it a measurement: both verdicts
    occur, and each recorded difference is actually exercised."""
    values = sorted(set(_corpus()))
    verdicts = {valid_xs_date(v) for v in values}
    assert verdicts == {True, False}
    differing = [v for v in values if valid_xs_date(v) != is_xs_date(v)]
    assert len(differing) >= 6, differing
    assert any(_year_of(v) == "0000" for v in differing)
    assert any(v.startswith("012345") for v in differing)
    assert any(v.startswith("-") and v.endswith("-02-29") for v in differing)
    assert any(v.endswith("\n") for v in differing)


#: Where the two agree, they are both allowed to be wrong together. These
#: are the values whose answer is fixed here rather than borrowed.
@pytest.mark.parametrize("value", (
    "2025-01-31", "2025-03-31", "2025-04-30", "2025-05-31", "2025-06-30",
    "2025-07-31", "2025-08-31", "2025-09-30", "2025-10-31", "2025-11-30",
    "2025-12-31", "2024-02-29", "2000-02-29", "2025-03-15Z",
    "2025-03-15+14:00", "2025-03-15-14:00", "2025-03-15+00:00", "-0001-01-01",
))
def test_a_conformant_date_is_accepted(value):
    """The direction with no second opinion. A value refused here draws
    HD-D8 against a file the metamodel channel is happy with, and a
    finding on a conformant file is the one thing worse than silence --
    so every month's last day, both leap rules, and both edges of the
    offset are named rather than left to the corpus to happen to cover."""
    assert valid_xs_date(value)


#: Three mutations of the predicate survive all of the above, and all
#: three are equivalent -- named here so the next person measuring does
#: not spend an afternoon on them.
#:
#: `offset[4:6]` widened to any larger end: the pattern admits exactly
#: `[+-]dd:dd`, so the slice cannot reach past the string. `^` removed
#: from the pattern: `match` anchors at the start already. The `^` stays
#: because it stops being redundant the moment somebody reaches for
#: `search`, which is a cheaper guard than a comment about it.


@pytest.mark.parametrize("value", (
    "2025-04-31", "2025-06-31", "2025-09-31", "2025-11-31", "2025-02-29",
    "1900-02-29", "2025-00-15", "2025-13-15", "2025-03-00", "2025-03-32",
    "2025-03-15+14:01", "2025-03-15-14:01", "2025-03-15+13:60",
    "2025-03-15+00:60", "2025-3-15", "2025-03-5",
))
def test_a_value_outside_the_lexical_space_is_refused(value):
    """The other edge of each branch. Thirty days hath September, 1900 is
    not a leap year, and the offset is bounded at fourteen hours -- none
    of which the eight strings that used to reach this predicate asked."""
    assert not valid_xs_date(value)
