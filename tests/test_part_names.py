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
from aas_submodel_validate.container import AasxPackage, canonical_part_name, has_scheme
from builders import (
    CONTENT_TYPES,
    ORIGIN_REL,
    SPEC_REL,
    build_aasx,
    hd_env,
    rels,
)
from verdicts import by_id

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
    findings = by_id(runner.run(path))
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


def test_the_exact_spelling_wins_over_the_folded_one_inside_the_index(tmp_path):
    """Two indexes answer for oddly-spelled entries, and their order is
    the guarantee.

    `part` asks the canonical index first and the ASCII-folded one after,
    for the same reason the literal attempts come before either: an
    archive holding a name in the case the document wrote must answer
    with that entry. Where the entries are spelled normally the exact
    matches above settle it and neither index is reached -- so the
    ordering *between the indexes* only shows on entries that are both
    oddly spelled and differ in case.

    Measured: emptying the canonical index alone leaves the whole suite
    green, because the folded index answers for everything the other test
    of these indexes asks. It is this case that tells them apart.
    """
    path = tmp_path / "both.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         rels([(SPEC_REL, "/aasx/env.json")]))
        archive.writestr("aasx/env.json", json.dumps(hd_env()).encode("utf-8"))
        archive.writestr("aasx/./files/Manual.pdf", b"UPPER")
        archive.writestr("aasx/./files/manual.pdf", b"lower")
    with AasxPackage(path) as package:
        assert package.part("/aasx/files/Manual.pdf") == "aasx/./files/Manual.pdf"
        assert package.part("/aasx/files/manual.pdf") == "aasx/./files/manual.pdf"


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


def test_a_directory_entry_is_not_a_part_and_does_not_alias_one(tmp_path):
    """Archives carry directory entries -- names ending in "/" -- and a
    directory is not a part. Two ways that has to hold: asking for a
    part *as* a directory (`aasx/env.json/`) answers None, and asking
    for `/` answers None even though a directory entry is in the index
    build's path. The second is the sharp one: `canonical_part_name` of
    a directory entry is None, and an index that files something under
    the None key hands that entry to *every* value that fails to
    normalise -- `part("/")` came back `aasx/`."""
    path = tmp_path / "dirs.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/", b"")
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         rels([(SPEC_REL, "/aasx/env.json")]))
        archive.writestr("aasx/env.json", json.dumps(hd_env()).encode("utf-8"))
    with AasxPackage(path) as package:
        assert package.part("aasx/env.json/") is None
        assert package.part("/") is None
        assert package.part("/aasx/env.json") == "aasx/env.json"


def _clash_archive(path, first, second):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels",
                         rels([(SPEC_REL, "/aasx/env.json")]))
        archive.writestr("aasx/env.json", json.dumps(hd_env()).encode("utf-8"))
        archive.writestr(first, b"first")
        archive.writestr(second, b"second")
    return path


def test_a_clash_resolves_to_the_entry_stored_first_in_either_order(tmp_path):
    """Two odd spellings of one name, neither canonical, so only the
    normalised index can answer -- and the index keeps the entry it met
    first. "First" must mean the archive's own order: the index used to
    be built off a frozenset, where "first" meant the process's hash
    seed, and the same archive resolved the same value to different
    entries on different runs.

    Two archives, same entries, opposite write order. Hash order gives
    both archives the same answer, so under that defect one of these two
    assertions fails on every seed -- a seed-proof pin, where a single
    fixture was measured killing on 12 seeds of 20."""
    value = "/aasx/f.pdf"
    odd_a, odd_b = "aasx/./f.pdf", "./aasx/f.pdf"
    with AasxPackage(_clash_archive(tmp_path / "ab.aasx", odd_a, odd_b)) as package:
        assert package.part(value) == odd_a
    with AasxPackage(_clash_archive(tmp_path / "ba.aasx", odd_b, odd_a)) as package:
        assert package.part(value) == odd_b



