"""SMT-D2: when two templates answer to one identifier, say which answered.

IDTA 02035-2 declares IDTA 02004's submodel semanticId exactly, so a file
that names it might mean either, and every report about such a file is
about a choice the reader cannot see. This rule makes the choice visible.

What it must not do is make the choice. There is no published 02035-2
instance anywhere, so nothing measures how often a real battery passport
would carry the mark; a signal like that may add a sentence and may not
subtract a check. Two of the tests below exist only to hold that line:
one proves a marked submodel loses no rule, one proves the note cannot
move an exit code.
"""
from __future__ import annotations

import ast
import copy
import inspect
import json
from pathlib import Path

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.model import Severity
from aas_submodel_validate.rules import (
    dbp_tables,
    detect,
    engine,
    hd_tables,
    profiles,
    td_tables,
)
from builders import (
    break_row,
    declaring_profile,
    env_json,
    hd_env,
    td_env,
    wearing_our_anchor_as_a_supplemental,
)

#: The one pair published today.
DBP = profiles.PROFILES[0]

#: What 02004 requires of a file and 02035-2 does not, by rule id.
RELIEVED = ["HD-E17", "HD-E20", "HD-E22", "HD-E23", "HD-E24", "HD-E25",
            "HD-E27", "HD-E29", "HD-E31", "HD-E36", "HD-E38"]

#: The six of those that sit under containers 02004 always requires, so a
#: conformant 02035-2 instance is faulted for exactly these.
UNCONDITIONAL = RELIEVED[:6]


def _report(tmp_path, env: dict, name="env.json"):
    path = tmp_path / name
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return runner.run(path)


def _ids(report):
    return {finding.id for finding in report.findings}


def _mark():
    """The mark, recomputed here from the two tables rather than read off
    the module under test -- a fixture that asked `profiles` what to write
    would agree with it however wrong it was."""
    difference = (frozenset(dbp_tables.TEMPLATE_SUPPLEMENTAL_SEMANTIC_IDS)
                  - frozenset(hd_tables.TEMPLATE_SUPPLEMENTAL_SEMANTIC_IDS))
    (only,) = difference
    return only


# -- the signal --------------------------------------------------------------

