"""The flags a pipeline reaches for, each with its contract."""
from __future__ import annotations

import copy
import json

import pytest

from aas_submodel_validate.cli import main
from aas_submodel_validate.registry import all_rules
from builders import env_json, hd_env

# The one copy of the published shape. Imported rather than repeated,
# because two golden lists disagree the day one of them is updated.
from test_model import (
    FINDING_KEYS,
    OPTIONS_KEYS,
    REPORT_KEYS,
    SUMMARY_KEYS,
)


def _write(tmp_path, payload: bytes):
    path = tmp_path / "env.json"
    path.write_bytes(payload)
    return str(path)


def test_warnings_as_errors_flips_the_exit_code(tmp_path):
    env = copy.deepcopy(hd_env())
    version = env["submodels"][0]["submodelElements"][0]["value"][0]["value"][2]["value"][0]
    for child in version["value"]:
        if child.get("idShort") == "StatusValue":
            child["value"] = "released"          # a warning (HD-D6)
    path = _write(tmp_path, json.dumps(env).encode("utf-8"))
    assert main([path]) == 0
    assert main(["-W", path]) == 1


def test_strict_meta_promotes_the_relay(tmp_path):
    env = copy.deepcopy(hd_env())
    env["submodels"][0]["submodelElements"][0]["value"][0]["idShort"] = "Datasheet"
    path = _write(tmp_path, json.dumps(env).encode("utf-8"))
    assert main([path]) == 0
    assert main(["--strict-meta", path]) == 1


def test_allow_unmatched_demotes_the_presence_rule_to_a_note(tmp_path, capsys):
    path = _write(tmp_path, env_json("urn:not:handover"))
    assert main([path]) == 1
    capsys.readouterr()
    assert main(["--allow-unmatched", path]) == 0
    out = capsys.readouterr().out
    assert "note" in out and "SMT-D1" not in out.split("note")[0]


def test_rules_lists_every_rule_without_an_input(capsys):
    assert main(["--rules"]) == 0
    out = capsys.readouterr().out
    assert "SMT-D1" in out and "HD-E38" in out and "META" in out
    assert out.count("\n") >= 57


def test_profile_chooses_which_template_answers(tmp_path, capsys):
    """The flag's whole contract, both ways. A battery passport judged as
    02004 is told it is missing six elements it is not required to have;
    the same file judged as 02035-2 is clean. And a file that declares
    the profile can still be held to 02004 -- the override runs in both
    directions, because the mark's recall is unmeasurable (no published
    02035-2 instance exists) and an operator needs a way back."""
    import json

    from builders import dbp_env
    path = tmp_path / "battery.json"
    path.write_bytes(json.dumps(dbp_env()).encode("utf-8"))
    assert main([str(path), "-q", "--profile", "02035-2"]) == 0
    assert main([str(path), "-q", "--profile", "02004"]) == 1
    assert main([str(path), "-q"]) == 1


def test_an_unknown_profile_is_the_callers_mistake_not_a_finding(capsys):
    """Exit 2, the code that means the tool could not run. A misspelled
    template number is not a defect in anybody's file.

    The example used to be `02023`, which the parser now accepts: it
    settles a collision this tool has no table for. `02099-1` is a real
    IDTA document number and still not one of these, which is the shape
    a misspelling actually has."""
    with pytest.raises(SystemExit) as raised:
        main(["x.json", "--profile", "02099-1"])
    assert raised.value.code == 2
    assert "02035-2" in capsys.readouterr().err


def test_the_profiles_on_offer_say_which_kind_each_one_is(capsys):
    """Two kinds, and `--help` has to tell them apart.

    This said `--help` cannot name a template with no table behind it,
    and that was the whole contract until `BAT-R2` started telling
    readers to pass one. A remedy naming a value the parser refuses is
    worse than no remedy -- measured: it shipped that way for a commit.
    So both kinds are on offer and the help text says which is which:
    some choose the table that judges, the rest only settle which
    template the file claims to be."""
    from aas_submodel_validate.rules.battery import _settles_only
    from aas_submodel_validate.rules.profiles import KEYS
    with pytest.raises(SystemExit):
        main(["--help"])
    helped = " ".join(capsys.readouterr().out.split())
    assert not set(KEYS) & set(_settles_only()), "a key cannot be both kinds"
    chooses, _, settles = helped.partition("choose the table that judges")
    assert "only settle which template the file claims to be" in settles
    # Each key on its own side of the sentence. Listing them all and
    # checking each appears somewhere passes for a help text that files
    # `02004` under "settles nothing", which is the opposite of true.
    for key in KEYS:
        assert key in chooses.rsplit(":", 1)[-1], key
        assert key not in settles.split(";")[0], key
    for key in _settles_only():
        assert key in settles, key
        assert key not in chooses.rsplit(":", 1)[-1], key


