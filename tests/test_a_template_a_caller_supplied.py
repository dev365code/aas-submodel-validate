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
import re

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
    # Asked of the runner rather than rebuilt here. A second copy of the
    # pack definition stood in this test, and it said `skip_sids:
    # frozenset()` -- which is what the runner said too, so the pair
    # agreed with each other and both were wrong about what a template
    # declares (`docs/divergences.md` #19). A reference the test writes
    # itself can only check that the report matches the test.
    built = runner._supplied_table(VENDORED)["table"]
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


def _console_script_shim(tmp_path):
    """The file an installer writes for `[project.scripts]`, built from
    the declaration instead of from an install.

    Running an installed `smtv` would run whichever one is on the PATH,
    which on a developer machine is an older release and in a fresh
    checkout is nothing at all. What has to hold is narrower and is
    entirely in this tree: the target named in `pyproject.toml` is a
    callable, and reaching the tool through it gives the same verdict as
    reaching it any other way. A shim generated from that declaration
    asks exactly that, and goes red if the declaration moves.
    """
    import re

    pyproject = (ROOT / "pyproject.toml").read_text("utf-8")
    block = re.search(r"(?ms)^\[project\.scripts\]\n(.*?)(?=^\[|\Z)",
                      pyproject)
    assert block, "no [project.scripts] to build a console script from"
    targets = {}
    for line in block.group(1).splitlines():
        name, sep, value = line.partition("=")
        if sep:
            targets[name.strip()] = value.strip().strip('"').strip("'")
    assert "smtv" in targets, sorted(targets)
    module, _, function = targets["smtv"].partition(":")
    shim = tmp_path / "smtv-console-script.py"
    shim.write_text("import sys\nfrom %s import %s\nsys.exit(%s())\n"
                    % (module, function, function), encoding="utf-8")
    return shim


def _verdicts_through_every_entrance(tmp_path):
    """One verdict per entrance, as the JSON document a consumer reads.

    The roster below is these keys, so the list and the comparison
    cannot drift: the list used to name the console script while the
    comparison ran the package, the library and the single file, and the
    gate that reads it passed.
    """
    import os
    import subprocess
    import sys

    instance = _instance(tmp_path)

    def through(argv):
        done = subprocess.run(argv, capture_output=True, text=True,
                              cwd=str(ROOT),
                              env=dict(os.environ, PYTHONPATH="src"))
        assert done.returncode in (0, 1), done.stderr
        return done.stdout.rstrip("\n")

    single = tmp_path / "smtv.pyz"
    built = subprocess.run([sys.executable,
                            str(ROOT / "tools" / "build_zipapp.py"),
                            "-o", str(single)], capture_output=True, text=True,
                           cwd=str(ROOT))
    assert built.returncode == 0, built.stdout + built.stderr

    tail = [str(instance), "--template", str(VENDORED), "-f", "json"]
    return {
        "library": json.dumps(
            runner.run(instance, template=VENDORED).as_dict(), indent=2),
        "python -m": through([sys.executable, "-m", "aas_submodel_validate"]
                             + tail),
        "console script": through([sys.executable,
                                   str(_console_script_shim(tmp_path))] + tail),
        "single file": through([sys.executable, str(single)] + tail),
    }


def test_the_same_template_gives_the_same_verdict_from_every_entrance(tmp_path):
    """The same verdict from every entrance, asked as bytes.

    The command line, the console script, the library and the single
    file are the same engine or they are not one engine. Compared as the
    JSON document, because that is the contract, and a difference
    anywhere in it is a difference a consumer sees.

    `path` is the one field that could legitimately differ and does not
    here: every entrance is handed the same absolute path.
    """
    verdicts = _verdicts_through_every_entrance(tmp_path)
    expected = verdicts["library"]
    for entrance, seen in sorted(verdicts.items()):
        assert seen == expected, "%s and the library disagree" % entrance


