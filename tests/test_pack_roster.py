"""A pack installs the hand rules its table can answer, and says which.

The 02035-2 table has sixteen fewer rows than 02004's, so three of the
fourteen shared hand rules navigate to elements it does not have. Asking
a table for a row it has no name for raises `KeyError`, and
`runner.execute` turns that into a finding at the rule's own severity
reading "the rule itself could not run" -- a conformant battery passport
told to report a defect in the validator, at error severity for two of
them and warning for the other two.

So the count is not a claim in a design note; it is what these tests
measure. And the refusal runs both ways: a pack that omits a rule its
table could have answered is refused too.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from aas_submodel_validate import registry
from aas_submodel_validate.rules import dbp_tables, handover, hd_tables, td_tables

#: What the walk is asked for by name.
NAVIGATION = ("instances_of", "child_of", "children_of", "property_value")


def test_02004_answers_every_hand_rule():
    assert handover.answerable(hd_tables) == {
        suffix for suffix, *_rest in handover.ROSTER}
    assert len(handover.ROSTER) == 14


def test_02035_2_answers_eleven_of_the_fourteen():
    """Eleven, measured. D6 navigates StatusValue, D8 StatusSetDate, D9
    the four reference elements -- rows 02035-2 does not have."""
    answers = handover.answerable(dbp_tables)
    assert len(answers) == 11
    assert {suffix for suffix, *_r in handover.ROSTER} - answers == {"-D6", "-D8", "-D9"}


def test_a_pack_that_cannot_answer_a_rule_is_refused_at_import(monkeypatch):
    """Not a KeyError at validation time, in a report a user reads."""
    monkeypatch.setattr(registry, "_registry", {})
    with pytest.raises(SystemExit, match="StatusValue"):
        handover.install("PROBE", dbp_tables)


def test_a_pack_that_omits_a_rule_it_could_answer_is_refused_too(monkeypatch):
    """The direction the guards in this repository keep turning out to
    lack. A pack that quietly checks less than it could is the failure;
    `omit` is where somebody says the loss was meant."""
    monkeypatch.setattr(registry, "_registry", {})
    with pytest.raises(SystemExit, match="omits -D2"):
        handover.install("PROBE", hd_tables, omit=("-D2",))


def test_the_file_labels_come_from_the_table(monkeypatch):
    """D7 navigates the rows the template declares as Files. 02004 has
    two, 02035-2 has one -- naming them in the body would have crashed
    the second pack on the row that is not there."""
    assert handover._file_labels(hd_tables) == ("DigitalFile", "PreviewFile")
    assert handover._file_labels(dbp_tables) == ("DigitalFile",)
    assert handover._file_labels(td_tables) == ("CompanyLogo", "ImageFile")


def _navigated_labels():
    """Every string literal handed to a navigation function, by factory."""
    tree = ast.parse(Path(inspect.getfile(handover)).read_text("utf-8"))
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("_"):
            continue
        found, via_variable = set(), set()
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
                    and inner.func.id in NAVIGATION):
                for argument in inner.args:
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                        found.add(argument.value)
                    elif isinstance(argument, ast.Name):
                        via_variable.add(argument.id)
        # A body may walk a literal list of labels rather than name them
        # one at a time -- D9 does. The loop's own tuple is where those
        # labels are written down, and skipping it would leave the rule
        # with the widest reach the least examined.
        for inner in ast.walk(node):
            if (isinstance(inner, ast.For) and isinstance(inner.target, ast.Name)
                    and inner.target.id in via_variable
                    and isinstance(inner.iter, (ast.Tuple, ast.List))):
                found |= {e.value for e in inner.iter.elts
                          if isinstance(e, ast.Constant) and isinstance(e.value, str)}
        out[node.name] = (found, {c.func.id for c in ast.walk(node)
                                  if isinstance(c, ast.Call)
                                  and isinstance(c.func, ast.Name)})
    # A body that navigates through a helper navigates those labels too.
    # Without this the helper's three labels belong to no rule, and a
    # label added there would be declared by nobody.
    resolved = {}
    for name, (labels, calls) in out.items():
        reached = set(labels)
        for callee in calls:
            if callee in out:
                reached |= out[callee][0]
        resolved[name] = reached
    return {name: labels for name, labels in resolved.items() if labels}


def test_the_roster_declares_every_label_its_bodies_navigate():
    """`needs` is what `install` refuses on, so a body that reaches for a
    label the roster does not declare would slip past the refusal and
    crash on the table that lacks it. Read from the module's own AST
    rather than trusted."""
    navigated = _navigated_labels()
    by_factory = {entry[-1].__name__: entry for entry in handover.ROSTER}
    for name, labels in navigated.items():
        entry = by_factory.get(name)
        if entry is None:
            continue                      # a helper, not a rule body
        # D7 alone is allowed the table's File rows; granting them to
        # every body would let a label slipped into the shared helper
        # pass as if some rule had declared it. Measured: it did.
        declared = set(entry[6])
        if entry[0] == "-D7":
            declared |= set(handover._file_labels(hd_tables))
        assert labels <= declared, \
            "%s navigates %s, which the roster does not declare" % (
                name, sorted(labels - declared))


def test_every_roster_entry_has_a_body_the_ast_can_see():
    """The guard above is only worth something if it looks at all of them."""
    navigated = _navigated_labels()
    reached = {entry[-1].__name__ for entry in handover.ROSTER}
    #: Bodies that name no label, with the reason each names none.
    nameless = {
        "_l1": "reads the walk's idShort drift, not any row by name",
        "_l2": "reads the walk's near misses",
        "_l3": "reads the walk's reference-type drift",
        "_d7": "walks the table's own File rows, which is the point of it",
    }
    assert (reached - set(nameless)) <= set(navigated), \
        sorted((reached - set(nameless)) - set(navigated))
    assert set(nameless) <= reached, "a reason is given for a body that is gone"


def test_the_file_rule_names_no_file_in_its_own_body():
    """D7's reach has to come from the table, because 02004 has two File
    rows and 02035-2 has one. Naming them in the body reads identically
    on 02004 -- the literal and the table agree there -- so nothing else
    in this suite can see the difference until a second pack installs
    the rule. This can: the body may not spell a File label at all.
    """
    tree = ast.parse(Path(inspect.getfile(handover)).read_text("utf-8"))
    (body,) = [node for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef) and node.name == "_d7"]
    spelled = {node.value for node in ast.walk(body)
               if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert not spelled & set(handover._file_labels(hd_tables)), \
        "D7 spells a File label; its reach must come from the table"
