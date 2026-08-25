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
    assert _check_targets() == ["lint", "generated", "vendored", "test", "exercised"]


@pytest.mark.parametrize("target,command", CHECKS, ids=[c for _t, c in CHECKS])
def test_ci_runs_everything_make_check_runs(target, command):
    if command in LOCAL_ONLY:
        pytest.skip(LOCAL_ONLY[command])
    assert command in _normalise(WORKFLOW), \
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
