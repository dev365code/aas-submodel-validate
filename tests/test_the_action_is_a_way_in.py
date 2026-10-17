"""The action is a way in, and it reaches the verdict the others reach.

`uses: dev365code/aas-submodel-validate@v0.13.0` is three lines somebody
writes once per repository, and what they get has to be `smtv`: the same
output and the same exit code, with nothing between them that can turn a
file name into a command or a failure into a pass.

So the step's own script is taken out of `action.yml` and run here, the
way a runner runs it -- `bash --noprofile --norc -e -o pipefail` -- on
the installed path, with this checkout standing in for the release it
would install. What it prints for a file is held to what `smtv` prints
for that file, byte for byte, and the code it leaves by to the code
`smtv` leaves by. The path that runs a carried single file needs the
file built, which needs the network once, so it is run by CI's job for
this action rather than here; the parts of it that need no file are
here.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from aas_submodel_validate import cli

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "action.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
EXAMPLE = ROOT / "src" / "aas_submodel_validate" / "data" / "example" / "idta-02004-2.0.aasx"

def _documented() -> set:
    """The codes `smtv --help` documents, read from the help it prints, so
    a code added there is a code this action has to have been told about."""
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed), pytest.raises(SystemExit):
        cli.main(["--help"])
    after = printed.getvalue().split("exit codes:", 1)[1]
    return {int(code) for code in re.findall(r"(?m)^\s*(\d+)\s{2}", after)}


def _bash():
    """The bash a runner runs `shell: bash` with. On Windows that is the one
    Git for Windows carries -- found beside `git`, because another
    `bash.exe` on PATH may be WSL's, which runs a different system and
    cannot see this checkout's paths."""
    if os.name != "nt":
        return shutil.which("bash")
    git = shutil.which("git")
    for parent in (Path(git).resolve().parents if git else ()):
        candidate = parent / "bin" / "bash.exe"
        if candidate.is_file():
            return str(candidate)
    return None


BASH = _bash()

bash = pytest.mark.skipif(BASH is None,
                          reason="the action's steps are bash, and this machine "
                                 "has no bash a runner would use; CI's job for "
                                 "the action runs them on Linux and Windows")


def _posix(path) -> str:
    """A path as a bash script may write it, on Windows too."""
    return Path(path).as_posix()


def _step(step_id):
    """The `run:` script of the step with this `id`, as the runner sees it,
    and the names its `env:` maps."""
    text = ACTION.read_text(encoding="utf-8")
    found = re.search(r"(?m)^    - id: %s\n((?:      .*\n|\s*\n)+)" % re.escape(step_id), text)
    assert found, "action.yml has no step with id %r" % step_id
    block = found.group(1)
    head, _, rest = block.partition("      run: |\n")
    assert rest, "step %r runs no script" % step_id
    lines = []
    for line in rest.splitlines(keepends=True):
        if line.strip() and not line.startswith(" " * 8):
            break
        lines.append(line[8:] if line.startswith(" " * 8) else line)
    env = dict(re.findall(r"(?m)^        ([A-Z_]+): (.+)$", head))
    return "".join(lines), env


def _shim(tmp_path):
    """`python3` on PATH meaning this interpreter, as setup-python supplies one."""
    shim = tmp_path / "bin"
    shim.mkdir(exist_ok=True)
    (shim / "python3").write_text('#!/bin/sh\nexec "%s" "$@"\n' % _posix(sys.executable))
    (shim / "python3").chmod(0o755)
    return shim


def _check(tmp_path, paths, args="", *, fail_on_finding="true", pyz="", sha256="",
           shims=()):
    """The check step, run as a runner runs it: what it printed on stdout,
    what it left by, and what it wrote to GITHUB_OUTPUT. `_check_bytes`
    keeps both streams as bytes."""
    out, err, left, written = _check_bytes(tmp_path, paths, args, fail_on_finding=fail_on_finding,
                                           pyz=pyz, sha256=sha256, shims=shims)
    return out.decode("utf-8").replace("\r\n", "\n"), left, written


