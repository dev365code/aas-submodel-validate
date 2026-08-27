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
import zipfile

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.container import AasxPackage, canonical_part_name
from builders import (
    CONTENT_TYPES,
    ORIGIN_REL,
    SPEC_REL,
    build_aasx,
    hd_env,
    rels,
)

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


def test_a_declared_supplementary_part_outside_the_package_is_still_reported(tmp_path):
    """X4 asks whether every declared aas-suppl part exists. Dropping a
    relationship whose target does not normalise took that question away
    with it -- and the comment justifying the drop said X2 would report
    it, which it cannot: an aas-suppl relationship is not on the chain,
    so nothing loads an error and X2 reads only chain errors."""
    path = build_aasx(tmp_path / "p.aasx", payload=_container_with("/" + PART),
                      files=[(PART, b"%PDF-1.4 ")],
                      suppl_targets=["../outside.pdf"])
    assert "X4" in {f.id for f in runner.run(path).findings}


def test_a_payload_whose_entry_name_holds_an_escape_is_still_read(tmp_path):
    """The claim was that a literal match comes first. It did in
    `part()`, and the chain never went through `part()`: the target was
    normalised, the decoded name was handed to a reader that looks up
    exact entry names, and an archive that spelled its payload with a
    percent escape drew X2 -- whose remedy is to repair a chain that is
    intact."""
    entry = "aasx/env%20a.json"
    path = tmp_path / "esc.aasx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels", rels([(SPEC_REL, "/" + entry)]))
        archive.writestr(entry, _container_with("/" + PART))
        archive.writestr(PART, b"%PDF-1.4 ")
    ids = {f.id for f in runner.run(path).findings}
    assert "X2" not in ids
    assert "SMT-D1" not in ids, "the payload was never read, so no template ran"


def test_a_part_stored_under_a_non_canonical_name_is_still_found(tmp_path):
    """The archive's own entry names are written by tools that were not
    all reading ECMA-376, so an entry may be stored as `aasx/./files/x`
    while the File value spells the same part `/aasx/files/x`.

    `part` tries the literal, then the literal without OPC's leading
    slash, then the value normalised -- and only then an index of every
    entry name normalised, which is the branch this reaches. Losing it
    reports a file as missing from a container that holds it, which is
    the direction this project treats as worst."""
    path = tmp_path / "odd.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         rels([(SPEC_REL, "/aasx/env.json")]))
        archive.writestr("aasx/env.json", json.dumps(hd_env()).encode("utf-8"))
        archive.writestr("aasx/./files/manual.pdf", b"%PDF-1.4")
    with AasxPackage(path) as package:
        assert package.part("/aasx/files/manual.pdf") == "aasx/./files/manual.pdf"
    assert "HD-D7" not in {f.id for f in runner.run(path).findings}


def test_closing_a_package_closes_the_archive(tmp_path):
    """`close` and `__exit__` exist so a reader does not hold the file
    open, and nothing asked whether they do. On Windows an unclosed
    handle keeps the file locked -- which is why that platform is in the
    matrix -- and everywhere else it is invisible."""
    path = build_aasx(tmp_path / "p.aasx", payload=json.dumps(hd_env()).encode("utf-8"))
    package = AasxPackage(path)
    assert package._zip.fp is not None
    package.close()
    assert package._zip.fp is None

    with AasxPackage(path) as package:
        assert package._zip.fp is not None
    assert package._zip.fp is None, "the context manager did not close it"


def test_an_exact_entry_beats_its_canonical_cousin(tmp_path):
    """`part` tries the value exactly before it interprets anything, and
    the order is the answer when an archive holds both spellings: an
    entry named `aasx/./files/m.pdf` beside `aasx/files/m.pdf`. The
    normalised index maps both to whichever it met first, so a value
    spelling the odd one exactly must win on the exact step or it is
    handed the cousin's bytes."""
    path = tmp_path / "clash.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         rels([(SPEC_REL, "/aasx/env.json")]))
        archive.writestr("aasx/env.json", json.dumps(hd_env()).encode("utf-8"))
        archive.writestr("aasx/files/m.pdf", b"%PDF-1.4 canonical")
        archive.writestr("aasx/./files/m.pdf", b"%PDF-1.4 odd")
    with AasxPackage(path) as package:
        assert package.part("/aasx/./files/m.pdf") == "aasx/./files/m.pdf"
        assert package.part("aasx/./files/m.pdf") == "aasx/./files/m.pdf"
        assert package.part("/aasx/files/m.pdf") == "aasx/files/m.pdf"


def test_an_entry_only_the_exact_step_can_name(tmp_path):
    """The exact step looked redundant with the literal step below it --
    stripping a leading slash from a value that has none changes nothing
    -- until the archive holds `//odd.pdf` *and* `odd.pdf`. A value
    spelling the doubled one exactly must reach it on the exact step:
    the literal step strips both slashes and hands back the plain
    cousin's name instead."""
    path = tmp_path / "abs.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         rels([(SPEC_REL, "/aasx/env.json")]))
        archive.writestr("aasx/env.json", json.dumps(hd_env()).encode("utf-8"))
        archive.writestr("odd.pdf", b"%PDF-1.4 plain")
        archive.writestr("//odd.pdf", b"%PDF-1.4 doubled")
    with AasxPackage(path) as package:
        assert package.part("//odd.pdf") == "//odd.pdf"
        assert package.part("odd.pdf") == "odd.pdf"


def test_a_whitespace_only_value_names_no_part():
    """`" "` is not a name and not the empty string either -- the guard
    reads `not value or not value.strip()`, and each half alone lets one
    of the two through."""
    assert canonical_part_name(" ") is None
    assert canonical_part_name("\t") is None
    assert canonical_part_name("") is None


def test_dot_only_and_root_values_name_no_part():
    """Both collapse to nothing once the dot segments go: `/` names the
    root and `/.` names it with a step, and a part is a file, not the
    package. The empty join falls back to None explicitly -- a caller
    comparing `is None` must not meet `""`."""
    assert canonical_part_name("/") is None
    assert canonical_part_name("/.") is None


def test_a_doubled_separator_finds_the_canonical_entry_not_its_cousin(tmp_path):
    """`aasx//x` is a sloppy spelling of `aasx/x`, and the archive holds
    both `aasx/x` and `aasx/./x` -- with the odd one stored first, so the
    normalised index maps their shared canonical name to the odd one.
    The direct canonical lookup answers before the index does, and the
    order is the verdict: lose it and the sloppy spelling is handed the
    cousin's bytes."""
    path = tmp_path / "cousins.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         rels([(SPEC_REL, "/aasx/env.json")]))
        archive.writestr("aasx/env.json", json.dumps(hd_env()).encode("utf-8"))
        archive.writestr("aasx/./files/x.pdf", b"%PDF odd first")
        archive.writestr("aasx/files/x.pdf", b"%PDF canonical")
    with AasxPackage(path) as package:
        assert package.part("aasx//files/x.pdf") == "aasx/files/x.pdf"


def test_the_repr_names_the_package(tmp_path):
    """`repr` is what lands in a log line or a debugger, and nothing else
    ever calls it -- so it could return None, or divide a string by a
    string, with everything green."""
    path = build_aasx(tmp_path / "p.aasx", payload=json.dumps(hd_env()).encode("utf-8"))
    with AasxPackage(path) as package:
        assert "AasxPackage" in repr(package)
        assert "p.aasx" in repr(package)