def test_a_run_time_rule_id_never_reaches_the_coverage_record(tmp_path):
    """`make exercised` asks whether every rule *this project publishes*
    fired somewhere, against a baseline listing exactly those.

    A rule that exists because somebody passed a file is in neither list,
    so recording it fails two of that gate's three comparisons at once --
    "fired but not registered", and "firing but not in the baseline".
    Measured: before the filter, one `--template` run in the suite turned
    `make exercised` red with `TPL-E01` on both lines.

    Widening the registered set answers the first comparison and leaves
    the second; keeping the ids out of the baseline guarantees the second
    fails. The place that answers both is where the ids are collected,
    which is why the filter is there and not in either list.
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
#: of them saw what the three below are about: a template one of the
#: packs also answers for hides every defect that turns on nothing else
#: answering. This was 02007 Software Nameplate's identifier until that
#: template was given a pack, and every test below then stood on a
#: claimed one; an identifier no published template uses is not taken
#: the same way.
UNCLAIMED = "urn:example:template:no-pack-answers-for-this"


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

    # An answer, whatever this interpreter does with the depth. That is
    # the whole property and it is the only portable form of it: three
    # thousand levels raised `RecursionError` on 3.9 and parsed cleanly
    # on 3.12 and 3.13, so asserting the refusal made this green here and
    # red on three matrix rows. Lowering `setrecursionlimit` does not
    # help either -- measured, those interpreters parse depth 3000 at a
    # limit of 200, because the scanner is C and does not spend Python
    # frames the way 3.9's did.
    assert main([str(_unclaimed_instance(tmp_path)), "--template", str(deep),
                 "-q"]) in (0, 1, 2)


def test_an_interpreter_limit_while_reading_a_template_is_a_refusal(tmp_path,
                                                                    monkeypatch):
    """And the branch that turns one into a refusal, asked directly.

    The test above cannot reach it on every interpreter, so it does not
    try; this one hands `_supplied_table` a reader that raises, which is
    what an exhausted stack looks like from inside. `loader.py` has the
    same classifier on the sibling path and says why: an interpreter
    limit is not a defect in the document, and a document nothing
    finished reading is not a verdict.
    """
    import json as _json

    from aas_submodel_validate import runner as _runner
    from aas_submodel_validate import tablegen

    # Patched on the module itself, because `_supplied_table` imports
    # `json` when it is called rather than at the top of the file.
    template = _unclaimed_template(tmp_path)
    for raised, word in ((RecursionError("maximum recursion depth exceeded"),
                          "deeply"),
                         (MemoryError(), "deeply")):
        monkeypatch.setattr(
            _json, "loads",
            lambda *_a, _raise=raised, **_k: (_ for _ in ()).throw(_raise))
        with pytest.raises(tablegen.TemplateRefused) as refused:
            _runner._supplied_table(template)
        assert word in str(refused.value), refused.value


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

    Measured: counted from the rules actually run it is 232 with no flag
    and 258 with a twenty-six row template -- the second figure being
    whatever that file declares. A build reading that number gets one
    that depends on a caller's argument. (Three fixed figures stood here
    and all three went stale, so what is written down is the shape.) The template's
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
    # Joined, and then the breaks argparse puts at hyphens rejoined:
    # it wraps to the terminal width, so "hand-written" arrives as
    # "hand- written" at some widths and not others. A test that passes
    # on a wide terminal and fails on a narrow one is a test about the
    # terminal.
    page = " ".join(capsys.readouterr().out.split()).replace("- ", "-")
    assert "--template" in page
    assert "not a statement about conformance" in page, page
    for named in ("hand-written", "which elements", "valueType"):
        assert named in page, "the help page does not say %r" % named


#: The ways this tool can be started, and how each is declared in the
#: tree. Read from the tree rather than listed, so an entrance that
#: arrives is an entrance this has to cover.
def _entrances_the_tree_declares():
    import re

    found = {"python -m": True}     # always, it is the package
    pyproject = (ROOT / "pyproject.toml").read_text("utf-8")
    scripts = re.search(r"(?ms)^\[project\.scripts\]\n(.*?)(?=^\[|\Z)", pyproject)
    if scripts and scripts.group(1).strip():
        found["console script"] = True
    if (ROOT / "tools" / "build_zipapp.py").is_file():
        found["single file"] = True
    if (ROOT / "action.yml").is_file() or (ROOT / "action.yaml").is_file():
        found["github action"] = True
    return found


#: What `test_the_same_template_gives_the_same_verdict_from_every_entrance`
#: actually runs -- read off the comparison rather than written beside
#: it. Written beside it, this named the console script while the
#: comparison ran the package, the library and the single file, and the
#: gate below read the list and passed.
def _compared_entrances(tmp_path):
    return set(_verdicts_through_every_entrance(tmp_path))


def test_the_parity_test_covers_every_entrance_this_tree_has(tmp_path):
    """"The same verdict from every entrance" is only worth what the
    comparison covers.

    Three entrances exist here and the comparison runs all three. A
    GitHub Action is named as a fourth and **does not exist** -- there is
    no `action.yml` in this tree -- so a promise about it is a promise
    about something unbuilt. When one arrives, this goes red until the
    comparison takes it, which is the only way that promise stays true
    without somebody remembering.
    """
    declared = set(_entrances_the_tree_declares())
    compared = _compared_entrances(tmp_path)
    assert declared <= compared, (
        "this tree declares %s and the comparison covers %s"
        % (sorted(declared), sorted(compared)))
    assert "github action" not in declared, (
        "an action exists now; add it to the comparison and to this list")


def test_the_security_page_names_the_second_file_and_its_bound():
    """`SECURITY.md` promises what this reader takes in, file by file
    and bound by bound, and `--template` reads one the paragraph did not
    mention.

    The row limit especially: it is the one bound in this project that
    is not about bytes, and it exists because bytes do not bound what a
    template costs. A reader sizing the tool from that page would have
    had no way to know either.
    """
    from aas_submodel_validate import tablegen

    page = " ".join((ROOT / "SECURITY.md").read_text("utf-8").split())
    assert "--template" in page, "the page does not mention the mode"
    assert "second" in page, page[:200]
    assert str(tablegen.MAX_TEMPLATE_ROWS) in page or "ten thousand" in page, (
        "the page does not name the row limit")


def test_the_schema_page_says_where_the_template_flag_is_recorded():
    """`options` is introduced as "the flags that move what is in the
    report", and `--template` moves it more than anything listed there.

    It is in `provenance` instead, on the argument that what decides a
    verdict is the template's bytes rather than the flag's spelling. That
    is a defensible place and an indefensible silence: the page states a
    rule and a reader who finds the flag in neither list is left to guess
    whether it was forgotten.
    """
    page = " ".join((ROOT / "docs" / "report-schema.md").read_text("utf-8").split())
    options = page.split("## `options`")[1].split("| key ")[0]
    assert "--template" in options, (
        "the options section states a rule the flag appears to break and "
        "never says where the flag went")
    assert "provenance" in options, options[:200]


def test_the_front_page_names_the_mode_where_a_reader_looks_for_a_capability():
    """It was named only in "When aas-submodel-validate is not the tool",
    which is the least likely place a reader looks for something the
    tool does."""
    page = (ROOT / "README.md").read_text("utf-8")
    section = page.split("## What it checks")[1].split("\n## ")[0]
    # Whitespace-normalised before matching. The sentence wraps across a
    # line in the file and a raw search for it finds nothing -- the same
    # miss the exit-code gates made, where a reflow was enough to hide a
    # promise from a check written line by line.
    flowing = " ".join(section.split())
    assert "--template" in flowing, (
        "the section that says what the tool checks does not mention the "
        "mode that checks a template the caller brought")
    assert "not a statement about conformance" in flowing, flowing[-400:]


#: JSON that parses and is not shaped like a template. A file somebody
#: else wrote is the case this mode exists for, and "well-formed JSON"
#: is a very long way from "an IDTA template".
NOT_TEMPLATE_SHAPED = (
    ('{"submodels":[{"semanticId":{"keys":[{"value":"urn:x"}]},'
     '"submodelElements":[{"idShort":"A"}]}]}', "an element with no modelType"),
    ('{"submodels":{"x":1}}', "submodels as an object"),
    ('{"submodels":[{"semanticId":3,"submodelElements":[]}]}',
     "a semanticId that is a number"),
    ('{"submodels":[{"semanticId":{"keys":"urn:x"},"submodelElements":[]}]}',
     "keys as a string"),
    ('{"submodels":[{"semanticId":{"keys":[{"value":"urn:x"}]},'
     '"submodelElements":{"a":1}}]}', "submodelElements as an object"),
    ('{"submodels":[{"semanticId":{"keys":[{"value":"urn:x"}]},'
     '"submodelElements":[{"modelType":"Property","idShort":"A",'
     '"qualifiers":7}]}]}', "qualifiers that are a number"),
    ('{"submodels":[7]}', "a submodel that is a number"),
)


@pytest.mark.parametrize("payload,shape", NOT_TEMPLATE_SHAPED,
                         ids=[shape for _p, shape in NOT_TEMPLATE_SHAPED])
def test_json_that_is_not_a_template_is_refused_not_raised(tmp_path, payload, shape):
    """The first repair wrapped the call that parses and left the three
    that read.

    Measured before this: fourteen of sixteen malformed shapes left as a
    traceback at exit 1 -- the code for a verdict with findings, about a
    file nothing finished reading, which is the contract that repair was
    about. The guard inside `_rows` for a child element existed and the
    entry loop over the submodel's own elements had none: written for the
    recursion and not for the way in.
    """
    from aas_submodel_validate.cli import main

    path = tmp_path / "not-a-template.json"
    path.write_text(payload, encoding="utf-8")
    assert main([str(_instance(tmp_path)), "--template", str(path), "-q"]) == 2, (
        "%s left by something other than 2" % shape)


def _declaring(identifier):
    """An environment whose one submodel declares `identifier`, and says
    which category of battery it is where that is what makes this tool's
    own rules speak."""
    from builders import env_json

    document = json.loads(env_json(identifier).decode("utf-8"))
    document["submodels"][0]["submodelElements"] = [{
        "modelType": "Property", "idShort": "batteryCategory",
        "semanticId": {"type": "ExternalReference", "keys": [{
            "type": "GlobalReference",
            "value": "urn:samm:io.admin-shell.idta.batterypass."
                     "technical_data:1.0.0#batteryCategory"}]},
        "valueType": "xs:string", "value": "ev"}]
    return json.dumps(document).encode("utf-8")


def test_no_rule_describes_a_submodel_a_supplied_table_took_over(tmp_path):
    """The stand-down reached `matched_submodels` and `SMT-D2` and not
    the battery rules, which walk `detect.instances` directly.

    Measured: a passport whose identifier a supplied template claims got
    `TPL-E02` saying the template requires an element, and `BAT-R8` four
    lines below saying the template permits it absent and "will not ask
    for it". One absent element, two findings, each denying the other —
    and `BAT-R8`'s whole premise is about a template that did not run.
    `BAT-R2` does the same on the identifier 02023 shares.

    Asked of every rule rather than of the two: the repair that reaches
    one of two siblings is the shape this project keeps meeting, and a
    third walker would inherit the same gap.
    """
    from aas_submodel_validate.rules import detect

    # Read from the source rather than listed. The list stood here and
    # held one identifier -- a `detect.PACKS` one -- while the docstring
    # above said "every rule". `BAT-R8` reads only the three
    # `PACK_ONLY_SEMANTIC_IDS`, so the loop never reached the rule whose
    # stand-down `detect.judgeable` was written for, and reverting that
    # stand-down left the whole suite green.
    identifiers = sorted(
        {pack.semantic_id for pack in detect.PACKS}
        | set(detect.PACK_ONLY_SEMANTIC_IDS))
    exercised = set()
    for index, identifier in enumerate(identifiers):
        instance = tmp_path / ("took-over-%d.json" % index)
        instance.write_bytes(_declaring(identifier))
        # A case that draws nothing without the flag proves nothing with
        # it. Measured: a bare submodel draws `BAT-R8` only once it says
        # which category of battery it is, and two of the three
        # table-less identifiers say nothing at all about a submodel
        # this thin. Those are passed over here rather than asserted
        # into silence -- and the coverage of the two *classes* is
        # asserted below, because the class with no table is the one the
        # loop used to miss entirely.
        alone = [f.id for f in runner.run(instance).findings
                 if not f.id.startswith(("TPL-", "META", "X"))]
        if not alone:
            continue
        exercised.add(identifier)

        template = _unclaimed_template(tmp_path, semantic_id=identifier)
        report = runner.run(instance, template=template)
        strangers = sorted({f.id for f in report.findings
                            if not f.id.startswith(("TPL-", "META", "X"))})
        assert not strangers, (
            "%s: a pack that stood down still reports on the submodel: %s"
            % (identifier, strangers))
        # And it was said. A report that simply gets quieter reads as the
        # file improving -- which is the failure
        # `test_standing_down_says_what_it_cost` exists to prevent, and
        # the note's condition consulted `detect.PACKS` alone, so for
        # these three identifiers two warnings vanished in silence.
        assert any("stood down" in note for note in report.notes), (
            "%s: %d finding(s) went away and no note says why: %s"
            % (identifier, len(alone), report.notes))
        # And nothing else describes what the stood-down rules found.
        # The coverage note was computed from `detect.instances` while
        # the rule it describes reads `detect.judgeable`, so it said
        # "BAT-R8 reported 2 of the 9 elements this table holds" in a run
        # where BAT-R8 reported none.
        reported = [note for note in report.notes
                    for rule_id in alone if note.startswith(rule_id + " ")]
        assert not reported, (
            "%s: a rule that stood down is described as having reported: %s"
            % (identifier, reported))

    assert exercised & {pack.semantic_id for pack in detect.PACKS}, (
        "no identifier with a table was exercised: %s" % sorted(exercised))
    assert exercised & set(detect.PACK_ONLY_SEMANTIC_IDS), (
        "no identifier whose rules have no table was exercised, which is "
        "exactly the class this test used to miss: %s" % sorted(exercised))


def test_rules_refuses_a_template_it_would_ignore(tmp_path):
    """`cli.py` carries a list of the flags `--rules` would have to
    ignore, under a comment saying that answering a different question
    in silence is what this tool refuses everywhere else. `--template`
    was added to the parser and not to the list.

    Measured: `--rules --template /no/such/file.json` printed all 220
    lines and exited 0, on a path that does not exist.
    """
    from aas_submodel_validate.cli import main

    with pytest.raises(SystemExit) as raised:
        main(["--rules", "--template", str(_unclaimed_template(tmp_path))])
    assert raised.value.code == 64, raised.value.code


def test_a_supplied_table_reads_an_idshort_pattern_and_says_nothing(tmp_path):
    """Pinned because four published sentences said otherwise.

    `--help`, `docs/scope.md`, the README and the CHANGELOG each listed
    "any `AllowedIdShort` pattern" among what a supplied template
    checks. The table does carry the pattern and the walk does record an
    element whose name does not match it -- and then `tablegen.rules_for`
    yields a rule per row from `violations` alone, so the drift reaches
    nothing. The only reporter is a pack's own lint, and a table built at
    run time registers no lints. Measured: a template demanding `^Beta$`
    against an element named `NotBeta` gave `ok`, 0 errors, 0 warnings,
    0 info.

    The four sentences say that now. This gate holds the fact rather
    than the wording: the day a supplied table reports the pattern, this
    goes red and the sentences are owed the item back.
    """
    from aas_submodel_validate import loader, rules
    from aas_submodel_validate import runner as runner_module
    from aas_submodel_validate.rules import engine

    template = _template_with_idshort_rule(tmp_path, "Beta")
    document = _instance_named(tmp_path, "NotBeta")

    report = runner.run(document, template=template)
    assert not report.findings, (
        "something reported the idShort pattern; the four sentences that "
        "say it is read and not said are owed the item back: %s"
        % [(f.id, f.violation.message) for f in report.findings])

    # The other half of what those sentences now say. A pattern this
    # reader cannot read at all is named in a note, because there it is
    # the template that went wrong and not the file -- and it is still
    # not a finding, so the verdict the caller asked for stands. Held
    # here beside the readable case: this gate ran only the readable one
    # while the same value was refusing whole templates, and stayed
    # green through it.
    unreadable = _template_with_idshort_rule(
        tmp_path, "Beta[\\d{3,2}]", name="unreadable.json")
    refused = runner.run(document, template=unreadable)
    assert not refused.findings, (
        "an unreadable naming suggestion became a finding about the file: "
        "%s" % [(f.id, f.violation.message) for f in refused.findings])
    assert any("AllowedIdShort" in note for note in refused.notes), (
        "a pattern this reader could not read was dropped in silence: %r"
        % refused.notes)

    # And the drift *is* seen -- so what the sentences describe is a
    # reporting gap and not a reading one, which is what they claim.
    table = runner_module._supplied_table(template)["table"]
    ctx = runner_module.Context(
        loader.load(document), rules.profiles.Selection(None),
        supplied=(table,), taken_over=frozenset([table.TEMPLATE_SEMANTIC_ID]))
    assert engine.analyze(ctx, table)["idshort_drift"], (
        "the walk no longer records the drift either, so the table is not "
        "reading the pattern at all")


def test_rules_refuses_an_empty_template_the_same_way(tmp_path):
    """`smtv --rules --template "$TPL"` with `TPL` unset.

    The list of flags `--rules` would have to ignore reads `args.path is
    not None` for the path, under a comment about this exact shape: a
    shell hands over `""`, read for truth it looks like "not given", and
    the tool answers a different question in silence. `--template` was
    added to that list two entries below, read for truth.

    Measured: `--rules --template ""` printed the listing and returned 0
    while the same call with a real path exits 64.
    """
    from aas_submodel_validate.cli import main

    with pytest.raises(SystemExit) as raised:
        main(["--rules", "--template", ""])
    assert raised.value.code == 64, (
        "an empty --template was dropped and the listing printed instead: "
        "returned %r" % (raised.value.code,))


def test_a_template_above_the_bound_is_refused_without_being_built(monkeypatch):
    """Refusing is cheap only if it happens while walking.

    The bound is read twice — once inside `_rows` as it goes, once after
    the tree is built — and the second alone is enough to refuse, which
    is why a test that only asserts the refusal cannot tell which one
    did it. What the first one buys is that the rows are never made:
    measured with only the second, three hundred thousand rows were
    materialised in 2.2 seconds and 282 MiB before the answer came, and
    the densest template inside the byte bound costs many times that —
    which on a machine with a memory limit is a kill and not an exit
    code.

    Counted rather than timed, so it says the same thing on every
    machine.
    """
    from aas_submodel_validate import tablegen

    calls = [0]
    original = tablegen._rows

    def counting(*args, **kwargs):
        calls[0] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(tablegen, "_rows", counting)

    over = tablegen.MAX_TEMPLATE_ROWS * 3
    document = {"submodels": [{
        "kind": "Template", "idShort": "T", "id": "urn:t",
        "semanticId": {"type": "GlobalReference",
                       "keys": [{"type": "GlobalReference", "value": "urn:x:top"}]},
        "submodelElements": [
            {"modelType": "Property", "idShort": "P%d" % i,
             "valueType": "xs:string",
             "semanticId": {"type": "GlobalReference",
                            "keys": [{"type": "GlobalReference",
                                      "value": "urn:x:%d" % i}]}}
            for i in range(over)]}]}
    with pytest.raises(tablegen.TemplateRefused):
        tablegen.build(document, {"prefix": "TPL-E", "citation": "c",
                                  "skip_sids": frozenset(), "item_names": {},
                                  "example_types": ()})
    assert calls[0] <= tablegen.MAX_TEMPLATE_ROWS + 1, (
        "%d rows were built before the refusal, of a template declaring %d; "
        "the bound is being read after the walk rather than during it"
        % (calls[0], over))


def test_no_pack_is_said_to_have_stood_down_when_none_did(tmp_path):
    """The sibling of a note that was already repaired, repaired one
    commit later than it should have been.

    The first note — "judged against the template you supplied" — got a
    condition and a test when it turned out to claim a verdict it took no
    part in. The second got a condition and no test, so making it
    unconditional leaves the report saying a pack of this tool's own
    answers for an identifier no pack here has ever heard of, with the
    whole suite green.
    """
    unclaimed = runner.run(_unclaimed_instance(tmp_path),
                           template=_unclaimed_template(tmp_path))
    assert not any("stood down" in note for note in unclaimed.notes), (
        "a pack is said to have stood down for an identifier no pack "
        "claims: %s" % unclaimed.notes)

    # And present where one really did, so this cannot pass by the note
    # having been deleted.
    claimed = runner.run(_instance(tmp_path), template=VENDORED)
    assert any("stood down" in note for note in claimed.notes), claimed.notes


def test_a_template_above_the_byte_bound_is_refused(tmp_path, monkeypatch):
    """`SECURITY.md` publishes a byte bound on the template file and
    nothing measured it.

    The row half of that sentence is held by a mutation row; the byte
    half was a promise with no gate, which is the one thing this project
    does not let itself ship.
    """
    from aas_submodel_validate import container, tablegen
    from aas_submodel_validate.cli import main

    monkeypatch.setattr(container, "MAX_PART_BYTES", 512)
    fat = tmp_path / "fat.json"
    fat.write_text(_unclaimed_template(tmp_path).read_text("utf-8")
                   + " " * 1024, encoding="utf-8")
    with pytest.raises(tablegen.TemplateRefused) as refused:
        runner._supplied_table(fat)
    assert "limit" in str(refused.value), refused.value
    assert main([str(_instance(tmp_path)), "--template", str(fat), "-q"]) == 2


def test_a_template_this_reader_cannot_open_is_a_refusal_not_a_traceback(tmp_path):
    """Named in the CHANGELOG as one of five refusals and measured as
    none of them.

    Without the classifier a missing path leaves as a `FileNotFoundError`
    traceback at exit 1 — the code for a verdict with findings, about a
    file nothing read.
    """
    from aas_submodel_validate.cli import main

    assert main([str(_instance(tmp_path)), "--template",
                 str(tmp_path / "no-such-template.json"), "-q"]) == 2


# -- what the file held, and what was read out of it --------------------------

def _declaring_it_as_a_specification(tmp_path):
    """An input whose submodel declares 02004's identifier as a *template*.

    `matched_submodels` reads `instances`, so a submodel marked
    `kind: Template` is filtered out before any rule sees it: the
    supplied table answers for nothing here, and the report says so in
    its own sentence rather than the one about an identifier nobody
    declares. That second sentence is the one the marker above missed.
    """
    from builders import hd_env

    document = json.loads(json.dumps(hd_env()))
    for submodel in document["submodels"]:
        submodel["kind"] = "Template"
    path = tmp_path / "declared-as-a-specification.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _two_template_file(tmp_path):
    """One file declaring two templates, which is a legal environment."""
    def ref(value):
        return {"type": "GlobalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    def template(semantic_id, short):
        return {"kind": "Template", "idShort": short, "id": "urn:t:" + short,
                "semanticId": ref(semantic_id),
                "submodelElements": [{
                    "modelType": "SubmodelElementCollection",
                    "idShort": short + "Type",
                    "semanticId": ref(semantic_id + "/Type"), "value": [],
                    "qualifiers": [{"type": "SMT/Cardinality",
                                    "valueType": "xs:string",
                                    "value": "One"}]}]}

    path = tmp_path / "two-templates.json"
    path.write_text(json.dumps({"submodels": [
        template(UNCLAIMED, "SoftwareNameplate"),
        template(UNCLAIMED + "/second", "Second")]}), encoding="utf-8")
    return path


def test_a_template_file_holding_more_than_one_template_says_so(tmp_path):
    """The table comes from the first submodel in the file. Nothing said
    the others were there.

    A caller whose file declares three templates gets a verdict about
    one of them, a `provenance.template` naming one identifier, and a
    summary counting the submodels that identifier matched -- and
    nothing anywhere distinguishes "your other templates matched
    nothing" from "your other templates were never read". Those call for
    opposite things from the reader, and the report let them look
    identical.

    It is a note rather than a refusal: an environment may legitimately
    carry several templates, and a reader who is told which one answered
    can split the file or reorder it. What it may not be is quiet.
    """
    report = runner.run(_unclaimed_instance(tmp_path),
                        template=_two_template_file(tmp_path))
    notes = " ".join(report.notes)
    assert "2 submodels" in notes or "two submodels" in notes, (
        "the template file declares two submodels and only the first was "
        "read; the report does not say so: %r" % report.notes)
    assert UNCLAIMED in notes, (
        "the note does not name the template the table came from: %r"
        % report.notes)


def test_a_profile_the_supplied_template_overrode_is_not_left_unsaid(tmp_path):
    """`--profile` chooses between two templates publishing one submodel
    identifier. A supplied table claiming that identifier takes it from
    both, so the flag decides nothing -- and nothing said so.

    The note that exists for a flag that chose nothing asks
    `Selection.chosen`, which knows about the pair and not about the
    stand-down, so it stays quiet on exactly the run where the flag was
    overridden. A caller who passed `--profile 02035-2` on purpose is
    entitled to know their choice was not the one that answered; the
    stand-down note beside it names the pack that stood down and not
    the flag that selected it.
    """
    import copy

    from builders import hd_env

    instance = tmp_path / "handover.json"
    instance.write_bytes(json.dumps(copy.deepcopy(hd_env())).encode("utf-8"))
    vendored = (pathlib.Path(runner.__file__).parent / "data" / "smt"
                / "02004" / "2.0.1" / "template.json")

    report = runner.run(instance, profile="02035-2", template=vendored)
    said = " ".join(report.notes)
    assert "--profile 02035-2" in said, (
        "the flag was overridden by the supplied template and no note "
        "mentions it: %r" % report.notes)
    assert "chose nothing" in said or "did not choose" in said, (
        "the notes never say the flag decided nothing: %r" % report.notes)


def test_the_two_notes_about_who_judged_cannot_both_be_said(tmp_path):
    """One of them says the supplied template made this verdict and the
    other says nothing was judged against it. A report carrying both
    tells a reader two incompatible things about the same file.

    They were written as one `if`/`else` and a later note was inserted
    between the two halves, which handed the `else` to the new
    condition: every single-submodel template that *did* answer then
    drew the sentence meant for one that answered nothing. The whole
    suite stayed green, because nothing asked whether the two could
    appear together.
    """
    import copy

    from builders import hd_env

    instance = tmp_path / "handover.json"
    instance.write_bytes(json.dumps(copy.deepcopy(hd_env())).encode("utf-8"))
    vendored = (pathlib.Path(runner.__file__).parent / "data" / "smt"
                / "02004" / "2.0.1" / "template.json")

    claimed = "judged against the template you supplied"
    # There are two sentences for "it answered nothing" -- one for an
    # identifier nothing declares and one for an identifier declared by
    # a specification rather than an instance -- and this read only the
    # first of them. Measured: with the `else` handed to a new
    # condition, a report drew the claiming note and the *second*
    # disowning one together, and this test passed. What the two have in
    # common is the clause, not the object of it.
    disowned = "othing was judged against"
    for label, report in (
            ("it answered", runner.run(instance, template=vendored)),
            ("it answered nothing",
             runner.run(_unclaimed_instance(tmp_path), template=vendored)),
            ("a specification declares it",
             runner.run(_declaring_it_as_a_specification(tmp_path),
                        template=vendored)),
            ("two templates in the file",
             runner.run(instance, template=_two_template_file(tmp_path)))):
        said = " ".join(report.notes)
        assert (claimed in said) != (disowned in said), (
            "%s: the report says both that the supplied template made this "
            "verdict and that nothing was judged against it -- %r"
            % (label, report.notes))


def test_a_run_time_table_places_its_rows_in_the_order_it_declares_them(tmp_path):
    """`rulesNotAsked` is "in the order the tables declare them", and a
    table built at run time was placed by none of them.

    `_all_rows` recovers each analysed table by looking its name up in
    `sys.modules`, which answers for the six vendored packs and cannot
    answer for a `Table` object: its name is a digest. So every run-time
    id fell to the fallback position `rows_not_reached` keeps for rows
    it cannot place, and came back sorted by its own spelling. The
    function's own comment said that fallback was unreachable "because
    every analysed table is an imported module" and named the moment it
    would stop being true; this is that moment.

    Past ninety-nine rows the two orders genuinely differ -- ids are
    zero-padded to two digits, so `TPL-E100` sorts before `TPL-E99` as a
    string and after it in the template.
    """
    from aas_submodel_validate import tablegen
    from aas_submodel_validate.loader import load
    from aas_submodel_validate.rules import engine, profiles

    def ref(value):
        return {"type": "GlobalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    rows = 105
    document = {"submodels": [{
        "kind": "Template", "idShort": "Wide", "id": "urn:t",
        "semanticId": ref(UNCLAIMED),
        "submodelElements": [
            {"modelType": "Property", "idShort": "Row%03d" % index,
             "semanticId": ref("%s/row%03d" % (UNCLAIMED, index)),
             "valueType": "xs:string",
             "qualifiers": [{"type": "SMT/Cardinality",
                             "valueType": "xs:string", "value": "One"}]}
            for index in range(rows)]}]}
    pack = {"prefix": "TPL-E", "citation": "a template you supplied",
            "skip_sids": frozenset(), "item_names": {}, "example_types": ()}
    table = tablegen.table_from(document, pack)
    assert len(table.ROWS) == rows

    ctx = runner.Context(load(_unclaimed_instance(tmp_path)),
                         profiles.Selection(None), supplied=(table,),
                         taken_over=frozenset([table.TEMPLATE_SEMANTIC_ID]))
    analysed = engine.analyze(ctx, table)

    # Two rows the run did not reach, given to the sorter the way the
    # walk gives them to it.
    analysed["lost_candidates"].extend(["TPL-E100", "TPL-E99"])
    assert engine.rows_not_reached(ctx) == ["TPL-E99", "TPL-E100"], (
        "a run-time table's rows are ordered by their spelling rather "
        "than by where the table puts them: %s"
        % engine.rows_not_reached(ctx))


def test_provenance_says_how_many_templates_the_file_held(tmp_path):
    """The note that says the file held more than one is prose, and
    `provenance` is the half a program reads.

    A consumer sees `rows` and `semanticId` and has no way to learn that
    two other templates in the same file were never opened: both fields
    describe the one submodel the table came from, and both look exactly
    the same whether the file held one or five. `notes` says it in a
    sentence, which means string-matching a sentence.
    """
    report = runner.run(_unclaimed_instance(tmp_path),
                        template=_two_template_file(tmp_path))
    carried = report.as_dict()["provenance"]["template"]
    assert carried["submodels"] == 2, (
        "provenance does not say how many submodels the template file "
        "declared: %s" % sorted(carried))
    # And the ordinary case is still stated rather than implied by
    # absence: a key that appears only sometimes is a key a consumer
    # cannot branch on.
    one = runner.run(_unclaimed_instance(tmp_path),
                     template=_unclaimed_template(tmp_path))
    assert one.as_dict()["provenance"]["template"]["submodels"] == 1


def _arbitrary_instance(tmp_path):
    """A Technical Data submodel carrying one element of a manufacturer's
    own, under 02003 §3.5's open-content marker.

    This is the shape `docs/divergences.md` #19 is about: the template
    says a section may hold content it does not describe, and the file
    holds some.
    """
    def sid(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    general = {
        "modelType": "SubmodelElementCollection",
        "idShort": "GeneralInformation",
        "semanticId": sid("0173-1#02-ABK161#002/0173-1#01-AHX838#002"),
        "value": [
            {"modelType": "Property", "idShort": "ManufacturerName",
             "semanticId": sid("0173-1#02-AAO677#004"),
             "valueType": "xs:string", "value": "x"},
            {"modelType": "MultiLanguageProperty",
             "idShort": "ManufacturerProductDesignation",
             "semanticId": sid("0173-1#02-AAW338#003"),
             "value": [{"language": "en", "text": "t"}]},
            {"modelType": "Property", "idShort": "ManufacturerArticleNumber",
             "semanticId": sid("0173-1#02-AAO676#005"),
             "valueType": "xs:string", "value": "x"},
            {"modelType": "Property", "idShort": "ManufacturerOrderCode",
             "semanticId": sid("0173-1#02-AAO227#004"),
             "valueType": "xs:string", "value": "x"},
        ],
    }
    area = {
        "modelType": "SubmodelElementCollection",
        "idShort": "TechnicalPropertyArea",
        "semanticId": sid("0173-1#02-ABL358#002/0173-1#01-AHX773#002"),
        "value": [{"modelType": "MultiLanguageProperty", "idShort": "MyOwnNote",
                   "semanticId": sid("https://admin-shell.io/SMT/General/Arbitrary"),
                   "value": [{"language": "en", "text": "mine"}]}],
    }
    areas = {
        "modelType": "SubmodelElementList", "idShort": "TechnicalPropertyAreas",
        "semanticId": sid("0173-1#02-ABK163#002"),
        "typeValueListElement": "SubmodelElementCollection",
        "orderRelevant": True, "value": [area],
    }
    path = tmp_path / "td-arbitrary.json"
    path.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:td", "idShort": "TechnicalData",
        "semanticId": sid("0173-1#01-AHX837#002"),
        "submodelElements": [general, areas]}]}).encode("utf-8"))
    return path


def test_open_content_a_template_declares_draws_nothing(tmp_path):
    """A manufacturer's own element passes, whichever table judges it.

    `docs/divergences.md` #19 is a reading of the *template*, not a
    choice one pack made: 02003 §3.5 says a section may hold content the
    template does not describe, so no rule is generated from the
    placeholder. Every pack that has such placeholders drops them.

    A table built at run time was handed an empty skip list, so it
    generated rules from them -- and #19 names what that produces
    exactly: "the first row would claim every arbitrary element the walk
    met and then fault it for being the wrong kind". Measured on this
    file and this project's own vendored 02003 template: clean by
    default, `TPL-E22 'Section (TechnicalPropertyAreasItem)' must be a
    SubmodelElementCollection` with the flag, exit 0 becoming exit 1 on
    a file nothing is wrong with.
    """
    supplied = runner.run(_arbitrary_instance(tmp_path), template=VENDORED)
    faulted = [f for f in supplied.findings if f.id.startswith("TPL-")]
    assert not faulted, (
        "a template's own open-content placeholder generated a rule, and it "
        "faulted an element the template permits: %s"
        % [(f.id, f.violation.message) for f in faulted])


def test_every_marker_idta_publishes_is_skipped(tmp_path):
    """Asked of a template of our own, because the parity gate cannot.

    That gate reads the six vendored templates, and what they happen to
    use is what the per-pack lists happened to hold -- so a marker IDTA
    publishes and none of the six uses is invisible to it, in both
    directions. `IntentionallyEmpty` was exactly that: named in *How to
    Create a Submodel Template Specification* V1.1 Table 11 beside
    `Arbitrary`, carried by no vendored pack, and therefore in no list.
    A template marking content with it generated a rule from the
    placeholder and faulted a manufacturer's own element for being the
    wrong kind -- `docs/divergences.md` #19's sentence, reached through
    the one marker the collection missed.

    Built here rather than read from a file, so a marker added to the
    set without a template to show for it still has to earn its place.
    """
    from aas_submodel_validate import tablegen

    def sid(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    def card(value):
        return {"semanticId": sid("https://admin-shell.io/SubmodelTemplates/"
                                  "Cardinality/1/0"),
                "type": "SMT/Cardinality", "valueType": "xs:string",
                "value": value}

    # Read from somewhere other than the set this holds. Iterating
    # `OPEN_CONTENT_MARKERS` made the gate agree with whatever the set
    # said: removing `IntentionallyEmpty` -- the defect this test was
    # written for -- simply shortened the loop and it passed. The two
    # published ones are literals with their source; the typed ones are
    # read out of the vendored template bytes, which is where they came
    # from and which no edit to the set can change.
    published = {
        # IDTA, How to Create a Submodel Template Specification V1.1
        # (June 2025), Table 11 "Marking arbitrary content in
        # SubmodelElement data" -- these two and no others.
        "https://admin-shell.io/SMT/General/Arbitrary",
        "https://admin-shell.io/SMT/General/IntentionallyEmpty",
    }
    carried = set()
    data = pathlib.Path(runner.__file__).parent / "data" / "smt"
    for document in sorted(data.glob("*/*/template.json")):
        for found in re.findall(r"https://admin-shell\.io/SMT/General/\w+",
                                document.read_text("utf-8-sig")):
            carried.add(found)
    assert carried, "no vendored template names a marker any more"
    missing = (published | carried) - set(tablegen.OPEN_CONTENT_MARKERS)
    assert not missing, (
        "a marker a published guideline names, or one a vendored template "
        "carries, is not skipped: %s" % sorted(missing))

    for marker in sorted(published | carried):
        template = tmp_path / ("marker-%s.json" % marker.rsplit("/", 1)[-1])
        template.write_bytes(json.dumps({"submodels": [{
            "modelType": "Submodel", "id": "urn:test:m", "idShort": "S",
            "kind": "Template", "semanticId": sid("urn:test:top"),
            "submodelElements": [{
                "modelType": "SubmodelElementCollection", "idShort": "Section",
                "semanticId": sid("urn:test:section"),
                "qualifiers": [card("One")],
                "value": [
                    {"modelType": "Property", "idShort": "Named",
                     "semanticId": sid("urn:test:named"),
                     "valueType": "xs:string", "qualifiers": [card("One")]},
                    {"modelType": "Property", "idShort": "UserProperty",
                     "semanticId": sid(marker), "valueType": "xs:string",
                     "qualifiers": [card("ZeroToMany")]}]}]}]}
        ).encode("utf-8"))

        instance = tmp_path / ("marker-inst-%s.json" % marker.rsplit("/", 1)[-1])
        instance.write_bytes(json.dumps({"submodels": [{
            "modelType": "Submodel", "id": "urn:test:i", "idShort": "S",
            "semanticId": sid("urn:test:top"),
            "submodelElements": [{
                "modelType": "SubmodelElementCollection", "idShort": "Section",
                "semanticId": sid("urn:test:section"),
                "value": [
                    {"modelType": "Property", "idShort": "Named",
                     "semanticId": sid("urn:test:named"),
                     "valueType": "xs:string", "value": "v"},
                    {"modelType": "MultiLanguageProperty",
                     "idShort": "MyOwnNote", "semanticId": sid(marker),
                     "value": [{"language": "en", "text": "mine"}]}]}]}]}
        ).encode("utf-8"))

        built = runner._supplied_table(template)["table"]
        assert len(built.ROWS) == 2, (
            "%s: the placeholder generated a row; the table is %s"
            % (marker, [row["label"] for row in built.ROWS]))
        report = runner.run(instance, template=template)
        assert not report.findings, (
            "%s: a manufacturer's own element was faulted against a "
            "placeholder the template says it may fill freely: %s"
            % (marker, [(f.id, f.violation.message) for f in report.findings]))


def test_a_marker_is_recognised_in_the_comparison_form(tmp_path):
    """The skip folds its side, like every other reference reader here.

    It was the one that did not, so a marker written with a trailing
    space generated a row while the same value matched on the instance
    side. Reverting the fold left the whole suite green, which is what
    this is for.
    """
    def sid(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    def card(value):
        return {"semanticId": sid("https://admin-shell.io/SubmodelTemplates/"
                                  "Cardinality/1/0"),
                "type": "SMT/Cardinality", "valueType": "xs:string",
                "value": value}

    spaced = " https://admin-shell.io/SMT/General/Arbitrary "
    template = tmp_path / "spaced-marker.json"
    template.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:sp", "idShort": "S",
        "kind": "Template", "semanticId": sid("urn:test:top"),
        "submodelElements": [
            {"modelType": "Property", "idShort": "Named",
             "semanticId": sid("urn:test:named"), "valueType": "xs:string",
             "qualifiers": [card("One")]},
            {"modelType": "Property", "idShort": "UserProperty",
             "semanticId": sid(spaced), "valueType": "xs:string",
             "qualifiers": [card("ZeroToMany")]}]}]}).encode("utf-8"))

    built = runner._supplied_table(template)["table"]
    assert [row["label"] for row in built.ROWS] == ["Named"], (
        "a marker this reader would match on the instance side generated a "
        "row on the template side: %s" % [r["label"] for r in built.ROWS])


def test_a_marker_beside_a_real_identity_does_not_become_one(tmp_path):
    """An open-content marker says a place is open, not what belongs in it.

    The skip reads an element's own semanticId; the row's match set reads
    that *and* its supplementals. So a template element that carries a
    real identifier and marks itself open content beside it kept its row
    -- and the marker went into the row's match values, where it is an
    identity like any other. A supplier's arbitrary element then answered
    a mandatory row it has nothing to do with.

    Measured: a template demanding one `urn:test:real` Property, against
    a file holding only the supplier's own element under the marker --
    `ok` true, no findings, the required element absent. The verdict this
    project exists to give, given backwards.

    Zero of the 156 rows across the packs hold a marker in their match
    set, because all 43 markers in the six vendored templates are an
    element's own semanticId. This is what a caller's template can do.
    """
    def sid(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    def card(value):
        return {"semanticId": sid("https://admin-shell.io/SubmodelTemplates/"
                                  "Cardinality/1/0"),
                "type": "SMT/Cardinality", "valueType": "xs:string",
                "value": value}

    marker = "https://admin-shell.io/SMT/General/Arbitrary"
    template = tmp_path / "supplemental-marker.json"
    template.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:sup", "idShort": "S",
        "kind": "Template", "semanticId": sid("urn:test:top"),
        "submodelElements": [
            {"modelType": "Property", "idShort": "Real",
             "semanticId": sid("urn:test:real"), "valueType": "xs:string",
             "supplementalSemanticIds": [sid(marker)],
             "qualifiers": [card("One")]}]}]}).encode("utf-8"))

    built = runner._supplied_table(template)["table"]
    assert [row["label"] for row in built.ROWS] == ["Real"], (
        "the element keeps its row: it has an identifier of its own, and "
        "the marker beside it does not take that away: %s"
        % [row["label"] for row in built.ROWS])
    assert marker not in built.ROWS[0]["match"], (
        "the row answers to the marker as though it were an identifier: %s"
        % (built.ROWS[0]["match"],))

    document = tmp_path / "suppliers-own.json"
    document.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:i", "idShort": "S",
        "semanticId": sid("urn:test:top"),
        "submodelElements": [
            {"modelType": "Property", "idShort": "SomethingOfMine",
             "semanticId": sid(marker), "valueType": "xs:string",
             "value": "x"}]}]}).encode("utf-8"))
    report = runner.run(document, template=template)
    assert not report.ok, (
        "the template requires one `urn:test:real` and the file has none; "
        "the run said the file is fine")
    assert any("Real" in finding.violation.message
               for finding in report.findings), (
        "nothing said which element is missing: %s"
        % [f.violation.message for f in report.findings])


def _marker_placeholder(tmp_path, own, supplemental, name):
    """A one-row template whose only element is a placeholder, with the
    marker in whichever position the caller names."""
    def sid(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    def card(value):
        return {"semanticId": sid("https://admin-shell.io/SubmodelTemplates/"
                                  "Cardinality/1/0"),
                "type": "SMT/Cardinality", "valueType": "xs:string",
                "value": value}

    element = {"modelType": "Property", "idShort": "AnyProp",
               "valueType": "xs:string", "qualifiers": [card("One")]}
    if own is not None:
        element["semanticId"] = sid(own)
    if supplemental is not None:
        element["supplementalSemanticIds"] = [sid(supplemental)]

    template = tmp_path / name
    template.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:ph", "idShort": "P",
        "kind": "Template", "semanticId": sid("urn:test:top"),
        "submodelElements": [element]}]}).encode("utf-8"))

    document = tmp_path / ("doc-" + name)
    document.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:doc", "idShort": "P",
        "semanticId": sid("urn:test:top"),
        "submodelElements": [{
            "modelType": "Property", "idShort": "MyOwn",
            "semanticId": sid("urn:vendor:mine"), "valueType": "xs:string",
            "value": "x"}]}]}).encode("utf-8"))
    return document, template


MARKER = "https://admin-shell.io/SMT/General/Arbitrary"


def test_a_placeholder_that_also_names_something_is_still_a_placeholder(tmp_path):
    """What the template calls the element decides, and what it carries
    beside that describes it.

    A placeholder may say more than "anything": a unit, a preferred
    type, a link to what the free content is about. Read as "every
    identifier has to be a marker", such an element stopped being open
    content and became a mandatory row -- so the supplier's own element,
    sitting in exactly the place the template left them, was reported
    missing. `found 0` about a file that is fine is the outcome
    `docs/divergences.md` #19 exists to prevent, arriving from the
    repair meant to prevent it.
    """
    document, template = _marker_placeholder(
        tmp_path, own=MARKER, supplemental="urn:vendor:unit", name="own.json")
    built = runner._supplied_table(template)["table"]
    assert not built.ROWS, (
        "the template's own placeholder generated a row: %s"
        % [row["label"] for row in built.ROWS])
    report = runner.run(document, template=template)
    assert report.ok and not report.findings, (
        "the supplier's own element was faulted against a placeholder the "
        "template says they may fill freely: %s"
        % [(f.id, f.violation.message) for f in report.findings])


def test_a_template_that_states_no_checkable_rule_says_so(tmp_path):
    """A pass that compared nothing looks exactly like a pass.

    `--require-all-judged` counts submodels, and a submodel judged
    against a table of no rows is judged. So a template whose every
    element is open content came back `ok` at exit 0 having asked
    nothing, and the only trace was `provenance.template.rows` at zero --
    a field a person reading the screen never sees, and the one number
    that would have told them.
    """
    document, template = _marker_placeholder(
        tmp_path, own=MARKER, supplemental=None, name="all-open.json")
    built = runner._supplied_table(template)["table"]
    assert not built.ROWS, [row["label"] for row in built.ROWS]
    report = runner.run(document, template=template)
    assert report.ok, report.findings
    assert any("no rule this reader can check" in note
               for note in report.notes), (
        "a run that compared nothing came back a pass and said nothing "
        "about it: %r" % report.notes)


def test_a_marker_somewhere_other_than_the_elements_own_id_does_not_hide_a_subtree(tmp_path):
    """Going quiet is the one direction with no second opinion.

    The rule was once "every identifier this element declares is a
    marker", and a container with no semanticId of its own and a marker
    in a supplemental met it -- so the container was dropped and every
    row beneath it with it. Measured on a template whose `Box` holds a
    mandatory `Inner`: a file missing `Inner` went from an error to `ok`
    at exit 0, and nothing on the page said a subtree had been skipped.

    Such a container is still not an obligation -- markers are not
    identities and nothing can answer a row with an empty match set --
    but that is settled the way every other unanswerable row is: the
    obligation is dropped, the rows underneath stay in the table, and
    the run says which element the template failed to identify.
    """
    def sid(*values):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}
                         for value in values]}

    def card(value):
        return {"semanticId": sid("https://admin-shell.io/SubmodelTemplates/"
                                  "Cardinality/1/0"),
                "type": "SMT/Cardinality", "valueType": "xs:string",
                "value": value}

    template = tmp_path / "hidden-subtree.json"
    template.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:h", "idShort": "S",
        "kind": "Template", "semanticId": sid("urn:test:top"),
        "submodelElements": [{
            "modelType": "SubmodelElementCollection", "idShort": "Box",
            "supplementalSemanticIds": [sid(MARKER)],
            "qualifiers": [card("One")],
            "value": [{"modelType": "Property", "idShort": "Inner",
                       "valueType": "xs:string",
                       "semanticId": sid("urn:test:inner"),
                       "qualifiers": [card("One")]}]}]}]}).encode("utf-8"))

    built = runner._supplied_table(template)["table"]
    labels = [row["label"] for row in built.ROWS]
    assert "Inner" in labels, (
        "the rows under an element the template did not identify were "
        "dropped with it: %s" % labels)
    box = built.BY_LABEL["Box"]
    assert box["card"] == (0, None), (
        "an element nothing can answer kept its obligation: %s"
        % (box["card"],))

    document = tmp_path / "no-inner.json"
    document.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:d", "idShort": "S",
        "semanticId": sid("urn:test:top"),
        "submodelElements": [{
            "modelType": "SubmodelElementCollection", "idShort": "Box",
            "semanticId": sid(MARKER), "value": []}]}]}).encode("utf-8"))
    report = runner.run(document, template=template)
    said = " ".join(report.notes)
    assert "Box" in said and "no semanticId" in said, (
        "a subtree went unexamined and the run said nothing: %r"
        % report.notes)


def test_every_pack_skips_through_the_one_shared_set(tmp_path):
    """The generator and the run-time builder read one list.

    Three packs kept a literal empty set after the list was shared --
    correct for the templates vendored today and one re-vendoring away
    from the divergence the sharing was meant to end. Reverting any one
    of them left the suite green and the generated tables byte-identical,
    because no vendored byte moves. Asked of the generator's own pack
    table instead.
    """
    from aas_submodel_validate import tablegen

    generator = _generator_module()
    for pack in generator.PACKS:
        assert pack["skip_sids"] is tablegen.OPEN_CONTENT_MARKERS, (
            "%s carries its own open-content list (%s); the point of sharing "
            "one is that a marker added to it reaches every pack"
            % (pack["output"].name, sorted(pack["skip_sids"])))


def _generator_module():
    """`tools/extract_smt_rules.py`, imported by path -- `tools/` is not
    a package and is not installed."""
    import importlib.util

    where = pathlib.Path(runner.__file__).parents[2] / "tools" / "extract_smt_rules.py"
    spec = importlib.util.spec_from_file_location("_extract_for_test", where)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_vendored_template_supplied_builds_the_table_its_pack_did(tmp_path):
    """The same file, read twice, describes the same obligations.

    Each pack here is generated from one of these template files. Handed
    the very file its pack came from, the run-time builder has to reach
    the same table -- and the row count is the cheap end of that: it went
    54 against the pack's 26 for 02003, 36 against 30 for 02006, 27
    against 26 for 02023, and every one of those extra rows was an
    open-content placeholder the pack drops.

    Asked of all eleven rather than of the one that failed, because the
    difference was a list the two readers kept separately.
    """
    from aas_submodel_validate.rules import (
        contact_tables,
        dbp1_tables,
        dbp4_tables,
        dbp5_tables,
        dbp_tables,
        dn_tables,
        hd_tables,
        hs_tables,
        pcf_tables,
        sn_tables,
        td_tables,
    )

    packs = {"02002": contact_tables, "02003": td_tables, "02004": hd_tables,
             "02006": dn_tables, "02007": sn_tables, "02011": hs_tables,
             "02023": pcf_tables, "02035-2": dbp_tables, "02035-5": dbp5_tables,
             "02035-1": dbp1_tables, "02035-4": dbp4_tables}
    data = pathlib.Path(runner.__file__).parent / "data" / "smt"
    seen = 0
    for document in sorted(data.glob("*/*/template.json")):
        key = document.parent.parent.name
        built = runner._supplied_table(document)["table"]
        assert len(built.ROWS) == len(packs[key].ROWS), (
            "%s: the table built from this file at run time has %d rows and "
            "the pack generated from the same file has %d"
            % (key, len(built.ROWS), len(packs[key].ROWS)))
        seen += 1
    assert seen == len(packs), (
        "this gate read %d vendored templates and there are %d packs"
        % (seen, len(packs)))


def _template_with_idshort_rule(tmp_path, pattern, name="t.json"):
    """A one-row template whose only row carries `AllowedIdShort`."""
    def sid(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    def qualifier(kind, value, marker):
        return {"semanticId": sid(marker), "type": kind,
                "valueType": "xs:string", "value": value}

    path = tmp_path / name
    path.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:tpl", "idShort": "Mine",
        "kind": "Template", "semanticId": sid("urn:test:mine"),
        "submodelElements": [{
            "modelType": "Property", "idShort": "A",
            "semanticId": sid("urn:test:a"), "valueType": "xs:string",
            "qualifiers": [
                qualifier("SMT/Cardinality", "One",
                          "https://admin-shell.io/SubmodelTemplates/"
                          "Cardinality/1/0"),
                qualifier("AllowedIdShort", pattern,
                          "https://admin-shell.io/SubmodelTemplates/"
                          "AllowedIdShort/1/0")]}]}]}).encode("utf-8"))
    return path


def _instance_named(tmp_path, id_short, name="i.json"):
    def sid(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    path = tmp_path / name
    path.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:inst", "idShort": "Mine",
        "semanticId": sid("urn:test:mine"),
        "submodelElements": [{
            "modelType": "Property", "idShort": id_short,
            "semanticId": sid("urn:test:a"), "valueType": "xs:string",
            "value": "v"}]}]}).encode("utf-8"))
    return path


def test_an_allowed_idshort_that_is_not_a_regex_does_not_blame_this_tool(tmp_path):
    """A caller's qualifier is a value, not a program.

    `_intended_pattern` translates IDTA's `Name[\\d{2,3}]` spelling and
    otherwise wrapped the value into `^...$` without compiling it. A
    template whose `AllowedIdShort` is `A[` therefore made *every* row of
    that table raise at walk time -- and the funnel turned each one into
    "the rule itself could not run", whose remedy reads "This is a defect
    in the validator, not in your file; please report it." It is a defect
    in the file, the run left by 1 rather than the 2 that means the input
    could not be judged, and the report said `judged 1 of 1` over a run
    in which no row was evaluated.

    Measured on every `AllowedIdShort` in all six vendored templates:
    each one uses the bracket spelling, so reading anything else as a
    literal moves no pack.
    """
    template = _template_with_idshort_rule(tmp_path, "A[")
    report = runner.run(_instance_named(tmp_path, "A["), template=template)
    could_not_run = [f for f in report.findings
                     if "could not run" in f.violation.message]
    assert not could_not_run, (
        "a value in the caller's file was run as a pattern and the crash was "
        "reported as ours: %s"
        % [(f.id, f.violation.fix) for f in could_not_run])


def test_an_allowed_idshort_is_read_as_written(tmp_path):
    """`Doc(1)` names an element called `Doc(1)`.

    Unescaped, the parentheses were a regex group and the qualifier
    matched `Doc1` -- so a file that carries the element the template
    asks for by name was told it does not, and one that does not was
    told it does. IDTA's own spelling for a numbering suffix is the
    bracket form, which `_intended_pattern` still translates."""
    from aas_submodel_validate import tablegen

    assert tablegen._intended_pattern("RefersTo[\\d{2,3}]") == \
        "^RefersTo(?:\\d{2,3})?$", "the IDTA spelling stopped being translated"

    import re

    # The branch that keeps IDTA's spelling is still the caller's text
    # in front of IDTA's suffix. The first repair escaped the other
    # branch only, so a value that matched this one carried both halves
    # of the defect: `A[[\\d{2}]` did not compile, and `Doc(1)[\\d{2}]`
    # matched `Doc1` rather than the element the template names.
    for spelling in ("A[[\\d{2}]", "A)[\\d{2}]", "A|B[\\d{2}]"):
        re.compile(tablegen._intended_pattern(spelling))
    numbered = tablegen._intended_pattern("Doc(1)[\\d{2}]")
    assert re.match(numbered, "Doc(1)") and re.match(numbered, "Doc(1)07"), numbered
    assert not re.match(numbered, "Doc1"), numbered

    literal = tablegen._intended_pattern("Doc(1)")
    assert re.match(literal, "Doc(1)"), (
        "the element the template names does not match its own qualifier: %r"
        % literal)
    assert not re.match(literal, "Doc1"), (
        "%r matched an element the template did not name" % literal)


def test_a_numbering_suffix_that_is_not_a_repeat_is_read_as_unreadable():
    """The bracket branch keeps IDTA's suffix as a program, and one
    spelling of it is a program Python will not build.

    `_ALLOWED` admits `\\d{M}` and `\\d{M,N}` for any digits, and a
    minimum above its maximum is not a repeat: `\\d{3,2}` raises
    `re.error` the first time the row is used. Nothing compiled it here,
    so the failure arrived at walk time inside the funnel, which reported
    every row of that table as "the rule itself could not run" under a
    remedy reading "This is a defect in the validator, not in your file".
    Of the spellings the pattern admits, the ones whose bounds run
    backwards do this, and they are not a small corner of the set.

    Compiled here rather than pattern-matched, so a spelling nobody
    anticipated is answered too: what this asks is whether the string
    this function returns is one Python can run.
    """
    from aas_submodel_validate import tablegen

    backwards, forwards = set(), set()
    suffixes = ["\\d{%d}" % low for low in range(10)]
    suffixes += ["\\d{%d,%d}" % (low, high)
                 for low in range(10) for high in range(10)]
    for suffix in suffixes:
        bounds = [int(n) for n in re.findall(r"\d", suffix.replace("\\d", ""))]
        (backwards if len(bounds) == 2 and bounds[0] > bounds[1]
         else forwards).add(suffix)
    assert backwards and forwards, "this gate stopped telling the two apart"

    unread = set()
    for suffix in suffixes:
        pattern = tablegen._intended_pattern("A[%s]" % suffix)
        if pattern is None:
            unread.add(suffix)
            continue
        re.compile(pattern)          # the walk's first act, brought forward

    assert unread == backwards, (
        "spellings this reader accepted and could not run: %s; spellings it "
        "gave up on and could have run: %s"
        % (sorted(backwards - unread), sorted(unread - backwards)))
    for suffix in sorted(forwards):
        assert tablegen._intended_pattern("A[%s]" % suffix) == \
            "^A(?:%s)?$" % suffix, suffix


def test_a_qualifier_carrying_no_string_is_not_a_traceback():
    """`Qualifier.value` is optional in the metamodel.

    So a qualifier declaring this type and no value at all is a legal
    file, and one carrying a number or a boolean is a file this reader
    should have an answer for. It had one answer for all three: the
    regular-expression match raised `TypeError`, which the reader above
    turned into "parses as JSON and is not shaped like an IDTA
    template" -- a sentence about the whole file, naming no qualifier,
    for something that is neither malformed nor fatal.
    """
    from aas_submodel_validate import tablegen

    for value in (None, 123, True, [], {}):
        assert tablegen._intended_pattern(value) is None, value


def test_an_unreadable_naming_suggestion_does_not_take_the_verdict_with_it(tmp_path):
    """What it costs to refuse, measured on a file that has a real defect.

    The value feeds one rule, at `info`, whose own remedy reads "Any
    unique idShort is legal; this is tidiness, not conformance" -- and a
    table built at run time registers no lints, so under this flag
    nothing reads it at all. Refused with the template, an unreadable
    one threw away every MUST verdict on the file: the run left by 2
    with no report, and the missing mandatory element went unmentioned.
    Ten lines above it in the same function, an unreadable
    `SMT/Cardinality` -- which decides whether an element is required at
    all -- quietly defaults to `0..*` and the run leaves by 0.

    So it is a note now, and the file is still judged.
    """
    def sid(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    def qualifier(kind, value, marker):
        made = {"semanticId": sid(marker), "type": kind,
                "valueType": "xs:string"}
        if value is not None:
            made["value"] = value
        return made

    def element(id_short, semantic, extra=()):
        return {"modelType": "Property", "idShort": id_short,
                "valueType": "xs:string", "semanticId": sid(semantic),
                "qualifiers": [qualifier(
                    "SMT/Cardinality", "One",
                    "https://admin-shell.io/SubmodelTemplates/Cardinality/1/0"
                )] + list(extra)}

    unreadable = qualifier(
        "AllowedIdShort", "Doc[\\d{3,2}]",
        "https://admin-shell.io/SubmodelTemplates/AllowedIdShort/1/0")
    template = tmp_path / "backwards.json"
    template.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:c", "idShort": "C",
        "kind": "Template", "semanticId": sid("urn:test:top"),
        "submodelElements": [element("Doc", "urn:test:doc", [unreadable]),
                             element("Needed", "urn:test:needed")]}]}
    ).encode("utf-8"))

    document = tmp_path / "doc.json"
    document.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:i", "idShort": "C",
        "semanticId": sid("urn:test:top"),
        "submodelElements": [{"modelType": "Property", "idShort": "Doc07",
                              "semanticId": sid("urn:test:doc"),
                              "valueType": "xs:string", "value": "v"}]}]}
    ).encode("utf-8"))

    report = runner.run(document, template=template)
    missing = [f for f in report.findings if "'Needed'" in f.violation.message]
    assert missing, (
        "the file is missing a mandatory element and the run did not say "
        "so: %s" % [(f.id, f.violation.message) for f in report.findings])
    said = " ".join(report.notes)
    assert "AllowedIdShort" in said and "Doc[\\d{3,2}]" in said, (
        "nothing told the caller which qualifier could not be read: %r"
        % report.notes)
    assert not [f for f in report.findings
                if "could not run" in f.violation.message], (
        "a value in the caller's template was run as a pattern and the "
        "crash was reported as ours")


def test_a_vendored_template_this_reader_cannot_read_stops_the_build(tmp_path):
    """The opposite answer, for the opposite reason.

    A caller's template is theirs and this project cannot fix it, so an
    unreadable qualifier is a note beside a verdict. A vendored one is
    this project's, and a table that silently dropped the value would
    ship the defect. The build tool stops and names the row.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "extract_smt_rules", ROOT / "tools" / "extract_smt_rules.py")
    extract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extract)

    template = _template_with_idshort_rule(tmp_path, "A[\\d{3,2}]")
    pack = {"prefix": "X-E", "citation": "a test", "item_names": {},
            "example_types": (), "skip_sids": frozenset(),
            "template": template, "output": tmp_path / "x_tables.py"}
    with pytest.raises(SystemExit) as stopped:
        extract.generate(pack)
    assert "AllowedIdShort" in str(stopped.value), stopped.value
    assert "A[\\d{3,2}]" in str(stopped.value), stopped.value


