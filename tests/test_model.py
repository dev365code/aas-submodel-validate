"""Findings carry their remedy, and severity follows the spec's own words.

And the report has a shape somebody else's program reads. `schemaVersion`
is a promise to that program, and it was a promise nothing kept: every
key in the document could be renamed, and the version itself could be
renamed or bumped, with the suite green.
"""
import json

import pytest

from aas_submodel_validate import __version__
from aas_submodel_validate.model import Finding, Report, Rule, Severity, Violation


def _rule(prio="MUST", fix="do the right thing"):
    return Rule(id="T1", kind="template", prio=prio, title="test rule",
                spec=None, fn=lambda ctx: (), fix=fix)


def test_severity_follows_the_specification_keyword():
    assert _rule("MUST").severity is Severity.ERROR
    assert _rule("SHALL").severity is Severity.ERROR
    assert _rule("SHOULD").severity is Severity.WARNING
    assert _rule("MAY").severity is Severity.INFO


def test_a_violations_own_fix_beats_the_rules_standing_advice():
    rule = _rule(fix="the general remedy")
    assert Finding(rule, Violation("m")).fix == "the general remedy"
    assert Finding(rule, Violation("m", fix="this specific one")).fix == "this specific one"


def test_findings_serialise_for_machines():
    entry = Finding(_rule(), Violation("wrong", subject="urn:x", detail="saw 2")).as_dict()
    assert entry["rule"] == "T1"
    assert entry["severity"] == "error"
    assert entry["subject"] == "urn:x"


#: The shape `schemaVersion: 1` names, written out rather than read off
#: the code. A contract derived from the thing it constrains constrains
#: nothing: `set(report.as_dict())` agrees with whatever is emitted,
#: including a typo.
#:
#: Adding a key is compatible and leaves the version where it is -- a
#: consumer that does not know the key reads what it read before.
#: Renaming or removing one is not. Both changes pass through this list,
#: which is the whole point: somebody has to say so.
#: Two lists, because one cannot tell a compatible change from a
#: breaking one. With a single golden, renaming `spec` and adding
#: `generatedBy` are the same diff -- edit the code, edit the list, stay
#: on version 1 -- and only one of those is allowed to.
#:
#: This is what `schemaVersion: 1` promises will not disappear. A diff
#: touching it is a diff that has to answer for the version.
#:
#: Everything shape 1 ships is in here, `toolVersion`, `options` and
#: `complete` included. They were not, and the omission was the same bug
#: in a smaller font: a floor that lists only what existed the day it was
#: written protects less with every key added, and renaming
#: `options.strictMeta` to `options.strict` would have been three green
#: lines. A consumer reading `report.options.strictMeta` gets `undefined`
#: -- falsy -- and a strict run silently reads as permissive.
V1_REQUIRED = {"schemaVersion", "toolVersion", "path", "ok", "options",
               "summary", "notes", "findings", "provenance"}
#: The evidence envelope, reserved rather than implemented.
#:
#: A report becomes evidence only when it says *what* was judged, *by
#: which engine*, and *who vouches for it* -- and the third is not this
#: tool's to answer. Signing belongs to the organisation that issued the
#: document, the way a declaration of conformity does; a validator that
#: signed its own verdicts would be selling an assurance it has no
#: standing to give. So the shape is fixed here, at the release that
#: fixes the shape, and two of its three fields are `null` until
#: somebody with standing fills them.
#:
#: `inputSha256` is not reserved -- it is computed, because the one thing
#: this tool can say for certain is which bytes it read.
V1_PROVENANCE = {"inputSha256", "engine", "envelope"}
V1_SUMMARY = {"errors", "warnings", "info", "rulesChecked", "complete", "judged"}
V1_OPTIONS = {"profile", "strictMeta", "allowUnmatched"}
V1_FINDING = {"rule", "kind", "severity", "priority", "message", "subject",
              "detail", "fix", "title", "spec"}

#: Keys added after shape 1 shipped. A key lands here alone -- a consumer
#: that does not know it reads what it read before, so the version stays
#: at 1 -- and moves up into the lists above at the release that ships
#: it, because from then on renaming it breaks somebody. That promotion
#: is the step nobody was told to take; it is written down here because
#: the floor is worthless without it.
ADDED_SINCE_V1 = set()
ADDED_SINCE_V1_PROVENANCE = set()
ADDED_SINCE_V1_SUMMARY = set()
ADDED_SINCE_V1_OPTIONS = set()
ADDED_SINCE_V1_FINDING = set()