def _check_bytes(tmp_path, paths, args="", *, fail_on_finding="true", pyz="", sha256="",
                 shims=()):
    body, _ = _step("check")
    script = tmp_path / "check.sh"
    script.write_text(body, encoding="utf-8")
    outputs = tmp_path / "outputs"
    outputs.write_text("", encoding="utf-8")
    env = {**os.environ,
           "PATH": os.pathsep.join([*map(str, shims), str(_shim(tmp_path)),
                                    os.environ.get("PATH", "")]),
           "PATHS": paths, "EXTRA": args, "PYZ": pyz, "WANT_SHA": sha256,
           "TARGET": str(ROOT / "src"), "FAIL_ON_FINDING": fail_on_finding,
           "GITHUB_OUTPUT": str(outputs), "PYTHONIOENCODING": "utf-8"}
    done = subprocess.run([BASH, "--noprofile", "--norc", "-e", "-o", "pipefail", _posix(script)],
                          capture_output=True, env=env, cwd=tmp_path, timeout=300)
    written = dict(line.split("=", 1) for line in outputs.read_text("utf-8").splitlines() if "=" in line)
    return done.stdout, done.stderr, done.returncode, written


def _smtv_bytes(path, args=""):
    """`smtv` itself on one file: both streams, as bytes, and its code."""
    done = subprocess.run([sys.executable, "-m", "aas_submodel_validate", *args.split(), str(path)],
                          capture_output=True, timeout=300,
                          env={**os.environ, "PYTHONPATH": str(ROOT / "src"),
                               "PYTHONIOENCODING": "utf-8"})
    return done.stdout, done.stderr, done.returncode


def _smtv(path, args=""):
    """What `smtv` printed on stdout and what it left by."""
    out, _, code = _smtv_bytes(path, args)
    return out.decode("utf-8").replace("\r\n", "\n"), code


# -- what the step is -------------------------------------------------------


def test_the_action_is_composite_and_runs_smtv_both_ways():
    text = ACTION.read_text(encoding="utf-8")
    assert re.search(r'(?m)^  using: "composite"$', text), "not a composite action"
    body, _ = _step("check")
    assert 'set -- "$PY" "$PYZ"' in body, "no way to run a carried single file"
    assert 'set -- "$PY" -m aas_submodel_validate' in body, "no way to run the installed one"


def test_no_input_is_written_into_a_script():
    """An expression in a script is text pasted into the script before it
    runs: a file named `x; touch y` would be a command. Inputs travel as
    environment variables, quoted where they are read."""
    for step_id in ("obtain", "check"):
        body, _ = _step(step_id)
        assert "${{" not in body, "%s: an expression inside the script" % step_id


def test_the_codes_it_reads_as_verdicts_are_the_ones_smtv_documents():
    body, _ = _step("check")
    found = re.search(r"(?m)^\s*([0-9|]+)\) ;;", body)
    assert found, "the step does not say which codes are verdicts"
    assert {int(code) for code in found.group(1).split("|")} == _documented() == {0, 1, 2, 64}


def test_the_code_is_published_before_anything_can_end_the_step():
    """GitHub publishes no outputs of a step it has decided failed, so the
    code is written before the branch that can fail it -- the log has it
    even when the job cannot."""
    body, _ = _step("check")
    assert body.index("exit-code=") < body.index("fail-on-finding is false")
    assert re.search(r'(?m)^exit "\$worst"$', body), "the code is computed and thrown away"


def test_the_gate_is_the_default():
    text = ACTION.read_text(encoding="utf-8")
    found = re.search(r'(?ms)^  fail-on-finding:\n.*?^    default: "(\w+)"$', text)
    assert found and found.group(1) == "true"


# -- what it says, against what smtv says -----------------------------------


@bash
@pytest.mark.parametrize("make, args", [
    ("the example", ""),
    ("the example", "-W"),
    ("the example", "-f json"),
    ("a document this reader refuses", ""),
    ("a path with nothing behind it", "-f json"),
    ("a template this reader will not read", "--template"),
    ("a flag smtv does not have", "--no-such-flag"),
], ids=["judged", "judged-W", "judged-json", "refused", "absent-json",
        "refused-template", "usage"])