def test_an_element_the_template_identifies_with_nothing_is_not_an_obligation(tmp_path):
    """An error no file could clear, on a file that carries the element.

    Matching here is by identifier and never by idShort -- that is the
    walk's own rule and `_matches_row` says so. An element a template
    declares with no semanticId therefore has an empty match set, and
    outside a list nothing can answer it: a mandatory row on one
    reported `found 0` against a file carrying an element of exactly the
    name the template writes, under a remedy that ended "with semanticId
    " and stopped, because there was nothing to name.

    Inside a list it is a different element: a sole item row with no
    identifier of its own is matched by its kind, which is how the
    published templates write one, so that row keeps its obligation.
    """
    def sid(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    def card(value):
        return {"semanticId": sid("https://admin-shell.io/SubmodelTemplates/"
                                  "Cardinality/1/0"),
                "type": "SMT/Cardinality", "valueType": "xs:string",
                "value": value}

    template = tmp_path / "unidentified.json"
    template.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:u", "idShort": "U",
        "kind": "Template", "semanticId": sid("urn:test:top"),
        "submodelElements": [{
            "modelType": "Property", "idShort": "Nameless",
            "valueType": "xs:string", "qualifiers": [card("One")]}]}]}
    ).encode("utf-8"))

    document = tmp_path / "carries-it.json"
    document.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:d", "idShort": "U",
        "semanticId": sid("urn:test:top"),
        "submodelElements": [{
            "modelType": "Property", "idShort": "Nameless",
            "valueType": "xs:string", "value": "v"}]}]}).encode("utf-8"))

    report = runner.run(document, template=template)
    assert report.ok and not report.findings, (
        "the file carries the element the template names and was told it "
        "does not: %s" % [(f.id, f.violation.message, f.violation.fix)
                          for f in report.findings])
    said = " ".join(report.notes)
    assert "no semanticId" in said and "Nameless" in said, (
        "the template asks for something it identifies with nothing and "
        "the run said nothing about it: %r" % report.notes)


