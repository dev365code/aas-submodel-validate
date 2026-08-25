"""The walk never guesses which template it is walking.

Every navigation function took the table as an optional argument, so a
rule that forgot it read 02004's. `KeyError` would have made that loud;
the two tables share a label — `ClassificationSystem`, naming a
different element in each — so forgetting is silent, and the rule
reports on an element the author never wrote.

Nothing has forgotten yet. A third pack is what these tests are for, and
02035-2 shares 02004's submodel identifier, which is the one arrangement
where a mistake here cannot be seen from the outside at all.
"""
from __future__ import annotations

import inspect

from aas_submodel_validate.rules import engine, hd_tables, td_tables

#: Everything a rule module uses to read a walk. Each one is a place a
#: table could have been guessed.
NAVIGATION = ("analyze", "matched_submodels", "instances_of",
              "child_of", "children_of", "property_value")


def test_the_walk_requires_its_table():
    for name in NAVIGATION:
        signature = inspect.signature(getattr(engine, name))
        tables = signature.parameters.get("tables")
        assert tables is not None, "%s takes no table at all" % name
        assert tables.default is inspect.Parameter.empty, \
            "%s would guess a table when a caller forgets one" % name


def test_the_two_tables_share_a_label_that_means_different_things():
    """The reason the above matters. If this ever stops being true the
    hazard is smaller, not gone -- a third template may reintroduce it."""
    shared = set(hd_tables.BY_LABEL) & set(td_tables.BY_LABEL)
    assert "ClassificationSystem" in shared
    assert (hd_tables.BY_LABEL["ClassificationSystem"]["sid"]
            != td_tables.BY_LABEL["ClassificationSystem"]["sid"])


def test_the_builders_require_their_table_too():
    """The fixtures decide which rows to strip and where to inject, so a
    builder that guesses a table cuts the wrong elements out of the wrong
    template -- and the test that called it still reads as though it
    exercised the row it named."""
    import builders
    for name in ("strip_row", "inject"):
        signature = inspect.signature(getattr(builders, name))
        tables = signature.parameters["tables"]
        assert tables.default is inspect.Parameter.empty, \
            "builders.%s would guess a table when a caller forgets one" % name
