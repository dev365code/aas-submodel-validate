"""Which element a loss is attributed to, and which losses stay unclaimed.

`summary.rulesNotAsked` has said *how many* rules a run never put since
0.1.2. It does not say which element left them unasked, and that is the
question a reader has as soon as the count is not zero. This adds it --
`summary.unmatchedElements`, one record per element, with the rules it kept
from being asked and the row its identifier resembles.

It adds *who*, and no new reason to claim a loss. A loss is still claimed
only where this reader already reported something that explains it -- the
near-miss lint fired in that scope, or a row matched an element of the
wrong kind -- because the template states a minimum rather than a
whitelist (docs/divergences.md #19) and an element of the supplier's own
explains no absence.

The half of #23 that stays open, stays open. A typo inside a path segment
that is not the last draws no near-miss and so hangs off nothing, and
widening the trigger to structural similarity is measured as unbuildable:
seventeen of the eighteen rows such a typo silences are ECLASS IRDIs, whose
adjacent codes are different real properties, so no bound separates a typo
from a legitimate neighbour without a dictionary this project does not
carry. The two tests at the end pin that consequence rather than papering
over it.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from aas_submodel_validate import runner
from builders import contact_env, dn_env

ROOT = Path(__file__).resolve().parents[1]

#: A version-style drift on a container: the last character of an
#: identifier, which is what a template version bump writes. The near-miss
#: lint recognises it, so the loss beneath it is reported -- and this is
#: where naming the element is the addition.
PHONE_TAIL = ("https://admin-shell.io/zvei/nameplate/1/0/ContactInformations/"
              "ContactInformation/PhonX")

#: A typo inside a segment that is not the last. Draws no near-miss (#22).
PHONE_MIDDLE = ("https://admin-shell.io/zvei/nameplate/1/0/ContactInformations/"
                "ContactInformaton/Phone")

#: The specification's spelling of 02002's `IPCommunication` collection,
#: which the vendored template does not carry (docs/divergences.md #51).
SPEC_IPCOMMUNICATION = ("https://admin-shell.io/zvei/nameplate/1/0/"
                        "ContactInformations/ContactInformation/IPCommunication/")


def _run(tmp_path, env, name="env.json", **options):
    path = tmp_path / name
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return runner.run(path, **options)


def _exit(tmp_path, env, name="env.json"):
    """The verdict as a caller sees it: the exit code lives in the CLI, and
    it is the CLI's answer this note must not move."""
    from aas_submodel_validate.cli import main
    path = tmp_path / name
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return main([str(path)])


def _drift(env, id_short, value):
    out = copy.deepcopy(env)
    for child in out["submodels"][0]["submodelElements"][0]["value"]:
        if child.get("idShort") == id_short:
            child["semanticId"]["keys"][0]["value"] = value
    return out


def test_a_reported_loss_now_names_the_element_behind_it(tmp_path):
    """`Phone` is `0..1`, so a drifted identifier violates no count; the
    walk never enters it and the mandatory `TelephoneNumber` beneath it is
    never asked. The near-miss lint already said the identifier was close
    to the template's. What is added is which element it was, and what its
    subtree took with it."""
    report = _run(tmp_path, _drift(contact_env(), "Phone", PHONE_TAIL))
    record = next(r for r in report.unmatched if r.seen == PHONE_TAIL)
    assert "CI-E10" in record.unasked      # the mandatory TelephoneNumber
    assert record.count == len(record.unasked)
    assert record.resembles and record.resembles.endswith("/Phone")
    assert record.subject, "a record with no subject names no element"


def test_the_note_is_machine_readable(tmp_path):
    """A pipeline that wants to act on this reads it, and no flag was added
    to the tool to make it a verdict."""
    document = _run(tmp_path, _drift(contact_env(), "Phone", PHONE_TAIL)).as_dict()
    assert "unmatchedElements" in document["summary"]
    entry = document["summary"]["unmatchedElements"][0]
    assert set(entry) >= {"subject", "seen", "rulesNotAskedHere"}
    assert entry["seen"] == PHONE_TAIL


