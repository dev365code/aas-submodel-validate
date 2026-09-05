"""What the 02003 template file cannot say, and the lints that watch it.

The generated table carries cardinality, kinds, value types and semantic
identifiers. It cannot say that a value declared `xs:date` is spelled
like one, that a File names a part the container holds, or that a
reference walks to something. Those are here.

Two of them are the same instruments 02004 has, pointed at the second
table: an identifier that nearly matches a row is diagnosed rather than
silently unmatched, and a reference type that differs from the
template's is noted. The engine already computed both for this table and
nothing was reading them.
"""
from __future__ import annotations

import copy
import json

import pytest

from aas_submodel_validate import runner
from builders import build_aasx, td_env
from test_hand_rules import FILE_VALUES

LOGO = "aasx/files/logo.png"
IMAGE = "aasx/files/front.png"


def _ids(tmp_path, env: dict):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return {finding.id: finding for finding in runner.run(path).findings}


def _general(env):
    return env["submodels"][0]["submodelElements"][0]


def _further(env):
    return env["submodels"][0]["submodelElements"][3]


def _classification(env):
    return env["submodels"][0]["submodelElements"][1]["value"][0]


# -- TD-D1: a date is spelled like a date ------------------------------------

def test_a_dotted_date_is_reported(tmp_path):
    env = copy.deepcopy(td_env())
    _further(env)["value"][1]["value"] = "15.03.2025"
    finding = _ids(tmp_path, env)["TD-D1"]
    assert "xs:date" in finding.fix


def test_a_calendar_date_is_accepted(tmp_path):
    assert "TD-D1" not in _ids(tmp_path, td_env())


def test_a_missing_valid_date_is_the_tables_business_not_this_rules(tmp_path):
    """Absence is the cardinality row's finding; this rule reads the
    spelling of a value that exists. Dropping the `is not None` guard
    makes every absent date a spelling complaint about `None`."""
    env = copy.deepcopy(td_env())
    _further(env)["value"] = [child for child in _further(env)["value"]
                              if child.get("idShort") != "ValidDate"]
    assert "TD-D1" not in _ids(tmp_path, env)



# -- TD-D2: a File names a part the container holds --------------------------

def _td_container(tmp_path, env, parts):
    return build_aasx(tmp_path / "p.aasx",
                      payload=json.dumps(env).encode("utf-8"), files=parts)


def _container_ids(path):
    return {finding.id: finding for finding in runner.run(path).findings}


def test_a_logo_the_archive_does_not_hold_is_reported(tmp_path):
    path = _td_container(tmp_path, td_env(), [(IMAGE, b"\x89PNG")])
    finding = _container_ids(path)["TD-D2"]
    assert "logo.png" in (finding.violation.detail or "")


def test_files_the_archive_holds_draw_nothing(tmp_path):
    path = _td_container(tmp_path, td_env(),
                         [(LOGO, b"\x89PNG"), (IMAGE, b"\x89PNG")])
    assert "TD-D2" not in _container_ids(path)


def test_without_a_container_the_file_rule_is_silent(tmp_path):
    """An environment JSON names files this rule cannot see. Silence
    there is honesty: the defect would be in packaging, and there is no
    packaging."""
    assert "TD-D2" not in _ids(tmp_path, td_env())


def test_a_file_the_archive_holds_needs_no_suppl_relationship(tmp_path):
    """This rule asks one question -- does the container hold the entry
    the value names -- and its remedy demanded a second one, an
    `aas-suppl` relationship declaring it. That is X4's question. A
    package with the parts and no relationships at all satisfies this
    rule, and the sentence a user reads sent them to fix something that
    was not broken."""
    path = build_aasx(tmp_path / "p.aasx",
                      payload=json.dumps(td_env()).encode("utf-8"),
                      files=[(LOGO, b"\x89PNG"), (IMAGE, b"\x89PNG")],
                      suppl_targets=[])
    assert "TD-D2" not in _container_ids(path)


# -- TD-D3: a reference walks to something -----------------------------------

def test_a_reference_to_a_property_area_that_is_not_there_is_reported(tmp_path):
    env = copy.deepcopy(td_env())
    reference = _classification(env)["value"][-1]
    assert reference["idShort"] == "ReferenceToTechnicalPropertyArea"
    reference["value"]["keys"][-1]["value"] = "7"
    finding = _ids(tmp_path, env)["TD-D3"]
    assert "7" in (finding.violation.detail or "")


def test_a_reference_that_resolves_draws_nothing(tmp_path):
    assert "TD-D3" not in _ids(tmp_path, td_env())


