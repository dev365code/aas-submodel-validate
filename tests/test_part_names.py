"""One answer to "what part does this name?", however it is spelled.

Two places in this reader turn a string into a part name: the container,
resolving an OPC relationship target, and the File rule, looking a File
element's value up. They are not the same question — a relationship
Target is a URI reference resolved against its source part
(docs/divergences.md #13), while a File value is a part name, which OPC
defines as absolute, with reserved characters percent-encoded and no
empty, "." or ".." segments.

So there is one normaliser and two entry points, not one function for
both. What the normaliser fixes is spelling; what stays different is
where the name starts from.

Every case below points at a part the archive actually holds. A finding
here is the validator inventing a defect in a conformant package.
"""
from __future__ import annotations

import copy
import json

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.container import AasxPackage, canonical_part_name
from builders import build_aasx, hd_env

PART = "aasx/files/manual.pdf"

#: Spellings of that one part. The first two are what tools actually
#: write; the rest are legal ways to write the same name that a reader
#: comparing strings would miss.
SAME_PART = [
    "/aasx/files/manual.pdf",
    "aasx/files/manual.pdf",
    "//aasx/files/manual.pdf",
    "./aasx/files/manual.pdf",
    "/aasx/./files/manual.pdf",
    "/aasx//files/manual.pdf",
    "/aasx/other/../files/manual.pdf",
    "\\aasx\\files\\manual.pdf",
]

#: Values that name no part of this package at all. They are a different
#: defect from "the file is missing", and say so.
NOT_A_PART_NAME = [
    "/../aasx/files/manual.pdf",
    "../manual.pdf",
]


def _container_with(value):
    env = copy.deepcopy(hd_env())
    version = env["submodels"][0]["submodelElements"][0]["value"][0]["value"][2]["value"][0]
    files = version["value"][-1]
    assert files["idShort"] == "DigitalFiles"
    files["value"][0]["value"] = value
    return json.dumps(env).encode("utf-8")


@pytest.mark.parametrize("spelling", SAME_PART)
def test_every_spelling_of_a_part_this_archive_holds_is_found(tmp_path, spelling):
    path = build_aasx(tmp_path / "p.aasx", payload=_container_with(spelling),
                      files=[(PART, b"%PDF-1.4 ")])
    assert "HD-D7" not in {f.id for f in runner.run(path).findings}


@pytest.mark.parametrize("spelling", NOT_A_PART_NAME)
def test_a_value_that_is_not_a_part_name_says_so(tmp_path, spelling):
    path = build_aasx(tmp_path / "p.aasx", payload=_container_with(spelling),
                      files=[(PART, b"%PDF-1.4 ")])
    findings = {f.id: f for f in runner.run(path).findings}
    assert "HD-D7" in findings
    # A value that is not a part name and a part that is absent are two
    # defects, and the finding has to say which one it met.
    assert "not a part name" in findings["HD-D7"].violation.message


def test_a_missing_file_is_still_reported(tmp_path):
    """The point of the normaliser is to stop inventing defects, not to
    stop finding them."""
    path = build_aasx(tmp_path / "p.aasx",
                      payload=_container_with("/aasx/files/absent.pdf"),
                      files=[(PART, b"%PDF-1.4 ")])
    assert "HD-D7" in {f.id for f in runner.run(path).findings}


def test_an_entry_whose_name_really_contains_a_percent_is_not_decoded_away(tmp_path):
    """Exact match comes first, so an archive holding a literal `%20` in
    an entry name still answers for a value spelled the same way. Only
    after that does the percent-decoded reading get a turn."""
    literal = "aasx/files/manual%20a.pdf"
    path = build_aasx(tmp_path / "p.aasx",
                      payload=_container_with("/" + literal),
                      files=[(literal, b"%PDF-1.4 ")])
    assert "HD-D7" not in {f.id for f in runner.run(path).findings}


def test_a_percent_encoded_value_reaches_the_entry_it_encodes(tmp_path):
    """And when the archive holds the decoded name, the encoded value
    finds it -- OPC part names escape reserved characters, so the two
    are one name written two ways."""
    entry = "aasx/files/manual a.pdf"
    path = build_aasx(tmp_path / "p.aasx",
                      payload=_container_with("/aasx/files/manual%20a.pdf"),
                      files=[(entry, b"%PDF-1.4 ")])
    assert "HD-D7" not in {f.id for f in runner.run(path).findings}


def test_the_normaliser_refuses_to_leave_the_package(tmp_path):
    assert canonical_part_name("/aasx/x") == "aasx/x"
    assert canonical_part_name("/../x") is None
    assert canonical_part_name("") is None


def test_the_container_answers_for_a_name_it_holds(tmp_path):
    path = build_aasx(tmp_path / "p.aasx", files=[(PART, b"%PDF-1.4 ")])
    with AasxPackage(path) as package:
        assert package.part("/aasx/./files/manual.pdf") == PART
        assert package.part("/aasx/files/absent.pdf") is None


def test_the_literal_spelling_really_does_win(tmp_path):
    """An archive holding both `a b.pdf` and `a%20b.pdf` has to answer
    for each of them separately, or the reader has silently merged two
    files. The claim was that an exact match is tried first -- but a File
    value conventionally starts with "/" and an entry name never does, so
    the exact match almost never fired and the decoded reading always
    won.
    """
    path = build_aasx(tmp_path / "p.aasx",
                      files=[("aasx/files/a b.pdf", b"1"),
                             ("aasx/files/a%20b.pdf", b"2")])
    with AasxPackage(path) as package:
        assert package.part("/aasx/files/a%20b.pdf") == "aasx/files/a%20b.pdf"
        assert package.part("/aasx/files/a b.pdf") == "aasx/files/a b.pdf"


def test_a_name_that_ends_in_a_separator_is_not_a_part_name():
    """OPC part names do not end in "/": that is a directory, and no
    part is named by it."""
    assert canonical_part_name("/aasx/files/") is None
    assert canonical_part_name("/aasx/") is None
    assert canonical_part_name("aasx/files/manual.pdf") == "aasx/files/manual.pdf"