#: Values where "is this a scheme?" answers differently depending on
#: whether the letters are ASCII or whatever `str.isalnum()` calls a
#: letter. RFC 3986 §3.1 is ASCII: `ALPHA *( ALPHA / DIGIT / "+" / "-"
#: / "." )`. Python's predicates are Unicode, and a validator that read
#: them as the grammar would take a package name written in Cyrillic
#: for a URI and stop asking whether the archive holds it.
NOT_A_SCHEME_BUT_ISALNUM_SAYS_SO = [
    "caf\u00e9:manual.pdf",                 # a Latin letter with an accent
    "\u0441\u043e:manual.pdf",              # Cyrillic es, o
    "\uff48\uff54\uff54\uff50:x.pdf",       # fullwidth h t t p
    "a\u00b2:manual.pdf",                   # superscript two is alphanumeric
]


@pytest.mark.parametrize("value", NOT_A_SCHEME_BUT_ISALNUM_SAYS_SO)
def test_a_scheme_is_ascii_and_the_letters_are_named_not_asked(value):
    """The letters of a scheme are written out in `container.py` rather
    than asked of `str`, and nothing said why in a way a test could
    fail on: swapping the frozensets back for `isalpha()`/`isalnum()`
    left the whole suite green, so the next tidy-up puts it back.

    Each value here is what the two readings disagree about. Reading
    them as schemes would mean a File value or a relationship target
    naming a real part -- in a package named in Korean, Russian or
    Japanese, which is who this project is for -- being passed over as
    somebody else's file, and the question "does the archive hold it"
    never asked.
    """
    assert has_scheme(value) is False


@pytest.mark.parametrize("value,expected", [
    ("urn:iso:std:iso:1234", True),
    ("mailto:docs@example.com", True),
    ("http://example.com/manual.pdf", True),
    ("a+b-c.d:x", True),                    # every character §3.1 allows
    ("ws://example.com/live", True),        # two letters is still a scheme
    ("C:\\docs\\manual.pdf", False),        # a drive letter, not a scheme
    ("files/a://absent.pdf", False),        # contains "://" and is a part name
    ("aasx/http:/example.com/manual.pdf", False),   # a URI already resolved
    ("1http:x", False),                     # a scheme starts with a letter
])
def test_what_the_scheme_test_answers(value, expected):
    """Both edges, so the predicate cannot be widened or narrowed
    without a red. Two of these are the ones that cost something: a
    substring test called `files/a://absent.pdf` a scheme and skipped a
    MUST, and `aasx/http:/…` is what joining a URI to a directory
    produces -- asked after that join, every scheme is gone.

    `ws:` pins the shortest head this accepts. The minimum is two
    letters rather than RFC 3986's one, so that `C:\\…` stays a path
    rather than becoming a scheme; that choice is what the drive-letter
    row above protects. Until `ws:` was added, raising the minimum to
    three left the whole suite green -- the sentence at the top of this
    docstring was true of one edge and not the other."""
    assert has_scheme(value) is expected


# -- which reason, and to whom it is said -------------------------------------


def test_every_reason_a_value_is_not_a_part_name_is_named_as_itself():
    """The rules had one sentence for four defects.

    `canonical_part_name` returning None already meant any of four
    things, and its own docstring listed three of them -- while the File
    rule told every one of them that the value "climbs out of the
    package". `/aasx/files/` climbs nowhere; it names a directory, and
    the remedy that followed was for a defect the author did not have.
    """
    from aas_submodel_validate.container import part_name_problem

    assert part_name_problem("aasx/files/manual.pdf") is None
    assert "climbs out" in part_name_problem("../evil.step")
    assert "directory" in part_name_problem("/aasx/files/")
    assert "empty" in part_name_problem("   ")
    assert "cannot carry" in part_name_problem("x?y.pdf")


@pytest.mark.parametrize("value, carried", [
    ("x?y.pdf", "'?'"),
    ("a<b>.pdf", "'<'"),
    ("a b.pdf", "a space"),
    ("[Content_Types].xml", "'['"),
    ("a|b.pdf", "'|'"),
    ('"q".pdf', '\'"\''),
])
def test_a_character_no_part_name_may_carry_is_named(value, carried):
    """RFC 3986 §3.3 builds a segment out of pchar, and ECMA-376 Part 2
    builds a part name out of those segments -- which is what this
    module's first paragraph has always said and nothing checked. The
    finding names the character, because "not a part name" without
    saying which character is a remedy the reader has to guess at."""
    from aas_submodel_validate.container import part_name_problem

    problem = part_name_problem(value)
    assert problem and carried in problem, (value, problem)


