"""A pack installs the hand rules its table can answer, and says which.

The 02035-2 table has sixteen fewer rows than 02004's, so three of the
fourteen shared hand rules navigate to elements it does not have. Asking
a table for a row it has no name for raises `KeyError`, and
`runner.execute` turns that into a finding at the rule's own severity
reading "the rule itself could not run" -- a conformant battery passport
told to report a defect in the validator, at error severity for D8 and
warning for D6 and D9.

So the count is not a claim in a design note; it is what these tests
measure. And the refusal runs both ways: a pack that omits a rule its
table could have answered is refused too.
"""
from __future__ import annotations

import ast
import inspect
import types
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
    with pytest.raises(SystemExit) as refused:
        handover.install("PROBE", dbp_tables)
    assert "StatusValue" in str(refused.value)
    assert "dbp_tables" in str(refused.value), str(refused.value)


def test_a_pack_that_omits_a_rule_it_could_answer_is_refused_too(monkeypatch):
    """The direction the guards in this repository keep turning out to
    lack. A pack that quietly checks less than it could is the failure;
    `omit` is where somebody says the loss was meant."""
    monkeypatch.setattr(registry, "_registry", {})
    with pytest.raises(SystemExit) as refused:
        handover.install("PROBE", hd_tables, omit=("-D2",))
    #: The name of the table is half the message: it is what tells a
    #: reader which of the two packs has the row that makes the omission
    #: a loss. Matching only "omits -D2" left that half unchecked.
    assert "omits -D2" in str(refused.value)
    assert "hd_tables" in str(refused.value), str(refused.value)


def test_a_rule_title_names_the_rows_the_table_actually_has():
    """`install` substitutes `%s` in a title with the table's own File
    rows, and until this test nothing read a title at all.

    That the substitution happens is not cosmetic here: the two packs get
    different sentences from one row, which is the whole reason the row
    is written with a placeholder rather than the names. Turn the
    substitution off and every reader of `HD-D7` is told a rule called
    "files named by %s exist in the container" failed -- a format string
    in a report, and one that no longer says which elements were read.
    """
    hd_title = registry._registry["HD-D7"].title
    dbp_title = registry._registry["DBP2-D7"].title
    assert hd_title == "files named by DigitalFile/PreviewFile exist in the container"
    assert dbp_title == "files named by DigitalFile exist in the container"
    for rule_id, rule in registry._registry.items():
        assert "%s" not in rule.title, (
            "%s reached a reader with an unsubstituted placeholder in its "
            "title: %r" % (rule_id, rule.title))


def test_an_inherited_rule_says_whose_requirement_it_is_carrying():
    """02035-2 declares 02004's submodel identifier and asks for
    something different (divergences #26), and eleven of these rules are
    installed for it on the strength of the row overlap that entry
    measures. A reader who sees `DBP2-D7` cite "IDTA 02004-2-0 §2.8"
    and nothing else has been shown a clause from a different document
    with no sentence saying why it applies here.

    `install` appends that sentence, and nothing read it. Suppress the
    appending and every 02035-2 spec still names only 02004 -- the
    verdict unchanged, the reason for it gone. This project's rule is
    that a verdict cannot move without the sentence explaining it moving
    too; this is the same rule pointed the other way, at a sentence that
    is doing the explaining for a verdict that did not move.
    """
    inherited = registry._registry["DBP2-D7"].spec
    assert inherited.endswith(
        "; IDTA 02035-2 1.0 inherits it (docs/divergences.md #26)"), inherited
    assert inherited.startswith(registry._registry["HD-D7"].spec), (
        "the inherited spec should be 02004's own, with the citation added")
    assert "inherits" not in (registry._registry["HD-D7"].spec or ""), (
        "02004 inherits nothing; the pack that owns a rule should not say "
        "it borrowed it")
    #: Read out of the roster rather than matched by prefix. Five of
    #: these suffixes are spelled without the dash -- `HDL4`, not
    #: `HD-L4` -- so a prefix of "DBP2-L" checks none of them and stays
    #: green on the six it does reach, which is the same half-checked
    #: shape the two guards below were in.
    borrowed = ["DBP2" + suffix for suffix, *_rest in handover.ROSTER
                if "DBP2" + suffix in registry._registry]
    assert len(borrowed) == 11, borrowed
    for rule_id in borrowed:
        assert "inherits it" in (registry._registry[rule_id].spec or ""), (
            "%s is installed for 02035-2 and does not say whose requirement "
            "it carries" % rule_id)