def test_a_list_item_with_no_identifier_of_its_own_keeps_its_obligation(tmp_path):
    """The other side of the same line, and the reason it is a line.

    A `SubmodelElementList` names its item row by kind, not by
    identifier -- the published templates write one that way -- so an
    item carrying no semanticId is the ordinary case and not a template
    defect. Dropping the obligation from every unidentified row would
    have taken these with it.
    """
    def sid(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    def card(value):
        return {"semanticId": sid("https://admin-shell.io/SubmodelTemplates/"
                                  "Cardinality/1/0"),
                "type": "SMT/Cardinality", "valueType": "xs:string",
                "value": value}

    template = tmp_path / "list-item.json"
    template.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:l", "idShort": "L",
        "kind": "Template", "semanticId": sid("urn:test:top"),
        "submodelElements": [{
            "modelType": "SubmodelElementList", "idShort": "Entries",
            "semanticId": sid("urn:test:entries"),
            "typeValueListElement": "Property",
            "qualifiers": [card("One")],
            "value": [{"modelType": "Property", "idShort": "Entry",
                       "valueType": "xs:string",
                       "qualifiers": [card("OneToMany")]}]}]}]}
    ).encode("utf-8"))

    built = runner._supplied_table(template)["table"]
    item = [row for row in built.ROWS if row["label"] == "Entry"]
    assert item, [row["label"] for row in built.ROWS]
    assert item[0]["card"] == (1, None), (
        "the item row lost the obligation the template states: %s"
        % (item[0]["card"],))
    assert not item[0].get("unidentified"), (
        "a list's item row was read as a template defect")


