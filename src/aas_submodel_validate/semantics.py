"""semanticId comparison: values, normalised, from any key.

Two decisions live here and nowhere else (docs/divergences.md #4, and
the matching policy behind #1--#3):

Values are collected from *every* key of a Reference, not keys[0] alone —
real instances differ in how they stack keys, and a comparison that only
looks at the first one silently unmatches files other tools accept.

ECLASS-CDP URLs normalise to their IRDI. The official 02004 template
itself spells exactly one property's semanticId as
`https://api.eclass-cdp.com/0173-1-02-ABI002-003` where every sibling
property uses `0173-1#02-ABI002#003` — the PDF does the same — so an
instance carrying either spelling must match either authority.
"""
from __future__ import annotations

import re
from typing import List, Optional

_CDP_URL = re.compile(r"^https?://api\.eclass-cdp\.com/([0-9A-Za-z.-]+)/?$")
_CDP_TAIL = re.compile(r"^(\d{4}-\d)-(\d{2}-[A-Z]{3}\d{3})-(\d{3})$")


def normalize(value: str) -> str:
    """The comparison form of one semanticId key value."""
    value = value.strip()
    url = _CDP_URL.match(value)
    if url:
        tail = _CDP_TAIL.match(url.group(1))
        if tail:
            return "%s#%s#%s" % tail.groups()
    return value


def key_values(reference) -> List[str]:
    """Every key's value in `reference`, normalised. None-safe, because
    semanticId is optional on every element."""
    if reference is None:
        return []
    return [normalize(key.value) for key in (reference.keys or [])]


def version_stem(irdi: str) -> Optional[str]:
    """`0173-1#01-AHF578#003` -> `0173-1#01-AHF578`; None when the value
    does not end in an ECLASS version suffix."""
    head, sep, tail = irdi.rpartition("#")
    if sep and tail.isdigit() and "#" in head:
        return head
    return None
