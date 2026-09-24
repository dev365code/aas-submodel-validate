"""What a finding costs to fix, and what its subject names.

Two attributes beside the severity a rule already carries. They answer
different questions and neither answers the other's: severity is how
loudly a defect is reported, fixability is what it would take to repair
it, and a file can hold a loud defect nobody can repair (a missing
original) beside a quiet one that is repaired by rewriting a string.

Every grade here is pinned to an input that produces it, because the
first version graded by message: "expects one, found none" was a 5 --
the content is not in this input -- on a file whose missing element sat
one key away under a drifted identifier, and a File value naming a part
the package holds under another folder was told its bytes were
nowhere. A grade is a claim about the input, and only what the reader
looked at can back it.

`path` is the third: what `subject` names, as a closed set of steps. It
is per finding for the same reason the grade is -- one rule's subject
can be the file the caller gave, or a part inside it -- and a route
fixed per rule said "part" of a bare JSON document's own path.
"""
from __future__ import annotations

import copy
import json
import re
import zlib
from pathlib import Path

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.model import ROUTES, Rule, Violation
from aas_submodel_validate.registry import all_rules
from builders import _sid, build_aasx, corrupt_part, dn_env, env_json, hd_env, pcf_env

SCHEMA = Path(__file__).resolve().parents[1] / "docs" / "report-schema.md"


def _run(tmp_path, env, name="input", aasx=False, files=(), **kwargs):
    path = tmp_path / (name + (".aasx" if aasx else ".json"))
    payload = env if isinstance(env, bytes) else json.dumps(env).encode()
    if aasx:
        build_aasx(str(path), payload, files=files)
    else:
        path.write_bytes(payload)
    return json.loads(json.dumps(runner.run(str(path), **kwargs).as_dict()))


def _only(document, rule_id):
    found = [f for f in document["findings"] if f["rule"] == rule_id]
    assert len(found) == 1, (rule_id, [f["rule"] for f in document["findings"]])
    return found[0]


def _version(env):
    """The one DocumentVersion of the golden Handover fixture."""
    return env["submodels"][0]["submodelElements"][0]["value"][0]["value"][2]["value"][0]


def _named(scope, id_short):
    return next(e for e in scope["value"] if e.get("idShort") == id_short)


# -- the boundary -------------------------------------------------------------

def test_every_rule_says_what_its_subject_names():
    """Declared, not defaulted: an empty route is legal on a `Rule` only
    for one written for a test and for the relayed channel, so a
    registered rule with none is one somebody forgot."""
    missing = [rule.id for rule in all_rules() if not rule.path]
    assert not missing, missing
    assert all(rule.path in ROUTES for rule in all_rules())


def test_the_routes_are_the_ones_the_schema_page_names():
    """The page lists the routes a consumer can switch on. A route added
    in code and not there -- or the other way -- is a report the page
    does not describe."""
    # The finding's `path`, not the report's, which is the input path
    # and a row further up the same page.
    row = next(line for line in SCHEMA.read_text("utf-8").splitlines()
               if line.startswith("| `path` | array of string |"))
    named = {tuple(re.findall(r'"(\w+)"', listed))
             for listed in re.findall(r"`\[([^\]]*)\]`", row)}
    assert named == set(ROUTES), (sorted(named), sorted(ROUTES))


@pytest.mark.parametrize("grade, reason", [
    (2, None),                 # a number nobody can check
    (2, ""),
    (None, "because"),         # a reason for no claim at all
    (0, "because"), (6, "because"), (-1, "because"),
    ("5", "because"), (2.0, "because"), (True, "because"),
])
def test_a_grade_is_a_whole_step_with_its_reason_or_nothing(grade, reason):
    """Refused where the violation is built, which is where every grade
    this package gives is set. The first version checked the rule's
    grade and not the violation's, and every grade it actually gave was
    a violation's: `Violation('x', fixability=2)` went out with a null
    reason, and `'5'` and `9` went out as given. `True` and `2.0`
    compare equal to steps of the scale and are not steps of it."""
    with pytest.raises(ValueError):
        Violation("x", fixability=grade, fixability_why=reason)


