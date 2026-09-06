"""The container and the File rule answer the same question the same way.

`docs/divergences.md` #18 records four archives where they did not.
There is one normaliser, and there were two ways in: the File rule folded
the value's surrounding whitespace and then asked, while `part` asked
literally first and interpreted after. The order is not a detail -- it
decides which entry a value lands on when an archive holds two spellings
of one name, and in the fourth case it decided whether the report agreed
with itself.

Three of the four archives here hold the file their value names, and a
finding on those is this reader inventing a defect in a package that has
what it says it has. The fourth is the opposite case and is here on
purpose: a value of `../evil.step` names no part at all, the archive
holds the file it would reach, and the finding is required. Both
directions, because the repair for #18 could have been made by
loosening until everything resolved.
"""
from __future__ import annotations

import copy
import json
import zipfile

from aas_submodel_validate import runner
from aas_submodel_validate.container import AasxPackage
from builders import CONTENT_TYPES, ORIGIN_REL, SPEC_REL, hd_env, rels

VALUE = "/aasx/files/manual.pdf"


def _archive(path, entries, value=None, suppl=()):
    """An archive holding `entries`, whose DigitalFile names `value`."""
    blob = json.dumps(copy.deepcopy(hd_env()))
    if value is not None:
        blob = blob.replace(VALUE, value)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
        archive.writestr("aasx/aasx-origin", b"")
        archive.writestr(
            "aasx/_rels/aasx-origin.rels",
            rels([(SPEC_REL, "/aasx/env.json")] + list(suppl)),
        )
        archive.writestr("aasx/env.json", blob.encode("utf-8"))
        for name, data in entries:
            archive.writestr(name, data)
    return str(path)


def _report(path):
    return {f.id: f for f in runner.run(path).findings}


def test_a_value_that_climbs_out_of_the_package_is_refused_by_both(tmp_path):
    """#18 case 1. `../evil.step` is not a part name however it is read,
    and neither way in may resolve it -- the file it would reach is
    outside the package."""
    path = _archive(
        tmp_path / "climb.aasx",
        [("aasx/files/manual.pdf", b"%PDF-1.4"), ("evil.step", b"solid")],
        value="../evil.step",
    )
    with AasxPackage(path) as package:
        assert package.part("../evil.step") is None
    finding = _report(path)["HD-D7"]
    assert "not a part name" in finding.violation.message


def test_two_spellings_of_one_name_land_on_the_same_entry_both_ways(tmp_path):
    """#18 case 2. The archive holds `files/x.step` and `/files/x.step`.
    A value naming one of them exactly must reach that one, and the rule
    must agree with the container about which."""
    path = _archive(
        tmp_path / "both.aasx",
        [("files/x.step", b"plain"), ("/files/x.step", b"absolute")],
        value="/files/x.step",
    )
    with AasxPackage(path) as package:
        assert package.part("/files/x.step") == "/files/x.step"
        assert package.part("files/x.step") == "files/x.step"
    assert "HD-D7" not in _report(path)


def test_a_relationship_and_a_file_value_resolve_the_same_spelling_alike(tmp_path):
    """#18 case 3. One spelling, asked of both ways in: the supplemental
    relationship and the File value name the same part with the same
    surrounding whitespace. Either both find it or neither does; what
    #18 recorded is one finding it while the other reported it absent."""
    entry = "aasx/files/manual.pdf"
    spelling = " /aasx/files/manual.pdf"
    path = _archive(
        tmp_path / "rel.aasx",
        [(entry, b"%PDF-1.4")],
        value=spelling,
        suppl=[("http://admin-shell.io/aasx/relationships/aasx-suppl", spelling)],
    )
    with AasxPackage(path) as package:
        resolved = package.part(spelling)
    report = _report(path)
    assert resolved == entry, resolved
    assert "HD-D7" not in report
    assert "X4" not in report


