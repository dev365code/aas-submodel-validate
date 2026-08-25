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

from aas_submodel_validate import runner
from aas_submodel_validate.rules import dbp_tables, engine, hd_tables, td_tables
from builders import wearing_our_anchor_as_a_supplemental

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


def test_the_third_table_shares_every_label_and_every_identifier():
    """The hazard the test above describes, one degree worse. 02003 at
    least disagreed with 02004 about what a shared label *identified*;
    02035-2 agrees about all 22 of them -- same label, same semanticId,
    same kind -- and differs only in what it obliges. No *identifier* a
    row is matched by distinguishes them, so the table argument is the
    whole of the distinction at the row level. (An instance can still say
    which template it means, one level up, in the submodel's
    supplementals -- that is what `SMT-D2` reads.)"""
    shared = set(hd_tables.BY_LABEL) & set(dbp_tables.BY_LABEL)
    assert len(shared) == len(dbp_tables.BY_LABEL) == 22
    assert all(hd_tables.BY_LABEL[label]["sid"] == dbp_tables.BY_LABEL[label]["sid"]
               for label in shared)


def test_a_submodel_that_wears_our_anchor_in_a_supplemental_is_not_walked(tmp_path):
    """The walk asks the submodel's *main* semanticId and nothing else,
    and a published template is the reason: IDTA 02035-4 carries this
    project's Technical Data anchor as a supplemental while being a
    template of its own. Element matching folds supplementals one level
    down (docs/divergences.md #14), so generalising it upward looks like
    tidying -- and the suite was green when it was done.

    Pointed at the Handover anchor here, at Technical Data's in
    tests/test_detect.py: the hazard belongs to both packs, and one
    fixture proving one of them would leave the other unpinned.
    """
    path = tmp_path / "env.json"
    path.write_bytes(wearing_our_anchor_as_a_supplemental(
        hd_tables.TEMPLATE_SEMANTIC_ID, "HandoverDocumentation"))
    ids = {finding.id for finding in runner.run(path).findings}
    assert not [rule_id for rule_id in ids
                if rule_id.startswith(("HD", "DBP"))], sorted(ids)


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
