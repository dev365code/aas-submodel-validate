"""Decisions this project made deliberately, each with a test that fails
when it is undone.

Every one of these survived having the code that implements it changed:
the reason was written down in a commit message and the behaviour was
not, so nothing went red.

Each test here names the decision it guards. They are gathered in one
file because they have one purpose; the rules they exercise are spread
across the tree.
"""
from __future__ import annotations

import copy
import json

from aas_submodel_validate import runner
from builders import build_aasx, corrupt_part, env_json, hd_env, td_env

PART = "aasx/files/manual.pdf"


def _ids(path):
    return {f.id for f in runner.run(path).findings}


def _env_ids(tmp_path, env):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return {f.id for f in runner.run(path).findings}


# -- an unreadable part is a defect in the archive, not in its chain ---------

def test_an_unreadable_chain_part_is_reported_as_the_archive_not_the_chain(tmp_path):
    """The decision: route it to X1, whose remedy is to re-create the
    archive, and not to X2, whose remedy is to repair a relationship
    chain that may be perfectly intact.

    The part corrupted here is read while following the chain, which is a
    different call site from the payload -- and the one a test had not
    reached."""
    path = build_aasx(tmp_path / "p.aasx", payload=env_json())
    corrupt_part(path, "aasx/_rels/aasx-origin.rels", "stream")
    ids = _ids(path)
    assert "X1" in ids
    assert "X2" not in ids


# -- one element belongs to one row -----------------------------------------

def test_an_element_claiming_two_rows_is_counted_for_one(tmp_path):
    """The decision: the first row to match an element claims it, so a
    shared identifier cannot be counted under two rows and make both
    cardinalities wrong.

    Nothing in either template shares a match value between siblings
    today, which is why this went untested. An element can still claim
    two rows by naming one as its semanticId and a sibling as a
    supplemental -- and the next template shares 02004's anchor, where
    two tables answer for one submodel."""
    env = copy.deepcopy(hd_env())
    document = env["submodels"][0]["submodelElements"][0]["value"][0]
    ids_list, classifications, _versions = document["value"]
    assert ids_list["idShort"] == "DocumentIds"
    assert classifications["idShort"] == "DocumentClassifications"
    # the sibling's identity, carried by an element that is not it
    ids_list["supplementalSemanticIds"] = [classifications["semanticId"]]
    document["value"].remove(classifications)
    # DocumentClassifications is required and is now absent; the element
    # wearing its identifier must not be counted as one.
    assert "HD-E08" in _env_ids(tmp_path, env)


# -- the file rule checks both of its labels, and both of its answers --------

def test_the_second_file_label_is_checked_too(tmp_path):
    """The decision: TD-D2 asks about CompanyLogo *and* ImageFile.
    Dropping either left the suite green."""
    path = build_aasx(tmp_path / "p.aasx",
                      payload=json.dumps(td_env()).encode("utf-8"),
                      files=[("aasx/files/logo.png", b"\x89PNG")])
    assert "TD-D2" in _ids(path)


def test_a_file_value_that_is_no_part_name_is_told_apart(tmp_path):
    """The decision: "not a part name" and "no such part" are different
    findings under one rule, because the remedy is the same sentence but
    the reader needs to know which one they met."""
    env = copy.deepcopy(td_env())
    logo = [e for e in env["submodels"][0]["submodelElements"][0]["value"]
            if e.get("idShort") == "CompanyLogo"][0]
    logo["value"] = "/../outside.png"
    path = build_aasx(tmp_path / "p.aasx", payload=json.dumps(env).encode("utf-8"),
                      files=[("aasx/files/logo.png", b"\x89PNG"),
                             ("aasx/files/front.png", b"\x89PNG")])
    findings = {f.id: f for f in runner.run(path).findings}
    assert "not a part name" in findings["TD-D2"].violation.message


# -- a reference out of this submodel is not this tool's to judge -----------

def test_the_guard_on_foreign_references_is_what_keeps_them_silent(tmp_path):
    """The decision: TD-D3 judges only references whose first key names
    this submodel.

    The test that claimed to pin it passed for another reason -- its key
    path resolved locally whether the guard ran or not. This one uses a
    path that resolves nowhere, so silence can only come from the
    guard."""
    env = copy.deepcopy(td_env())
    classification = env["submodels"][0]["submodelElements"][1]["value"][0]
    reference = classification["value"][-1]
    assert reference["idShort"] == "ReferenceToTechnicalPropertyArea"
    reference["value"]["keys"][0]["value"] = "urn:somewhere:else"
    reference["value"]["keys"][-1]["value"] = "41"      # resolves nowhere
    assert "TD-D3" not in _env_ids(tmp_path, env)


def test_an_element_identified_only_by_a_supplemental_still_matches(tmp_path):
    """The other half of divergence #14. A supplier's own semanticId on an
    element, with the template's identifier carried beside it, is a shape
    the ledger says must match -- "an instance that declares its identity
    only through a supplemental should match too".

    Only the refusing half was pinned: that an element wearing a
    *sibling's* identifier cannot satisfy the sibling's cardinality.
    Deleting the fold entirely satisfied that test too, because the
    element then matched nothing at all -- and turned a conformant file
    into a failing one, with the suite green.
    """
    env = copy.deepcopy(hd_env())
    document = env["submodels"][0]["submodelElements"][0]["value"][0]
    ids_list = document["value"][0]
    assert ids_list["idShort"] == "DocumentIds"
    ids_list["supplementalSemanticIds"] = [ids_list["semanticId"]]
    ids_list["semanticId"] = {"type": "ExternalReference", "keys": [
        {"type": "GlobalReference", "value": "urn:somesupplier:their-own-id"}]}
    assert _env_ids(tmp_path, env) == set()
