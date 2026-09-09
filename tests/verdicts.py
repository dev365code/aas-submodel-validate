"""One reader for a report's findings, shared by the tests that had a
copy of it each.

Twenty-three call sites built `{finding.id: finding for finding in
report.findings}` themselves, in four spellings. That is what this
replaces, and all it does.

It deliberately asserts nothing. The property those call sites needed --
that a rule which *crashed* is not read as a rule that fired, since the
crash carries the rule's own id, its own severity and the subject it was
reading -- is enforced in `conftest.py`, once, for every report the suite
produces. Putting it here as well would mean two places to keep true and
one of them silently unreachable for the eighty-one assertions that never
call this at all.

So: if you are looking for why a crashed rule cannot be mistaken for a
verdict, it is in `conftest.py`, and `tests/test_suite_hygiene.py` is
what proves it still works by injecting one.
"""
from __future__ import annotations


def by_id(report) -> dict:
    """`report`'s findings keyed by rule id."""
    return {finding.id: finding for finding in report.findings}
