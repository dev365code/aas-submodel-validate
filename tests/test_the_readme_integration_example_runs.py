"""The front page's integration example, run as written.

It is the one piece of code a product integrator copies whole, and its
comment said exit 2 "neither writes a report to parse" -- while
`docs/report-schema.md` says exit 2 writes one for everything but a
refused `--template`, and that report is where a refusal says what was
refused. Followed as written, the example threw it away and kept one
line of stderr. So the example runs here, with `smtv` meaning this
checkout, against the cases its comment names.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
EXAMPLE = ROOT / "src" / "aas_submodel_validate" / "data" / "example" / "idta-02004-2.0.aasx"


def _example():
    after = README.split("There is no importable Python API yet", 1)[1]
    code = re.search(r"(?s)```python\n(.*?)```", after)
    assert code, "the README no longer shows the integration example"
    return code.group(1)


def _run(monkeypatch, capsys, path, *before):
    """The example, as written, on `path`; `before` goes ahead of its own
    arguments, which is how a usage error is made of a fixed command."""
    code = _example()
    assert code.count('"submodel.aasx"') == 1, code
    code = code.replace('"submodel.aasx"', repr(str(path)))
    real = subprocess.run

    def smtv(command, **kwargs):
        assert command[0] == "smtv", command
        kwargs.setdefault("env", {**os.environ, "PYTHONPATH": str(ROOT / "src")})
        return real([sys.executable, "-m", "aas_submodel_validate", *before, *command[1:]],
                    timeout=120, **kwargs)

    monkeypatch.setattr(subprocess, "run", smtv)
    exec(compile(code, "README.md", "exec"), {})
    return capsys.readouterr().out


def test_a_document_this_reader_refuses_is_read_from_its_report(tmp_path, monkeypatch, capsys):
    broken = tmp_path / "broken.json"
    broken.write_bytes(b"not json at all")
    printed = _run(monkeypatch, capsys, broken)
    assert printed.startswith("X3 error"), printed


def test_a_path_that_is_not_there_is_read_from_its_report(tmp_path, monkeypatch, capsys):
    printed = _run(monkeypatch, capsys, tmp_path / "nothing-here.aasx")
    assert printed.startswith("X6 error"), printed


def test_a_judged_file_is_read_from_its_report(monkeypatch, capsys):
    printed = _run(monkeypatch, capsys, EXAMPLE)
    assert "HD-D10 warning" in printed, printed


def test_a_usage_error_leaves_with_what_was_wrong(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit) as left:
        _run(monkeypatch, capsys, EXAMPLE, "--no-such-option")
    assert "usage:" in str(left.value.code), left.value.code


def test_a_refused_template_leaves_with_what_was_wrong(tmp_path, monkeypatch, capsys):
    """Exit 2 with nothing on stdout: the one 2 that writes no report."""
    template = tmp_path / "template.json"
    template.write_bytes(b"not a template")
    with pytest.raises(SystemExit) as left:
        _run(monkeypatch, capsys, EXAMPLE, "--template", str(template))
    assert "template" in str(left.value.code), left.value.code
