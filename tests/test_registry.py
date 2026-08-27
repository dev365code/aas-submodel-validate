"""A rule id is a contract: registered once, forever findable."""
import re

import pytest

from aas_submodel_validate import registry
from aas_submodel_validate import rules as _rules  # noqa: F401 - registers
from aas_submodel_validate.model import KINDS, Severity, Violation
from aas_submodel_validate.registry import all_rules
from aas_submodel_validate.runner import _meta_rule


def test_registration_and_lookup(monkeypatch):
    monkeypatch.setattr(registry, "_registry", {})

    @registry.rule("Z1", kind="container", prio="MUST", title="a test rule",
                   fix="mend it")
    def z1(ctx):
        yield Violation("broken")

    (rule,) = registry.all_rules()
    assert (rule.id, rule.kind, rule.fix) == ("Z1", "container", "mend it")


def test_a_duplicate_id_is_refused(monkeypatch):
    monkeypatch.setattr(registry, "_registry", {})

    @registry.rule("Z1", kind="container", prio="MUST", title="first", fix="f")
    def one(ctx):
        return ()

    with pytest.raises(ValueError, match="Z1"):
        @registry.rule("Z1", kind="container", prio="MUST", title="second", fix="f")
        def two(ctx):
            return ()


def test_every_registered_rule_names_its_remedy(monkeypatch):
    """A validator that names a defect without naming the remedy has told
    you something is wrong and left you the expertise. Refused at the
    registration boundary, not by a later audit."""
    monkeypatch.setattr(registry, "_registry", {})
    with pytest.raises(ValueError, match="fix"):
        @registry.rule("Z2", kind="container", prio="MUST", title="no remedy")
        def bad(ctx):
            return ()


def test_a_kind_the_report_cannot_read_is_refused(monkeypatch):
    """`kind` reaches two table lookups and a published field. The
    reading order's lookup used to fall back, so a rule registered as
    `tempalte` sorted where lints sort -- into the middle of the channels
    a reader is scanning rather than beside the other template findings
    -- and the JSON report carried the typo out to whoever reads `kind`.
    Nothing anywhere said so."""
    monkeypatch.setattr(registry, "_registry", {})
    with pytest.raises(ValueError, match="tempalte"):
        @registry.rule("Z3", kind="tempalte", prio="MUST", title="a typo", fix="f")
        def bad(ctx):
            return ()


def test_a_priority_that_scores_as_nothing_is_refused(monkeypatch):
    """Worse than the kind, because it moves the verdict: severity is
    looked up from `prio`, and the lookup fell back to *warning*. A MUST
    typed `MSUT` stopped counting as an error, so the file it condemned
    came back `ok` and the run exited 0 -- a validator silently agreeing
    with a document it had just found a MUST violation in."""
    monkeypatch.setattr(registry, "_registry", {})
    with pytest.raises(ValueError, match="MSUT"):
        @registry.rule("Z4", kind="template", prio="MSUT", title="a typo", fix="f")
        def bad(ctx):
            return ()


def test_the_gate_admits_every_kind_the_vocabulary_names(monkeypatch):
    """A gate that refused a legitimate kind would be found by whoever
    added the rule, loudly; asserted anyway, because the cost of finding
    it that way is somebody's afternoon."""
    monkeypatch.setattr(registry, "_registry", {})
    for kind in KINDS:
        @registry.rule("Z-%s" % kind, kind=kind, prio="MUST", title=kind, fix="f")
        def fine(ctx):
            return ()
    assert len(registry.all_rules()) == len(KINDS)


#: The one kind no rule registers. The metamodel channel is relayed from
#: aas-core3.0 and built by hand in `runner`, deliberately outside the
#: registry, and this project re-implements no AASd constraint -- so a
#: registered rule wearing `meta` would be that promise breaking.
UNREGISTERED_KINDS = {"meta"}


def test_every_kind_in_the_vocabulary_has_a_user():
    """The other direction, and the one that needed writing.

    The test this replaced emptied the registry, registered one rule per
    kind and then asserted that the kinds it had just registered were the
    kinds in the list. It could not fail. A fifth kind added to `KINDS`
    and used by nothing passed it, which is exactly the case its
    docstring named.

    Asked of the real registry, so the vocabulary cannot grow a word
    nobody says, and `meta` cannot quietly acquire a registered rule."""
    registered = {rule.kind for rule in all_rules()}
    assert registered, "nothing registered at all -- this test proves nothing"
    assert registered <= set(KINDS), "a rule wears a kind the report cannot read"
    assert set(KINDS) - registered == UNREGISTERED_KINDS
    assert _meta_rule(strict=False).kind in UNREGISTERED_KINDS


