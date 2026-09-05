"""A change that cannot change what a file means must not move the verdict.

Every rule in this repository has a fixture and most have several, and
each one asks about the rule it was written for. None of them asks the
question here: take a file the tool already judged, change it in a way
the standards say carries no meaning, and see whether the answer is the
same.

That question matters because it is the shape of nearly every defect
this project shipped and then found. A language tag in the wrong case,
a trailing space, an encoding declaration naming a legacy code page, a
submodel that says it is a template -- each was a conformant file
refused, each was found by a person who happened to aim at that layer,
and each was found one at a time. A per-rule fixture cannot find them,
because none of them is about a rule: they are about what reaches the
rules, and they reach every rule at once.

Refusing a conformant file is the failure this project ranks worst --
a reader who is told their good file is bad has no second opinion to
consult, and the cost lands on the person who did the work correctly.
So the corpus is the point of this file. A new transformation is one
entry, and adding it exposes all 125 rules to it at once.

**An entry without a citation is an opinion.** This project's opinions
about what preserves conformance have been wrong before, in both
directions, so every entry names the clause that says the change
carries no meaning. An entry that cannot name one does not belong
here: asserting invariance the standards do not promise would build a
gate that blocks correct behaviour, which is the same defect this file
exists to catch, wearing the other hat.
"""
from __future__ import annotations

import re
import zipfile

import pytest

from aas_submodel_validate import runner
from builders import build_aasx, env_json, hd_env
from test_official_material import AASX_EXAMPLE


def _members(path):
    """(name, bytes) for every entry, in the order the archive holds them."""
    with zipfile.ZipFile(path) as archive:
        return [(item.filename, archive.read(item.filename))
                for item in archive.infolist()]


def _payload_of(members):
    """The entry holding the AAS environment.

    Found rather than named: hard-coding the example's payload path
    would make every entry below pass the day the example is replaced,
    which is the day they most need to run.
    """
    candidates = [(name, data) for name, data in members
                  if name.endswith(".xml") and "_rels/" not in name
                  and not name.startswith("[")]
    return max(candidates, key=lambda pair: len(pair[1]))[0]


def _repack(dest, members, *, compression=zipfile.ZIP_DEFLATED):
    with zipfile.ZipFile(dest, "w", compression) as archive:
        for name, data in members:
            archive.writestr(name, data)
    return dest


def _rewrite_payload(members, change):
    payload = _payload_of(members)
    out = []
    for name, data in members:
        if name == payload:
            data = change(data)
        out.append((name, data))
    return out


def _verdict(path):
    """What a reader is told, in the form two runs can be compared in.

    Ids and severities, not the rendered text: a transformation may
    legitimately move a byte offset or the spelling of a path inside a
    `detail`, and a gate that failed on those would be abandoned within
    a week. What it must not move is which rules fired, how loudly, and
    whether everything was read and judged.

    The relayed metamodel channel is counted apart from the rest. It is
    not this project's voice -- it is aas-core3's, passed through -- and
    the two can move for different reasons: a predicate upstream may
    read a value more narrowly than the standard the value comes from,
    and no repair here can change that. Folding them together would let
    an upstream change hide one of ours, or the reverse.
    """
    report = runner.run(str(path))
    ours = sorted((finding.id, str(finding.severity))
                  for finding in report.findings if finding.id != "META")
    relayed = sum(1 for finding in report.findings if finding.id == "META")
    return ours, relayed, report.complete, report.checked


# --------------------------------------------------------------------------
# Transformations. Each one: (name, why it preserves conformance, apply).
# --------------------------------------------------------------------------

def _declare_encoding(encoding):
    def apply(members):
        def change(data):
            text = data.decode("utf-8-sig")
            text = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", text)
            text = '<?xml version="1.0" encoding="%s"?>\n' % encoding + text
            return text.encode(encoding, "xmlcharrefreplace")
        return _rewrite_payload(members, change)
    return apply


def _language_tags(fold):
    def apply(members):
        def change(data):
            text = data.decode("utf-8-sig")
            text = re.sub(r"<language>([^<]*)</language>",
                          lambda m: "<language>%s</language>" % fold(m.group(1)),
                          text)
            return text.encode("utf-8")
        return _rewrite_payload(members, change)
    return apply