def test_the_mark_is_derived_from_the_tables_and_never_written_down():
    """The value is upstream's and lives hash-verified in the vendored
    template. A copy in this module would be a second place for it to be
    right, and the copy is the one nobody regenerates.

    Read through the AST rather than the source text, which catches one
    spelling a substring search misses: Python joins adjacent string
    literals at parse time, so a copy wrapped across two lines is
    invisible in the file. It catches no other spelling -- `+` between
    the halves, an f-string, `bytes`, or the value living in a different
    module all pass -- and it is a tripwire on the obvious mistake, not a
    proof.
    """
    assert DBP.marks == frozenset([_mark()])
    source = Path(inspect.getfile(profiles)).read_text("utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert _mark() not in node.value, \
                "the mark is written into rules/profiles.py; derive it"


def test_the_relieved_rows_are_what_02004_requires_and_02035_2_does_not():
    """Eleven, not six. Six of them sit under containers 02004 always
    requires and so appear in every report about a battery passport; the
    other five are required children of an optional container, and a file
    that uses one of those branches is faulted for them just the same."""
    assert [row["id"] for row in DBP.relieved] == RELIEVED
    for row_id in UNCONDITIONAL:
        assert hd_tables.BY_ID[row_id]["label"] not in dbp_tables.BY_LABEL \
            or dbp_tables.BY_LABEL[hd_tables.BY_ID[row_id]["label"]]["card"][0] == 0


# -- what it says ------------------------------------------------------------

def test_an_unmarked_submodel_is_told_nothing(tmp_path):
    """Silence on the default profile is load-bearing: the golden fixture
    and the official example must keep drawing nothing at all."""
    assert _ids(_report(tmp_path, hd_env())) == set()


def test_a_marked_submodel_is_told_which_template_answered(tmp_path):
    report = _report(tmp_path, declaring_profile(hd_env(), _mark()))
    (finding,) = [f for f in report.findings if f.id == "SMT-D2"]
    assert finding.severity is Severity.INFO
    assert finding.violation.subject == "HandoverDocumentation"
    assert "IDTA 02004" in finding.violation.detail
    assert "IDTA 02035-2" in finding.violation.detail


def test_the_notice_names_every_cardinality_the_two_templates_differ_on(tmp_path):
    report = _report(tmp_path, declaring_profile(hd_env(), _mark()))
    (finding,) = [f for f in report.findings if f.id == "SMT-D2"]
    for row_id in RELIEVED:
        assert row_id in finding.violation.detail


def test_the_notice_names_the_findings_a_conformant_battery_passport_gets(tmp_path):
    """The list is not decoration. A file that is exactly what 02035-2
    asks for draws six errors under 02004, and the notice names each of
    them -- so a reader can tell which of the findings above are the
    profile's disagreement rather than their own mistake."""
    env = hd_env()
    for row_id in UNCONDITIONAL:
        env = break_row(env, hd_tables.BY_ID[row_id], hd_tables)
    report = _report(tmp_path, declaring_profile(env, _mark()))
    errors = {f.id for f in report.findings if f.severity is Severity.ERROR}
    assert errors == set(UNCONDITIONAL)
    (finding,) = [f for f in report.findings if f.id == "SMT-D2"]
    assert all(row_id in finding.violation.detail for row_id in errors)


# -- what it must not do -----------------------------------------------------

def _classification(env, field, value):
    """Rewrite one field of every Document's classification."""
    env = copy.deepcopy(env)
    for document in env["submodels"][0]["submodelElements"][0]["value"]:
        for child in document["value"]:
            if child.get("idShort") != "DocumentClassifications":
                continue
            for item in child["value"]:
                for leaf in item["value"]:
                    if leaf.get("idShort") == field:
                        leaf["value"] = value
    return env


#: One broken file per rule a switch would be tempted to excuse, and one
#: per kind of rule it would not. Every relieved row is here by name --
#: measured, not chosen: a version of this test that broke one of them
#: passed while five others were being silenced, because those five sit
#: under optional containers and no fixture reached them.
BREAKAGE = dict(
    [("relieved: " + hd_tables.BY_ID[row_id]["label"],
      (lambda row: lambda: break_row(hd_env(), row, hd_tables))(hd_tables.BY_ID[row_id]))
     for row_id in RELIEVED]
    + [
        ("a generated row 02035-2 keeps",
         lambda: break_row(hd_env(), hd_tables.BY_LABEL["Title"], hd_tables)),
        ("a hand rule", lambda: _classification(hd_env(), "ClassificationSystem", "SOMETHING-ELSE")),
        ("another hand rule", lambda: _classification(hd_env(), "ClassId", "99-99")),
        ("a lint", lambda: _classification(hd_env(), "ClassificationSystem", "VDI2770:2020")),
        ("nothing at all", lambda: json.loads(env_json(hd_tables.TEMPLATE_SEMANTIC_ID))),
    ])


@pytest.mark.parametrize("broken", sorted(BREAKAGE), ids=sorted(BREAKAGE))
def test_the_mark_changes_the_report_by_exactly_one_sentence(tmp_path, broken):
    """The invariant the whole slice rests on, written as a comparison
    rather than as a claim about one rule: for one file, marked and
    unmarked, the findings are the same set apart from SMT-D2 itself.

    It has to be a comparison. Every narrower version of this test was
    measured and found to pass while the invariant was broken: a switch
    installed in `rules/hd.py` -- where the rules that would be switched
    actually live, not in `engine.py` -- excused HD-D2, the mandatory VDI
    2770 classification this tool exists to check, and left 318 tests,
    four gates and ruff green while a faulty file's exit code went from 1
    to 0.
    """
    env = BREAKAGE[broken]()
    plain = _ids(_report(tmp_path, env, "plain.json"))
    marked = _ids(_report(tmp_path, declaring_profile(env, _mark()), "marked.json"))
    assert plain, "this fixture breaks nothing, so it proves nothing"
    assert marked - {"SMT-D2"} == plain
    assert "SMT-D2" in marked


# -- what it must not do, continued ------------------------------------------

def test_the_mark_adds_a_sentence_and_no_finding(tmp_path):
    """A conformant 02004 file that also declares the battery-passport
    profile draws the note and nothing else -- the mark invents no defect.

    It does *not* prove the mark takes no check away: this fixture is
    clean, so silencing every 02004 rule would leave the same result.
    That claim belongs to the test below, and writing it here is a
    mistake this file made once.
    """
    assert _ids(_report(tmp_path, declaring_profile(hd_env(), _mark()))) == {"SMT-D2"}


def test_a_marked_submodel_that_is_broken_is_still_faulted(tmp_path):
    """Choosing the other table here would silence 52 rules and leave 0 in
    their place, and the tool would print `ok` over a file that violates
    both templates. It does not."""
    env = json.loads(env_json(hd_tables.TEMPLATE_SEMANTIC_ID))
    report = _report(tmp_path, declaring_profile(env, _mark()))
    assert "HD-E01" in _ids(report)
    assert not report.ok


def test_the_package_registers_the_rule_and_not_only_this_test(tmp_path):
    """`tests/test_profiles.py` imports the module, which registers the
    rule -- so the suite counts 90 rules whether or not the shipped
    package does. Dropping `profiles` from `rules/__init__.py` leaves all
    317 tests green and only `make exercised` red; the installed package
    would quietly lose the rule. This is the suite saying why."""
    imports = (Path(inspect.getfile(profiles)).parent / "__init__.py").read_text("utf-8")
    assert "profiles" in imports, \
        "importing the rules package must register this rule, not the test that tests it"


def test_the_notice_alone_cannot_move_an_exit_code(tmp_path):
    """`Report.ok` counts errors, so an `info` rule cannot make a clean
    file dirty -- and cannot make a dirty one clean either. That is why
    the priority is MAY and not something louder."""
    report = _report(tmp_path, declaring_profile(hd_env(), _mark()))
    assert _ids(report) == {"SMT-D2"}
    assert report.ok


# -- what it must not answer to ----------------------------------------------

def test_a_template_of_its_own_wearing_our_anchor_draws_no_notice(tmp_path):
    """IDTA 02035-4 carries our Technical Data anchor as a supplemental.
    This rule reads supplementals, so it is the one place where that shape
    could be mistaken for a profile declaration."""
    path = tmp_path / "foreign.json"
    path.write_bytes(wearing_our_anchor_as_a_supplemental(
        td_tables.TEMPLATE_SEMANTIC_ID, "TechnicalData"))
    assert "SMT-D2" not in {f.id for f in runner.run(path).findings}


def test_a_template_of_its_own_that_also_carries_the_mark_is_still_not_ours(tmp_path):
    """The shape where the shield and the profile question meet: a
    submodel with an identity of its own, this project's Handover anchor
    in a supplemental, and the battery-passport mark beside it.

    Both existing fixtures for the shield carry no mark, so neither can
    see the failure where folding supplementals into
    `semantics.submodel_declares` makes a foreign template *both* ours
    and a declared profile of ours -- the report then names a template it
    has just said it does not recognise.
    """
    path = tmp_path / "foreign-and-marked.json"
    path.write_bytes(wearing_our_anchor_as_a_supplemental(
        hd_tables.TEMPLATE_SEMANTIC_ID, "HandoverDocumentation", also=_mark()))
    ids = {finding.id for finding in runner.run(path).findings}
    assert ids == {"SMT-D1"}, sorted(ids)


def test_a_mark_on_a_different_template_draws_nothing(tmp_path):
    """The guard is the main semanticId: a Technical Data submodel that
    somehow carried the battery-passport URN is not a Handover profile,
    and saying so would be a finding about nothing."""
    assert "SMT-D2" not in _ids(_report(tmp_path, declaring_profile(td_env(), _mark())))


def test_the_template_id_is_not_a_profile_signal(tmp_path):
    """02035-2's own AASX declares `templateId` `.../idta-02004-2-0` while
    its JSON declares `.../idta-02035-2`, and IDTA 02035-4 declares the
    bare string `IDTA-02003-2-0`, which a suffix match reads as ours. The
    field is evidence about nothing, and this rule does not read it."""
    env = copy.deepcopy(hd_env())
    env["submodels"][0]["administration"] = {
        "version": "1", "revision": "0",
        "templateId": "https://admin-shell.io/idta-02035-2"}
    assert "SMT-D2" not in _ids(_report(tmp_path, env))


def test_the_mark_answers_where_the_template_id_contradicts_it(tmp_path):
    """The shape 02035-2's published AASX actually has: the mark present,
    the templateId naming 02004. The mark is what this rule reads."""
    env = declaring_profile(hd_env(), _mark(),
                            template_id="https://admin-shell.io/idta-02004-2-0")
    assert "SMT-D2" in _ids(_report(tmp_path, env))


# -- where it lives ----------------------------------------------------------

def test_the_walk_and_the_presence_rule_never_import_profiles():
    """The profile question is asked outside the matching path on purpose:
    if `engine` or `detect` depended on this module, the next
    reasonable-looking change is the one that makes matching read
    supplementals, which a published template would break
    (tests/test_detect.py).

    Read as imports and not as text. The first version searched the
    source for the word, and turned red the moment `engine.py`'s
    docstring said where the profile question is asked instead -- a guard
    that forbade documenting the design it was guarding.

    It is a statement about dependency direction and nothing more. A
    module reaching this one through `importlib` would pass here; what
    catches that is the comparison above, which is about behaviour.
    """
    for module in (engine, detect):
        tree = ast.parse(Path(inspect.getfile(module)).read_text("utf-8"))
        for node in ast.walk(tree):
            imported = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [alias.name for alias in node.names] + [node.module or ""]
            assert not [name for name in imported if "profiles" in name], \
                "%s imports profiles; matching must not depend on it" % module.__name__