def test_a_pack_that_omits_a_name_this_module_does_not_have_is_refused(monkeypatch):
    """The other direction of `omit`, and the one nothing asked for.

    The two guards above refuse a pack that cannot answer a rule and a
    pack that omits one it could answer. Between them sits a third: a
    name in `omit` that is no rule at all. Without it a typo omits
    nothing and is not a loss anybody said was meant -- `omit` is the one
    place in this module where somebody writes down that a check is
    deliberately not run, and a line there that names nothing is a
    sentence with no subject.
    """
    monkeypatch.setattr(registry, "_registry", {})
    with pytest.raises(SystemExit) as refused:
        handover.install("PROBE", hd_tables, omit=("-D99",))
    assert "-D99" in str(refused.value), str(refused.value)


def test_a_table_with_no_file_rows_does_not_claim_the_file_rule(monkeypatch):
    """`-D7` is the one rule whose labels are not in its `needs`: it
    navigates whatever rows the table declares as Files, so a table with
    none can no more answer it than a table missing a named row can. The
    discard that says so was never measured, because all three real
    tables have File rows -- 02004 two, 02035-2 one, 02003 two.

    `answerable` is a function of the table and nothing else, so the
    missing case can simply be built: 02004's rows with the File ones
    taken out. Both halves are asserted, since a discard that fired
    always would be just as wrong and just as green.
    """
    #: `BY_LABEL` is left whole on purpose. Every other rule stays
    #: answerable, so the only thing that can move the result is the File
    #: rows, and the refusal below has to be about D7 rather than about
    #: whichever rule a narrower table happened to lose first.
    fileless = types.SimpleNamespace(
        __name__="tests.fileless_tables",
        ROWS=[row for row in hd_tables.ROWS if row["kind"] != "File"],
        BY_LABEL=hd_tables.BY_LABEL)
    assert handover._file_labels(hd_tables) == ("DigitalFile", "PreviewFile")
    assert handover._file_labels(fileless) == ()
    assert "-D7" in handover.answerable(hd_tables)
    assert "-D7" not in handover.answerable(fileless)
    #: Everything else it could answer, it still answers -- the discard
    #: takes one rule away and not the roster.
    assert (handover.answerable(hd_tables) - handover.answerable(fileless)
            == {"-D7"})

    monkeypatch.setattr(registry, "_registry", {})
    with pytest.raises(SystemExit) as refused:
        handover.install("PROBE", fileless)
    #: The remedy has to name something. `needs` is empty for this rule,
    #: so the list of missing labels is empty too, and without the
    #: fallback the sentence reads "navigates , which ...".
    assert "a File row" in str(refused.value), str(refused.value)
    assert "fileless_tables" in str(refused.value), str(refused.value)


def test_the_file_labels_come_from_the_table(monkeypatch):
    """D7 navigates the rows the template declares as Files. 02004 has
    two, 02035-2 has one -- naming them in the body would have crashed
    the second pack on the row that is not there."""
    assert handover._file_labels(hd_tables) == ("DigitalFile", "PreviewFile")
    assert handover._file_labels(dbp_tables) == ("DigitalFile",)
    assert handover._file_labels(td_tables) == ("CompanyLogo", "ImageFile")


def _navigation_call(node):
    """Is this call one of the walk's navigation functions?

    Both spellings: `instances_of(...)` and `engine.instances_of(...)`.
    The first version matched only the bare name, and an attribute call
    walked straight past the guard.
    """
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name):
        return node.func.id in NAVIGATION
    return isinstance(node.func, ast.Attribute) and node.func.attr in NAVIGATION