def test_a_profile_that_only_settles_a_collision_is_not_reported_as_idle(tmp_path,
                                                                        capsys):
    """The runner tells a caller when `--profile` named a template no
    submodel answered to, so the flag chose nothing. A key that settles a
    collision chose nothing by design -- it silenced a finding instead --
    and saying it was idle contradicts the finding it just removed."""
    env = {"assetAdministrationShells": [], "conceptDescriptions": [],
           "submodels": [{
               "modelType": "Submodel", "id": "urn:x", "idShort": "CarbonFootprint",
               "semanticId": {"type": "ExternalReference", "keys": [
                   {"type": "GlobalReference",
                    "value": "https://admin-shell.io/idta/CarbonFootprint/"
                             "CarbonFootprint/1/0"}]},
               "submodelElements": []}]}
    path = tmp_path / "cf.json"
    path.write_text(json.dumps(env))
    assert main([str(path), "--profile", "02035-3"]) in (0, 1)
    printed = capsys.readouterr().out
    assert "BAT-R2" not in printed, "the flag did not settle the collision"
    assert "chose nothing" not in printed


def test_a_run_with_a_note_does_not_call_itself_ok(tmp_path, capsys):
    """`--allow-unmatched` moves the presence finding to a note, leaving
    the findings empty -- and the headline used to read `ok — file (123
    rules)` over an input this tool recognised nothing in. A run that had
    to be told to allow something is not the plain "ok" case, and the
    parenthetical says `registered` because a Technical Data file is not
    judged by 02004's fifty-two."""
    path = tmp_path / "unknown.json"
    path.write_bytes(env_json("urn:acme:private"))
    assert main([str(path), "--allow-unmatched"]) == 0
    out = capsys.readouterr().out
    assert "ok —" not in out
    assert "note    SMT-D1 (allowed)" in out

    clean = tmp_path / "clean.json"
    clean.write_bytes(json.dumps(hd_env()).encode("utf-8"))
    assert main([str(clean)]) == 0
    assert "rules registered · judged 1 of 1 submodel)" in capsys.readouterr().out


def test_the_json_a_pipeline_reads_is_the_shape_it_was_promised(tmp_path, capsys):
    """`as_dict` is unit-tested against the shape `schemaVersion: 1`
    names, and that proves the model can produce it. This is the path a
    consumer actually uses -- and nothing here read the flag's output at
    all, so `-f json` could have printed anything that did not crash."""
    path = _write(tmp_path, env_json("urn:nobody:recognises:this"))
    assert main([path, "-f", "json"]) == 1
    document = json.loads(capsys.readouterr().out)
    assert set(document) == REPORT_KEYS
    assert set(document["summary"]) == SUMMARY_KEYS
    # `options` is part of the published shape too, and its inner keys
    # were checked only on the unit path -- the one place this file's own
    # docstring says is not where a consumer reads from.
    assert set(document["options"]) == OPTIONS_KEYS
    assert document["findings"], "no finding, so the finding shape went unchecked"
    for finding in document["findings"]:
        assert set(finding) == FINDING_KEYS
    assert document["path"] == path
    # The number itself, not just its key. `report.checked = 0` passed
    # everything: the count was pinned where it is copied into the
    # document and nowhere where a run produces it.
    assert document["summary"]["rulesChecked"] == len(all_rules())


def test_the_options_a_report_publishes_are_the_flags_it_was_given(tmp_path, capsys):
    """The flags move the verdict, so the report carries them -- and
    nothing read them back off a run. Recording them was three lines in
    `runner.run`, and all three could be deleted, or two of them swapped
    so every strict run published `"strictMeta": false`, with the suite
    green. A consumer diffing two reports would have concluded the tool
    was non-deterministic.

    One flag at a time, because a swap is invisible whenever two of them
    agree."""
    path = _write(tmp_path, json.dumps(hd_env()).encode("utf-8"))

    def published(argv):
        main([path, "-f", "json"] + argv)
        return json.loads(capsys.readouterr().out)["options"]

    def expected(**changed):
        options = {"profile": None, "meta": "warning", "strictMeta": False,
                   "allowUnmatched": False}
        options.update(changed)
        return options

    assert published([]) == expected()
    assert published(["--strict-meta"]) == expected(meta="error", strictMeta=True)
    assert published(["--meta", "error"]) == expected(meta="error", strictMeta=True)
    assert published(["--meta", "info"]) == expected(meta="info")
    assert published(["--allow-unmatched"]) == expected(allowUnmatched=True)
    assert published(["--profile", "02004"]) == expected(profile="02004")