def _self_containing(tmp_path):
    """A template whose `Node` holds a `Node`, and a file three deep.

    The two inner copies each break the template's own mandatory row.
    """
    def sid(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    def card(value):
        return {"semanticId": sid("https://admin-shell.io/SubmodelTemplates/"
                                  "Cardinality/1/0"),
                "type": "SMT/Cardinality", "valueType": "xs:string",
                "value": value}

    inner = {"modelType": "SubmodelElementCollection", "idShort": "Node",
             "semanticId": sid("urn:test:node"),
             "qualifiers": [card("ZeroToMany")], "value": []}
    node = {"modelType": "SubmodelElementCollection", "idShort": "Node",
            "semanticId": sid("urn:test:node"), "qualifiers": [card("One")],
            "value": [{"modelType": "Property", "idShort": "Name",
                       "semanticId": sid("urn:test:name"),
                       "valueType": "xs:string",
                       "qualifiers": [card("One")]}, inner]}
    template = tmp_path / "hier-tpl.json"
    template.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:htpl", "idShort": "H",
        "kind": "Template", "semanticId": sid("urn:test:top"),
        "submodelElements": [node]}]}).encode("utf-8"))

    def instance_node(id_short, children):
        return {"modelType": "SubmodelElementCollection", "idShort": id_short,
                "semanticId": sid("urn:test:node"), "value": children}

    third = instance_node("Node3", [])
    second = instance_node("Node2", [third])
    first = instance_node("Node", [
        {"modelType": "Property", "idShort": "Name",
         "semanticId": sid("urn:test:name"), "valueType": "xs:string",
         "value": "v"}, second])
    document = tmp_path / "hier.json"
    document.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:h", "idShort": "H",
        "semanticId": sid("urn:test:top"),
        "submodelElements": [first]}]}).encode("utf-8"))
    return document, template


