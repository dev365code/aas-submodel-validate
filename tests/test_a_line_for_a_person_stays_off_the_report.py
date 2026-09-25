"""A line meant for the person running the check goes to stderr, or nowhere.

Four of them were written with `print(..., file=sys.stderr)`: why nothing
was judged, a template refused, how many submodels `--require-all-judged`
found judged, and a package that carries no example. With stderr closed --
`2>&-`, or pythonw with no console -- `sys.stderr` is None, and `print`
handed None writes to stdout: into the JSON a pipeline was about to parse.
With a stderr whose reader has gone, the write raised, and the process left
by 120 instead of the code the run had decided. Both are what the bug report's
lines were made safe from; these four are held to the same.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import aas_submodel_validate.cli as cli
from builders import dn_env, env_json

ROOT = Path(__file__).resolve().parents[1]


def _refused(tmp_path):
    path = tmp_path / "not-a-package.aasx"
    path.write_bytes(b"this is not an archive")
    return path


def _two_submodels_one_judged(tmp_path):
    env = dn_env()
    other = json.loads(env_json("urn:example:no-table-answers-for-this"))["submodels"][0]
    other["id"] = "urn:example:another"
    env["submodels"].append(other)
    path = tmp_path / "two.json"
    path.write_text(json.dumps(env), encoding="utf-8")
    return path


def _refused_template(tmp_path):
    template = tmp_path / "t.json"
    template.write_text("[1, 2]", encoding="utf-8")
    good = tmp_path / "good.json"
    good.write_text(json.dumps(dn_env()), encoding="utf-8")
    return [str(good), "--template", str(template)]


def _cases(tmp_path):
    """(arguments, the code the run leaves by, whether stdout holds a report)"""
    return [
        ([str(_refused(tmp_path)), "-f", "json"], cli.EXIT_ERROR, True),
        ([str(_two_submodels_one_judged(tmp_path)), "-f", "json", "--require-all-judged"],
         cli.EXIT_FINDINGS, True),
        (_refused_template(tmp_path), cli.EXIT_ERROR, False),
    ]


def test_with_stderr_closed_no_line_reaches_stdout(tmp_path, capsys, monkeypatch):
    for arguments, code, reports in _cases(tmp_path):
        assert cli.main(arguments) == code
        captured = capsys.readouterr()
        assert captured.err.startswith("smtv: "), (arguments, captured.err)
        with monkeypatch.context() as closed:
            closed.setattr(sys, "stderr", None)
            closed.setattr(sys, "__stderr__", None)
            assert cli.main(arguments) == code
            out = capsys.readouterr().out
        assert out == captured.out, "a line meant for a person is in stdout: %r" % out[-200:]
        if reports:
            json.loads(out)
        else:
            assert out == ""


def test_with_stderr_closed_a_package_without_its_example_says_nothing_on_stdout(
        capsys, monkeypatch):
    from aas_submodel_validate.example import NotBundled

    def missing():
        raise NotBundled("this package carries no example")
    monkeypatch.setattr(cli, "bundled_example", missing)
    assert cli.main(["--example", "-f", "json"]) == cli.EXIT_ERROR
    assert "no example" in capsys.readouterr().err
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(sys, "__stderr__", None)
    assert cli.main(["--example", "-f", "json"]) == cli.EXIT_ERROR
    assert capsys.readouterr().out == ""


def _dead_stderr(tmp_path, arguments):
    reader, writer = os.pipe()
    os.close(reader)
    try:
        done = subprocess.run([sys.executable, "-m", "aas_submodel_validate", *arguments],
                              stdout=subprocess.DEVNULL, stderr=writer, cwd=str(tmp_path),
                              timeout=120, env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    finally:
        os.close(writer)
    return done.returncode


@pytest.mark.skipif(sys.platform == "win32", reason="a pipe's closed end reads differently here")
def test_a_stderr_nobody_reads_leaves_the_run_s_own_exit_code(tmp_path):
    for arguments, code, _reports in _cases(tmp_path):
        assert _dead_stderr(tmp_path, arguments) == code, arguments