def test_the_note_does_not_move_the_exit_code(tmp_path):
    """The template states a minimum, not a whitelist (#19), so an element
    matching no row is not a defect and must not turn a run red."""
    from aas_submodel_validate.cli import EXIT_OK

    assert _exit(tmp_path, contact_env(), "clean.json") == EXIT_OK
    drifted = _drift(contact_env(), "Phone", PHONE_TAIL)
    assert _run(tmp_path, drifted, "d.json").unmatched
    assert _exit(tmp_path, drifted, "drifted.json") == EXIT_OK


def test_a_conformant_file_with_a_supplier_element_says_nothing(tmp_path):
    """The case that made guessing wrong before (#19): an extra element of
    the supplier's own resembles no row, so nothing is attributed to it."""
    from aas_submodel_validate.cli import EXIT_OK

    env = copy.deepcopy(contact_env())
    env["submodels"][0]["submodelElements"][0]["value"].append({
        "idShort": "AcmeInternalCode", "modelType": "Property",
        "valueType": "xs:string", "value": "X-1",
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference",
                                 "value": "urn:acme:internal:code"}]}})
    assert not _run(tmp_path, env).unmatched
    assert _exit(tmp_path, env, "extension.json") == EXIT_OK


def test_a_middle_segment_typo_is_still_unclaimed_and_that_is_measured(tmp_path):
    """The open half of #23, pinned rather than papered over.

    A typo inside a segment that is not the last changes the identifier's
    head, so the near-miss comparison does not fire and nothing explains
    the loss -- and nothing is attributed to it here either, deliberately.
    Claiming it would mean treating any element one segment off a row as a
    misspelling, and seventeen of the eighteen rows this shape silences are
    ECLASS IRDIs whose adjacent codes are different real properties. This
    fails the day that argument stops being true, which is the point."""
    # Positive control first: without it this test also passes when the
    # whole mechanism is switched off, so it would pin the silence and not
    # the decision. The same element with a last-character drift IS
    # reported, which is what makes the absence below meaningful.
    live = _run(tmp_path, _drift(contact_env(), "Phone", PHONE_TAIL))
    assert live.unmatched, "the mechanism is off; the silence below proves nothing"

    report = _run(tmp_path, _drift(contact_env(), "Phone", PHONE_MIDDLE), "m.json")
    assert not report.unmatched, (
        "a middle-segment typo is claimed now; #23's measurement says no "
        "bound separates it from a legitimate neighbour -- re-read that "
        "before keeping this")
    assert not report.not_asked
    # And the reason, measured rather than asserted: the comparison itself
    # says no, so widening a bound is not what would change this.
    from aas_submodel_validate.rules import contact_tables
    from aas_submodel_validate.rules.engine import _near_miss
    row = contact_tables.BY_LABEL["Phone"]
    assert _near_miss(frozenset({PHONE_MIDDLE}), row["match"]) is None


def test_the_specification_path_case_is_unclaimed_too(tmp_path):
    """docs/divergences.md #51, as a fixture, and honest about the outcome.

    A file built to 02002's published specification carries an
    `IPCommunication` identifier the vendored template does not, so it
    matches no row -- and because that collection is `0..*`, nothing is
    violated and the mandatory `AddressOfAdditionalLink` beneath it simply
    leaves the run. The identifier differs from the row's by a whole
    segment, which draws no near-miss, so this run says nothing about it.

    That is the cost of the reading recorded in #51, measured here rather
    than asserted in prose: the template file is the authority, the
    specification is evidence, and a file following the specification is
    not judged on that subtree."""
    live = _run(tmp_path, _drift(contact_env(), "Phone", PHONE_TAIL))
    assert live.unmatched, "the mechanism is off; the silence below proves nothing"

    report = _run(tmp_path, _drift(contact_env(), "IPCommunication01",
                                   SPEC_IPCOMMUNICATION), "s.json")
    assert not report.unmatched
    assert "CI-E22" not in report.not_asked
    # The measured reason: the two identifiers differ by one whole segment
    # of nineteen characters, so no bound in the range #23 measured can see
    # it -- this is not a case a wider bound would reach.
    from aas_submodel_validate.rules import contact_tables
    from aas_submodel_validate.rules.engine import _near_miss
    row = contact_tables.BY_LABEL["IPCommunication__00__"]
    assert _near_miss(frozenset({SPEC_IPCOMMUNICATION}), row["match"]) is None
    assert len("ContactInformation/") == 19