#: And this is everything the document carries today.
REPORT_KEYS = V1_REQUIRED | ADDED_SINCE_V1
SUMMARY_KEYS = V1_SUMMARY | ADDED_SINCE_V1_SUMMARY
OPTIONS_KEYS = V1_OPTIONS | ADDED_SINCE_V1_OPTIONS
FINDING_KEYS = V1_FINDING | ADDED_SINCE_V1_FINDING
PROVENANCE_KEYS = V1_PROVENANCE | ADDED_SINCE_V1_PROVENANCE


def _report():
    """One error, two warnings, three info.

    Distinct and non-zero, because a golden with two zeroes in it cannot
    see them swapped: `errors`/`warnings` was caught and `warnings`/`info`
    was not, and the difference was that one pair happened to differ."""
    report = Report(path="machine-docs.json")
    report.findings = (
        [Finding(_rule("MUST"), Violation("wrong", subject="urn:x",
                                          detail="saw 2", fix="mend it"))]
        + [Finding(_rule("SHOULD"), Violation("iffy %d" % n)) for n in range(2)]
        + [Finding(_rule("MAY"), Violation("noted %d" % n)) for n in range(3)])
    report.checked = 123
    report.notes = ["something worth saying once"]
    return report


def test_the_report_has_the_shape_version_one_names():
    document = _report().as_dict()
    # What may not go, and then what is actually there. A rename passes
    # the second on its own -- edit the code, edit the list -- and fails
    # the first, which is where the version question gets asked.
    assert set(document) >= V1_REQUIRED
    assert set(document["summary"]) >= V1_SUMMARY
    assert set(document["findings"][0]) >= V1_FINDING
    assert set(document["options"]) >= V1_OPTIONS
    assert set(document["provenance"]) >= V1_PROVENANCE
    assert set(document) == REPORT_KEYS
    assert set(document["summary"]) == SUMMARY_KEYS
    assert set(document["findings"][0]) == FINDING_KEYS
    assert set(document["options"]) == OPTIONS_KEYS
    assert set(document["provenance"]) == PROVENANCE_KEYS


def test_the_summary_counts_what_it_says_it_counts():
    """Names and types leave the numbers free: swapping `errors` and
    `warnings`, or counting findings where the registry was meant, was
    invisible. A consumer gates a build on these."""
    document = _report().as_dict()
    assert document["summary"] == {"errors": 1, "warnings": 2, "info": 3,
                                   "rulesChecked": 123, "complete": True,
                                   "judged": True}


def test_the_report_says_what_was_asked_of_it():
    """The same file comes back `ok` under one set of flags and not under
    another. Two documents said nothing about which run they were, so a
    reader comparing them had the prose of a finding's message and
    nothing else."""
    report = _report()
    report.profile, report.strict_meta, report.allow_unmatched = "02035-2", True, False
    document = report.as_dict()
    assert document["options"] == {"profile": "02035-2", "strictMeta": True,
                                   "allowUnmatched": False}
    assert document["toolVersion"] == __version__
    # The documented default, which the case above never reaches: a run
    # with no --profile publishes `null`, not the empty string a reader
    # would have to treat as a profile named "".
    assert _report().as_dict()["options"]["profile"] is None


def test_the_notes_reach_the_document():
    """`notes` is where a --profile that matched nothing and an
    --allow-unmatched pass are reported, and only its type was asserted:
    emitting `[]` for every run, forever, was green."""
    assert _report().as_dict()["notes"] == ["something worth saying once"]


def test_the_version_says_which_shape_it_is():
    """A version nobody asserts is a number that moves without meaning
    anything -- and this one could be bumped, or renamed away, with
    everything green."""
    assert _report().as_dict()["schemaVersion"] == 1


def test_the_report_says_what_the_types_promise():
    """Key names alone let a boolean become a string. A consumer reading
    `ok` branches on it."""
    document = _report().as_dict()
    assert isinstance(document["ok"], bool)
    assert isinstance(document["path"], str)
    assert isinstance(document["notes"], list)
    assert isinstance(document["findings"], list)
    assert isinstance(document["summary"]["complete"], bool)
    assert isinstance(document["summary"]["judged"], bool)
    assert isinstance(document["toolVersion"], str)
    for counter in ("errors", "warnings", "info", "rulesChecked"):
        assert isinstance(document["summary"][counter], int), counter
    # The flags especially. `1 == True` in Python, so a value assertion
    # comparing the options dict passes while `json.dumps` writes
    # `"strictMeta": 1` and a consumer testing `=== true` breaks.
    for flag in ("strictMeta", "allowUnmatched"):
        assert isinstance(document["options"][flag], bool), flag


