"""A line meant for the person running the check goes to stderr, or nowhere.

Four of them were written with `print(..., file=sys.stderr)`: why nothing
was judged, a template refused, how many submodels `--require-all-judged`
found judged, and a package that carries no example. With stderr closed --
`2>&-`, or pythonw with no console -- `sys.stderr` is None, and `print`
handed None writes to stdout: into the JSON a pipeline was about to parse.
With a stderr whose reader has gone, the write raised, and the process left
by 120 instead of the code the run had decided. Both are what the bug report's
lines were made safe from; these four are held to the same.

And a program that calls `main` itself is held to it too. It may hand
`contextlib.redirect_stderr` a writer with nothing but `write` -- all `print`
asks of a stream -- and the line is still its to read; and it goes on running
after `main` returns, so a stderr let go of is not handed back as None, which
would send that program's own lines for stderr to its stdout.
"""
from __future__ import annotations

import contextlib
import errno
import io
import json
import os
import subprocess
import sys
from pathlib import Path

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


def _missing():
    from aas_submodel_validate.example import NotBundled
    raise NotBundled("this package carries no example")


def _runs(tmp_path, monkeypatch):
    """All four lines, in-process: (arguments, the code the run leaves by).
    The fourth needs a package without its example, which is patched in;
    the other three never ask for one."""
    monkeypatch.setattr(cli, "bundled_example", _missing)
    return ([(arguments, code) for arguments, code, _reports in _cases(tmp_path)]
            + [(["--example", "-f", "json"], cli.EXIT_ERROR)])


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
    monkeypatch.setattr(cli, "bundled_example", _missing)
    assert cli.main(["--example", "-f", "json"]) == cli.EXIT_ERROR
    assert "no example" in capsys.readouterr().err
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(sys, "__stderr__", None)
    assert cli.main(["--example", "-f", "json"]) == cli.EXIT_ERROR
    assert capsys.readouterr().out == ""


class _Writer:
    """What a program hands `contextlib.redirect_stderr`: `write`, and
    nothing else. `print` asks no more of a stream."""

    def __init__(self):
        self.text = []

    def write(self, text):
        self.text.append(text)
        return len(text)


def test_a_stderr_that_only_writes_gets_the_line_and_the_run_keeps_its_code(
        tmp_path, capsys, monkeypatch):
    for arguments, code in _runs(tmp_path, monkeypatch):
        sink = _Writer()
        with contextlib.redirect_stderr(sink):
            assert cli.main(arguments) == code, arguments
        assert "".join(sink.text).startswith("smtv: "), (arguments, sink.text)
        capsys.readouterr()


class _Dead(io.TextIOBase):
    """A stderr whose reader has gone, as a program in-process sees one."""

    def write(self, text):
        raise BrokenPipeError(errno.EPIPE, "Broken pipe")


def test_a_stderr_let_go_of_is_not_handed_back_as_none(tmp_path, capsys, monkeypatch):
    for arguments, code in _runs(tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "stderr", _Dead())
        assert cli.main(arguments) == code, arguments
        capsys.readouterr()
        print("a line of the caller's own, for its stderr", file=sys.stderr)
        assert "the caller's own" not in capsys.readouterr().out, (
            "after main returned, the caller's line for stderr went to stdout (%r)" % arguments)


def test_a_stderr_already_closed_is_let_go_of_too(tmp_path, capsys, monkeypatch):
    # A stream closed in-process raises ValueError, not OSError.
    for arguments, code in _runs(tmp_path, monkeypatch):
        closed = io.StringIO()
        closed.close()
        monkeypatch.setattr(sys, "stderr", closed)
        assert cli.main(arguments) == code, arguments
        capsys.readouterr()


def _dead_stderr(tmp_path, command):
    """The exit code of `python <command>` run with a stderr whose reader has gone."""
    reader, writer = os.pipe()
    os.close(reader)
    try:
        done = subprocess.run([sys.executable, *command],
                              stdout=subprocess.DEVNULL, stderr=writer, cwd=str(tmp_path),
                              timeout=120, env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    finally:
        os.close(writer)
    return done.returncode


def test_a_stderr_nobody_reads_leaves_the_run_s_own_exit_code(tmp_path):
    for arguments, code, _reports in _cases(tmp_path):
        assert _dead_stderr(tmp_path, ["-m", "aas_submodel_validate", *arguments]) == code, arguments


#: The command line with no example in the package: what `_missing` does
#: in-process, done where the interpreter's own flush at exit can be seen.
_WITHOUT_ITS_EXAMPLE = """\
import sys
import aas_submodel_validate.cli as cli
from aas_submodel_validate.example import NotBundled
def missing():
    raise NotBundled("this package carries no example")
cli.bundled_example = missing
sys.exit(cli.main(["--example", "-f", "json"]))
"""


def test_a_stderr_nobody_reads_leaves_a_package_without_its_example_its_exit_code(tmp_path):
    assert _dead_stderr(tmp_path, ["-c", _WITHOUT_ITS_EXAMPLE]) == cli.EXIT_ERROR