def test_a_template_that_contains_itself_is_judged_at_every_depth(tmp_path):
    """Silence is the one answer this cannot give, and a note is no longer
    the answer either.

    The template's `Node` holds a `Node`; the file is three deep, and its
    two inner copies each omit the template's own mandatory `Name`. The
    first version judged the outermost occurrence and nothing below it --
    no finding, `ok` true, exit 0 -- and then learned to say in a note
    that it had not looked inside two copies. The nested `Node` is a row
    of its own now, and the walk gives each copy the rows of the element
    it copies (`docs/divergences.md` #48): both omissions are findings,
    each at the copy that has it, and there is nothing left for the note
    to say.
    """
    document, template = _self_containing(tmp_path)
    report = runner.run(document, template=template)
    missing = sorted(f.violation.subject for f in report.findings
                     if "'Name'" in f.violation.message)
    assert missing == ["H/Node/Node2", "H/Node/Node2/Node3"], (
        missing, [(f.id, f.violation.subject, f.violation.message)
                  for f in report.findings])
    assert not [n for n in report.notes if "contains itself" in n], report.notes


def _tree_template(tmp_path, inner, name="tree-tpl.json"):
    """A template whose `Node` holds `Name` and the nested `Node` given."""
    def sid(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    def card(value):
        return {"semanticId": sid("https://admin-shell.io/SubmodelTemplates/"
                                  "Cardinality/1/0"),
                "type": "SMT/Cardinality", "valueType": "xs:string", "value": value}

    node = {"modelType": "SubmodelElementCollection", "idShort": "Node",
            "semanticId": sid("urn:test:node"), "qualifiers": [card("One")],
            "value": [{"modelType": "Property", "idShort": "Name",
                       "semanticId": sid("urn:test:name"), "valueType": "xs:string",
                       "qualifiers": [card("One")]}, inner(sid, card)]}
    template = tmp_path / name
    template.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:tree", "idShort": "H",
        "kind": "Template", "semanticId": sid("urn:test:top"),
        "submodelElements": [node]}]}).encode("utf-8"))
    return template, sid