def test_an_unknown_step_is_refused_on_a_violation_as_on_a_rule():
    with pytest.raises(ValueError):
        Violation("x", subject="a/b", path=("document", "shell"))
    with pytest.raises(ValueError):
        Rule(id="T-1", kind="template", prio="MUST", title="t", spec=None,
             fn=lambda ctx: (), fix="do it", path=("document", "shell"))


def test_the_positional_fields_a_caller_had_keep_their_places():
    """The new fields go after `severity`. Inserted before it, a caller
    passing a severity as the sixth positional argument set a grade."""
    names = list(Violation.__dataclass_fields__)
    assert names[:6] == ["message", "subject", "detail", "fix", "spec",
                         "severity"], names


def test_the_reason_is_bounded_like_every_other_text_field():
    long = "x" * 5000
    kept = Violation("x", fixability=5, fixability_why=long).fixability_why
    assert len(kept) <= 2000 and "more characters, not shown" in kept


@pytest.mark.allow_crash
def test_a_rule_that_could_not_run_claims_no_grade(tmp_path, monkeypatch):
    """A crash is the validator's defect, not a repair to the file. With a
    grade on the rule the crash finding inherited it: "the rule itself
    could not run" beside "the identifier's absolute form is a fact
    about the product". No rule carries a grade now; the crash builds its
    own violation, and it has none."""
    from aas_submodel_validate import registry

    def broken(ctx):
        raise RuntimeError("simulated")
    rule = registry._registry["DN-D1"]
    monkeypatch.setitem(registry._registry, "DN-D1",
                        Rule(id=rule.id, kind=rule.kind, prio=rule.prio,
                             title=rule.title, spec=rule.spec, fn=broken,
                             fix=rule.fix, path=rule.path))
    crashed = _only(_run(tmp_path, dn_env()), "DN-D1")
    assert crashed["message"] == runner.COULD_NOT_RUN
    assert crashed["fixability"] is None and crashed["fixabilityWhy"] is None
    assert crashed["path"] == ["document"], crashed


# -- the grades, each on an input that produces it ----------------------------

def _grade(finding):
    assert (finding["fixability"] is None) == (finding["fixabilityWhy"] is None), finding
    return finding["fixability"]


def test_an_element_missing_with_nothing_like_it_here_is_a_5(tmp_path):
    env = hd_env()
    version = _version(env)
    version["value"].remove(_named(version, "Version"))
    finding = _only(_run(tmp_path, env), "HD-E17")
    assert _grade(finding) == 5, finding
    assert finding["path"] == ["document", "submodel", "element"], finding


def test_an_element_missing_beside_one_drifted_copy_is_a_2(tmp_path):
    """The case the first version got backwards: the element is here, one
    version suffix off, and the lint says so on the next line. Renamed
    as well, so the identifier alone is what finds it -- with the row's
    idShort still on it, the name would have found it and this would
    not be measuring the near miss."""
    env = hd_env()
    drifted = _named(_version(env), "Version")
    drifted["semanticId"]["keys"][0]["value"] = "0173-1#02-AAP003#004"
    drifted["idShort"] = "Revision"
    finding = _only(_run(tmp_path, env), "HD-E17")
    assert _grade(finding) == 2, finding


def test_an_element_missing_beside_two_drifted_copies_is_a_3(tmp_path):
    env = hd_env()
    version = _version(env)
    drifted = _named(version, "Version")
    drifted["semanticId"]["keys"][0]["value"] = "0173-1#02-AAP003#004"
    second = copy.deepcopy(drifted)
    second["idShort"] = "Version2"
    second["semanticId"]["keys"][0]["value"] = "0173-1#02-AAP003#006"
    version["value"].append(second)
    finding = _only(_run(tmp_path, env), "HD-E17")
    assert _grade(finding) == 3, finding


def test_an_element_missing_whose_name_is_here_without_its_identifier_is_a_2(tmp_path):
    env = hd_env()
    del _named(_version(env), "Version")["semanticId"]
    finding = _only(_run(tmp_path, env), "HD-E17")
    assert _grade(finding) == 2, finding


def test_a_missing_section_the_template_fully_gives_is_a_2(tmp_path):
    """A required list whose items are all optional: the template gives
    everything it holds. Named at the submodel, so the route stops there."""
    env = pcf_env()
    submodel = env["submodels"][0]
    submodel["submodelElements"] = [e for e in submodel["submodelElements"]
                                    if e.get("idShort") != "ProductCarbonFootprints"]
    finding = _only(_run(tmp_path, env), "PCF-E01")
    assert _grade(finding) == 2, finding
    assert finding["subject"] == submodel["idShort"]
    assert finding["path"] == ["document", "submodel"], finding