def _add_bom(members):
    return _rewrite_payload(
        members, lambda data: data if data.startswith(b"\xef\xbb\xbf")
        else b"\xef\xbb\xbf" + data)


def _reverse_order(members):
    return list(reversed(members))


VARIATIONS = [
    (
        "the encoding is declared instead of left to the default",
        "XML 1.0 §4.3.3 -- an entity with no declaration and no mark is "
        "UTF-8, so writing UTF-8 out says what was already true.",
        _declare_encoding("utf-8"),
    ),
    (
        "the payload declares ISO-8859-1 and is written in it",
        "XML 1.0 §4.3.3 -- a document may be written in any encoding it "
        "declares. 0.1.0 refused this outright and told the author to fix "
        "syntax that was not wrong.",
        _declare_encoding("iso-8859-1"),
    ),
    (
        "the payload declares windows-1252 and is written in it",
        "XML 1.0 §4.3.3, as above. This is what a German or Korean "
        "Windows editor writes without being asked.",
        _declare_encoding("windows-1252"),
    ),
    (
        "the payload is UTF-16",
        "XML 1.0 §4.3.3 names UTF-16 beside UTF-8 as the two every "
        "processor must read.",
        _declare_encoding("utf-16"),
    ),
    (
        "the payload carries a UTF-8 byte order mark",
        "XML 1.0 §F -- the mark is an encoding signature, not content. "
        "Real AASX files carry one on their relationship parts.",
        _add_bom,
    ),
    (
        "every language tag is upper case",
        "RFC 5646 §2.1.1 -- subtags 'are to be treated as case "
        "insensitive', and conventions for capitalisation 'MUST NOT be "
        "taken to carry meaning'. See docs/divergences.md #35.",
        _language_tags(str.upper),
    ),
    (
        "every language tag is title case",
        "RFC 5646 §2.1.1, as above. `En` was a finding on a conformant "
        "file in 0.1.0, printed above a line reading 'languages present: "
        "En, de'.",
        _language_tags(str.title),
        # Ours is silent on `En`; the channel we relay is not, and this
        # is the count of how loudly. aas-core3's `is_bcp_47_for_english`
        # is `^(en|EN)(-.*)?$`, so `En` and `eN` fail it while `EN`
        # passes -- measured, not read off the pattern. `HD-D4` calls
        # that same function on a folded tag and so agrees with RFC 5646
        # (docs/divergences.md #35); the relay calls it on the tag as
        # written, and nothing here can reach inside it.
        #
        # Left standing rather than filtered. The channel exists to say
        # "this is upstream's reading, not ours", it is a warning that
        # does not move the exit code, and `--meta info` is the operator's
        # say over it. Suppressing a delegated verdict on our own reading
        # of the clause is a policy this release has not argued for.
        #
        # If this number falls, upstream has folded the case: delete the
        # exception and let the row assert zero like the others.
        65,
    ),
    (
        "the archive members are stored in the reverse order",
        "The order of entries in a ZIP central directory carries no "
        "meaning; a reader is directed to parts by relationships, never "
        "by position.",
        _reverse_order,
    ),
]


@pytest.mark.parametrize(
    "why,apply,relayed_delta",
    [pytest.param(entry[1], entry[2], entry[3] if len(entry) > 3 else 0, id=entry[0])
     for entry in VARIATIONS])
def test_a_change_that_carries_no_meaning_does_not_move_the_verdict(
        tmp_path, why, apply, relayed_delta):
    base_ours, base_relayed, base_complete, base_checked = _verdict(AASX_EXAMPLE)
    assert base_ours, "the example draws findings; a silent baseline proves nothing"
    varied = _repack(tmp_path / "varied.aasx", apply(_members(AASX_EXAMPLE)))
    ours, relayed, complete, checked = _verdict(varied)
    assert ours == base_ours, why
    assert (complete, checked) == (base_complete, base_checked), why
    # Asserted, never ignored: a row that expects the relayed channel to
    # move says by how much, so an upstream repair fails here and gets
    # noticed rather than quietly widening what this gate tolerates.
    assert relayed - base_relayed == relayed_delta, (
        "the relayed channel moved by %d, not the %d this row expects -- %s"
        % (relayed - base_relayed, relayed_delta, why))