def test_a_raw_eclass_url_is_normalised_before_any_comparison():
    """Order pin. An ECLASS identifier in `api.eclass-cdp.com` URL form
    would put a dense code where a comparison expects a word -- two
    different real properties are one character apart in that form. It
    never reaches one, and the only reason is that `semantics.normalize`
    rewrites those URLs to the bare IRDI first, and a bare IRDI is compared
    by exact version stem rather than by distance. Nothing else pins that
    ordering, so a refactor that reversed it would reopen the false
    positive silently."""
    from aas_submodel_validate.semantics import normalize

    raw = "https://api.eclass-cdp.com/0173-1-02-ABI000-003"
    assert normalize(raw) == "0173-1#02-ABI000#003"
    assert "://" not in normalize(raw)


def test_the_terminal_line_names_the_element_too(tmp_path):
    """The other half of this change, and it had no gate: the JSON key was
    pinned six ways while the sentence a person actually reads was pinned
    by nothing -- deleting the naming block left the suite green. The
    terminal is where most readers meet this, so it is held here."""
    from aas_submodel_validate.report import render

    report = _run(tmp_path, _drift(contact_env(), "Phone", PHONE_TAIL))
    text = render(report)
    record = next(r for r in report.unmatched if r.seen == PHONE_TAIL)
    assert record.subject in text, (
        "the terminal says a count but not which element: %r" % text)
    assert "their element" not in text and "its element" not in text


def test_each_record_answers_only_for_the_element_it_names(tmp_path):
    """Two unplaceable containers in one scope must not each be handed the
    other's children. The scope's loss is split by the row each identifier
    was said to resemble, so the per-element counts sum to the scope's loss
    rather than to a multiple of it -- and the one question this record
    exists to answer stays answerable when more than one thing drifted."""
    from builders import td_env

    env = copy.deepcopy(td_env())
    for element in env["submodels"][0]["submodelElements"]:
        if element.get("idShort") in ("ProductClassifications",
                                      "TechnicalPropertyAreas"):
            value = element["semanticId"]["keys"][0]["value"]
            element["semanticId"]["keys"][0]["value"] = (
                value[:-1] + ("8" if value[-1] != "8" else "7"))
    report = _run(tmp_path, env)
    assert len(report.unmatched) == 2, [r.subject for r in report.unmatched]
    lists = [set(record.unasked) for record in report.unmatched]
    assert not lists[0] & lists[1], (
        "two elements were handed the same rules: %s" % lists)
    assert sum(r.count for r in report.unmatched) == len(report.not_asked)
    for record in report.unmatched:
        assert set(record.unasked) <= set(report.not_asked)


def test_the_records_own_keys_are_documented_too(tmp_path):
    """The closed-key discipline reaches inside this object as well.

    `summary` is held to an exact key set, so an undeclared key there fails
    four gates. The keys *inside* each record escaped that: adding one left
    the suite green, which is the drift the top-level gate exists to stop.
    """
    import pathlib as _pathlib

    document = _run(tmp_path, _drift(contact_env(), "Phone", PHONE_TAIL)).as_dict()
    entry = document["summary"]["unmatchedElements"][0]
    schema = (_pathlib.Path(__file__).resolve().parents[1]
              / "docs" / "report-schema.md").read_text(encoding="utf-8")
    row = [line for line in schema.splitlines() if "`unmatchedElements`" in line]
    assert row, "the schema no longer documents unmatchedElements"
    for key in entry:
        assert "`%s`" % key in row[0], (
            "the record emits %r and the schema does not name it" % key)


