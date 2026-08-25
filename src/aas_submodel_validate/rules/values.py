"""Value spellings the metamodel declares but does not check.

A `valueType` says what a value claims to be. Whether the characters
in it are that thing is a separate question, and the commoner mistake:
`xs:date` declared over `06.02.2020`. Nothing here belongs to one
template -- 02004 asks it of StatusSetDate and 02003 of ValidDate.
"""
from __future__ import annotations

import re

#: `\Z` rather than `$`, which matches before a final newline, and
#: ASCII digits rather than every decimal digit Unicode knows: an
#: XML Schema processor accepts neither spelling.
_XS_DATE = re.compile(r"^(-?\d{4,})-(\d{2})-(\d{2})(Z|[+-]\d{2}:\d{2})?\Z", re.ASCII)


def valid_xs_date(value: str) -> bool:
    """xs:date lexical space -- which is wider than datetime.date: the year
    may be negative or run past 9999, so it is checked lexically rather
    than by constructing a date (which would reject `-0001-01-01`, a value
    aas-core3 accepts). The timezone offset is bounded to +/-14:00."""
    matched = _XS_DATE.match(value)
    if not matched:
        return False
    year, month, day = int(matched.group(1)), int(matched.group(2)), int(matched.group(3))
    if not 1 <= month <= 12:
        return False
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    days_in = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[month - 1]
    if not 1 <= day <= days_in:
        return False
    offset = matched.group(4)
    if offset and offset != "Z":
        hours, minutes = int(offset[1:3]), int(offset[4:6])
        if minutes > 59 or hours * 60 + minutes > 14 * 60:
            return False
    return True