def test_the_step_says_what_smtv_says_about_one_file(tmp_path, make, args):
    path = {"the example": EXAMPLE,
            "a document this reader refuses": tmp_path / "broken.json",
            "a path with nothing behind it": tmp_path / "nothing-here.aasx",
            "a template this reader will not read": EXAMPLE,
            "a flag smtv does not have": EXAMPLE}[make]
    if make == "a document this reader refuses":
        path.write_bytes(b"not json at all")
    if args == "--template":
        template = tmp_path / "not-a-template.json"
        template.write_text("[]", "utf-8")
        args = "--template %s" % template
    # One line of a block, the way `paths: |` hands a file over -- this
    # checkout's own folder has a space in its name.
    block = "%s\n" % path
    said, warned, code = _smtv_bytes(path, args)
    # As bytes, both streams: what a log keeps is what was written.
    printed, complained, left, written = _check_bytes(tmp_path, block, args)
    assert (printed, complained, left) == (said, warned, code)
    assert written["exit-code"] == str(code)
    # Reading the code instead of failing on it: the same stdout, the code in
    # the output, a pass, and one line more on stderr saying why it passed.
    printed, complained, left, written = _check_bytes(tmp_path, block, args,
                                                      fail_on_finding="false")
    assert (printed, left, written["exit-code"]) == (said, 0, str(code))
    assert complained.startswith(warned) and complained[len(warned):].count(b"\n") == 1


@bash
def test_several_files_leave_by_the_heaviest_code_in_either_order(tmp_path):
    """One run of smtv per file, because it judges one; their outputs in
    the order given, and the code that says the most: a call made wrong,
    then a file that could not be judged, then a finding, then nothing."""
    broken = tmp_path / "broken.json"
    broken.write_bytes(b"not json at all")
    for order in ((EXAMPLE, broken), (broken, EXAMPLE)):
        printed, left, written = _check(tmp_path, "\n".join(map(str, order)))
        assert printed == "".join(_smtv(path)[0] for path in order)
        assert left == 2 and written["exit-code"] == "2"
    printed, left, _ = _check(tmp_path, "%s\n%s\n" % (EXAMPLE, EXAMPLE), "-W")
    assert left == 1
    # On one line the names are separated by spaces, as documented; these
    # two have none in them.
    copy = tmp_path / "copy.aasx"
    shutil.copy(EXAMPLE, copy)
    printed, left, _ = _check(tmp_path, "%s %s" % (copy, broken))
    assert printed == _smtv(copy)[0] + _smtv(broken)[0]
    assert left == 2


@bash
def test_several_files_as_json_are_one_document_each(tmp_path):
    """What the front page tells a machine reader: one JSON document per
    file, each the bytes smtv prints for it -- a sequence, not a document."""
    broken = tmp_path / "broken.json"
    broken.write_bytes(b"not json at all")
    out, _, left, _ = _check_bytes(tmp_path, "%s\n%s\n" % (EXAMPLE, broken), "-f json")
    assert out == b"".join(_smtv_bytes(path, "-f json")[0] for path in (EXAMPLE, broken))
    text, documents, at = out.decode("utf-8"), [], 0
    decoder = json.JSONDecoder()
    while text[at:].strip():
        document, at = decoder.raw_decode(text, at + len(text[at:]) - len(text[at:].lstrip()))
        documents.append(document)
    assert [document["path"] for document in documents] == [str(EXAMPLE), str(broken)]
    assert left == 2


@bash
def test_a_file_name_is_a_name_and_not_a_command(tmp_path):
    """Neither a name with a space in its directory nor one shaped like a
    command is anything but a path to judge."""
    spaced = tmp_path / "a folder" / "example.aasx"
    spaced.parent.mkdir()
    shutil.copy(EXAMPLE, spaced)
    marker = tmp_path / "ran"
    shaped = "x; touch %s" % marker
    printed, left, _ = _check(tmp_path, "%s\n%s" % (spaced, shaped))
    assert printed.startswith(_smtv(spaced)[0])
    assert left == 2, "the shaped name should be a file nothing is behind"
    assert not marker.exists()