def test_the_terminal_does_not_charge_the_element_with_more_than_it_explains(tmp_path):
    """The sentence and the JSON must not give different answers.

    The count in the sentence is the run's total, and an element named
    beside it may account for only part of that; welding the two asserts
    a cause the JSON denies. An optional container the file omits used to
    put its children in the total, with no element to charge them to --
    this test's fixture was that shape -- until a near miss stopped
    claiming rows it does not resemble; an element two tables walked was
    the other way in, until its record held both tables' rules. The suite
    now checks on every report that each rule not asked arrives with its
    element (`conftest.py`), so the case is built by hand: one rule the
    named element does not explain."""
    from aas_submodel_validate.report import render

    env = copy.deepcopy(contact_env())
    kids = env["submodels"][0]["submodelElements"][0]["value"]
    kids[:] = [c for c in kids if c.get("idShort") != "Fax"]   # 0..1: legal
    for child in kids:
        if child.get("idShort") == "Phone":
            child["semanticId"]["keys"][0]["value"] = PHONE_TAIL
    report = _run(tmp_path, env)
    explained = {rule for record in report.unmatched for rule in record.unasked}
    assert explained == set(report.not_asked), (
        "a rule arrived unasked with no element to explain it: %s"
        % sorted(set(report.not_asked) - explained))
    # `CI-E14`, beneath the omitted `Fax`: the rule the old total carried.
    report.not_asked = list(report.not_asked) + ["CI-E14"]
    line = [text for text in render(report).splitlines()
            if "not asked" in text][0]
    assert "accounts for %d of them" % len(explained) in line, (
        "the sentence charges the element with the run's whole count: %r" % line)


def test_an_element_two_tables_walked_is_charged_with_both(tmp_path):
    """A submodel carrying a pack's identifier and a supplied template's
    is walked by both tables, and one drifted container costs rules in
    each. Its record kept the larger loss and dropped the other, so seven
    rules stood in `rulesNotAsked` with no element beside them and the
    line said the container accounted for seven of fourteen."""
    import glob

    source = glob.glob(str(ROOT / "src" / "aas_submodel_validate" / "data"
                           / "smt" / "02006" / "3.0" / "*.json"))[0]
    template = json.loads(Path(source).read_text(encoding="utf-8-sig"))
    template["submodels"][0]["semanticId"]["keys"][0]["value"] = "urn:x:dn-copy"
    supplied = tmp_path / "copy.json"
    supplied.write_text(json.dumps(template), encoding="utf-8")
    env = copy.deepcopy(dn_env())
    submodel = env["submodels"][0]
    submodel["semanticId"]["keys"].append(
        {"type": "GlobalReference", "value": "urn:x:dn-copy"})
    markings = next(e for e in submodel["submodelElements"]
                    if e.get("idShort") == "Markings")
    markings["semanticId"]["keys"][0]["value"] = "0112/2///61360_7#AAS006#002"
    report = _run(tmp_path, env, template=str(supplied))
    [record] = report.unmatched
    assert set(record.unasked) == set(report.not_asked), (record.unasked, report.not_asked)
    assert any(r.startswith("DN-") for r in record.unasked)
    assert any(r.startswith("TPL-") for r in record.unasked)


