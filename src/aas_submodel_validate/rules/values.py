"""Value spellings the metamodel declares but does not check.

A `valueType` says what a value claims to be. Whether the characters
in it are that thing is a separate question, and the commoner mistake:
`xs:date` declared over `06.02.2020`. Nothing here belongs to one
template -- 02004 asks it of StatusSetDate and 02003 of ValidDate.
"""
from __future__ import annotations

import re

#: `\Z` rather than `$`, which matches before a final newline, and ASCII
#: digits rather than every decimal digit Unicode knows.
#:
#: A year runs to at least four digits and carries a leading zero only
#: inside them: `0001` is the year one, `012345` is not a year at all.
#: Spelling that here rather than counting digits afterwards keeps the
#: one place that decides what a year looks like in one place.
_XS_DATE = re.compile(
    r"^(-?(?:[1-9]\d{3,}|0\d{3}))-(\d{2})-(\d{2})(Z|[+-]\d{2}:\d{2})?\Z", re.ASCII)


def valid_xs_date(value: str) -> bool:
    """xs:date lexical space -- wider than `datetime.date`, because the
    year may be negative or run past 9999. Checked lexically rather than
    by constructing a date, which would reject `-0001-01-01`.

    Whitespace goes first, because the type says so: `xs:date` carries
    `whiteSpace="collapse" fixed="true"` in the schema W3C publishes for
    the built-in types, so a conforming processor folds tabs, newlines
    and runs of spaces and trims the ends *before* the value is matched.
    A predicate that skipped that step reported a defect against a
    document an XML Schema processor calls conformant -- and a finding on
    a conformant file is the one direction with no second opinion, since
    the metamodel channel accepts what it accepts and says nothing.

    There is no year zero: `-0001` is 1 BCE, and the astronomical year is
    one greater, which is what the leap rule has to divide. Getting that
    wrong is silent in both directions -- February 29th of a year before
    the common era is either refused when it exists or accepted when it
    does not, and only a date that old ever notices.
    """
    matched = _XS_DATE.match(" ".join(value.split()))
    if not matched:
        return False
    year, month, day = int(matched.group(1)), int(matched.group(2)), int(matched.group(3))
    if year == 0:
        return False
    if not 1 <= month <= 12:
        return False
    astronomical = abs(year) - 1 if year < 0 else year
    leap = (astronomical % 4 == 0
            and (astronomical % 100 != 0 or astronomical % 400 == 0))
    days_in = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[month - 1]
    if not 1 <= day <= days_in:
        return False
    offset = matched.group(4)
    if offset and offset != "Z":
        hours, minutes = int(offset[1:3]), int(offset[4:6])
        if minutes > 59 or hours * 60 + minutes > 14 * 60:
            return False
    return True