def test_allow_unmatched_forgives_only_the_presence_rule(tmp_path, capsys):
    """The flag partitions findings on one rule id, and every fixture for
    it had only that finding to move -- so the partition could sweep
    every finding into the notes, or empty the report entirely, and the
    flag would still look like it worked.

    Here the unmatched submodel also carries a metamodel defect, and the
    run is strict, so there is a real error in the report beside the
    forgiven one. The error must stay a finding and keep the exit code;
    the note must still name the semanticId the input declared."""
    env = copy.deepcopy(hd_env())
    submodel = env["submodels"][0]
    submodel["semanticId"]["keys"][0]["value"] = "urn:not:ours"

    def poison(node):
        if isinstance(node, dict):
            if node.get("idShort") == "DocumentIsPrimary":
                node["value"] = "TRUE"     # aas-core3 refuses the spelling
            for child in node.values():
                poison(child)
        elif isinstance(node, list):
            for child in node:
                poison(child)

    poison(env)
    path = tmp_path / "unmatched-strict.json"
    path.write_text(json.dumps(env))
    assert main([str(path), "--allow-unmatched", "--strict-meta"]) == 1
    out = capsys.readouterr().out
    assert "error   META" in out, "the real error went with the forgiven one"
    assert out.count("(allowed)") == 1, "every finding was echoed as a note"
    assert "urn:not:ours" in out, "the note lost the detail naming what was declared"


def test_no_path_and_no_rules_is_a_usage_error(capsys):
    """argparse's own exit: code 2 and a usage line, not a traceback from
    handing None to the loader two calls later."""
    with pytest.raises(SystemExit) as caught:
        main([])
    assert caught.value.code == 2
    assert "required" in capsys.readouterr().err


def test_the_json_report_is_indented_for_a_human_holding_a_pager(tmp_path, capsys):
    """`indent=2` is part of what ships: one key per line, two spaces.
    Nothing structural reads the whitespace, which is exactly why nothing
    else would notice it going."""
    path = tmp_path / "ok.json"
    path.write_text(json.dumps(hd_env()))
    main([str(path), "-f", "json"])
    assert capsys.readouterr().out.startswith('{\n  "')


def test_warnings_as_errors_needs_a_warning_not_a_vibe(tmp_path):
    """The flag reads `count(WARNING) > 0`: a clean file stays exit 0
    under it, and one warning flips to 1. Both edges, because `> 0` can
    drift to `>= 0` (every clean run fails) or `> -1` (same) and only
    the clean edge notices."""
    clean = tmp_path / "clean.json"
    clean.write_text(json.dumps(hd_env()))
    assert main([str(clean), "--warnings-as-errors"]) == 0

    warned = copy.deepcopy(hd_env())

    def lowercase_status(node):
        if isinstance(node, dict):
            if node.get("idShort") == "StatusValue":
                node["value"] = "released"          # HD-D6, a SHOULD
            for child in node.values():
                lowercase_status(child)
        elif isinstance(node, list):
            for child in node:
                lowercase_status(child)

    lowercase_status(warned)
    warmed = tmp_path / "warned.json"
    warmed.write_text(json.dumps(warned))
    assert main([str(warmed)]) == 0
    assert main([str(warmed), "--warnings-as-errors"]) == 1



def test_warnings_as_errors_still_means_every_warning(tmp_path):
    """`-W` fails on warnings. All of them.

    A version of this file exempted the relayed metamodel channel,
    reasoning that no edit to a submodel can clear a finding about the
    metamodel. That reasoning is false and the project's own example
    disproves it: of the 77 relayed findings it raises, 45 are about
    `.submodels` -- 33 of them AASd-120, which is cleared by deleting an
    idShort. A submodel whose `id` is empty raises one relayed finding
    and no other, and under the exemption `smtv -q -W` passed it while
    printing "1 warning(s)". Anyone who put that line in a build on
    0.1.0 would have had a red build turn quietly green.

    The escape the exemption was reaching for is `--meta info`, which
    says out loud that this channel is not to decide the build."""
    env = copy.deepcopy(hd_env())
    env["submodels"][0]["id"] = ""       # AASd: the value must not be empty
    path = _write(tmp_path, json.dumps(env).encode("utf-8"))
    assert main([path]) == 0
    assert main(["-W", path]) == 1
    assert main(["-W", "--meta", "info", path]) == 0