@bash
def test_paths_that_name_nothing_are_a_call_made_wrong(tmp_path):
    """A blank `paths` -- an unset variable in the caller's workflow -- is
    64, the way `smtv` with no path is, and not a pass over nothing."""
    printed, left, written = _check(tmp_path, "  \n ")
    assert left == 64
    # On stdout, where a runner reads its annotations, and nothing else.
    assert printed.startswith("::error::") and printed.count("\n") == 1, printed
    assert "exit-code" not in written


@bash
def test_a_code_smtv_does_not_give_is_not_a_verdict(tmp_path):
    """126, 127, a signal: the checker did not run, and reporting that as a
    finding about a file -- or, with fail-on-finding false, passing over it
    -- would be a verdict nobody gave."""
    fake = tmp_path / "fake.pyz"
    fake.write_text("import sys\nsys.exit(0 if '--version' in sys.argv else 3)\n", "utf-8")
    printed, left, written = _check(tmp_path, str(EXAMPLE), pyz=str(fake),
                                    fail_on_finding="false")
    assert left == 3
    assert "exit-code" not in written


@bash
def test_a_validator_that_does_not_start_is_not_a_finding(tmp_path):
    """A validator that cannot start -- an install that left no module, an
    interpreter it does not run on -- leaves by 1, which is also the code
    for a finding. Asked to start before it is asked about a file, it is
    told apart: the step ends with what it said, and no code is published
    as though a file had been judged."""
    fake = tmp_path / "smtv.pyz"
    fake.write_text("import sys\nsys.stderr.write('no module named it\\n')\nsys.exit(1)\n",
                    "utf-8")
    out, err, left, written = _check_bytes(tmp_path, "%s\n" % EXAMPLE, pyz=str(fake),
                                           fail_on_finding="false")
    assert left == 1 and "exit-code" not in written
    assert b"no module named it" in err and b"did not start" in out


@bash
def test_a_carried_file_with_the_wrong_hash_is_not_run(tmp_path):
    fake = tmp_path / "smtv.pyz"
    marker = tmp_path / "ran"
    fake.write_text("import pathlib\npathlib.Path(%r).write_text('')\n" % str(marker), "utf-8")
    _, left, _ = _check(tmp_path, str(EXAMPLE), pyz=str(fake), sha256="0" * 64)
    assert left == 64 and not marker.exists()


#: `sha256sum` as GNU coreutils writes it -- on Linux, and in the bash Git
#: for Windows carries, where a path written the Windows way has backslashes
#: in it: a name holding a backslash or a newline is escaped, and the line
#: then starts with a backslash, before the digest.
GNU_SHA256SUM = """#!/bin/sh
exec "PYTHON" -c '
import hashlib, sys
for name in sys.argv[1:] or ["-"]:
    data = sys.stdin.buffer.read() if name == "-" else open(name, "rb").read()
    escaped = chr(92) in name or chr(10) in name
    shown = name.replace(chr(92), chr(92) * 2).replace(chr(10), chr(92) + "n")
    print((chr(92) if escaped else "") + hashlib.sha256(data).hexdigest() + "  " + shown)
' "$@"
"""


@bash
@pytest.mark.parametrize("given", ["lower", "upper"])
def test_a_carried_file_with_the_right_hash_is_run_whatever_it_is_called(tmp_path, given):
    """The digest a caller pins is compared with the file's bytes. Read off
    the line `sha256sum` writes for a name, it came back with a backslash in
    front wherever the name had one -- as a path written the Windows way
    does -- and a pinned file named so never ran. So the name here has one,
    and `sha256sum` behaves as GNU's does."""
    shim = tmp_path / "gnu"
    shim.mkdir()
    (shim / "sha256sum").write_text(GNU_SHA256SUM.replace("PYTHON", _posix(sys.executable)),
                                    "utf-8")
    (shim / "sha256sum").chmod(0o755)
    folder = tmp_path / ("carried\\in" if os.name != "nt" else "carried in")
    folder.mkdir()
    fake = folder / "smtv.pyz"
    fake.write_text("import sys\nsys.exit(0)\n", "utf-8")
    digest = hashlib.sha256(fake.read_bytes()).hexdigest()
    digest = digest.upper() if given == "upper" else digest
    _, left, written = _check(tmp_path, "%s\n" % EXAMPLE, pyz=str(fake), sha256=digest,
                              shims=(shim,))
    assert left == 0 and written["exit-code"] == "0", (left, written)
    assert written["pyz"] == str(fake)


