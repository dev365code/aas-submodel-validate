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
    template number is not a defect in anybody's file."""
    with pytest.raises(SystemExit) as raised:
        main(["x.json", "--profile", "02023"])
    assert raised.value.code == 2
    assert "02035-2" in capsys.readouterr().err


def test_the_profiles_on_offer_come_from_the_tables(capsys):
    """`--help` cannot name a template this tool has no table for."""
    from aas_submodel_validate.rules.profiles import KEYS
    with pytest.raises(SystemExit):
        main(["--help"])
    helped = capsys.readouterr().out
    for key in KEYS:
        assert key in helped


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
    assert "rules registered)" in capsys.readouterr().out


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

    assert published([]) == {
        "profile": None, "strictMeta": False, "allowUnmatched": False}
    assert published(["--strict-meta"]) == {
        "profile": None, "strictMeta": True, "allowUnmatched": False}
    assert published(["--allow-unmatched"]) == {
        "profile": None, "strictMeta": False, "allowUnmatched": True}
    assert published(["--profile", "02004"]) == {
        "profile": "02004", "strictMeta": False, "allowUnmatched": False}


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

