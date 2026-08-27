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
    dbp_env,
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
    assert "IDTA 02035-2" in finding.violation.detail
    assert "--profile 02035-2" in finding.fix, "the remedy names the flag first"


def test_the_notice_counts_everything_the_other_template_would_not_ask(tmp_path):
    """Twenty-one, not eleven. The first version of this notice named the
    rows 02004 requires and 02035-2 does not -- and said nothing about the
    sixteen elements 02035-2 has no row for at all, or the three hand
    rules whose elements it dropped. Those three leave no other trace: a
    StatusSetDate rule that was never installed is not a row anybody can
    look up. Measured against the tables and the roster."""
    absent, relaxed, hand = DBP.not_asked
    assert (len(absent), len(relaxed), len(hand)) == (16, 2, 3)
    report = _report(tmp_path, declaring_profile(hd_env(), _mark()))
    (finding,) = [f for f in report.findings if f.id == "SMT-D2"]
    assert "21" in finding.violation.detail


def test_the_notice_names_the_elements_a_conformant_battery_passport_is_faulted_for(tmp_path):
    """A file that is exactly what 02035-2 asks for draws six errors under
    02004, and the notice names the elements each of them is about -- so a
    reader can tell which of the findings above are the profile's
    disagreement rather than their own mistake."""
    env = hd_env()
    for row_id in UNCONDITIONAL:
        env = break_row(env, hd_tables.BY_ID[row_id], hd_tables)
    report = _report(tmp_path, declaring_profile(env, _mark()))
    errors = {f.id for f in report.findings if f.severity is Severity.ERROR}
    assert errors == set(UNCONDITIONAL)
    (finding,) = [f for f in report.findings if f.id == "SMT-D2"]
    for row_id in errors:
        assert hd_tables.BY_ID[row_id]["label"] in finding.violation.detail


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
    """The decision, written as a comparison rather than as a claim about
    one rule: for one file, marked and unmarked, the findings are the same
    set apart from SMT-D2 itself.

    The mark reports and does not choose (docs/divergences.md #30). It
    has precision 1.0 over everything published and recall nobody can
    measure, and letting it choose would silence 21 rule ids on a file
    that carries it wrongly, 18 of them turning exit 1 into exit 0.
    `--profile` chooses instead, in both directions, and the note names
    it. What this test refuses is the switch arriving by accident.

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
    """A file that is barely a submodel is faulted whichever table
    answers. When this was written, choosing the other table would have
    silenced 52 rules and left nothing in their place; there are 33 in
    their place now, and this is the fixture that says the substitution
    happened rather than the silence."""
    env = json.loads(env_json(hd_tables.TEMPLATE_SEMANTIC_ID))
    report = _report(tmp_path, declaring_profile(env, _mark()))
    assert "HD-E01" in _ids(report)
    assert not report.ok


def test_the_package_registers_the_rule_and_not_only_this_test(tmp_path):
    """`tests/test_profiles.py` imports the module, which registers the
    rule -- so the suite counts every rule whether or not the shipped
    package does. Dropping `profiles` from `rules/__init__.py` left the
    whole suite green and only `make exercised` red; the installed
    package would quietly lose the rule. This is the suite saying why."""
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


# -- what the notice says once a template can be chosen ----------------------

def _notice(tmp_path, env, profile=None):
    path = tmp_path / "n.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    found = [f for f in runner.run(path, profile=profile).findings if f.id == "SMT-D2"]
    return found[0] if found else None


def test_choosing_the_other_template_is_reported(tmp_path):
    """A switch nobody reports is the failure this pack is arranged
    around. The flag moves 52 rules out of the way and 33 into it; the
    report has to carry which."""
    finding = _notice(tmp_path, hd_env(), profile="02035-2")
    assert finding is not None
    assert "IDTA 02035-2" in finding.violation.message
    assert "--profile 02035-2" in finding.violation.message


def test_choosing_the_template_that_would_have_answered_anyway_is_still_reported(tmp_path):
    """An explicit `--profile 02004` picks the template that would have
    answered anyway, so nothing about the verdict changes -- and the
    report still records that somebody chose. A stored report cannot say
    which requirements produced it otherwise, and the README promises it
    says. Silence is for the run where there was no choice to make."""
    finding = _notice(tmp_path, hd_env(), profile="02004")
    assert finding is not None
    assert "--profile 02004" in finding.violation.message
    assert _notice(tmp_path, hd_env()) is None, "no flag, no mark, no choice"


def test_a_declaration_the_run_did_not_follow_is_reported(tmp_path):
    """The file said one thing and the tool judged by another. Without
    this the stored report cannot be told from a run where the file said
    nothing."""
    marked = declaring_profile(hd_env(), _mark())
    finding = _notice(tmp_path, marked, profile="02004")
    assert finding is not None
    assert "declares" in (finding.violation.detail or "")


def test_a_profile_that_chose_nothing_says_so(tmp_path):
    """`--profile` names a template. Pointed at a file no submodel of
    which answers to that template's identifier, it chooses nothing and
    the verdict is the one the run would have had anyway -- and somebody
    who passed the flag believes they validated by it. A run-level note,
    where `--allow-unmatched` already puts one."""
    path = tmp_path / "td.json"
    path.write_bytes(json.dumps(td_env()).encode("utf-8"))
    report = runner.run(path, profile="02035-2")
    assert any("chose nothing" in note for note in report.notes), report.notes
    assert not [f for f in report.findings if f.id == "SMT-D2"]
    assert runner.run(path).notes == [], "no flag, no note"


def test_a_profile_pair_never_silences_a_pack_outside_it(tmp_path):
    """A submodel may declare more than one identifier -- `candidate_values`
    collects every key of the reference, deliberately (divergences #4).
    When one of them belongs to a profile pair, the pair decides which of
    *its* two tables answers. It has nothing to say about anybody else's.

    It used to say `False` to all of them. A Technical Data submodel that
    also declared 02004's anchor lost the entire 02003 pack -- a real
    TD-E01 vanished -- and SMT-D2 stayed silent, because from the
    profile's own point of view the default had answered and nothing was
    declared. That is the verdict changing without the sentence that
    explains it, which this arrangement exists to make impossible.
    """
    from aas_submodel_validate.rules import td_tables
    broken = break_row(td_env(), td_tables.BY_LABEL["GeneralInformation"], td_tables)
    assert "TD-E01" in _ids(_report(tmp_path, broken, "plain.json"))

    stacked = copy.deepcopy(broken)
    stacked["submodels"][0]["semanticId"]["keys"].append(
        {"type": "Submodel", "value": hd_tables.TEMPLATE_SEMANTIC_ID})
    assert "TD-E01" in _ids(_report(tmp_path, stacked, "stacked.json")), \
        "a profile pair silenced a pack it has nothing to do with"


def test_one_pair_today_and_what_a_second_one_has_to_change():
    """`Selection.chosen` returns on the first pair a submodel belongs to.

    With one pair that is the only pair, so the shortcut is invisible.
    IDTA 02023 and IDTA 02035-3 publish the same collision -- one
    CarbonFootprint identifier, two templates (`PROFILES`' own comment
    says so) -- and the slice that adds them steps here: a submodel
    declaring both pairs' default anchors would have the second pair
    decided for it by the first, `--profile` for the second silently
    ignored, and nothing said. That is the shape of the defect this
    module was already fixed for once, at `answers`.

    So this counts. When it goes red, `chosen` has to answer per pair
    rather than per submodel, and `SMT-D2` has to be able to speak twice
    about one submodel.
    """
    assert len(profiles.PROFILES) == 1, (
        "a second profile pair arrived; `chosen` still returns on the first "
        "match and `SMT-D2` still yields once per submodel")


def test_a_profile_reaches_past_a_submodel_that_is_not_in_the_pair(tmp_path):
    """Every fixture for the profile decision holds exactly one submodel,
    and an environment may hold several of different kinds.

    Two decisions ride on walking all of them. `SMT-D2` reports the
    choice for each submodel that is in a pair, and stopping at the first
    one that is not leaves a run that changed six verdicts saying nothing
    about why. And the run-level note -- "named a template no submodel
    here answers to" -- asks whether *any* submodel answered; asking
    whether *all* did would print it on a run where one did, which is a
    sentence telling the reader their flag did nothing while it was
    removing the errors in front of them.

    A Technical Data submodel first, a battery passport second: with
    `--profile 02035-2` the second is judged by 02035-2 and comes back
    clean, where 02004 finds six."""
    env = copy.deepcopy(td_env())
    battery = copy.deepcopy(dbp_env()["submodels"][0])
    battery["id"] = "urn:example:battery"
    env["submodels"].append(battery)
    path = tmp_path / "two.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))

    without = runner.run(path)
    assert not without.ok, "the battery passport has to be faulted under 02004"

    report = runner.run(path, profile="02035-2")
    assert report.ok
    assert "SMT-D2" in {finding.id for finding in report.findings}, \
        "the choice was made and the report did not say so"
    assert report.notes == [], report.notes
