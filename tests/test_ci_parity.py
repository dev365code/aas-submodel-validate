"""`make check` and CI must run the same commands.

The sibling repositories learned this the loud way: a gate that exists in
one place and not the other fails quietly in the dangerous direction — a
gate only in the Makefile means CI is not checking something somebody
believes it checks, and nothing says so. This is a text comparison, not a
build system, on purpose: something that understood both files would be a
third thing to keep in step.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
if not _WORKFLOW_PATH.exists() or not (ROOT / "Makefile").exists():
    pytest.skip("no CI workflow / Makefile here (installed package, not a checkout)",
                allow_module_level=True)
MAKEFILE = (ROOT / "Makefile").read_text("utf-8")


def _without_comments(text: str) -> str:
    """The workflow with YAML comments removed. A gate that is only a
    commented-out step is not a gate, and a substring search over the raw
    file would be fooled by the comment text -- so the comparison runs
    against the executable part only."""
    return "\n".join(re.sub(r"#.*$", "", line) for line in text.splitlines())


WORKFLOW = _without_comments(_WORKFLOW_PATH.read_text("utf-8"))

#: Commands `make check` runs that CI is not expected to, with the reason.
#: Empty today. An entry here is a deliberate exemption and needs justifying.
LOCAL_ONLY: dict = {}


def _check_targets():
    line = re.search(r"^check:(.*)$", MAKEFILE, re.M)
    assert line, "the Makefile has no check target"
    return line.group(1).split()


def _commands_of(target: str):
    body = re.search(r"^%s:.*?\n((?:\t.*\n|\n)*)" % re.escape(target), MAKEFILE, re.M)
    if not body:
        return []
    return [raw.strip().replace("$(PYTHON)", "").strip()
            for raw in body.group(1).splitlines()
            if raw.strip().startswith("$(PYTHON)")]


def _normalise(command: str) -> str:
    command = command.replace("-m pytest", "pytest").replace("-m ruff", "ruff")
    return re.sub(r"\s+", " ", command).strip()


#: The workflow, one line at a time. It used to be flattened whole and
#: the recipe looked for as a substring of the result, so any line
#: anywhere that happened to contain the words satisfied the check --
#: and one did: a step added to run the suite from an unpacked sdist
#: writes `python -m pytest -q`, which normalises to a string containing
#: `pytest -q`. From then on the whole test matrix could stop running
#: the suite and this file would not notice. Measured: deleting
#: `- run: pytest -q` from the matrix job left ten passing.
WORKFLOW_LINES = WORKFLOW.splitlines()


def _is_the_step(line: str, command: str) -> bool:
    """Whether this line *is* CI running that command, not merely a line
    with those words in it.

    A step is `- run: <command>` or, inside a block, the command alone.
    Asked as a substring of the whole flattened file, then of a whole
    line, both were satisfied by a step that runs the suite from an
    unpacked sdist: `PYTHONPATH=... python -m pytest -q` normalises to
    something ending in `pytest -q`. From then on the entire matrix
    could stop running the suite unnoticed. Measured both times by
    deleting `- run: pytest -q` and watching this file pass.
    """
    spoken = _normalise(line)
    for prefix in ("- run: ", "run: ", ""):
        rest = spoken[len(prefix):] if spoken.startswith(prefix) else None
        if rest is None:
            continue
        for interpreter in ("python ", "python3 ", ""):
            if rest == interpreter + command:
                return True
    return False


CHECKS = [(target, _normalise(command))
          for target in _check_targets()
          for command in _commands_of(target)]


def test_the_check_target_has_recipes_to_compare():
    assert len(CHECKS) >= 2, CHECKS


def test_no_gate_can_leave_make_check_quietly():
    """The comparison above is parametrised over `check:`'s own dependency
    list, so removing a target does not fail a test -- it deletes one.
    Measured: dropping `vendored` left `make check` green and this file at
    six passing tests instead of seven. The list of gates is therefore
    named here, where losing one is a diff somebody has to justify."""
    assert _check_targets() == ["lint", "generated", "vendored", "battery-data",
                                "test", "exercised"]


@pytest.mark.parametrize("target,command", CHECKS, ids=[c for _t, c in CHECKS])
def test_ci_runs_everything_make_check_runs(target, command):
    if command in LOCAL_ONLY:
        pytest.skip(LOCAL_ONLY[command])
    assert any(_is_the_step(line, command) for line in WORKFLOW_LINES), \
        "`make %s` runs %r and no CI job does" % (target, command)


def test_the_ruff_version_is_pinned_the_same_everywhere():
    """Makefile, ci.yml and pyproject must install one ruff. A local
    `make lint` and a CI `ruff check` that run different linters are two
    gates wearing one name -- the drift test_ci_parity's command match
    cannot see, because the version guard line is not a check recipe."""
    makefile = (ROOT / "Makefile").read_text("utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text("utf-8")
    version = re.search(r"RUFF_VERSION\s*:=\s*(\S+)", makefile).group(1)
    assert "ruff==%s" % version in workflow, "ci.yml ruff pin != Makefile RUFF_VERSION"
    assert '"ruff==%s"' % version in pyproject, "pyproject dev ruff pin != Makefile RUFF_VERSION"


#: The words the front page uses for platforms, and the runner that
#: measures each. The page claims all three in its first four lines; two
#: of them were measured, and what protected the third was a YAML
#: comment saying why the row was added.
RUNNERS = {"Linux": "ubuntu-latest",
           "macOS": "macos-latest",
           "Windows": "windows-latest"}


def test_the_matrix_measures_every_platform_the_page_claims():
    """A claim on the front page and a row in the matrix are one fact
    written twice, and only one of them was pinned.

    Deleting the macOS row leaves every test green, including the one
    that reads this workflow -- parity asks whether `make check`'s
    commands appear somewhere in CI, not whether they appear on the
    machines the page says they run on. So the page is read for the
    claim and the matrix for the measurement. One direction only, which
    is the one that matters: a platform the page claims has to be
    measured. Dropping the claim and keeping the row is allowed -- a
    runner nobody advertises is a runner doing extra work, not a lie."""
    readme = (ROOT / "README.md").read_text("utf-8")
    runners = set(re.findall(r"os:\s*([a-z0-9-]+)", WORKFLOW))
    assert runners, "no runners in the matrix at all"
    for platform, runner in RUNNERS.items():
        if re.search(r"(?<![\w-])%s(?![\w-])" % platform, readme):
            assert runner in runners, (
                "the front page claims %s and no CI job runs on %s, so "
                "the claim is not measured anywhere" % (platform, runner))


def test_the_recorded_hashes_are_checked_on_every_platform():
    """`vendor_template.py --check` runs twice on purpose, and the
    second one is load-bearing: end-of-line damage is a property of the
    checkout, so a hash verified only on the machine that wrote the file
    verifies nothing about the machine that unpacks it. The workflow
    says that in a comment. A comment is not a gate -- delete the
    matrix copy and everything stays green, leaving the lint job's
    single-OS run looking like the same check."""
    jobs = WORKFLOW.split("\n  test:", 1)
    assert len(jobs) == 2, "no `test:` job in this workflow to look inside"
    matrix_job = jobs[1].split("\n  wheel:", 1)[0]
    assert "vendor_template.py --check" in matrix_job, (
        "the vendored-bytes check is not in the job that runs on every "
        "platform, so nothing measures what a checkout did to the bytes")
