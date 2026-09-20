"""Judging against a template the caller brought.

Three properties, each a test here. The report says where the table came
from and that it is not a published IDTA template. Every entrance gives
the same verdict. What the generator cannot produce stays out.

And one this project set for itself: a file somebody else wrote is
refused rather than trusted — with the code that means "could not judge
this input", which is 2 and not the 1 a build tool leaves by.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from aas_submodel_validate import runner

ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDORED = (pathlib.Path(runner.__file__).parent / "data" / "smt"
            / "02003" / "2.0.1" / "template.json")


def _instance(tmp_path):
    from builders import env_json

    path = tmp_path / "env.json"
    path.write_bytes(env_json("0173-1#01-AHX837#002"))
    return path


def test_a_submodel_judged_by_a_supplied_template_counts_as_judged(tmp_path):
    """`submodels_judged` came from a fixed list of packs, so a submodel
    judged by a table built at run time was counted as unjudged -- the
    report would carry findings about it and say `judged 0 of 1`, and
    `--require-all-judged` could never pass. The same contradiction the
    battery pack already had repaired once."""
    report = runner.run(_instance(tmp_path), template=VENDORED)
    assert report.submodels_seen == 1
    assert report.submodels_judged == 1, (
        "a submodel judged against the supplied template is counted as "
        "unjudged: judged %d of %d" % (report.submodels_judged,
                                       report.submodels_seen))
    # And it was actually judged. `submodels_judged` is computed from the
    # identifier the table claims and would say 1 even if the rules built
    # from that table were never run -- measured: dropping them from
    # `rules_to_run` left this test green, so the count alone is a claim
    # about the table and not about the judging.
    assert any(finding.id.startswith("TPL-") for finding in report.findings), (
        "nothing the supplied table produced reached the report: %s"
        % sorted({f.id for f in report.findings}))


def test_the_report_says_the_template_was_not_idtas(tmp_path):
    """A verdict against a file the caller brought is not a verdict
    against a published template, and a reader who cannot tell the two
    apart has been told something untrue."""
    import hashlib

    from aas_submodel_validate import tablegen

    document = runner.run(_instance(tmp_path), template=VENDORED).as_dict()
    provenance = document["provenance"]
    assert "template" in provenance, sorted(provenance)
    said = provenance["template"]

    # Every field, not the one that was easy to assert. Four of the five
    # could be wrong with the whole suite green -- measured, including
    # the strongest of them: `sha256` set to the digest of the *input*,
    # which is the field whose entire purpose is naming the bytes that
    # judged.
    assert said["published"] is False, (
        "the report presents a supplied template as a published one")
    assert said["sha256"] == hashlib.sha256(VENDORED.read_bytes()).hexdigest(), (
        "the report names bytes that are not the template's")
    assert said["sha256"] != provenance["inputSha256"], (
        "the template's digest is the input's")
    assert said["path"] == str(VENDORED), said["path"]
    assert said["semanticId"] == "0173-1#01-AHX837#002", said["semanticId"]
    built = tablegen.table_from(
        json.loads(VENDORED.read_text("utf-8-sig")),
        {"prefix": "TPL-E", "citation": "c", "skip_sids": frozenset(),
         "item_names": {}, "example_types": ()})
    assert said["rows"] == len(built.ROWS) > 0, (
        "the report says %r rows and the table has %d"
        % (said["rows"], len(built.ROWS)))


def test_a_template_that_is_not_a_template_is_refused_at_2(tmp_path):
    """Not 1, which is a build tool's way of leaving, and not a
    traceback. 2 is this reader's code for "could not judge the input"
    and a file somebody else wrote is exactly that case."""
    from aas_submodel_validate.cli import main

    broken = tmp_path / "not-a-template.json"
    broken.write_text("{}", encoding="utf-8")
    assert main([str(_instance(tmp_path)), "--template", str(broken), "-q"]) == 2


def test_a_template_with_too_many_rows_is_refused(tmp_path):
    """The bound that could not be written while nothing handed this a
    file it did not choose. A template is not bounded by the reader's own
    byte limit: 46 MiB of template sits inside the 64 MiB this reader
    advertises, and what costs is rows."""
    from aas_submodel_validate import tablegen

    enormous = {"submodels": [{
        "kind": "Template", "idShort": "T",
        "semanticId": {"type": "GlobalReference",
                       "keys": [{"type": "GlobalReference", "value": "urn:x:top"}]},
        "submodelElements": [
            {"modelType": "Property", "idShort": "P%d" % i, "valueType": "xs:string",
             "semanticId": {"type": "GlobalReference",
                            "keys": [{"type": "GlobalReference",
                                      "value": "urn:x:%d" % i}]}}
            for i in range(tablegen.MAX_TEMPLATE_ROWS + 1)]}]}
    pack = {"prefix": "TPL-E", "citation": "c", "skip_sids": frozenset(),
            "item_names": {}, "example_types": ()}
    with pytest.raises(tablegen.TemplateRefused) as refused:
        tablegen.build(enormous, pack)
    assert "rows" in str(refused.value), refused.value

    # Nested, not only flat. The bound counts every row and the first
    # version of this test built the rows at the top level, so a bound
    # that counted only those would have passed it -- measured: swapping
    # the counter for `len(tree)` left the whole suite green while three
    # top-level collections holding twenty thousand children each sailed
    # through.
    def nest(rows):
        children = [{"modelType": "Property", "idShort": "P%d" % i,
                     "valueType": "xs:string",
                     "semanticId": {"type": "GlobalReference",
                                    "keys": [{"type": "GlobalReference",
                                              "value": "urn:x:%d" % i}]}}
                    for i in range(rows)]
        return {"modelType": "SubmodelElementCollection", "idShort": "Holder",
                "semanticId": {"type": "GlobalReference",
                               "keys": [{"type": "GlobalReference",
                                         "value": "urn:x:holder"}]},
                "value": children}

    deep = dict(enormous)
    deep["submodels"] = [dict(enormous["submodels"][0],
                              submodelElements=[nest(tablegen.MAX_TEMPLATE_ROWS)])]
    with pytest.raises(tablegen.TemplateRefused) as nested:
        tablegen.build(deep, pack)
    assert "rows" in str(nested.value), (
        "a template whose rows are nested rather than flat was not counted: %s"
        % nested.value)


def test_the_same_template_gives_the_same_verdict_from_every_entrance(tmp_path):
    """The same verdict from every entrance, asked as bytes.

    The command line, the library and the single file are the same engine
    or they are not one engine. Compared as the JSON document, because
    that is the contract, and a difference anywhere in it is a difference
    a consumer sees.
    """
    import os
    import subprocess
    import sys

    instance = _instance(tmp_path)
    from_library = json.dumps(
        runner.run(instance, template=VENDORED).as_dict(), indent=2)

    def through(argv):
        done = subprocess.run(argv, capture_output=True, text=True, cwd=str(ROOT),
                              env=dict(os.environ, PYTHONPATH="src"))
        assert done.returncode in (0, 1), done.stderr
        return done.stdout.rstrip("\n")

    command = through([sys.executable, "-m", "aas_submodel_validate",
                       str(instance), "--template", str(VENDORED), "-f", "json"])

    single = tmp_path / "smtv.pyz"
    built = subprocess.run([sys.executable, str(ROOT / "tools" / "build_zipapp.py"),
                            "-o", str(single)], capture_output=True, text=True,
                           cwd=str(ROOT))
    assert built.returncode == 0, built.stdout + built.stderr
    archive = through([sys.executable, str(single), str(instance),
                       "--template", str(VENDORED), "-f", "json"])

    # `path` is the one field that legitimately differs, and it does not
    # here: all three are handed the same path.
    assert command == from_library, "the command line and the library disagree"
    assert archive == from_library, "the single file and the library disagree"


def test_a_run_time_rule_id_never_reaches_the_coverage_record(tmp_path):
    """`make exercised` asks whether every rule *this project publishes*
    fired somewhere, against a baseline listing exactly those.

    A rule that exists because somebody passed a file is in neither list,
    so recording it fails two of that gate's three comparisons at once --
    "fired but not registered", and "firing but not in the baseline".
    Measured: before the filter, one `--template` run in the suite turned
    `make exercised` red with `TPL-E01` on both lines.

    The design for this mode proposed widening the registered set, which
    answers the first comparison and leaves the second, and proposed
    keeping the ids out of the baseline, which guarantees the second
    fails. The place that answers both is where the ids are collected.
    """
    import json

    from conftest import FIRED, RUN_TIME_PREFIX

    report = runner.run(_instance(tmp_path), template=VENDORED)
    ours = {finding.id for finding in report.findings}
    assert any(rule_id.startswith(RUN_TIME_PREFIX) for rule_id in ours), (
        "no run-time rule fired, so this test proves nothing: %s" % sorted(ours))
    assert not any(rule_id.startswith(RUN_TIME_PREFIX) for rule_id in FIRED), (
        "a run-time id reached the coverage record: %s"
        % sorted(i for i in FIRED if i.startswith(RUN_TIME_PREFIX)))

    recorded = pathlib.Path(runner.__file__).resolve().parents[2] / ".rule-coverage.json"
    if recorded.is_file():
        kept = json.loads(recorded.read_text("utf-8"))
        assert not [i for i in kept if i.startswith(RUN_TIME_PREFIX)], \
            "the recorded observation carries run-time ids"


def test_a_supplied_template_answers_instead_of_the_pack_not_as_well(tmp_path):
    """Two tables for one identifier is one defect reported twice.

    Measured: handing `--template` the very file 02003's pack was
    generated from gave two errors where the pack alone gives one -- the
    same missing element, under `TD-E01` and under `TPL-E01`. A reader is
    told there are two problems when there is one, and a build counting
    errors gets a number that depends on a flag rather than on the file.

    The caller asked for their template explicitly, so theirs answers and
    the pack stands down for the identifiers theirs declares. Standing
    down is said out loud, because a pack that quietly stops answering is
    the silence this project refuses everywhere else -- `--profile` has
    the same shape and the same sentence.
    """
    report = runner.run(_instance(tmp_path), template=VENDORED)
    ours = [f for f in report.findings if f.severity.name == "ERROR"]
    ids = sorted(f.id for f in ours)
    # Not vacuously: `all` over nothing is true, and nothing is what a
    # supplied table produces if its rules are never run.
    assert ids, "the supplied table produced no errors at all"
    assert all(rule_id.startswith("TPL-") for rule_id in ids), (
        "the pack answered as well as the supplied table: %s" % ids)

    without = runner.run(_instance(tmp_path))
    assert len(ours) == len([f for f in without.findings
                             if f.severity.name == "ERROR"]), (
        "the same file has %d errors with the template and %d without"
        % (len(ours), len([f for f in without.findings
                           if f.severity.name == "ERROR"])))

    said = " ".join(note for note in (report.notes or []))
    assert "0173-1#01-AHX837#002" in said, (
        "nothing says which identifier the supplied template took over: %r"
        % said)


def test_the_terminal_says_the_template_was_yours(tmp_path):
    """Where the table came from belongs in the report field *and* on
    the screen. The field was there and the line was not -- and the person
    reading a terminal is the one most likely to forget which table
    answered."""
    import contextlib
    import io

    from aas_submodel_validate.cli import main

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main([str(_instance(tmp_path)), "--template", str(VENDORED)])
    screen = out.getvalue()
    assert "template you supplied" in screen or "template you gave" in screen, screen
    assert "not a published IDTA template" in screen, screen


#: A template no pack here has, which is the case the mode exists for.
#: Every test above points at a vendored template, and that is why none
#: of them saw what the three below are about: a template one of the six
#: packs also answers for hides every defect that turns on nothing else
#: answering.
UNCLAIMED = "https://admin-shell.io/idta/SoftwareNameplate/1/0"


def _unclaimed_template(tmp_path, *, semantic_id=UNCLAIMED):
    def ref(value):
        return {"type": "GlobalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    path = tmp_path / "unclaimed-template.json"
    path.write_text(json.dumps({"submodels": [{
        "kind": "Template", "idShort": "SoftwareNameplate", "id": "urn:t",
        "semanticId": ref(semantic_id),
        "submodelElements": [{
            "modelType": "SubmodelElementCollection",
            "idShort": "SoftwareNameplateType",
            "semanticId": ref(semantic_id + "/Type"), "value": [],
            "qualifiers": [{"type": "SMT/Cardinality", "valueType": "xs:string",
                            "value": "One"}]}]}]}), encoding="utf-8")
    return path


def _unclaimed_instance(tmp_path, *, semantic_id=UNCLAIMED):
    from builders import env_json

    path = tmp_path / "unclaimed.json"
    path.write_bytes(env_json(semantic_id))
    return path


def test_a_submodel_the_supplied_template_judged_is_not_also_unmatched(tmp_path):
    """`SMT-D1` says no submodel declares an identifier this tool has a
    table for, and its remedy tells the author to relabel their document
    as one of the six.

    Measured on the mode's own headline case -- a template none of the
    packs claims -- it fired anyway, beside a `TPL-E01` finding about
    that very submodel and a summary reading `judged 1 of 1`. Three
    statements in one report, each denying the one beside it, and two
    errors where there is one defect.

    The repair reached `submodels_judged` and not the rule: the summary
    was handed the supplied table and `SMT-D1` calls `judged` with the
    default. This is the contradiction that function's own docstring
    records repairing once, for the battery pack.
    """
    report = runner.run(_unclaimed_instance(tmp_path),
                        template=_unclaimed_template(tmp_path))
    ids = sorted(f.id for f in report.findings)
    assert "SMT-D1" not in ids, (
        "the submodel was judged and reported unmatched in the same report: %s"
        % ids)
    assert any(rule_id.startswith("TPL-") for rule_id in ids), ids
    assert report.submodels_judged == 1


def test_a_template_the_interpreter_cannot_read_is_refused_not_raised(tmp_path):
    """A file somebody else wrote can be deep enough to exhaust the
    stack. `loader.py` has a classifier for exactly this on the sibling
    path -- an interpreter limit is not a defect in the document -- and
    this reader reached one of the two.

    Measured: three thousand nested collections, half a megabyte of
    well-formed JSON, came out as a `RecursionError` traceback at exit 1.
    Exit 1 is the code for a verdict with findings, about a file nothing
    finished reading; the same bytes handed in as the *input* exit 2 with
    a sentence.
    """
    from aas_submodel_validate.cli import main

    # Written as text. `json.dumps` walks the structure recursively, so
    # building this the obvious way exhausts the stack in the test rather
    # than in the reader -- which proves nothing about the reader.
    collection = ('{"modelType": "SubmodelElementCollection", "idShort": "C", '
                  '"semanticId": {"type": "GlobalReference", "keys": '
                  '[{"type": "GlobalReference", "value": "urn:x:c"}]}, '
                  '"value": [')
    depth = 3000
    deep = tmp_path / "deep.json"
    deep.write_text(
        '{"submodels": [{"kind": "Template", "idShort": "D", "id": "urn:t", '
        '"semanticId": {"type": "GlobalReference", "keys": [{"type": '
        '"GlobalReference", "value": "%s"}]}, "submodelElements": [%s%s]}]}'
        % (UNCLAIMED, collection * depth, "]}" * depth),
        encoding="utf-8")

    assert main([str(_unclaimed_instance(tmp_path)), "--template", str(deep),
                 "-q"]) == 2


def test_the_templates_own_identifier_is_normalised_like_every_other(tmp_path):
    """Every value on the instance side goes through `normalize`, and so
    do the template's supplementals four lines from where its own
    identifier is read raw.

    Measured: the vendored 02003 template with its submodel identifier
    written in the ECLASS-CDP spelling built fifty-four rules that could
    match nothing, did not take the identifier over -- so the pack
    answered instead -- and the report still said the caller's template
    decided the run. Three wrong answers from one missing call.
    """
    from aas_submodel_validate import tablegen

    cdp = "https://api.eclass-cdp.com/0173-1-01-AHX837-002"
    path = _unclaimed_template(tmp_path, semantic_id=cdp)
    built = tablegen.table_from(json.loads(path.read_text("utf-8")),
                                {"prefix": "TPL-E", "citation": "c",
                                 "skip_sids": frozenset(), "item_names": {},
                                 "example_types": ()})
    assert built.TEMPLATE_SEMANTIC_ID == "0173-1#01-AHX837#002", (
        "the template's own identifier was not normalised: %r"
        % built.TEMPLATE_SEMANTIC_ID)


def test_no_pack_describes_a_run_it_stood_down_from(tmp_path):
    """Two notes denying each other in one report is this codebase's own
    phrase for the failure, and the stand-down produced it.

    Measured: with `--template` and `--profile 02035-2` together, the
    report said *"judged as Digital Battery Passport part 2 (IDTA
    02035-2)"* and, three lines down, *"a pack of this tool's own also
    answers for 0173-1#01-AHF578#003 and stood down"*. Neither pack ran.
    The whole `SMT-D2` detail was an account of a table that did not
    answer. `BAT-R2` has the same shape, on the identifier 02023 shares.

    The stand-down was implemented in `matched_submodels` and the other
    readers of "which table judged this submodel" were left alone --
    which is the shape this project keeps meeting.
    """
    from aas_submodel_validate.cli import main

    vendored = (pathlib.Path(runner.__file__).parent / "data" / "smt"
                / "02004" / "2.0.1" / "template.json")
    from builders import env_json

    instance = tmp_path / "hd.json"
    instance.write_bytes(env_json("0173-1#01-AHF578#003"))

    report = runner.run(instance, template=vendored, profile="02035-2")
    said = sorted(f.id for f in report.findings)
    assert "SMT-D2" not in said, (
        "a pack that stood down still describes the run: %s" % said)
    assert any(rule_id.startswith("TPL-") for rule_id in said), said
    assert main([str(instance), "--template", str(vendored),
                 "--profile", "02035-2", "-q"]) in (0, 1)


def test_a_published_number_does_not_move_with_a_flag(tmp_path):
    """`summary.rulesChecked` is documented as "every rule registered in
    this build ... the number does not move when a different template
    answers", and the rules a supplied table makes are deliberately not
    registered.

    Measured: it went from 219 to 273 with the flag, and to 221 on a run
    where the supplied template matched nothing at all. A build reading
    that number gets one that depends on a caller's file. The template's
    own contribution is already carried, in `provenance.template.rows`,
    which is where a reader who wants it should find it.
    """
    from aas_submodel_validate.registry import all_rules

    registered = len(all_rules())
    plain = runner.run(_instance(tmp_path)).as_dict()["summary"]["rulesChecked"]
    assert plain == registered, plain

    with_template = runner.run(_instance(tmp_path),
                               template=VENDORED).as_dict()
    assert with_template["summary"]["rulesChecked"] == registered, (
        "a published number moved with a flag: %d registered, %d reported"
        % (registered, with_template["summary"]["rulesChecked"]))
    assert with_template["provenance"]["template"]["rows"] > 0, (
        "and the template's own contribution is nowhere")


def test_a_template_that_matched_nothing_does_not_claim_the_verdict(tmp_path):
    """The note said "judged against the template you supplied" on a run
    where that template matched nothing at all.

    Measured with `--example` and a template claiming an identifier the
    bundled document does not carry: the 02004 pack produced the entire
    verdict and the report said otherwise, with `provenance.template`
    present, which a consumer reads as "this verdict was made against a
    supplied template".
    """
    import contextlib
    import io

    from aas_submodel_validate.cli import main

    unmatched = _unclaimed_template(tmp_path)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main([str(_instance(tmp_path)), "--template", str(unmatched)])
    screen = out.getvalue()
    assert "judged against the template you supplied" not in screen, (
        "the report claims a verdict the supplied template took no part in")
    assert "no submodel in this input declares" in screen, screen


def test_standing_down_says_what_it_cost(tmp_path):
    """A pack that stands down stops answering entirely — its table, its
    hand-written rules and its lints — and the note said only that it
    "stood down".

    Measured on 02003: without the flag the report carries `TD-E01` and
    `TDL2`; with it, `TPL-E01` alone. The info finding is gone and
    nothing said a check was lost. A reader comparing two reports of one
    file would see the run get quieter and read that as the file
    improving.
    """
    vendored = (pathlib.Path(runner.__file__).parent / "data" / "smt"
                / "02003" / "2.0.1" / "template.json")
    without = runner.run(_instance(tmp_path))
    with_it = runner.run(_instance(tmp_path), template=vendored)

    lost = ({f.id for f in without.findings}
            - {f.id for f in with_it.findings})
    assert lost, "this test proves nothing: the pack lost no finding"
    said = " ".join(with_it.notes or [])
    assert "hand-written" in said or "none of its rules" in said, (
        "the note says a pack stood down and not what that removed: %r" % said)


def test_the_help_page_says_a_supplied_verdict_is_not_a_conformance_claim(capsys):
    """The load-bearing sentence lived in `docs/scope.md` and the
    CHANGELOG and reached neither `--help` nor the terminal.

    A stranger reading `--help` is the reader most likely to use the flag
    without reading either, and "what the generator cannot read from a
    template is not checked" is circular to somebody who does not know
    what a generator reads."""
    import pytest as _pytest

    from aas_submodel_validate.cli import main

    with _pytest.raises(SystemExit):
        main(["--help"])
    page = " ".join(capsys.readouterr().out.split())
    assert "--template" in page
    assert "not a statement about conformance" in page, page
    for named in ("hand-written", "which elements"):
        assert named in page, "the help page does not say %r" % named