@pytest.mark.parametrize("value", [
    "aasx/files/manual.pdf",
    "a%20b/c.pdf",              # the legal way to spell a space
    "o'brien(1),v2;x=1.pdf",    # sub-delims, all of them legal
    "a:b@c.pdf",                # ":" and "@" are pchar
    "Handbuch_Größe.pdf",       # not ASCII, deliberately not refused
    "discount50%.pdf",          # a lone % is not legal and not refused
])
def test_a_part_name_this_reader_must_not_refuse(value):
    """The direction that costs more. Every one of these is either legal
    or something this reader has decided not to be sure about, and a
    finding on any of them is a conformant package called broken."""
    from aas_submodel_validate.container import part_name_problem

    assert part_name_problem(value) is None, (value, part_name_problem(value))


def test_the_archives_own_entry_names_are_not_judged_as_part_names(tmp_path):
    """A ZIP entry name is not a part name. This reader's whole
    literal-first arrangement exists so that an entry spelled oddly is
    still reachable, and putting the character rule inside the spelling
    walk took those entries out of the canonical index -- `X4` then
    reported a part missing that was sitting in the archive."""
    path = tmp_path / "odd.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr("aasx/_rels/aasx-origin.rels", rels([(SPEC_REL, "/aasx/env.json")]))
        archive.writestr("aasx/env.json", json.dumps(hd_env()).encode("utf-8"))
        archive.writestr("aasx/files/man ual.pdf", b"%PDF-1.4")
    with AasxPackage(path) as package:
        assert package.part("aasx/files/man ual.pdf") == "aasx/files/man ual.pdf"
        assert package.part("/aasx/files/man ual.pdf") == "aasx/files/man ual.pdf"
        # And the package's own content-types stream, which is not a part
        # and is still an entry the archive holds.
        assert package.part("[Content_Types].xml") == "[Content_Types].xml"


def test_the_remedy_for_a_value_no_part_can_carry_is_not_add_the_file(tmp_path):
    """`HD-D7`'s own remedy says to add the file under the name the value
    gives. That is right when a part is missing and wrong here: no entry
    added under this spelling is a part, and for a value that climbs out
    of the package adding one is the last thing to do."""
    environment = copy.deepcopy(hd_env())
    blob = json.dumps(environment).replace("/aasx/files/manual.pdf", "x?y.pdf")
    path = build_aasx(tmp_path / "bad.aasx", payload=blob.encode("utf-8"),
                      files=(("aasx/files/manual.pdf", b"%PDF-1.4"),))
    (finding,) = [f for f in runner.run(str(path)).findings if f.id == "HD-D7"]
    assert "not a part name" in finding.violation.message
    assert "Add the file" not in (finding.violation.fix or "")
    assert "no part can carry this name" in finding.violation.fix
    # And the reason reaches the report, not only the function that
    # computes it. Restoring the stock sentence left every test above
    # green: they asked `part_name_problem` and nothing asked the
    # finding.
    assert "climbs out" not in finding.violation.detail
    assert "cannot carry '?'" in finding.violation.detail


def test_the_report_carries_the_reason_the_walk_gave(tmp_path):
    """Each of the four, end to end. The clause the reader sees has to
    be the one the walk decided on."""
    from aas_submodel_validate.container import part_name_problem

    for value in ("../evil.step", "/aasx/files/", "x?y.pdf", "[Content_Types].xml"):
        blob = json.dumps(copy.deepcopy(hd_env())).replace(
            "/aasx/files/manual.pdf", value)
        path = build_aasx(tmp_path / "r.aasx", payload=blob.encode("utf-8"),
                          files=(("aasx/files/manual.pdf", b"%PDF-1.4"),))
        (finding,) = [f for f in runner.run(str(path)).findings if f.id == "HD-D7"]
        assert finding.violation.detail == "%s: %s" % (value, part_name_problem(value))