def test_the_same_bytes_repacked_are_the_control(tmp_path):
    """The control the eight above are read against.

    Without it a failure cannot be told apart from `_repack` itself
    changing something -- and every variation goes through `_repack`.
    """
    repacked = _repack(tmp_path / "same.aasx", _members(AASX_EXAMPLE))
    assert _verdict(repacked) == _verdict(AASX_EXAMPLE)


def test_stored_entries_are_read_as_deflated_ones_are(tmp_path):
    """Compression method is not content. Kept out of the table above
    because it is a property of `_repack`, not of the members."""
    stored = _repack(tmp_path / "stored.aasx", _members(AASX_EXAMPLE),
                     compression=zipfile.ZIP_STORED)
    assert _verdict(stored) == _verdict(AASX_EXAMPLE)


# --------------------------------------------------------------------------
# Conformant shapes. Not a transformation of a judged file -- a container
# that is correct by construction, where a named rule must stay silent.
# --------------------------------------------------------------------------

#: Every shape an aas-suppl relationship's target takes, and whether X4
#: -- "this names a part the archive does not hold" -- has a question to
#: ask about it.
#:
#: Two guards answer these, and the table is built so each row is the
#: only row one of them answers. That is not tidiness: with a single
#: external row, deleting *either* guard left the whole suite green,
#: because whichever survived covered for the one removed. A guard no
#: test can tell the absence of is a guard the next reader deletes.
SUPPL_SHAPES = [
    (
        "an external target, spelled the way OPC spells one",
        {"suppl_external": ["http://example.com/manual.pdf"]},
        False,
        "ECMA-376 Part 2: `TargetMode=\"External\"` says the target is "
        "not a part of this package, so there is no part to hold. A "
        "supplementary file kept on a server is written exactly this "
        "way and the package is conformant.",
    ),
    (
        "an external target that is relative",
        {"suppl_external": ["../docs/manual.pdf"]},
        False,
        "Also conformant -- OPC does not require an external target to "
        "be absolute. Only the declared mode answers this row: there is "
        "no scheme in it for the second guard to read.",
    ),
    (
        "an absolute URI with no TargetMode declared",
        {"suppl_verbatim": ["http://example.com/manual.pdf"]},
        False,
        "Not conformant -- OPC asks for the mode -- but the question "
        "this rule puts still does not arise, because there is no part "
        "name here either. Only the scheme answers this row: nothing "
        "was declared for the first guard to read.",
    ),
    (
        "a part name the archive does not hold",
        {"suppl_targets": ["aasx/files/absent.pdf"]},
        True,
        "The question the rule exists for. Without this row every row "
        "above is satisfied by a rule that says nothing at all.",
    ),
]


@pytest.mark.parametrize(
    "kwargs,expected,why",
    [pytest.param(kwargs, expected, why, id=name)
     for name, kwargs, expected, why in SUPPL_SHAPES])
def test_x4_asks_only_where_there_is_a_part_to_hold(
        tmp_path, kwargs, expected, why):
    path = build_aasx(tmp_path / "suppl.aasx", payload=env_json(hd_env()),
                      **kwargs)
    fired = {finding.id for finding in runner.run(str(path)).findings}
    assert ("X4" in fired) is expected, why


@pytest.mark.parametrize(
    "kwargs",
    [pytest.param(kwargs, id=name) for name, kwargs, _, _ in SUPPL_SHAPES])
def test_no_finding_names_a_path_the_archive_could_not_hold(tmp_path, kwargs):
    """The half of the rule above that survives whatever is decided
    about whether X4 should speak.

    A URI resolved as though it were a relative part name becomes
    `aasx/http:/example.com/manual.pdf`: a well-formed part name, in no
    archive, in no file, and in nothing the reader wrote. It was printed
    on the `at` line under a remedy telling them to add that part or
    delete the relationship. Whatever any rule decides to say about
    these containers, it may not say it about a string like that.
    """
    path = build_aasx(tmp_path / "suppl.aasx", payload=env_json(hd_env()),
                      **kwargs)
    for finding in runner.run(str(path)).findings:
        printed = " ".join(str(part) for part in
                           (finding.violation.subject, finding.violation.detail)
                           if part)
        assert "http:" not in printed, printed