@bash
@pytest.mark.parametrize("wanted, ref, expected", [
    ("", "v0.12.0", "0.12.0"),
    ("0.11.0", "v0.12.0", "0.11.0"),
    ("", "main", None),
], ids=["the-ref-pinned", "the-version-asked", "a-branch"])
def test_the_release_it_installs_is_the_one_it_was_pinned_at(tmp_path, wanted, ref, expected):
    """With pip stood in for, so nothing is fetched: what it would install,
    and the version it says it decided on. A branch has no release in its
    name, so it runs the version the tree it came from declares. The ref
    names an older release than this tree, so that reading the tree in its
    place could not give the right answer by accident."""
    body, _ = _step("obtain")
    script = tmp_path / "obtain.sh"
    script.write_text(body, encoding="utf-8")
    shim = tmp_path / "bin"
    shim.mkdir()
    asked = tmp_path / "asked"
    (shim / "python3").write_text('#!/bin/sh\nprintf "%%s\\n" "$@" > "%s"\n' % _posix(asked))
    (shim / "python3").chmod(0o755)
    outputs = tmp_path / "outputs"
    outputs.write_text("", encoding="utf-8")
    # The bash a runner uses, as every other step here is run: on Windows
    # the bare name found WSL's, which runs another system entirely and
    # answered in UTF-16 that it had no distribution installed.
    done = subprocess.run(
        [BASH, "--noprofile", "--norc", "-e", "-o", "pipefail", _posix(script)],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "PATH": "%s%s%s" % (shim, os.pathsep, os.environ.get("PATH", "")),
             "WANTED": wanted, "ACTION_REF": ref, "ACTION_PATH": str(ROOT),
             "RUNNER_TEMP": str(tmp_path), "GITHUB_OUTPUT": str(outputs)})
    assert done.returncode == 0, done.stderr
    declared = re.search(r'(?m)^version = "(.+)"$',
                         (ROOT / "pyproject.toml").read_text("utf-8")).group(1)
    version = expected or declared
    written = dict(line.split("=", 1) for line in outputs.read_text("utf-8").splitlines())
    assert written["version"] == version
    argv = asked.read_text("utf-8").split("\n")
    assert "aas-submodel-validate==%s" % version in argv
    assert {"--only-binary", ":all:", "--target"} <= set(argv)


def test_this_repository_runs_its_own_action():
    """An action nobody runs is a README section. CI uses it the way a
    caller would: on a file it judges, on one that must fail -- checking the
    failure was the checker's code and not the step falling over -- and
    from a single file it carries, fetching nothing."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert len(re.findall(r"(?m)^\s+uses: \./$", text)) >= 3, "CI does not run this action"


# -- the front page ---------------------------------------------------------


def _front_page_step() -> str:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    found = re.search(r"(?s)```yaml\n(- uses: dev365code/aas-submodel-validate@.*?)```", readme)
    assert found, "the README shows no workflow step using this action"
    return found.group(1)


def test_the_front_page_pins_the_release_this_tree_is():
    """The line a reader copies names a release, and the page that ships
    with a release hands out that release -- not the one before it."""
    pins = re.findall(r"uses: dev365code/aas-submodel-validate@v([\d.]+)",
                      (ROOT / "README.md").read_text(encoding="utf-8"))
    declared = re.search(r'(?m)^version = "(.+)"$',
                         (ROOT / "pyproject.toml").read_text("utf-8")).group(1)
    assert pins and set(pins) == {declared}, (pins, declared)


def test_the_front_page_step_asks_only_for_what_the_action_takes():
    step = _front_page_step()
    asked = set(re.findall(r"(?m)^    ([a-z][\w-]*):", step))
    declared = set(re.findall(r"(?m)^  ([a-z][\w-]*):\n    description:",
                              ACTION.read_text(encoding="utf-8")))
    assert asked and asked <= declared, (sorted(asked - declared), sorted(declared))