def test_a_name_differing_only_in_ascii_case_names_the_same_part(tmp_path):
    """ECMA-376 Part 2 (5th edition, December 2021) 6.2.2.3: "Equivalence
    of part names shall be determined by ASCII case-insensitive matching."
    The clause spells out the mapping -- 0x41-0x5A treated as 0x61-0x7A --
    and its Example 1 says a package holding "/a" cannot also hold "/A",
    because those are one name. 7.2.5.5 carries it into the physical
    package: a ZIP item maps to a part name with an *equivalent* prefix,
    not an identical one.

    So an archive written by a tool that capitalised the file and a
    document that did not are naming the same part, and reporting the
    part absent tells the author to add a file that is already there.
    """
    entry = "aasx/files/Manual.pdf"
    path = build_aasx(tmp_path / "p.aasx",
                      payload=_container_with("/aasx/files/manual.pdf"),
                      files=[(entry, b"%PDF-1.4 ")])
    assert "HD-D7" not in {f.id for f in runner.run(path).findings}
    with AasxPackage(path) as package:
        assert package.part("/aasx/files/manual.pdf") == entry


def test_an_archive_holding_a_directory_entry_still_answers_for_a_missing_part(tmp_path):
    """A ZIP tool may write directory entries -- `aasx/files/` -- and no
    part name is spelled like one, so such an entry has no canonical
    reading. Asked about a part the archive does not hold, the lookup
    reaches the case-folded index last of all, and building that index
    has to pass the directory entry by: folding its missing reading
    raises, and X4 asks exactly this question about every declared file
    the archive lacks. Measured before this was written: with the entry
    folded anyway, the whole suite still passed -- no archive in it held
    a directory entry.
    """
    path = build_aasx(tmp_path / "d.aasx", files=[("aasx/files/", b""),
                                                  ("aasx/files/manual.pdf", b"%PDF-1.4 ")],
                      suppl_targets=["aasx/files/manual.pdf"])
    with AasxPackage(path) as package:
        assert package.part("/aasx/files/missing.pdf") is None


def test_the_character_check_ends_where_ascii_ends():
    """RFC 3986 names the characters a part name may carry, all of them
    ASCII, and what lies outside ASCII is recorded rather than refused.
    DEL is the last ASCII character and is not one of them; U+0080 is the
    first that is not ASCII. That edge is one comparison, and `< 127`,
    `<= 128` and `< 129` all passed the suite."""
    from aas_submodel_validate.container import part_name_problem

    assert "'\\x7f'" in (part_name_problem("aasx/files/a\x7fb.pdf") or "")
    assert part_name_problem("aasx/files/a\x80b.pdf") is None


def test_the_case_folding_is_ascii_and_stops_there(tmp_path):
    """The clause says ASCII, and names the two code point ranges. It
    does not say Unicode: the same subclause puts NFC/NFD collisions
    under "should not", as a recommendation to package authors, and
    never says two names differing outside ASCII are one name.

    `str.lower()` would fold them anyway -- 'E WITH ACUTE' to its small
    form -- and answer that a part the archive does not hold is present.
    """
    path = build_aasx(tmp_path / "p.aasx",
                      files=[("aasx/files/\u00c9.pdf", b"%PDF-1.4 ")])
    with AasxPackage(path) as package:
        assert package.part("aasx/files/\u00c9.pdf") == "aasx/files/\u00c9.pdf"
        assert package.part("/aasx/files/\u00e9.pdf") is None

def test_the_archive_own_case_still_wins_over_the_folded_reading(tmp_path):
    """Case folding is the last question asked, not the first.

    An archive holding both spellings is already outside 6.2.2.3, which
    says a package may not hold two parts with equivalent names. It can
    still be read: each document value that names one of them exactly
    gets that one. Folding earlier would merge two files the way folding
    whitespace earlier once took the archive's own spelling out of reach
    (docs/divergences.md #18), and the fix there was the ordering this
    keeps.
    """
    path = build_aasx(tmp_path / "p.aasx",
                      files=[("aasx/files/Manual.pdf", b"UPPER"),
                             ("aasx/files/manual.pdf", b"lower")])
    with AasxPackage(path) as package:
        assert package.part("/aasx/files/Manual.pdf") == "aasx/files/Manual.pdf"
        assert package.part("/aasx/files/manual.pdf") == "aasx/files/manual.pdf"
        #: Neither spelling is in the archive, so the folded index
        #: answers -- in the archive's own write order, which is the only
        #: order it has. Pinned because the sibling index resolved a
        #: clash by hash seed once, and the same archive then answered
        #: differently on different runs.
        assert package.part("/aasx/files/MANUAL.pdf") == "aasx/files/Manual.pdf"