def test_the_report_survives_the_trip_through_json():
    """The point of the shape is that it leaves this process. A value the
    encoder refuses is a report nobody receives."""
    document = _report().as_dict()
    assert json.loads(json.dumps(document)) == document


@pytest.mark.parametrize("prio,severity", (
    ("MUST", "error"), ("SHALL", "error"), ("SHOULD", "warning"), ("MAY", "info")))
def test_a_findings_severity_and_priority_are_both_published(prio, severity):
    """Two fields, not one: the severity is this project's reading and the
    priority is the specification's word for it. A consumer that wants to
    re-derive the first from the second needs both, and dropping either
    leaves it guessing."""
    entry = Finding(_rule(prio), Violation("m")).as_dict()
    assert entry["severity"] == severity
    assert entry["priority"] == prio


def test_a_fresh_reports_defaults_are_the_documented_ones():
    """What a report says when nobody set anything: zero rules checked
    -- a refused input reaches serialisation with this default, so `-1`
    here would ship -- and both flags off, which is what the README says
    a bare run means."""
    document = Report(path="p").as_dict()
    assert document["summary"]["rulesChecked"] == 0
    assert document["options"] == {"profile": None, "strictMeta": False,
                                   "allowUnmatched": False}


def test_a_run_with_warnings_does_not_wear_the_clean_banner():
    """`render`'s clean line is guarded three ways -- ok, no findings, no
    notes. The first is implied by the second (a failing run has the
    error finding that failed it), so the guard that can actually decide
    is "no findings": a warnings-only run is `ok` and must still show its
    findings, not the sentence that says there were none."""
    from aas_submodel_validate.report import render
    report = _report()   # one error, two warnings, three info
    report.findings = [f for f in report.findings
                       if str(f.severity) != "error"]
    report.notes = []    # or the notes guard hides the findings guard
    text = render(report)
    assert "ok —" not in text
    assert "warning" in text


def test_the_terminal_gets_no_control_bytes_but_the_tab():
    """`_safe` keeps tabs and escapes all three control ranges. The first
    version kept everything from 0x20 up, which is only C0: DEL walked
    through, and so did C1 -- and 0x9B alone is CSI on a terminal
    honouring 8-bit controls, the byte class the function exists to
    stop. Printable non-ASCII stays itself."""
    from aas_submodel_validate.report import _safe
    assert _safe("a\tb") == "a\tb"
    assert _safe("a\x07b") == "a\\x07b"
    assert _safe("a\x7fb") == "a\\x7fb"
    assert _safe("a\x9bb") == "a\\x9bb"
    assert _safe("caf\xe9") == "caf\xe9"


def test_the_clean_banner_spells_ok_with_an_em_dash():
    """The positive anchor for the two `"ok —" not in` assertions above
    and in the CLI tests: if the banner ever respells itself, this goes
    red instead of those going quietly vacuous."""
    from aas_submodel_validate.report import render
    report = Report(path="clean.json")
    report.checked = 123
    assert render(report).startswith("ok \u2014 ")


def test_the_report_names_the_bytes_it_judged(tmp_path):
    """The one thing this tool can say for certain about provenance.

    A report that says "this file failed" and does not say which bytes
    it read is an assertion about a filename, and filenames are not
    evidence. The digest is of the file as it arrived -- computed, not
    reserved -- and two reports of one file agree on it."""
    import hashlib

    from aas_submodel_validate import runner
    from builders import hd_env
    path = tmp_path / "env.json"
    payload = json.dumps(hd_env()).encode("utf-8")
    path.write_bytes(payload)
    document = runner.run(path).as_dict()
    assert document["provenance"]["inputSha256"] == hashlib.sha256(payload).hexdigest()
    assert runner.run(path).as_dict()["provenance"] == document["provenance"]


def test_the_slots_nobody_may_fill_yet_are_null_and_stay_in_the_shape():
    """Reserved, not omitted. A consumer building an evidence pipeline
    needs to know the field will be there before anything can fill it --
    a key that appears later is a schema change, and a key that is
    always `null` is a promise. Signing is deliberately not this tool's:
    it belongs to whoever issued the document."""
    document = _report().as_dict()
    assert document["provenance"]["engine"] is None
    assert document["provenance"]["envelope"] is None


def test_a_report_of_nothing_still_names_its_provenance():
    """A `Report` built without a file -- the shape every unit test uses
    -- must still carry the block, or a consumer has to branch on
    whether the digest was computable."""
    document = Report(path="nowhere.json").as_dict()
    assert set(document["provenance"]) == PROVENANCE_KEYS
    assert document["provenance"]["inputSha256"] is None

