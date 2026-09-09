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

import copy
import inspect

from aas_submodel_validate import runner
from aas_submodel_validate.rules import dbp_tables, engine, hd_tables, td_tables
from builders import hd_env, wearing_our_anchor_as_a_supplemental

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


def test_no_hand_rule_navigates_to_a_child_that_is_not_there(tmp_path):
    """`child_of` looks at direct children only, and answers `None` for
    anything it cannot find.

    That is the right answer for an absent element -- the generated
    cardinality rule is what speaks about those -- and it is also what a
    hand rule gets when it asks for a label that is not a child of the
    element it was handed at all. The two are indistinguishable at the
    call site, and the second is silent: a rule reads nothing, reports
    nothing, and the file passes a check that never happened.

    Two of the three preconditions `child_of` rests on are already held
    elsewhere. Labels are unique within a pack because
    `tools/extract_smt_rules.py` refuses to emit a table where they are
    not, naming the duplicate. The table is never guessed because every
    navigation function takes it without a default, which the test at
    the top of this file asserts. This is the third: on a file that has
    everything, every `child_of` a rule makes finds it.

    The battery fixture is deliberately not here. It is short of six
    mandatory elements -- `HD-E17`, `E20`, `E22`, `E23`, `E24`, `E25`
    report on it -- so `child_of` answering `None` there is the correct
    answer to a question about a file that really is missing them.
    """
    import collections
    import json

    from aas_submodel_validate import runner
    from aas_submodel_validate.rules import engine, handover
    from aas_submodel_validate.rules import td as td_rules
    from builders import build_aasx, hd_env, td_env

    original = engine.child_of
    # Every module that holds the name, not just the one that defines
    # it. `handover.py` does `from .engine import child_of`, so the
    # binding it calls was made at import and rebinding `engine.child_of`
    # never reaches it -- the first version of this test patched only
    # `engine` and three mis-scoped navigations walked straight past it.
    holders = [m for m in (engine, handover, td_rules) if hasattr(m, "child_of")]
    assert len(holders) >= 2, "nothing but the engine holds the name; check the imports"
    try:
        for name, make in (("hd", hd_env), ("td", td_env)):
            missed = collections.Counter()

            wrong_kind = []

            def spy(element, label, tables, _missed=missed, _wrong=wrong_kind):
                found = original(element, label, tables)
                if found is None:
                    _missed[label] += 1
                elif type(found).__name__ != tables.BY_LABEL[label]["kind"]:
                    # Asking for the item and getting the list. In five
                    # Handover places IDTA gives a list and its own item
                    # the same semanticId -- `DigitalFiles` and
                    # `DigitalFile` are both `0173-1#02-ABK126#002` --
                    # and `child_of` matches on the identifier, so the
                    # two labels are interchangeable at a call site and
                    # only one of them is right. The label looks like it
                    # is doing the work and is not.
                    _wrong.append((label, tables.BY_LABEL[label]["kind"],
                                   type(found).__name__))
                return found

            for module in holders:
                module.child_of = spy
            path = build_aasx(
                tmp_path / (name + ".aasx"),
                payload=json.dumps(make()).encode("utf-8"),
                files=(("aasx/files/manual.pdf", b"%PDF-1.4"),
                       ("aasx/files/logo.png", b"\x89PNG"),
                       ("aasx/files/front.png", b"\x89PNG")))
            report = runner.run(str(path))
            # The control. A fixture that stopped being conformant would
            # satisfy the assertion below by never reaching a hand rule.
            assert [f.id for f in report.findings] == [], (name, report.findings)
            assert not missed, (name, dict(missed))
            assert not wrong_kind, (name, wrong_kind)
    finally:
        for module in holders:
            module.child_of = original


def test_a_list_or_property_reaching_the_walk_has_declared_its_type():
    """A precondition two guards in `_scope` rest on, and the comment
    explaining one of them named the wrong field.

    `_scope` compares a list's declared item type and a property's
    declared value type against the template, each behind
    `<declaration> is not None`. The comment said
    `typeValueListElement` is optional in the metamodel and that a file
    saying nothing is not a file saying something wrong.

    Measured, it is mandatory: `SubmodelElementList.type_value_list_element`
    and `Property.value_type` are both required arguments in `aas_core3`,
    and both JSON and XML deserialisation refuse a file that omits them
    -- refuse it before this project's rules run at all. So neither guard
    can fire, and the reason given for one of them was not its reason.

    The optional field is `valueTypeListElement`, one letter-order away
    from `typeValueListElement` and a different thing entirely. That is
    almost certainly where the comment came from, and it is why this is
    pinned rather than argued: if `aas_core3` ever relaxes either field,
    those guards stop being unreachable and start being load-bearing,
    and whoever is here then should be told by a red test rather than by
    a crash in `None.value`.
    """
    import inspect

    import aas_core3.jsonization as jsonization
    import aas_core3.types as core_types
    import aas_core3.xmlization as xmlization

    for owner, field in ((core_types.SubmodelElementList, "type_value_list_element"),
                         (core_types.Property, "value_type")):
        parameter = inspect.signature(owner.__init__).parameters[field]
        assert parameter.default is inspect.Parameter.empty, (
            "%s.%s has become optional; the guards in `_scope` that assume "
            "otherwise are now reachable" % (owner.__name__, field))

    #: The confusable one, asserted so the distinction cannot rot back.
    optional = inspect.signature(
        core_types.SubmodelElementList.__init__).parameters["value_type_list_element"]
    assert optional.default is None

    def refuses(strip_key, model_type):
        env = copy.deepcopy(hd_env())

        def walk(node):
            if isinstance(node, dict):
                if node.get("modelType") == model_type and strip_key in node:
                    node.pop(strip_key)
                    return True
                return any(walk(v) for v in node.values())
            if isinstance(node, list):
                return any(walk(item) for item in node)
            return False

        assert walk(env), "the fixture no longer has a %s to strip" % model_type
        try:
            jsonization.environment_from_jsonable(env)
        except Exception as exc:                     # noqa: BLE001
            return strip_key in str(exc)
        return False

    assert refuses("typeValueListElement", "SubmodelElementList")
    assert refuses("valueType", "Property")

    #: And the same on the other serialisation, because an AASX payload
    #: may be either and only one of them was checked here at first.
    bare = ("<environment xmlns=\"https://admin-shell.io/aas/3/0\">"
            "<submodels><submodel><id>urn:x</id><submodelElements>"
            "<submodelElementList><idShort>L</idShort><value/>"
            "</submodelElementList></submodelElements></submodel></submodels>"
            "</environment>")
    try:
        xmlization.environment_from_str(bare)
        raise AssertionError("XML accepted a list with no typeValueListElement")
    except Exception as exc:                         # noqa: BLE001
        assert "typeValueListElement" in str(exc), exc
