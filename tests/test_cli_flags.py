"""The flags a pipeline reaches for, each with its contract."""
from __future__ import annotations

import copy
import json

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