def _tree_file(tmp_path, sid, first_children, name="tree.json"):
    document = tmp_path / name
    document.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:t", "idShort": "H",
        "semanticId": sid("urn:test:top"),
        "submodelElements": [{"modelType": "SubmodelElementCollection",
                              "idShort": "Node", "semanticId": sid("urn:test:node"),
                              "value": first_children}]}]}).encode("utf-8"))
    return document


def _name(sid):
    return {"modelType": "Property", "idShort": "Name", "semanticId": sid("urn:test:name"),
            "valueType": "xs:string", "value": "v"}


def test_a_copy_the_template_bounds_is_counted_against_its_own_bound(tmp_path):
    """The nested `Node` is `ZeroToOne` where the outer one is `One`: the
    copy's row carries the template's bound, not the 0..* an assumption
    would give, and two copies in one node are one too many."""
    template, sid = _tree_template(tmp_path, lambda sid, card: {
        "modelType": "SubmodelElementCollection", "idShort": "Node",
        "semanticId": sid("urn:test:node"), "qualifiers": [card("ZeroToOne")], "value": []})
    copy = {"modelType": "SubmodelElementCollection", "semanticId": sid("urn:test:node"),
            "value": [_name(sid)]}
    document = _tree_file(tmp_path, sid, [_name(sid), dict(copy, idShort="A"),
                                          dict(copy, idShort="B")])
    report = runner.run(document, template=template)
    said = [f.violation.message for f in report.findings if f.violation.subject == "H/Node"]
    assert any("at most one" in m and "found 2" in m for m in said), said


def test_a_copy_written_with_content_is_judged_as_written(tmp_path):
    """The nested `Node` declares `Extra` and not `Name`. Given the outer
    rows, a file built as the template writes it was told its copy lacked
    `Name`, and a copy lacking the `Extra` the template asks for passed."""
    template, sid = _tree_template(tmp_path, lambda sid, card: {
        "modelType": "SubmodelElementCollection", "idShort": "Node",
        "semanticId": sid("urn:test:node"), "qualifiers": [card("ZeroToMany")],
        "value": [{"modelType": "Property", "idShort": "Extra",
                   "semanticId": sid("urn:test:extra"), "valueType": "xs:string",
                   "qualifiers": [card("One")]}]})
    extra = {"modelType": "Property", "idShort": "Extra", "semanticId": sid("urn:test:extra"),
             "valueType": "xs:string", "value": "x"}
    as_written = _tree_file(tmp_path, sid, [_name(sid), {
        "modelType": "SubmodelElementCollection", "idShort": "Node2",
        "semanticId": sid("urn:test:node"), "value": [extra]}])
    assert runner.run(as_written, template=template).findings == []
    without = _tree_file(tmp_path, sid, [_name(sid), {
        "modelType": "SubmodelElementCollection", "idShort": "Node2",
        "semanticId": sid("urn:test:node"), "value": [_name(sid)]}], name="without.json")
    said = [(f.violation.subject, f.violation.message)
            for f in runner.run(without, template=template).findings]
    assert any(subject == "H/Node/Node2" and "'Extra'" in message
               for subject, message in said), said


def test_a_mandatory_copy_is_not_charged_to_the_file(tmp_path):
    """A nested `Node` the template makes `One` needs one inside every
    copy, which no finite file has; a tree with `Name` everywhere drew an
    error at its bottom. It is judged as optional, and the note says why."""
    template, sid = _tree_template(tmp_path, lambda sid, card: {
        "modelType": "SubmodelElementCollection", "idShort": "Node",
        "semanticId": sid("urn:test:node"), "qualifiers": [card("One")], "value": []})
    deepest = {"modelType": "SubmodelElementCollection", "idShort": "Node3",
               "semanticId": sid("urn:test:node"), "value": [_name(sid)]}
    document = _tree_file(tmp_path, sid, [_name(sid), {
        "modelType": "SubmodelElementCollection", "idShort": "Node2",
        "semanticId": sid("urn:test:node"), "value": [_name(sid), deepest]}])
    report = runner.run(document, template=template)
    assert report.findings == [], [(f.id, f.violation.subject, f.violation.message)
                                   for f in report.findings]
    assert any("mandatory" in note and "no finite file" in note for note in report.notes), \
        report.notes