#: What a rule's priority decides is whether a build stops. `MUST` is an
#: error and sets the exit code; `SHOULD` and `MAY` do not. Both
#: directions are one word away and both are observable:
#:
#: - `MUST` -> `SHOULD` finds the violation and exits 0, which is a
#:   conformance tool agreeing with a file it has just failed.
#: - `SHOULD` -> `MUST` fails a file that was conformant.
#:
#: Measured before this list existed: the *promotions* were caught, and
#: only because the official published example draws those warnings and
#: is pinned as `ok`. The *demotions* were not caught at all -- every
#: fixture that fires a rule asserts its id and never its severity. The
#: direction this project calls worst was the one accidentally guarded.
#:
#: Read down the columns rather than the rows: MUST is what the template
#: obliges (the mandatory classification, its English name, its class
#: from the published twelve, files that exist, dates that are dates) and
#: what leaves nothing judged at all (X1-X3, X5, SMT-D1). SHOULD is
#: interoperability and the readings this project prefers without
#: insisting -- a PDF/A rendition, a primary identifier, the status
#: vocabulary, references that resolve, near-misses, duplicates, the
#: canonical spelling, declared supplementary parts. MAY is tidiness
#: alone: idShort patterns, reference types, and the sentence naming
#: which of two templates answered.
MUST_RULES = {
    "DBP2-D2", "DBP2-D3", "DBP2-D4", "DBP2-D7",
    "HD-D2", "HD-D3", "HD-D4", "HD-D7", "HD-D8",
    "SMT-D1", "TD-D1", "TD-D2", "X1", "X2", "X3", "X5",
}
SHOULD_RULES = {
    "DBP2-D5", "DBP2-D10", "DBP2L2", "DBP2L4", "DBP2L5",
    "HD-D5", "HD-D6", "HD-D9", "HD-D10", "HDL2", "HDL4", "HDL5",
    "TD-D3", "TDL1", "X4",
}
MAY_RULES = {"DBP2L1", "DBP2L3", "HDL1", "HDL3", "SMT-D2", "TDL2"}

#: The generated rules are not listed one by one: a row's rule reports a
#: cardinality the vendored template states, so all of them are `MUST`
#: and the byte-compare gate holds the table they come from. What is
#: asserted is that none of them has drifted off it.
GENERATED_ID = re.compile(r"^(HD|TD|DBP2)-E\d\d$")


def test_every_generated_rule_stops_a_build():
    """A generated row says what the template obliges, so a row's rule
    failing is a file failing. One of them at `SHOULD` would report a
    cardinality the template states and let the build through."""
    generated = [rule for rule in all_rules() if GENERATED_ID.match(rule.id)]
    assert len(generated) == 86
    assert {rule.prio for rule in generated} == {"MUST"}


def test_the_hand_rules_have_the_severities_that_were_decided():
    """Every hand-written rule, in the column somebody put it in.

    Both directions matter and neither was held: promotions only by
    accident, demotions not at all."""
    hand = [rule for rule in all_rules() if not GENERATED_ID.match(rule.id)]
    assert len(hand) == len(MUST_RULES | SHOULD_RULES | MAY_RULES)
    assert {r.id for r in hand if r.severity is Severity.ERROR} == MUST_RULES
    assert {r.id for r in hand if r.severity is Severity.WARNING} == SHOULD_RULES
    assert {r.id for r in hand if r.severity is Severity.INFO} == MAY_RULES


#: Every rule-id namespace this tool registers, as the whole shape of an
#: id rather than a prefix, and what asks the question. A pack that starts
#: registering adds a line; a pack that stops empties one. Both are diffs
#: somebody has to justify.
#:
#: Whole shapes because a prefix is a wildcard: `"X"` admitted `XT-E01`
#: and `XYZ99`, so an entire pack installed under the letter X passed the
#: census as container rules.
NAMESPACES = {
    r"X\d+": "the AASX/OPC container the submodel arrived in",
    r"SMT-D\d+": "the tool's own questions, belonging to no template",
    r"HD-E\d\d": "IDTA 02004, generated from the template's rows",
    r"HD-D\d+": "IDTA 02004, what the template file cannot say",
    r"HDL\d+": "IDTA 02004, informational lints",
    r"TD-E\d\d": "IDTA 02003, generated from the template's rows",
    r"TD-D\d+": "IDTA 02003, what the template file cannot say",
    r"TDL\d+": "IDTA 02003, informational lints",
    r"DBP2-E\d\d": "IDTA 02035-2, generated from the template's rows",
    r"DBP2-D\d+": "IDTA 02035-2, 02004's hand rules over 02035-2's table",
    r"DBP2L\d+": "IDTA 02035-2, informational lints",
}


def _namespace(rule_id):
    for pattern in NAMESPACES:
        if re.fullmatch(pattern, rule_id):
            return pattern
    return None


def test_every_registered_id_belongs_to_a_declared_namespace():
    """This replaced a guard that said "no rule id starts with DBP-",
    written to hold the boundary of the slice that vendored IDTA 02035-2's
    table without judging by it. That guard could not see the prefix being
    renamed -- it stayed green when `DBP-E` became `DBP2-E` -- and it could
    not see any other pack arriving either. A census can see both."""
    for rule in all_rules():
        assert _namespace(rule.id), \
            "%s belongs to no declared namespace; declare it or rename it" % rule.id


def test_every_declared_namespace_has_at_least_one_rule():
    """The other direction, which the guard it replaced did not have: a
    pack that quietly stops registering leaves its line here, and the
    line is what says the loss was deliberate."""
    registered = [rule.id for rule in all_rules()]
    assert registered, "nothing registered at all -- this test proves nothing"
    for namespace in NAMESPACES:
        assert [rule_id for rule_id in registered
                if _namespace(rule_id) == namespace], \
            "%s is declared and empty" % namespace