def test_a_surplus_copy_is_a_3(tmp_path):
    env = hd_env()
    version = _version(env)
    extra = copy.deepcopy(_named(version, "Version"))
    extra["idShort"] = "VersionAgain"
    version["value"].append(extra)
    finding = _only(_run(tmp_path, env), "HD-E17")
    assert "found 2" in finding["message"], finding
    assert _grade(finding) == 3, finding


def test_an_item_standing_where_its_list_belongs_is_a_2(tmp_path):
    env = hd_env()
    version = _version(env)
    at = next(i for i, e in enumerate(version["value"]) if e.get("idShort") == "Language")
    version["value"][at] = {"idShort": "Language", "modelType": "Property",
                            "valueType": "xs:string", "value": "en",
                            "semanticId": _sid("0173-1#02-AAN468#008")}
    finding = _only(_run(tmp_path, env), "HD-E15")
    assert "Wrap this element" in finding["fix"], finding
    assert _grade(finding) == 2, finding


def test_a_collection_of_the_lists_own_items_is_a_2(tmp_path):
    env = hd_env()
    documents = env["submodels"][0]["submodelElements"][0]
    documents["modelType"] = "SubmodelElementCollection"
    documents.pop("typeValueListElement")
    documents["value"][0]["idShort"] = "Document01"
    finding = _only(_run(tmp_path, env), "HD-E01")
    assert _grade(finding) == 2, finding


def test_a_kind_the_content_does_not_map_onto_is_a_4(tmp_path):
    env = hd_env()
    title = _named(_version(env), "Title")
    title.update(modelType="Property", valueType="xs:string",
                 value="Operating manual")
    finding = _only(_run(tmp_path, env), "HD-E18")
    assert "must be a MultiLanguageProperty" in finding["message"], finding
    assert _grade(finding) == 4, finding


def test_a_declared_type_the_template_states_is_a_2(tmp_path):
    env = hd_env()
    _named(_version(env), "Version")["valueType"] = "xs:int"
    finding = _only(_run(tmp_path, env), "HD-E17")
    assert "must carry valueType" in finding["message"], finding
    assert _grade(finding) == 2, finding


def test_a_present_element_with_no_value_is_a_5(tmp_path):
    env = hd_env()
    del _named(_version(env), "Version")["value"]
    finding = _only(_run(tmp_path, env), "HD-E17")
    assert "carries no value" in finding["message"], finding
    assert _grade(finding) == 5, finding


def _with_file_value(value):
    env = hd_env()
    _named(_version(env), "DigitalFiles")["value"][0]["value"] = value
    return env


PDF = ("aasx/files/manual.pdf", b"%PDF-1.4 bytes")


@pytest.mark.parametrize("value, files, grade", [
    # the part is in the package, one folder over
    ("/aasx/documents/manual.pdf", [PDF], 2),
    # a path from somebody's disk, naming the same file
    ("C:\\Users\\me\\manual.pdf", [PDF], 2),
    # two parts carry that file name
    ("/aasx/documents/manual.pdf",
     [PDF, ("aasx/other/manual.pdf", b"%PDF-1.4 other")], 3),
    # two parts carry it, and they are one file stored twice
    ("/aasx/documents/manual.pdf",
     [PDF, ("aasx/other/manual.pdf", PDF[1])], 2),
    # nothing in the package carries it
    ("../manuals/manual-v3.pdf", [PDF], 5),
    ("/aasx/files/missing.pdf", [PDF], 5),
    # a directory: no file to look for
    ("/aasx/files/", [PDF], 4),
])
def test_a_file_value_is_graded_by_what_the_package_holds(tmp_path, value, files, grade):
    document = _run(tmp_path, _with_file_value(value), aasx=True, files=files)
    finding = _only(document, "HD-D7")
    assert _grade(finding) == grade, finding
    assert finding["path"] == ["document", "submodel", "element"], finding