def test_the_report_cannot_call_a_part_absent_that_the_container_hands_back(tmp_path):
    """#18 case 4, the sharpest, and the reason the other three are worth
    closing. The archive holds an entry whose name ends in a space and
    the value names it exactly. `part` returns that entry. The rule folded
    the value before asking, so the literal step never saw the spelling
    the archive holds, and the report said the container holds no part at
    a value the container resolves. A reader cannot act on a document
    that contradicts itself in one page."""
    entry = "aasx/files/manual.pdf "
    value = "/aasx/files/manual.pdf "
    path = _archive(tmp_path / "ws.aasx", [(entry, b"%PDF-1.4")], value=value)
    with AasxPackage(path) as package:
        resolved = package.part(value)
    assert resolved == entry, resolved
    report = _report(path)
    assert "HD-D7" not in report, report["HD-D7"].violation.message


def test_a_wrong_identifier_takes_rules_out_of_the_run_by_the_measured_amount():
    """`docs/divergences.md` #23 says a row whose identifier does not
    match is never entered and its subtree's rules leave the run with it.
    It gives a number, and nothing recomputed the number.

    `tools/scope_silence.py` does. Pinned here so the entry and the tool
    move together, and because the split between the two shapes is the
    argument for the near-miss lint: a version bump -- the last character
    -- leaves every affected row still speaking through the lint, and a
    typo inside a path segment leaves 18 of them saying nothing at all.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import scope_silence

    tried, mute, lint_only, _detail, absent = scope_silence.measure("tail")
    assert (tried, len(mute), len(lint_only)) == (69, 0, 18)
    assert len(absent) == 17, "the fixtures now carry a different set of rows"

    tried, mute, lint_only, _detail, absent = scope_silence.measure("middle")
    assert (tried, len(mute), len(lint_only)) == (69, 18, 0)

    # Every row is really mutated. The first version substituted a fixed
    # `9`, so ten identifiers ending `...9#00N` came back unchanged --
    # and an unmodified fixture produces no new finding, so all of them
    # were counted among the rows that "say nothing at all". Seven of a
    # published twenty-four were rows with no typo in them.
    from aas_submodel_validate.rules import dbp_tables, hd_tables, td_tables

    for tables in (hd_tables, td_tables, dbp_tables):
        for row in tables.ROWS:
            if row.get("sid"):
                for mode in ("tail", "middle"):
                    assert scope_silence.drift(row["sid"], mode) != row["sid"], (
                        row["id"], mode)


def test_the_rows_a_middle_typo_silences_are_identifiers_nothing_can_separate():
    """Why the other half of #23 is not built, kept as a measurement.

    The proposal was to extend the near-miss lint to structural
    similarity -- an element one segment off a row's identifier is
    probably a typo, and a manufacturer's own identifier is near
    nothing. That works for an IRI. It cannot work here.

    Seventeen of the eighteen rows a middle-segment typo silences are
    ECLASS IRDIs, and adjacent ECLASS codes are *different real
    properties*: `0173-1#02-ABH994#003` and `0173-1#02-ABH995#003` are
    both rows of these tables. So the typo and the legitimate neighbour
    sit at the same distance, and no bound separates them without an
    ECLASS dictionary this project deliberately does not carry.

    Kept as a test rather than a sentence so the argument fails loudly
    if it stops being true: templates whose IRDIs are far apart would
    make the extension worth revisiting.
    """
    import itertools
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import scope_silence
    from aas_submodel_validate.rules import dbp_tables, hd_tables, td_tables

    rows = {row["id"]: row for tables in (hd_tables, td_tables, dbp_tables)
            for row in tables.ROWS}
    _tried, mute, _lint, _detail, _absent = scope_silence.measure("middle")
    irdis = [rid for rid in mute if rows[rid]["sid"].startswith("0173-1#")]
    assert len(mute) == 18 and len(irdis) == 17, (len(mute), len(irdis))

    def apart(left, right):
        return sum(1 for a, b in zip(left, right) if a != b) + abs(len(left) - len(right))

    published = sorted({row["sid"] for row in rows.values()
                        if row.get("sid", "").startswith("0173-1#")})
    neighbours = [(a, b) for a, b in itertools.combinations(published, 2) if apart(a, b) == 1]
    assert neighbours, (
        "no two published IRDIs are one character apart any more -- the "
        "reason #23's second half was left unbuilt may no longer hold")
    assert len(neighbours) >= 30, len(neighbours)