def test_the_relayed_channel_has_one_dial_with_three_settings(tmp_path,
                                                              capsys):
    """One flag decides this channel's severity, and `--strict-meta` is
    the older spelling of its top setting.

    Two flags governing one channel is what made `-W` unusable in the
    first place, and answering that with a third would have been the
    same mistake again."""
    env = copy.deepcopy(hd_env())
    env["submodels"][0]["submodelElements"][0]["value"][0]["idShort"] = "Datasheet"
    path = _write(tmp_path, json.dumps(env).encode("utf-8"))

    seen = {}
    for level in ("error", "warning", "info"):
        main(["-f", "json", "--meta", level, path])
        report = json.loads(capsys.readouterr().out)
        relayed = [f for f in report["findings"] if f["kind"] == "meta"]
        assert relayed, "this fixture is meant to raise relayed findings"
        assert {f["severity"] for f in relayed} == {level}
        seen[level] = report["options"]["meta"]
    assert seen == {"error": "error", "warning": "warning", "info": "info"}

    main(["-f", "json", "--strict-meta", path])
    aliased = json.loads(capsys.readouterr().out)["options"]
    assert aliased["meta"] == "error"
    assert aliased["strictMeta"] is True, \
        "the field 0.1.0 readers parse has to keep answering"


def test_require_all_judged_turns_the_coverage_number_into_a_verdict(tmp_path):
    """`judged 1 of 3 submodels` and `exit 0` is a silent pass.

    An environment carries submodels this tool has no business judging,
    so an unjudged one stays a number rather than a finding -- but a
    pipeline written as `smtv pkg.aasx && ship` reads the exit code and
    nothing else, and sees success for a package two thirds of which was
    never looked at. The number was already in the report; what was
    missing was a way to make it decide."""
    env = copy.deepcopy(hd_env())
    stranger = copy.deepcopy(env["submodels"][0])
    stranger["id"] = "urn:some:other:submodel"
    stranger["semanticId"]["keys"][0]["value"] = "urn:not:a:template:we:have"
    env["submodels"].append(stranger)
    path = _write(tmp_path, json.dumps(env).encode("utf-8"))
    assert main([path]) == 0
    assert main(["--require-all-judged", path]) == 1


def test_the_relayed_channel_is_summarised_until_it_is_asked_for(tmp_path, capsys):
    """Seventy-seven relayed lines bury the ten the reader came for.

    The official example this project points a newcomer at raises
    eighty-seven warnings, and seventy-seven of them are aas-core3.0
    speaking about IDTA's own concept descriptions -- all carrying one
    remedy sentence that no edit to the submodel can act on. Printed in
    full they are the first thing a stranger sees, and the verdict is
    two hundred and seventy lines below.

    Counted, never dropped: the summary line still totals them and the
    JSON report is untouched, because a reader who cannot see a finding
    must at least be told it exists and how to read it."""
    env = copy.deepcopy(hd_env())
    env["submodels"][0]["submodelElements"][0]["value"][0]["idShort"] = "Datasheet"
    path = _write(tmp_path, json.dumps(env).encode("utf-8"))

    assert main([path]) == 0
    folded = capsys.readouterr().out
    assert "--show-meta" in folded, "the fold has to say how to open it"
    assert "META" not in folded.split("--show-meta")[1], (
        "a folded channel prints no finding of its own")

    assert main(["--show-meta", path]) == 0
    opened = capsys.readouterr().out
    assert "META" in opened
    assert len(opened.splitlines()) > len(folded.splitlines())

    # Folding is a rendering choice, not a change of verdict: the count
    # in the summary and the JSON a pipeline reads both stay whole.
    assert folded.splitlines()[-1] == opened.splitlines()[-1]
    assert main(["-f", "json", path]) == 0
    report = json.loads(capsys.readouterr().out)
    assert sum(1 for f in report["findings"] if f["kind"] == "meta") > 0


