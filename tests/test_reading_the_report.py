"""Whether the report can be read by someone who has not read the source.

Every other test here asks whether the verdict is *right*. These ask
whether it is *legible* -- which is a different property, and the one a
first-time reader actually runs into. Someone who installed the tool and
typed `smtv --example` gets eighty-eight rows of terminal, four labels
nothing on the screen defines, and a last line that answers the question
they asked in a clause at the end of a hundred and seventy-nine
characters. They knew `fix:` meant something had to change; they could
not tell what.

The tests are written from what such a reader can do with the screen
alone. A README is not a defence: this project already had a table
explaining the four labels, and it is two thirds of the way down the
page, nested inside the section about wiring the tool into a build. The
gate that guarded it asserted the page explained the label -- which is
not the same claim as the reader knowing what it means, and the
difference is this file.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from aas_submodel_validate import rules, runner  # noqa: F401 - registers
from aas_submodel_validate.model import Finding, Report, Rule, Violation
from aas_submodel_validate.report import render

ROOT = Path(__file__).resolve().parents[1]


def _rule(prio="MUST", fix="do the right thing"):
    return Rule(id="T1", kind="template", prio=prio, title="test rule",
                spec="Some standard SS1", fn=lambda ctx: (), fix=fix)


def _with_findings():
    report = Report(path="machine-docs.json")
    report.findings = [
        Finding(_rule("MUST"), Violation("wrong", subject="urn:x",
                                         detail="saw 2", fix="mend it"))]
    report.checked = 123
    return report


def _example_run(*flags):
    """The run the front page sends a stranger to, in a real process.

    A subprocess and not `main()`: the thing under test includes the
    exit code, and an in-process call that returns an int is not the
    thing the reader's shell reported."""
    done = subprocess.run(
        [sys.executable, "-m", "aas_submodel_validate", "--example", *flags],
        capture_output=True, text=True, cwd=str(ROOT),
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"})
    return done.returncode, done.stdout


def test_the_screen_says_what_the_exit_code_says():
    """The one fact the reader wanted, and the one only `$?` held.

    `--example` and `--example -W` printed byte-identical screens and
    left by 0 and 1. Both are eighty-eight rows whose last line opens
    `0 error(s), 87 warning(s)` -- so the reader who asks "did my file
    pass" is shown the same eighty-eight rows either way, and the word
    that answers them exists nowhere on the screen.

    Warnings are the ordinary case, not an edge: the example this
    project ships to every newcomer has eighty-seven of them and no
    errors. `render` refuses the clean banner over a run with findings,
    correctly -- and the effect was that the run a stranger is sent to
    is the one run that can print no verdict at all."""
    plain_code, plain = _example_run()
    strict_code, strict = _example_run("-W")
    assert (plain_code, strict_code) == (0, 1), (plain_code, strict_code)
    assert plain != strict, \
        "the same screen for a run that passed and a run that failed"
    summary = plain.rstrip("\n").splitlines()[-1]
    assert summary.startswith("ok -- "), summary
    assert strict.rstrip("\n").splitlines()[-1].startswith("FAILED -- "), \
        strict.rstrip("\n").splitlines()[-1]


def test_the_verdict_word_is_the_exit_code_and_not_a_second_opinion():
    """Derived from what the caller decided, not recomputed beside it.

    `report.ok` is "no errors" and the exit code is that plus `-W` plus
    `--require-all-judged`. A verdict word computed from `report.ok`
    would agree with the exit code on the default flags and disagree on
    exactly the flags somebody reached for on purpose."""
    def summary(report, **kw):
        return render(report, **kw).splitlines()[-1]

    report = _with_findings()
    assert summary(report).startswith("FAILED -- ")
    report.findings = [Finding(_rule("SHOULD"), Violation("iffy"))]
    assert summary(report).startswith("ok -- ")
    assert summary(report, failed=True).startswith("FAILED -- ")
    assert summary(report, failed=False).startswith("ok -- ")


def test_the_screen_explains_every_label_it_prints():
    """The labels, where the reader meets them.

    Derived from the renderer rather than listed, because a hand-kept
    list is how the next label goes unexplained -- the same discipline
    as the page gate, asked of the screen instead of the document. The
    older gate could be green while the reader was stuck, and was."""
    source = (ROOT / "src" / "aas_submodel_validate" / "report.py").read_text("utf-8")
    labels = set(re.findall(r'"        (\w+)[: ]', source))
    assert labels, "the renderer prints no labelled lines any more"
    printed = render(_with_findings())
    for label in sorted(labels):
        assert "%s=" % label in printed, (
            "the report prints a %r line and the screen never says what it is"
            % label)


def test_the_key_is_printed_only_where_there_is_something_to_key():
    """A clean run has no labels on it, so it gets no legend."""
    clean = Report(path="clean.json")
    clean.checked = 123
    assert "at=" not in render(clean), render(clean)


def test_a_note_says_on_the_screen_that_it_is_not_a_defect():
    """`note` sits in the column `warning` and `error` sit in.

    Three columns of severity and a fourth word that is not one, at the
    same indent and the same weight -- so "here is something to change"
    and "here is something I did not look at" read alike. The `fix:`
    line is the real distinction and nothing says so."""
    report = _with_findings()
    report.notes = ["SMT-D1 (allowed): nothing matched a template table"]
    printed = render(report)
    assert "note    SMT-D1" in printed
    assert "note=" in printed, \
        "a note is printed and the screen never says a note is not a defect"


def test_the_summary_names_the_rules_it_says_were_not_asked():
    """"1 rule not asked" and no way to find out which.

    The JSON has carried the ids in `summary.rulesNotAsked` since they
    were introduced. The terminal said a rule went unasked, said why in
    the abstract, and named neither the rule nor the element -- so the
    reader is told something was skipped and handed nothing to look up.
    The example ships in this state: one rule, `HD-E38`."""
    report = _with_findings()
    report.not_asked = ["HD-E38"]
    printed = render(report)
    assert "HD-E38" in printed, printed.splitlines()[-1]


def test_the_summary_does_not_list_more_ids_than_a_line_can_hold():
    """A typo in one identifier silences eighteen rows, and eighteen ids
    inline is the wall this was meant to stop. Named up to a bound, then
    counted, with the place the whole list lives."""
    report = _with_findings()
    report.not_asked = ["HD-E%d" % n for n in range(18)]
    summary = render(report).splitlines()[-1]
    assert "HD-E0" in summary
    assert "HD-E17" not in summary, summary
    assert "-f json" in summary, summary


def test_the_screen_uses_no_word_only_this_project_has():
    """"an element matched no row of the template".

    `row` is not an AAS word and not an IDTA word. It is this project's
    name for a line of its own template table -- so a reader who goes
    and learns the standard still will not find it, which is worse than
    jargon they could look up. It reached the screen in the sentence a
    first-time reader was most likely to stop on."""
    report = _with_findings()
    report.not_asked = ["HD-E38"]
    report.notes = ["a note"]
    printed = render(report)
    assert not re.search(r"\brows?\b", printed), printed


def test_a_rule_that_fires_five_times_says_itself_once():
    """The wall, measured: ten findings on the bundled example, four
    rules, and every repeat identical but for `at`. One of them prints
    its message, its clause and a four-line remedy five times over,
    changing one path each time.

    Grouped, not folded -- nothing leaves the screen. The evidence, the
    clause and the remedy are the same sentence five times and are said
    once; the five places stay, one `at` line each."""
    report = Report(path="x.json")
    rule = _rule("SHOULD", fix="mend it")
    report.findings = [
        Finding(rule, Violation("same complaint", subject="A", detail="'released'")),
        Finding(rule, Violation("same complaint", subject="B", detail="'released'")),
        Finding(rule, Violation("same complaint", subject="C", detail="'released'")),
    ]
    printed = render(report).splitlines()
    assert printed.count("warning T1       same complaint") == 1, printed
    assert [line for line in printed if line.startswith("        at ")] == [
        "        at   A", "        at   B", "        at   C"], printed
    assert len([row for row in printed if row.startswith("        saw ")]) == 1, printed
    assert len([row for row in printed if row.startswith("        fix:")]) == 1, printed


def test_a_group_is_only_the_findings_that_are_actually_the_same():
    """Same rule, different evidence, is two findings and not one.

    `saw` is what lets a reader tell this finding from a similar one --
    collapsing two that differ there would print one of the two values
    and drop the other, which is the report lying about what it saw."""
    report = Report(path="x.json")
    rule = _rule("SHOULD", fix="mend it")
    report.findings = [
        Finding(rule, Violation("same complaint", subject="A", detail="'released'")),
        Finding(rule, Violation("same complaint", subject="B", detail="'draft'")),
    ]
    printed = render(report)
    assert printed.count("warning T1       same complaint") == 2, printed
    assert "'released'" in printed and "'draft'" in printed


def test_the_screen_still_accounts_for_every_finding_it_printed():
    """The arithmetic a reader can do, and that grouping could break.

    The summary counts 87 and the example shows four heads. That closes
    only because every grouped finding leaves exactly one `at` line
    behind -- so findings that carry no subject are never grouped, or
    five would silently become one and the screen would stop adding
    up."""
    report = Report(path="x.json")
    rule = _rule("SHOULD", fix="mend it")
    report.findings = [Finding(rule, Violation("no place given")) for _ in range(3)]
    printed = render(report).splitlines()
    assert printed.count("warning T1       no place given") == 3, printed


def test_grouping_does_not_reorder_the_report():
    """Adjacent findings only. The order is a promise made elsewhere --
    severity, then kind, then id -- and a grouping that gathered matches
    from anywhere in the list would quietly rewrite it."""
    report = Report(path="x.json")
    same = _rule("SHOULD", fix="mend it")
    other = _rule("MUST", fix="mend it")
    other = Rule(id="T0", kind="template", prio="MUST", title="t",
                 spec=None, fn=lambda ctx: (), fix="mend it")
    report.findings = [
        Finding(same, Violation("b", subject="A")),
        Finding(other, Violation("a", subject="B")),
        Finding(same, Violation("b", subject="C")),
    ]
    heads = [row for row in render(report).splitlines()
             if not row.startswith("        ")]
    assert heads[:3] == ["warning T1       b", "error   T0       a",
                         "warning T1       b"], heads


def test_no_rule_spends_the_private_word_on_a_reader():
    """The same question of every rule, not only of the summary.

    A rule's own `spec` is what a finding prints when the violation
    carries none, so it is reader-facing whether or not any input
    reaches it today -- and `BAT-R8`, the finding this project's front
    page is built around, said "each finding names the provision its own
    row cites". Checked over the whole registry rather than over one
    rendered report, because the report only shows the rules one input
    happened to draw."""
    from aas_submodel_validate.registry import all_rules
    guilty = {}
    for rule in all_rules():
        for field in ("title", "spec", "fix"):
            value = getattr(rule, field, None)
            if value and re.search(r"\brows?\b", str(value)):
                guilty["%s.%s" % (rule.id, field)] = str(value)
    assert not guilty, guilty


def test_the_front_page_teaches_the_labels_before_it_teaches_a_build():
    """Where the explanation sits on the page.

    The table explaining the four labels was inside `## Putting it in a
    build`, past the two thirds mark -- filed under wiring a pipeline,
    which is not what someone who has just run the tool once is
    reading."""
    readme = (ROOT / "README.md").read_text("utf-8")
    anatomy = readme.index("# Reading a finding")
    build = readme.index("## Putting it in a build")
    catches = readme.index("## What it catches")
    assert anatomy < build, \
        "the section that teaches a finding is filed under wiring a build"
    assert anatomy < catches, anatomy