def _navigated_labels():
    """Every label handed to a navigation function, by function.

    Labels must be literals -- a name, a module constant or an f-string
    would put the label somewhere the roster cannot be checked against,
    and `test_every_label_reaches_the_walk_as_a_literal` refuses that
    separately. Helpers are folded into their callers to a fixpoint: one
    round of folding let a two-step chain hide a label, which is the
    shape the roster exists to catch.
    """
    tree = ast.parse(Path(inspect.getfile(handover)).read_text("utf-8"))
    direct, calls = {}, {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        found = set()
        called = set()
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call):
                if isinstance(inner.func, ast.Name):
                    called.add(inner.func.id)
                elif isinstance(inner.func, ast.Attribute):
                    called.add(inner.func.attr)
            if not _navigation_call(inner):
                continue
            for argument in inner.args:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    found.add(argument.value)
                elif isinstance(argument, ast.Name):
                    for loop in ast.walk(node):
                        if (isinstance(loop, ast.For) and isinstance(loop.target, ast.Name)
                                and loop.target.id == argument.id
                                and isinstance(loop.iter, (ast.Tuple, ast.List))):
                            found |= {e.value for e in loop.iter.elts
                                      if isinstance(e, ast.Constant)
                                      and isinstance(e.value, str)}
        direct[node.name], calls[node.name] = found, called
    resolved = dict(direct)
    for _round in range(len(direct) + 1):        # fixpoint, not one hop
        changed = False
        for name, callees in calls.items():
            reached = set(resolved[name])
            for callee in callees:
                reached |= resolved.get(callee, set())
            if reached != resolved[name]:
                resolved[name], changed = reached, True
        if not changed:
            break
    return {name: labels for name, labels in resolved.items() if labels}


def test_every_label_reaches_the_walk_as_a_literal():
    """A label that arrives as a name is a label the roster cannot be
    checked against, so the check is that none does. Measured: a module
    constant and an `engine.`-qualified call each carried an undeclared
    label past the first version of this file with every gate green."""
    tree = ast.parse(Path(inspect.getfile(handover)).read_text("utf-8"))
    loop_variables = {loop.target.id for loop in ast.walk(tree)
                      if isinstance(loop, ast.For) and isinstance(loop.target, ast.Name)
                      and isinstance(loop.iter, (ast.Tuple, ast.List))}
    for node in ast.walk(tree):
        if not _navigation_call(node):
            continue
        for argument in node.args[1:]:
            if isinstance(argument, ast.Constant) or (
                    isinstance(argument, ast.Name)
                    and argument.id in loop_variables | {"tables", "label"}):
                continue
            if isinstance(argument, ast.Name) and argument.id.isupper():
                raise AssertionError(
                    "a navigation label comes from %s; write it out so the "
                    "roster can be checked against it" % argument.id)


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


def test_no_rule_module_reaches_past_the_reader_into_aas_core3():
    """Three modules may import the library and none of them is a rule.

    `loader.py` turns bytes into a model and `runner.py` relays the
    metamodel channel: reading and relaying *are* the dependency.
    `upstream.py` is the seam for everything else. A rule asks questions
    about a model this project already has, so a rule importing the
    library is a layer boundary crossed for the convenience of one call
    -- and `aas_core3` is pinned `>=1.1.4` with its own CI stopping at
    Python 3.12, so the day a 2.x renames something, every direct import
    is a separate repair in a separate file.

    Read out of the source rather than out of `sys.modules`: an import
    that runs only on a branch the fixtures do not take is still an
    import.
    """
    import ast
    from pathlib import Path

    allowed = {"loader.py", "runner.py", "upstream.py"}
    package = Path(__file__).resolve().parents[1] / "src/aas_submodel_validate"
    offenders = []
    for source in sorted(package.rglob("*.py")):
        if source.name in allowed:
            continue
        tree = ast.parse(source.read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name == "aas_core3" or name.startswith("aas_core3."):
                    offenders.append("%s:%d imports %s"
                                     % (source.relative_to(package), node.lineno, name))
    assert not offenders, offenders

    # And the seam is not empty: a boundary nothing crosses is a
    # boundary nobody drew.
    from aas_submodel_validate import upstream

    assert upstream.is_english_language_tag("en")
    assert not upstream.is_english_language_tag("de")
    assert not upstream.is_multi_language_property(object())
