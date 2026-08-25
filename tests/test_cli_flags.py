"""The flags a pipeline reaches for, each with its contract."""
from __future__ import annotations

import copy
import json

import pytest

from aas_submodel_validate.cli import main
from builders import env_json, hd_env


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