def test_a_reference_into_another_submodel_is_left_alone(tmp_path):
    """A reference out of this submodel is a promise this tool cannot
    check offline, and saying nothing is the honest answer."""
    env = copy.deepcopy(td_env())
    reference = _classification(env)["value"][-1]
    reference["value"]["keys"][0]["value"] = "urn:somewhere:else"
    assert "TD-D3" not in _ids(tmp_path, env)


# -- TDL1 / TDL2: the instruments 02004 has, pointed at this table ------------

def test_a_version_drifted_identifier_is_diagnosed(tmp_path):
    env = copy.deepcopy(td_env())
    _general(env)["value"][0]["semanticId"]["keys"][0]["value"] = "0173-1#02-AAO677#003"
    finding = _ids(tmp_path, env)["TDL1"]
    assert "0173-1#02-AAO677#004" in (finding.violation.detail or "")


def test_a_reference_type_that_differs_from_the_template_is_noted(tmp_path):
    env = copy.deepcopy(td_env())
    env["submodels"][0]["semanticId"]["type"] = "ExternalReference"
    env["submodels"][0]["semanticId"]["keys"][0]["type"] = "GlobalReference"
    finding = _ids(tmp_path, env)["TDL2"]
    assert "ModelReference" in (finding.violation.detail or "")


def test_the_golden_environment_draws_no_lint(tmp_path):
    ids = _ids(tmp_path, td_env())
    assert "TDL1" not in ids and "TDL2" not in ids


def test_a_date_with_a_trailing_newline_is_still_a_date(tmp_path):
    """`xs:date` carries `whiteSpace="collapse" fixed="true"` in the
    schema W3C publishes for the built-in types, so a conforming
    processor folds and trims before matching and this is the date it
    looks like.

    This asserted the opposite, on the reasoning that `$` matches before
    a final newline and an XML Schema processor would refuse the value.
    The first half is true of Python; the second is not true of XML
    Schema, and the two together made a MUST finding out of a conformant
    document. Read the standard, not the regex."""
    env = copy.deepcopy(td_env())
    _further(env)["value"][1]["value"] = "2025-03-15\n"
    assert "TD-D1" not in _ids(tmp_path, env)


def test_a_date_written_in_other_digits_is_not_a_date(tmp_path):
    """`\\d` matches every decimal digit Unicode knows, and int() reads
    them. xs:date is written in ASCII."""
    env = copy.deepcopy(td_env())
    _further(env)["value"][1]["value"] = "٢٠٢٥-٠٣-١٥"
    assert "TD-D1" in _ids(tmp_path, env)


def _find_with_parent(env, label):
    """The element and the list that holds it, so a twin lands where the
    table's row actually looks -- appended at the top level it matches no
    row and the walk never sees it."""
    out = []

    def walk(node, parent):
        if isinstance(node, dict):
            if node.get("idShort") == label:
                out.append((parent, node))
            for child in node.values():
                walk(child, None)
        elif isinstance(node, list):
            for child in node:
                walk(child, node)

    walk(env, None)
    ((parent, element),) = out
    assert parent is not None
    return parent, element


def _company_logo(env):
    return _find_with_parent(env, "CompanyLogo")[1]


def _area_reference(env):
    return _find_with_parent(env, "ReferenceToTechnicalPropertyArea")[1]


def test_conformant_file_shapes_leave_the_file_rule_silent(tmp_path):
    """Three values the guard exists to pass over -- no value at all, a
    blank one, an external URL -- inside a container, where the rule is
    live. None is a defect this rule owns: the empty ones are the
    cardinality table's business, and a URL is not a part name. The
    guard's terms each carry one of the three; losing `isinstance` is a
    crash, losing `strip` reports a blank as climbing out of the
    package, and losing `://` reports every external logo as a missing
    part."""
    for value in (None, "   ", "http://example.com/logo.png"):
        env = copy.deepcopy(td_env())
        logo = _company_logo(env)
        if value is None:
            logo.pop("value", None)
        else:
            logo["value"] = value
        path = _td_container(tmp_path, env, [(IMAGE, b"\x89PNG")])
        findings = _container_ids(path)
        offending = [f for f in findings.values()
                     if f.id == "TD-D2"
                     and "logo" in ((f.violation.detail or "") + f.violation.message)]
        assert not offending, (value, [f.violation.message for f in offending])
        assert not any("could not run" in f.violation.message
                       for f in findings.values()), value