def test_two_elements_printed_as_one_place_lose_no_rule(tmp_path):
    """A Property whose idShort is spelled like a position, `[1]`, beside an
    unnamed collection at index 1: both print as `.../[1]`, and here both
    carry one identifier. The record is keyed by those two, so one of them
    was dropped with the rules it cost (#53 names why the place cannot be
    told apart; losing the rules is what it no longer does)."""
    phone = ("https://admin-shell.io/zvei/nameplate/1/0/ContactInformations/"
             "ContactInformation/Phone")
    drifted = "0173-1#02-AAQ834#004"      # Fax is ...#005

    def ref(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    env = copy.deepcopy(contact_env())
    kids = env["submodels"][0]["submodelElements"][0]["value"]
    kids[:] = [c for c in kids if c.get("idShort") not in ("Phone", "Fax")]
    kids[:0] = [
        {"idShort": "[1]", "modelType": "Property", "valueType": "xs:string",
         "value": "+49 69 1234", "semanticId": ref(phone),
         "supplementalSemanticIds": [ref(drifted)]},
        {"modelType": "SubmodelElementCollection", "semanticId": ref(drifted),
         "value": [{"idShort": "FaxNumber", "modelType": "MultiLanguageProperty",
                    "value": [{"language": "en", "text": "+49 69 5678"}]}]}]
    report = _run(tmp_path, env)
    explained = {rule for record in report.unmatched for rule in record.unasked}
    assert report.not_asked and explained == set(report.not_asked), (
        sorted(set(report.not_asked) - explained))


def test_siblings_carrying_one_drift_are_one_loss_not_two(tmp_path):
    """A version bump hits every item of a list, which is the cause #23 and
    `tools/scope_silence.py` both name as the realistic one. Each item then
    resembles the same row, and giving each of them that row's subtree
    counted one loss as many times as there were items."""
    from builders import td_env

    env = copy.deepcopy(td_env())
    for element in env["submodels"][0]["submodelElements"]:
        if element.get("idShort") == "ProductClassifications":
            element["value"].append(copy.deepcopy(element["value"][0]))
            for item in element["value"]:
                value = item["semanticId"]["keys"][0]["value"]
                item["semanticId"]["keys"][0]["value"] = value[:-1] + "4"
    report = _run(tmp_path, env)
    ids = [rule for record in report.unmatched for rule in record.unasked]
    assert len(ids) == len(set(ids)), "one loss counted twice: %s" % ids
    assert set(ids) <= set(report.not_asked)
    assert sum(r.count for r in report.unmatched) == len(set(ids))


def test_a_long_id_short_cannot_grow_the_report(tmp_path):
    """The record carries file-supplied text -- the idShort chain and the
    file's own identifier -- and every such field goes through one funnel
    rather than a list of exceptions somebody has to remember. A 200,000
    character idShort produced a 200,000 character terminal line."""
    from aas_submodel_validate.model import MAX_REPORTED_CHARACTERS
    from aas_submodel_validate.report import render

    env = copy.deepcopy(contact_env())
    for child in env["submodels"][0]["submodelElements"][0]["value"]:
        if child.get("idShort") == "Phone":
            child["idShort"] = "P" * 200000
            child["semanticId"]["keys"][0]["value"] = PHONE_TAIL
    report = _run(tmp_path, env)
    assert len(report.unmatched[0].subject) == MAX_REPORTED_CHARACTERS
    assert len(render(report)) < 6000


def test_an_element_of_the_wrong_kind_is_named_too(tmp_path):
    """The second trigger, and the one where the element is certain.

    A row matched an element of the wrong kind: the walk reported that
    (`CI-E09`), did not recurse into it, and the rules beneath it left the
    run. Nothing had to be guessed -- that element claimed the row, and the
    finding beside this already prints its subject -- yet this was the one
    case with no record, so the terminal fell back to "their element is not
    one the template describes" about an element it could name exactly.
    """
    from aas_submodel_validate.report import render

    identifier = ("https://admin-shell.io/zvei/nameplate/1/0/"
                  "ContactInformations/ContactInformation/Phone")
    env = copy.deepcopy(contact_env())
    kids = env["submodels"][0]["submodelElements"][0]["value"]
    kids[:] = [c for c in kids if c.get("idShort") != "Phone"]
    kids.append({"idShort": "Phone", "modelType": "Property",
                 "valueType": "xs:string", "value": "+49 69 1234",
                 "semanticId": {"type": "ExternalReference",
                                "keys": [{"type": "GlobalReference",
                                          "value": identifier}]}})
    report = _run(tmp_path, env)
    assert "CI-E09" in {finding.rule.id for finding in report.findings}
    record = next(r for r in report.unmatched if r.seen == identifier)
    assert "CI-E10" in record.unasked          # the mandatory TelephoneNumber
    assert set(record.unasked) <= set(report.not_asked)
    text = render(report)
    assert record.subject in text
    assert "their element" not in text and "its element" not in text


def _two_parents_one_name(env, id_short, value):
    """Two scopes whose containers share an idShort, each holding its own
    drifted child.

    This is the shape `docs/divergences.md` #53 describes, and it is not
    the same as two *siblings* sharing a drift: those carry one drift
    between them and are one record on purpose, because handing each the
    other's subtree is the double count #23 records an earlier version
    making. Here there are two containers, two subtrees and two losses --
    and the subject strings collided, so the record keyed on them kept
    one.
    """
    out = _drift(env, id_short, value)
    scope = out["submodels"][0]["submodelElements"][0]
    out["submodels"][0]["submodelElements"].append(copy.deepcopy(scope))
    return out


def test_two_scopes_that_each_lost_rules_are_two_records(tmp_path):
    """A subject was not an identity, so two elements were reported as one.

    `_subject` appended an index only where an element had no idShort at
    all, so an element under either of two same-named containers produced
    the same string -- and the record is deduplicated by `(subject,
    identifier)`, which merged them. Measured before the change: two
    `ContactInformation` containers, each with a drifted `Phone`, one
    record. The reader was told one element did what two did.

    The metamodel forbids the shared idShort and this project relays that
    as a warning rather than refusing the file ("ID-shorts of the value
    must be unique"), so a file like this is judged, and what it is judged
    to have done has to be attributable.
    """
    report = _run(tmp_path, _two_parents_one_name(contact_env(), "Phone",
                                                  PHONE_TAIL))
    records = [r for r in report.unmatched if r.seen == PHONE_TAIL]
    assert len(records) == 2, (
        "two scopes left rules unasked and %d record(s) were kept: %s"
        % (len(records), [r.subject for r in records]))
    assert len({r.subject for r in records}) == 2, (
        "both records name the same element: %s" % [r.subject for r in records])
    assert all("ContactInformation[" in r.subject for r in records), (
        "the containers were not told apart: %s" % [r.subject for r in records])


def test_siblings_carrying_one_drift_are_still_one_record(tmp_path):
    """The direction this must not break.

    Two siblings with the same drifted identifier carry one drift between
    them, and handing each of them the whole subtree made the per-element
    counts sum to twice what was lost. That grouping is by row and
    identifier and is not what this change touches; pinned here because a
    subject that now varies per element is exactly what would tempt
    somebody to group by subject instead.
    """
    env = _drift(contact_env(), "Phone", PHONE_TAIL)
    children = env["submodels"][0]["submodelElements"][0]["value"]
    children.append(copy.deepcopy(
        next(c for c in children if c.get("idShort") == "Phone")))
    records = [r for r in _run(tmp_path, env).unmatched if r.seen == PHONE_TAIL]
    assert len(records) == 1, (
        "two siblings sharing one drift produced %d records: %s"
        % (len(records), [r.subject for r in records]))


def test_an_element_whose_id_short_is_its_own_is_named_by_it(tmp_path):
    """And the reason this was recorded rather than repaired for a
    release: disambiguating every subject would have changed the subject
    string of every finding this project prints. Only a shared idShort
    earns an index."""
    report = _run(tmp_path, _drift(contact_env(), "Phone", PHONE_TAIL))
    record = next(r for r in report.unmatched if r.seen == PHONE_TAIL)
    assert record.subject.endswith("/Phone"), (
        "an element with an idShort nothing shares was renamed: %s"
        % record.subject)
