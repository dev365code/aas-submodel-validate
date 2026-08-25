"""A rule id is a contract: registered once, forever findable."""
import pytest

from aas_submodel_validate import registry
from aas_submodel_validate import rules as _rules  # noqa: F401 - registers
from aas_submodel_validate.model import Violation
from aas_submodel_validate.registry import all_rules


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


#: Every rule-id namespace this tool registers, and what asks the question.
#: A pack that starts registering adds a line; a pack that stops empties
#: one. Both are diffs somebody has to justify.
NAMESPACES = {
    "X": "the AASX/OPC container the submodel arrived in",
    "SMT-D": "the tool's own questions, belonging to no template",
    "HD-E": "IDTA 02004, generated from the template's rows",
    "HD-D": "IDTA 02004, what the template file cannot say",
    "HDL": "IDTA 02004, informational lints",
    "TD-E": "IDTA 02003, generated from the template's rows",
    "TD-D": "IDTA 02003, what the template file cannot say",
    "TDL": "IDTA 02003, informational lints",
}


def _namespace(rule_id):
    matches = [ns for ns in NAMESPACES if rule_id.startswith(ns)]
    return max(matches, key=len) if matches else None


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
