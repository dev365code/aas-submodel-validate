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


def test_a_screen_does_not_say_what_its_own_remedy_contradicts(tmp_path, capsys):
    """A Submodel nested deeper than this interpreter builds is read to the
    end -- `json.loads` takes all of it -- and its remedy says so. The same
    screen said, on stderr, that nothing in the file could be read, and in
    its summary that some of it was not read. What is known is that nothing
    was judged, and that is what both say now."""
    element = {"idShort": "leaf", "modelType": "Property", "valueType": "xs:string",
               "value": "x"}
    for level in range(400):
        element = {"idShort": "c%d" % level, "modelType": "SubmodelElementCollection",
                   "value": [element]}
    path = tmp_path / "deep.json"
    path.write_text(json.dumps({"id": "urn:deep", "modelType": "Submodel",
                                "submodelElements": [element]}), "utf-8")
    assert main([str(path)]) == 2
    out, err = capsys.readouterr()
    assert "read the document to the end" in out
    assert "not read" not in out and "could be read" not in err, (out, err)
    assert "(not a full verdict: some of it was not judged)" in out
    assert "nothing in %s was judged" % path in err