def test_a_copy_below_a_copy_the_walk_missed_is_counted_too(tmp_path):
    """A copy the walk did not reach hides the copies inside it: the count
    walks the whole chain, and the note names the identifier it is about."""
    document, template = _self_containing_list(tmp_path, copies=1)
    data = json.loads(document.read_text("utf-8"))
    nodes = data["submodels"][0]["submodelElements"][0]["value"][1]["value"]
    nodes[0]["value"].append({"modelType": "SubmodelElementCollection", "idShort": "Deep",
                              "semanticId": {"type": "ExternalReference", "keys": [
                                  {"type": "GlobalReference", "value": "urn:test:node"}]},
                              "value": []})
    document.write_text(json.dumps(data), "utf-8")
    note = next(n for n in runner.run(document, template=template).notes
                if "contains itself" in n)
    assert "2 elements carrying" in note, note
    assert "H/Node/Nodes/[0]/Deep" in note, note
    assert "urn:test:node" in note, note


def test_a_note_about_two_self_containing_elements_names_both(tmp_path):
    """A template in which `A` and `B` each contain themselves, and a file
    putting a copy of each where no row describes it. The note counted two
    and named one identifier -- the first in path order, `B`'s -- so the
    copy of `A` was reported as a copy of `B`."""
    def sid(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    def card(value):
        return {"semanticId": sid("https://admin-shell.io/SubmodelTemplates/"
                                  "Cardinality/1/0"),
                "type": "SMT/Cardinality", "valueType": "xs:string", "value": value}

    def smc(short, identifier, value, bound=None):
        out = {"modelType": "SubmodelElementCollection", "idShort": short, "value": value}
        if identifier:
            out["semanticId"] = sid(identifier)
        if bound:
            out["qualifiers"] = [card(bound)]
        return out

    template = tmp_path / "two-tpl.json"
    template.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:two", "idShort": "H", "kind": "Template",
        "semanticId": sid("urn:test:top"),
        "submodelElements": [smc("A", "urn:test:a", [
            smc("A", "urn:test:a", [], "ZeroToMany"),
            smc("B", "urn:test:b", [smc("B", "urn:test:b", [], "ZeroToMany")],
                "ZeroToOne")], "One")]}]}).encode("utf-8"))
    inner = [{"modelType": "Property", "idShort": "Note", "valueType": "xs:string",
              "value": "x", "semanticId": sid("urn:test:note")}]
    document = tmp_path / "two.json"
    document.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:d", "idShort": "H",
        "semanticId": sid("urn:test:top"),
        "submodelElements": [smc("A", "urn:test:a", [
            smc("BoxA", None, [smc("Ax", "urn:test:a", inner)]),
            smc("B", "urn:test:b", [smc("BoxB", None, [smc("Bx", "urn:test:b", inner)])])
        ])]}]}).encode("utf-8"))
    [note] = [n for n in runner.run(document, template=template).notes
              if "contain themselves" in n]
    assert "(urn:test:a, urn:test:b)" in note, note
    assert "did not reach 2 elements carrying those identifiers" in note, note


def _self_containing_list(tmp_path, copies=3):
    """The same template, and a file whose nested copies sit in a list.

    A `SubmodelElementList` names its items by position -- the metamodel
    forbids its children an idShort -- so this is the ordinary shape for
    repeats, not a corner of it.
    """
    def sid(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    def card(value):
        return {"semanticId": sid("https://admin-shell.io/SubmodelTemplates/"
                                  "Cardinality/1/0"),
                "type": "SMT/Cardinality", "valueType": "xs:string",
                "value": value}

    inner = {"modelType": "SubmodelElementCollection", "idShort": "Node",
             "semanticId": sid("urn:test:node"),
             "qualifiers": [card("ZeroToMany")], "value": []}
    node = {"modelType": "SubmodelElementCollection", "idShort": "Node",
            "semanticId": sid("urn:test:node"), "qualifiers": [card("One")],
            "value": [{"modelType": "Property", "idShort": "Name",
                       "semanticId": sid("urn:test:name"),
                       "valueType": "xs:string",
                       "qualifiers": [card("One")]}, inner]}
    template = tmp_path / "list-tpl.json"
    template.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:ltpl", "idShort": "H",
        "kind": "Template", "semanticId": sid("urn:test:top"),
        "submodelElements": [node]}]}).encode("utf-8"))

    def copy():
        return {"modelType": "SubmodelElementCollection",
                "semanticId": sid("urn:test:node"), "value": []}

    document = tmp_path / "list.json"
    document.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:l", "idShort": "H",
        "semanticId": sid("urn:test:top"),
        "submodelElements": [{
            "modelType": "SubmodelElementCollection", "idShort": "Node",
            "semanticId": sid("urn:test:node"),
            "value": [{"modelType": "Property", "idShort": "Name",
                       "semanticId": sid("urn:test:name"),
                       "valueType": "xs:string", "value": "v"},
                      {"modelType": "SubmodelElementList", "idShort": "Nodes",
                       "semanticId": sid("urn:test:nodes"),
                       "typeValueListElement": "SubmodelElementCollection",
                       "value": [copy() for _ in range(copies)]}]}]}]}
        ).encode("utf-8"))
    return document, template


def test_nested_copies_with_no_name_of_their_own_are_counted_apart(tmp_path):
    """Three unentered copies are three, and the note said one.

    The fixture the count was first held against names every copy, and
    a `SubmodelElementList`'s children cannot be named -- the metamodel
    forbids it, so this is where repeats actually live. `_repeats_below`
    spelled a nameless child `?`, the three siblings produced one string,
    and `repeats_not_entered` deduplicates: the reader was told one
    subtree went unexamined where three did, and told to look in a place
    with no name.

    The record keyed on a subject that two elements share is the defect
    `docs/divergences.md` #53 already named and `_subject` already
    repairs, by appending the position an unnamed element is addressed
    by. This walk was written beside it and did not call it.
    """
    document, template = _self_containing_list(tmp_path)
    report = runner.run(document, template=template)
    said = " ".join(report.notes)
    assert "3 elements carrying" in said, said
    for where in ("H/Node/Nodes/[0]", "H/Node/Nodes/[1]", "H/Node/Nodes/[2]"):
        assert where in said, (where, said)


def test_a_note_names_the_first_few_copies_and_counts_all_of_them(tmp_path):
    """The note is bounded, and the count is not.

    A reader needs to know how much went unexamined and where to start
    looking; a note that printed five hundred paths would be neither. So
    the count is the whole number and the naming stops, and the note says
    it stopped -- the published sentence beside this said the note names
    where *each* copy sits, which is true only up to the bound.

    Held here because the bound is invisible in the fixtures the count
    was built on: two copies and three copies both fit inside it, so
    removing the bound left every other gate green.
    """
    document, template = _self_containing_list(tmp_path, copies=5)
    report = runner.run(document, template=template)
    note = next(n for n in report.notes if "contains itself" in n)
    assert "5 elements carrying" in note, note
    named = re.findall(r"H/Node/Nodes/\[\d+\]", note)
    assert len(named) == 3, (
        "the note named %d of five copies; the bound is three and the "
        "count carries the rest: %s" % (len(named), note))
    assert ", and more)" in note, (
        "the note stopped naming and did not say so: %s" % note)

    # And the first few are the first few. Positions are how an unnamed
    # element is addressed, and sorted as text a scope of twelve reads
    # `[0] [10] [11]` -- so the three offered as a place to start
    # looking were the wrong three. Twelve, because the defect is
    # invisible below ten.
    document, template = _self_containing_list(tmp_path, copies=12)
    note = next(n for n in runner.run(document, template=template).notes
                if "contains itself" in n)
    assert "12 elements carrying" in note, note
    assert re.findall(r"H/Node/Nodes/\[(\d+)\]", note) == ["0", "1", "2"], note



def test_a_specification_that_declares_the_identifier_is_not_called_absent(tmp_path):
    """Two sentences about one file, and the second one is false.

    A submodel declared `kind: Template` is a specification, and every
    rule here is a requirement on an instance, so it is set aside and
    the report says so. When the only submodel carrying the supplied
    template's identifier is one of those, the run also said "claims
    ..., which no submodel in this input declares" -- because
    `matched_submodels` reads `instances`, which had filtered it out.

    The identifier is declared. The remedy a reader takes from the false
    sentence is to change it, which fixes nothing and breaks a correct
    file. Reproduces with a template file handed to itself as input.
    """
    document, template = _self_containing(tmp_path)
    report = runner.run(template, template=template)
    absent = [note for note in report.notes
              if "no submodel in this input declares" in note]
    assert not absent, (
        "a specification declaring the identifier was reported as nothing "
        "declaring it: %s" % absent)
    assert any("kind Template" in note for note in report.notes), (
        "the run no longer says the specification was set aside: %s"
        % report.notes)


def test_a_multi_key_template_identifier_is_normalised_key_by_key(tmp_path):
    """The same reference, read by the two halves of this module, has to
    come out the same.

    `_values_of` normalises each key and joins; `build` joined and then
    normalised once. For a reference stacking two ECLASS-CDP URLs the
    two disagree: the joined string matches no CDP shape, so it stays a
    URL pair while every element row and every instance-side candidate
    carries the IRDI form. The template then took its identifier over
    from nobody, a pack answered instead, and `provenance.template`
    named a joined URL as the identifier the caller's file claims --
    the three wrong answers one missing call already produced once for
    the single-key case, repaired there and not here.
    """
    from aas_submodel_validate import runner as runner_module
    from aas_submodel_validate.semantics import normalize

    keys = ["https://api.eclass-cdp.com/0173-1-01-AHF578-003",
            "https://api.eclass-cdp.com/0173-1-02-ABI002-003"]
    expected = "/".join(normalize(key) for key in keys)
    assert expected != normalize("/".join(keys)), (
        "this fixture no longer tells the two orders apart")

    def sid(values):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": v}
                         for v in values]}

    template = tmp_path / "two-key.json"
    template.write_bytes(json.dumps({"submodels": [{
        "modelType": "Submodel", "id": "urn:test:two", "idShort": "T",
        "kind": "Template", "semanticId": sid(keys),
        "submodelElements": [{
            "modelType": "Property", "idShort": "A",
            "semanticId": sid(["urn:test:a"]), "valueType": "xs:string",
            "qualifiers": [{
                "semanticId": sid(["https://admin-shell.io/SubmodelTemplates/"
                                   "Cardinality/1/0"]),
                "type": "SMT/Cardinality", "valueType": "xs:string",
                "value": "One"}]}]}]}).encode("utf-8"))

    built = runner_module._supplied_table(template)["table"]
    assert expected == built.TEMPLATE_SEMANTIC_ID, (
        "the table claims %r where every other reader of this reference "
        "says %r" % (built.TEMPLATE_SEMANTIC_ID, expected))