def test_a_promoted_relay_is_never_folded_away(tmp_path, capsys):
    """`--strict-meta` makes this channel the verdict, and a verdict is
    printed.

    The fold exists for a relayed warning nobody asked to be judged by.
    Once the flag has made those findings errors they decide the exit
    code, and the first version folded them anyway -- a run that exited 1
    with no error on the screen. Caught by a test written for a different
    flag, which is the only reason it was not shipped."""
    env = copy.deepcopy(hd_env())
    env["submodels"][0]["submodelElements"][0]["value"][0]["idShort"] = "Datasheet"
    path = _write(tmp_path, json.dumps(env).encode("utf-8"))
    assert main(["--strict-meta", path]) == 1
    out = capsys.readouterr().out
    assert "error   META" in out
    assert "--show-meta" not in out


def test_example_judges_the_bundled_package_with_no_repository(tmp_path,
                                                               monkeypatch,
                                                               capsys):
    """`pip install` used to leave a reader with nothing to validate.

    The front page's first command named a file only a clone has, and on
    a machine where the clone is blocked -- which is the machine this
    project is for -- there was no first verdict at all. The example
    IDTA publishes now travels in the wheel under the same licence and
    the same NOTICE entry as the templates beside it.

    Run from somewhere that is not this repository, so a path that
    happens to resolve here cannot pass for a bundled one."""
    monkeypatch.chdir(tmp_path)
    assert main(["--example"]) == 0
    out = capsys.readouterr().out
    assert "judged 1 of 1 submodel" in out
    assert "idta-02004-2.0.aasx" in out


def test_example_and_a_path_are_two_different_requests(tmp_path, capsys):
    """Giving both is a mistake to name, not one to resolve silently.

    Whichever the tool picked, the other would be judged without being
    mentioned -- a report about bytes the caller did not think it was
    reading, which is the one thing this report's provenance field
    exists to prevent."""
    path = _write(tmp_path, json.dumps(hd_env()).encode("utf-8"))
    with pytest.raises(SystemExit) as raised:
        main(["--example", path])
    assert raised.value.code == 2


def test_help_says_what_the_exit_codes_mean(capsys):
    """Someone wiring this into a build reads `--help` before a README.

    The codes were on the front page only, so the reader most likely to
    depend on them was the one least likely to have seen them."""
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    # The first version of this test asked only that "exit" and the three
    # digits appeared somewhere, and passed against a help page that says
    # nothing about exit codes -- every one of those strings occurs in
    # some flag's own description. What is wanted is a place where the
    # three are explained together.
    tail = out.split("--require-all-judged")[-1]
    assert "exit codes" in tail.lower(), \
        "the help page explains the exit codes nowhere"
    for code, meaning in ((" 0 ", "no"), (" 1 ", "error"), (" 2 ", "run")):
        assert code in tail and meaning in tail.lower()


def test_the_text_report_cites_the_clause_the_json_already_carried(tmp_path,
                                                                   capsys):
    """`spec` is the field a regulatory reader needs most.

    A finding says which clause of which document it comes from, and the
    JSON has carried that since the first release -- but the person at a
    terminal, who is the one writing "conforms: yes/no" into a report,
    could not see it without re-running with `-f json`."""
    env = copy.deepcopy(hd_env())
    version = env["submodels"][0]["submodelElements"][0]["value"][0]["value"][2]["value"][0]
    for child in version["value"]:
        if child.get("idShort") == "StatusValue":
            child["value"] = "released"
    path = _write(tmp_path, json.dumps(env).encode("utf-8"))

    assert main(["-f", "json", path]) == 0
    cited = [f for f in json.loads(capsys.readouterr().out)["findings"] if f.get("spec")]
    assert cited, "this fixture is meant to raise a finding that cites a clause"

    assert main([path]) == 0
    out = capsys.readouterr().out
    assert cited[0]["spec"] in out


