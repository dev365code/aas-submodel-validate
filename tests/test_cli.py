"""Exit codes are the API a build pipeline actually calls."""
import json

from aas_submodel_validate.cli import main
from builders import env_json, hd_env


def test_a_clean_file_exits_zero(tmp_path, capsys):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(hd_env()).encode("utf-8"))
    assert main([str(path)]) == 0
    assert "ok" in capsys.readouterr().out


def test_findings_exit_one_and_name_the_remedy(tmp_path, capsys):
    path = tmp_path / "env.json"
    path.write_bytes(env_json("urn:wrong"))
    assert main([str(path)]) == 1
    out = capsys.readouterr().out
    assert "SMT-D1" in out
    assert "fix:" in out


def test_a_missing_path_exits_two(tmp_path, capsys):
    assert main([str(tmp_path / "absent.aasx")]) == 2
    assert "no such file" in capsys.readouterr().err


def test_quiet_is_exit_code_only(tmp_path, capsys):
    path = tmp_path / "env.json"
    path.write_bytes(env_json("urn:wrong"))
    assert main(["-q", str(path)]) == 1
    assert capsys.readouterr().out == ""


def test_json_output_is_json(tmp_path, capsys):
    path = tmp_path / "env.json"
    path.write_bytes(env_json("urn:wrong"))
    main(["--format", "json", str(path)])
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False
    assert report["findings"][0]["fix"]