def test_the_row_s_idshort_is_recognised_where_its_label_is_qualified(tmp_path):
    """Two rows sharing an idShort get a qualified label (#48), and the
    remedy still names the element by its idShort. An element carrying it,
    under an identifier no row claims, sat beside the missing one and was
    not recognised: the grade said nothing there resembled it. The same
    shape beside a row with a plain label was a 2, and is the control."""
    from builders import _sid, sn_env

    def named(children, short):
        return next(child for child in children if child.get("idShort") == short)

    def graded(env, rule, name):
        path = tmp_path / name
        path.write_text(json.dumps(env), encoding="utf-8")
        return next(f for f in runner.run(str(path)).as_dict()["findings"] if f["rule"] == rule)

    env = sn_env()
    instance = named(env["submodels"][0]["submodelElements"], "SoftwareNameplateInstance")
    link = named(named(named(instance["value"], "Contact")["value"],
                       "IPCommunication01")["value"], "AddressOfAdditionalLink")
    link["semanticId"] = _sid("urn:x:another-identifier")
    qualified = graded(env, "SN-E59", "qualified.json")
    assert "'AddressOfAdditionalLink (IPCommunication__00__)'" in qualified["message"]
    assert _grade(qualified) == 2, qualified
    assert "idShort" in qualified["fixabilityWhy"], qualified

    env = sn_env()
    kind = named(env["submodels"][0]["submodelElements"], "SoftwareNameplateType")
    named(kind["value"], "Version")["semanticId"] = _sid("urn:x:another-identifier")
    plain = graded(env, "SN-E09", "plain.json")
    assert _grade(plain) == 2, plain


def test_one_file_stored_under_two_names_is_nothing_to_choose(tmp_path):
    """The same bytes in two folders, and a File value naming neither: the
    grade said a person must choose between them, and whichever is chosen
    is the same file. The reason says what the reader looked at -- the
    archive's record of size and checksum, not the bytes."""
    same = _only(_run(tmp_path, _with_file_value("/aasx/documents/manual.pdf"), aasx=True,
                      files=[PDF, ("aasx/other/manual.pdf", PDF[1])]), "HD-D7")
    assert _grade(same) == 2, same
    assert "same size and checksum" in same["fixabilityWhy"], same
    # The same size and other bytes: two files, and a choice. A size alone
    # would call them one.
    other = PDF[1][:-1] + b"z"
    assert len(other) == len(PDF[1]) and other != PDF[1]
    differ = _only(_run(tmp_path, _with_file_value("/aasx/documents/manual.pdf"), aasx=True,
                        files=[PDF, ("aasx/other/manual.pdf", other)], name="differ"),
                   "HD-D7")
    assert _grade(differ) == 3, differ
    # And the size is half of what is compared: two parts forged to one
    # CRC-32 at different lengths are two files, and a checksum alone would
    # have called them one.
    forged = b"%PDF-1.4 a different, longer manual\x1d\x01\x80\xbe"
    assert zlib.crc32(forged) == zlib.crc32(PDF[1]) and len(forged) != len(PDF[1])
    collided = _only(_run(tmp_path, _with_file_value("/aasx/documents/manual.pdf"), aasx=True,
                          files=[PDF, ("aasx/other/manual.pdf", forged)], name="collided"),
                     "HD-D7")
    assert _grade(collided) == 3, collided


def test_an_identifier_one_version_off_is_a_2(tmp_path):
    finding = _only(_run(tmp_path, env_json("0173-1#01-AHF578#002")), "SMT-D1")
    assert _grade(finding) == 2, finding
    assert finding["path"] == ["document"], finding


def test_an_identifier_of_a_template_without_a_table_claims_nothing(tmp_path):
    """Its own remedy says to leave such an identifier alone. Nothing in
    the file is asked to change, so there is no repair to grade."""
    document = _run(tmp_path, env_json("https://admin-shell.io/idta/TimeSeries/1/1"))
    assert _grade(_only(document, "SMT-D1")) is None


def test_an_input_with_no_submodel_is_a_5(tmp_path):
    assert _grade(_only(_run(tmp_path, {"submodels": []}), "SMT-D1")) == 5


@pytest.mark.parametrize("value, grade", [
    ("www.example.com/model-1234/serial-5678", 4),
    ("", 5),                                   # the same absence as DN-E01's
    ("   ", 5),
])
def test_uri_of_the_product(tmp_path, value, grade):
    env = dn_env()
    uri = next(e for e in env["submodels"][0]["submodelElements"]
               if e.get("idShort") == "URIOfTheProduct")
    uri["value"] = value
    assert _grade(_only(_run(tmp_path, env), "DN-D1")) == grade


