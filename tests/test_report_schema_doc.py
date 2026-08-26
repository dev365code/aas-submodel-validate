"""The JSON report has a documented shape, and the document is checked.

`schemaVersion: 1` is a promise to somebody else's program, and until
this file existed the promise was unwritten: `-f json` emitted eleven
keys nothing described, so a consumer had to read the source to learn
what `complete` meant or that `subject` could be null. A shape nobody
can look up is a shape nobody can depend on.

And a written one rots. Every key here is compared against what the
report actually emits, in both directions -- a key added to the report
and not the document is undocumented, and a key in the document that
the report does not emit is a lie somebody will code against.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from aas_submodel_validate import __version__, rules  # noqa: F401 - registers
from aas_submodel_validate.model import (
    KINDS,
    PRIO_SEVERITY,
    Finding,
    Report,
    Rule,
    Severity,
    Violation,
)
from aas_submodel_validate.registry import all_rules
from aas_submodel_validate.runner import run
from builders import hd_env

DOC = (Path(__file__).resolve().parents[1] / "docs/report-schema.md").read_text("utf-8")


def _sections(text):
    """`## heading` -> the text under it, headings normalised to plain
    words so the document may spell them `` `options` `` or not."""
    parts = re.split(r"^## +(.+)$", text, flags=re.MULTILINE)[1:]
    return {heading.strip().strip("`").lower(): body
            for heading, body in zip(parts[::2], parts[1::2])}


def _documented_keys(section):
    """The first column of the one table in a section."""
    return {match.group(1) for match in
            re.finditer(r"^\| *`(\w+)` *\|", section, flags=re.MULTILINE)}


def _description_of(section, key):
    """The description cell of the one table row for `key`.

    Not the whole section, and not the whole row: read off the section,
    dropping `lint` from the row that lists the kinds passed, because the
    prose above the table names the kinds too for a different reason. Not
    the row either, because the row opens with the key's own name.
    """
    row = next(line for line in section.splitlines()
               if line.startswith("| `%s` " % key))
    return row.split("|")[3]


SECTIONS = _sections(DOC)


def _report():
    rule = Rule(id="T1", kind="template", prio="MUST", title="a rule",
                spec="IDTA 02004-2-0 §2.8", fn=lambda ctx: (), fix="mend it")
    report = Report(path="machine-docs.aasx")
    report.findings = [Finding(rule, Violation("wrong", subject="urn:x",
                                               detail="saw 2"))]
    return report.as_dict()


def test_every_key_the_report_emits_is_described_and_no_others():
    document = _report()
    for heading, emitted in (("the top level", set(document)),
                             ("options", set(document["options"])),
                             ("summary", set(document["summary"])),
                             ("findings", set(document["findings"][0]))):
        assert _documented_keys(SECTIONS[heading]) == emitted, heading


def test_the_vocabularies_are_the_codes():
    """Three closed sets a consumer branches on, each read off its own
    row and compared as a set. A value added to the code and not here
    leaves a reader with a case their switch statement has no arm for; a
    value here and not in the code is an arm that never runs."""
    findings = SECTIONS["findings"]
    for key, vocabulary in (("kind", set(KINDS)),
                            ("severity", {str(s) for s in Severity}),
                            ("priority", set(PRIO_SEVERITY))):
        quoted = set(re.findall(r"`([A-Za-z][A-Za-z ]*)`", _description_of(findings, key)))
        assert quoted == vocabulary, key


def _a_real_finding(tmp_path):
    """A file with one thing wrong in it, and the finding it draws."""
    env = copy.deepcopy(hd_env())
    documents = env["submodels"][0]["submodelElements"][0]
    for child in documents["value"][0]["value"][2]["value"][0]["value"]:
        if child.get("idShort") == "StatusSetDate":
            child["value"] = "06.02.2020"
    path = tmp_path / "machine-docs.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return next(f.as_dict() for f in run(path).findings if f.id == "HD-D8")


def test_the_sample_is_a_report_of_the_shape_it_documents(tmp_path):
    """A hand-written sample is the part most likely to go stale and the
    part a reader copies, so none of it is taken on trust: the shape
    against the live shape, and the finding against one this tool
    actually produces.

    The finding, because keys alone let the values drift. The first draft
    of this sample invented a message, a subject and a detail that no run
    has ever emitted -- a reader matching on any of them would have
    matched nothing."""
    sample = json.loads(re.search(r"```json\n(.*?)\n```", DOC, re.S).group(1))
    document = _report()
    assert set(sample) == set(document)
    for section in ("options", "summary"):
        assert set(sample[section]) == set(document[section])
    assert sample["findings"] == [_a_real_finding(tmp_path)]
    assert sample["schemaVersion"] == document["schemaVersion"] == 1
    assert sample["toolVersion"] == __version__
    assert sample["summary"]["rulesChecked"] == len(all_rules())
    # And the counts agree with the findings printed beside them, so the
    # sample cannot show one error and claim none.
    for severity, counter in (("error", "errors"), ("warning", "warnings"),
                              ("info", "info")):
        shown = [f for f in sample["findings"] if f["severity"] == severity]
        assert sample["summary"][counter] == len(shown), counter
    assert sample["ok"] == (sample["summary"]["errors"] == 0)