def test_a_defect_after_a_skipped_file_is_still_reported(tmp_path):
    """Two CompanyLogos -- the count rule will mind, this one must not
    be distracted: the first is an external URL the guard passes over,
    and the second names a part the archive does not hold. Skipping is
    `continue`; a `break` loses every file after the first skip."""
    env = copy.deepcopy(td_env())
    parent, logo = _find_with_parent(env, "CompanyLogo")
    twin = copy.deepcopy(logo)
    logo["value"] = "http://example.com/logo.png"
    twin["value"] = "/aasx/files/ghost.png"
    parent.append(twin)
    path = _td_container(tmp_path, env, [(IMAGE, b"\x89PNG")])
    findings = [f for f in _container_ids(path).values()
                if f.id == "TD-D2" and "ghost" in (f.violation.detail or "")]
    assert findings, "the defect behind the skipped file went unreported"


def test_references_the_resolver_must_pass_over(tmp_path):
    """Three reference shapes TD-D3 deliberately does not judge: an
    ExternalReference (a promise about another AAS), a ModelReference
    with no keys at all (the metamodel's complaint, not this rule's),
    and a first key that is not this submodel even though its value
    matches. Each guard term carries one; the empty-keys case is a crash
    with the guard gone."""
    shapes = (
        {"type": "ExternalReference",
         "keys": [{"type": "Submodel", "value": "urn:example:technicaldata"},
                  {"type": "SubmodelElementList", "value": "Nowhere"}]},
        {"type": "ModelReference", "keys": []},
        {"type": "ModelReference",
         "keys": [{"type": "AssetAdministrationShell",
                   "value": "urn:example:technicaldata"},
                  {"type": "SubmodelElementList", "value": "Nowhere"}]},
    )
    for reference in shapes:
        env = copy.deepcopy(td_env())
        _area_reference(env)["value"] = reference
        findings = _ids(tmp_path, env)
        assert "TD-D3" not in findings, reference["type"]
        assert not any("could not run" in f.violation.message
                       for f in findings.values()), reference


def test_a_dangling_reference_after_a_foreign_one_is_still_reported(tmp_path):
    """Two references: the first points into another AAS and is passed
    over, the second dangles in this submodel and must still be found --
    the pass-over is a `continue`, and a `break` would end the walk at
    the first foreign reference."""
    env = copy.deepcopy(td_env())
    parent, reference = _find_with_parent(env, "ReferenceToTechnicalPropertyArea")
    twin = copy.deepcopy(reference)
    reference["value"] = {"type": "ExternalReference",
                          "keys": [{"type": "GlobalReference", "value": "urn:other"}]}
    twin["value"] = {"type": "ModelReference",
                     "keys": [{"type": "Submodel", "value": "urn:example:technicaldata"},
                              {"type": "SubmodelElementList", "value": "Nowhere"}]}
    parent.append(twin)
    finding = _ids(tmp_path, env)["TD-D3"]
    assert finding.violation.detail == "no element at key path Nowhere"



@pytest.mark.parametrize("value,drawn", FILE_VALUES)
def test_td_d2_reads_a_file_value_the_way_hd_d7_does(tmp_path, value, drawn):
    """The same table the handover rule is held to, asked here.

    The two rules were verbatim twins -- same three branches, same three
    sentences -- and the repair that replaced `"://" in value` with a
    scheme test reached one of them. Four of these values came back
    differently from the two rules for a day, in both directions, and
    both rules are MUST. They share a body now; this is what says so if
    somebody copies it apart again."""
    env = copy.deepcopy(td_env())
    # Both labels this rule reads. Setting one and leaving the other is
    # how the same test on the handover side first passed for the wrong
    # reason: the untouched File went on drawing the finding.
    placed = 0
    def stamp(node):
        nonlocal placed
        if isinstance(node, dict):
            if node.get("idShort") in ("CompanyLogo", "ImageFile"):
                node["value"] = value
                placed += 1
            for child in node.values():
                stamp(child)
        elif isinstance(node, list):
            for child in node:
                stamp(child)
    stamp(env)
    assert placed, "the fixture has no File for this rule to read"
    packed = build_aasx(tmp_path / "p.aasx",
                        payload=json.dumps(env).encode("utf-8"),
                        files=(("aasx/files/manual.pdf", b"%PDF-1.4"),))
    drawn_ids = {f.id for f in runner.run(packed).findings}
    assert ("TD-D2" in drawn_ids) is drawn, (
        "%r: expected TD-D2 %s, got %s"
        % (value, "drawn" if drawn else "silent", sorted(drawn_ids)))