def test_findings_that_ask_no_change_of_the_file_claim_no_grade(tmp_path):
    """A notice about which table answered, and a bound this reader sets,
    are not defects anybody repairs in the file. Graded 1 -- determined
    by the input alone -- they told a consumer the file held a repair."""
    handover = tmp_path / "handover.json"
    handover.write_bytes(json.dumps(hd_env()).encode())
    for profile in ("02004", "02035-2"):
        report = runner.run(str(handover), profile=profile).as_dict()
        for finding in report["findings"]:
            if finding["rule"] == "SMT-D2":
                assert _grade(finding) is None, finding
                assert finding["path"] == ["document", "submodel"], finding
    carbon = tmp_path / "carbon.json"
    carbon.write_bytes(json.dumps(pcf_env()).encode())
    said = [f for f in runner.run(str(carbon)).as_dict()["findings"]
            if f["rule"] == "BAT-R2"]
    assert said, "the carbon footprint fixture is supposed to draw BAT-R2"
    assert all(_grade(f) is None for f in said), said


# -- what the subject names ---------------------------------------------------

def test_a_container_rule_says_whether_it_named_the_file_or_a_part(tmp_path):
    missing = tmp_path / "nope.json"
    assert _only(json.loads(json.dumps(runner.run(str(missing)).as_dict())),
                 "X6")["path"] == ["document"]
    missing_package = tmp_path / "nope.aasx"
    assert _only(json.loads(json.dumps(runner.run(str(missing_package)).as_dict())),
                 "X6")["path"] == ["container"]
    broken = tmp_path / "broken.json"
    broken.write_text("{")
    finding = _only(json.loads(json.dumps(runner.run(str(broken)).as_dict())), "X3")
    assert finding["subject"] == str(broken) and finding["path"] == ["document"]
    package = tmp_path / "part.aasx"
    build_aasx(str(package), json.dumps(hd_env()).encode())
    corrupt_part(package, "aasx/env.json", "declared_size")
    finding = _only(json.loads(json.dumps(runner.run(str(package)).as_dict())), "X1")
    assert finding["subject"] == "aasx/env.json", finding
    assert finding["path"] == ["container", "part"], finding
    not_a_zip = tmp_path / "saved-as.aasx"
    not_a_zip.write_bytes(json.dumps(hd_env()).encode())
    finding = _only(json.loads(json.dumps(runner.run(str(not_a_zip)).as_dict())), "X1")
    assert finding["path"] == ["container"] and _grade(finding) is None, finding


def test_a_relayed_finding_names_no_step_of_this_readers(tmp_path):
    """Its subject is the upstream library's expression and can name a
    shell or a concept description, which no step here spells."""
    env = hd_env()
    env["conceptDescriptions"] = [{"modelType": "ConceptDescription",
                                   "id": "urn:example:cd", "idShort": "2bad"}]
    relayed = [f for f in _run(tmp_path, env)["findings"] if f["rule"] == "META"]
    assert relayed, "the idShort is supposed to break a metamodel constraint"
    assert all(f["path"] == [] for f in relayed), relayed


def test_a_supplied_templates_findings_say_what_they_name(tmp_path):
    import test_a_template_a_caller_supplied as supplied
    document = json.loads(json.dumps(runner.run(
        str(supplied._instance(tmp_path)), template=str(supplied.VENDORED)).as_dict()))
    minted = [f for f in document["findings"] if f["rule"].startswith("TPL-")]
    assert minted, "this instance is supposed to draw a finding from the supplied table"
    assert all(f["path"] for f in minted), minted


def test_the_report_carries_all_three_and_stays_schema_one(tmp_path):
    document = _run(tmp_path, env_json("0173-1#01-AHF578#002"))
    assert document["schemaVersion"] == 1
    assert document["findings"], "this input is supposed to draw one"
    for finding in document["findings"]:
        for key in ("fixability", "fixabilityWhy", "path"):
            assert key in finding, key
        for was_there in ("rule", "severity", "priority", "message", "subject",
                          "fix", "title", "spec"):
            assert was_there in finding, was_there