def test_the_bundled_example_is_named_by_what_it_is(tmp_path, monkeypatch,
                                                    capsys):
    """The reader is told which file was judged, and a temporary one is
    not an answer.

    From a zipapp the example has to be extracted before it can be read,
    so the path the run actually opened is
    `/var/folders/.../tmpXXXXidta-02004-2.0.aasx` -- true, useless, and
    gone by the time anyone looks. The report names the example instead.
    The bytes are still identified exactly: `provenance.inputSha256` is
    of what was read, and it is the same hash the package records beside
    the file."""
    monkeypatch.chdir(tmp_path)
    assert main(["-f", "json", "--example"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert "tmp" not in report["path"], report["path"]
    assert report["path"].endswith("idta-02004-2.0.aasx")

    from aas_submodel_validate.example import NAME, bundled_example
    with bundled_example() as path:
        recorded = (path.parent / "sha256sums.txt")
        if recorded.is_file():                 # absent once extracted
            assert report["provenance"]["inputSha256"] in \
                recorded.read_text(encoding="utf-8")
    assert NAME in report["path"]


def test_require_all_judged_fails_on_a_file_with_nothing_to_judge(tmp_path):
    """Nothing judged out of nothing is the emptiest pass of all.

    The comparison was `judged < seen`, and an environment holding no
    submodels makes that `0 < 0` -- so the flag failed a file with one
    unjudged submodel and passed one with none at all, which is the risk
    ordering exactly backwards. An exporter that writes an empty
    environment is not a rare accident, and
    `--allow-unmatched --require-all-judged` is the combination the front
    page recommends to the reader most likely to hit it."""
    for payload in (b'{"submodels": []}', b"{}"):
        path = _write(tmp_path, payload)
        assert main(["-q", "--allow-unmatched", path]) == 0
        assert main(["-q", "--allow-unmatched", "--require-all-judged", path]) == 1


def test_example_and_rules_are_two_different_requests(capsys):
    """`--example --rules` listed the rules and said nothing about the
    example.

    `--rules` returns before the conflict check, so one flag was obeyed
    and the other silently dropped -- while `--example <path>` is an
    error. The same kind of mistake, answered two ways."""
    with pytest.raises(SystemExit) as raised:
        main(["--example", "--rules"])
    assert raised.value.code == 2
    assert "--example" in capsys.readouterr().err


def test_the_two_spellings_of_the_meta_dial_cannot_disagree(tmp_path, capsys):
    """One of them was losing silently, and losing meant exit 0.

    `--strict-meta` is the older spelling of `--meta error`, and the
    code read `args.meta or args.strict_meta` -- so `--strict-meta
    --meta info` dropped the first without a word, and a build pinned on
    `--strict-meta` went green the moment anyone added `--meta` beside
    it. That is the failure this dial was introduced to end, arriving
    through the dial itself. Agreeing is fine; disagreeing is a question
    only the caller can answer."""
    env = copy.deepcopy(hd_env())
    env["submodels"][0]["submodelElements"][0]["value"][0]["idShort"] = "Datasheet"
    path = _write(tmp_path, json.dumps(env).encode("utf-8"))

    assert main(["-q", "--strict-meta", path]) == 1
    assert main(["-q", "--strict-meta", "--meta", "error", path]) == 1
    for level in ("warning", "info"):
        with pytest.raises(SystemExit) as raised:
            main(["--strict-meta", "--meta", level, path])
        assert raised.value.code == 2
        assert "--strict-meta" in capsys.readouterr().err


def test_the_example_says_what_it_is_before_it_says_what_is_wrong(tmp_path,
                                                                  monkeypatch,
                                                                  capsys):
    """87 findings with no subject line is a first screen that reads as
    a broken install.

    The front page says this is IDTA's own example and that its defects
    are the point of shipping that one; the terminal did not, and the
    file it names is fifty lines below. Text only -- a pipeline reading
    `-f json` must find JSON on the first byte."""
    monkeypatch.chdir(tmp_path)
    assert main(["--example"]) == 0
    first = capsys.readouterr().out.splitlines()[0]
    assert "IDTA" in first and "defects" in first

    assert main(["-f", "json", "--example"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["errors"] == 0

    assert main(["-q", "--example"]) == 0
    assert capsys.readouterr().out == ""


def test_rules_takes_no_input_and_says_so(tmp_path, capsys):
    """`--rules` judged nothing and accepted a path and a `--profile`
    anyway, answering neither.

    `--example <path>` was made an error for exactly this shape in the
    same change that left this one alone; half a principle is worse than
    none, because it teaches that the silence is deliberate somewhere."""
    path = _write(tmp_path, json.dumps(hd_env()).encode("utf-8"))
    for argv in ([path], ["--profile", "02004"]):
        with pytest.raises(SystemExit) as raised:
            main(["--rules"] + argv)
        assert raised.value.code == 2
        assert "--rules" in capsys.readouterr().err
    assert main(["--rules"]) == 0
    assert len(capsys.readouterr().out.splitlines()) > 100
