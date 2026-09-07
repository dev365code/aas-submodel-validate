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


# -- the gate before the publish, read by what it does ------------------------

def _workflows():
    """Every workflow file, both spellings.

    `*.yml` alone misses `*.yaml`, which GitHub runs just the same, so a
    second publishing workflow named the other way would be invisible to
    everything below. Ported from the sibling project that met that.
    """
    where = ROOT / ".github" / "workflows"
    return sorted(p for p in where.iterdir() if p.suffix in (".yml", ".yaml"))


def _steps(path):
    """Each step of each job as attributes and commands.

    Read by effect rather than by name. A gate is not "a step called
    `everything must be green first`" -- that name survives every way of
    removing the gate underneath it -- so what is collected is what the
    step would actually run, and the attributes that decide whether
    running it matters.
    """
    steps, current, block_indent = [], None, None
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip())
        if block_indent is not None:
            if stripped and indent > block_indent:
                if not stripped.startswith("#"):
                    current["commands"].append(stripped.split("#")[0].strip())
                continue
            block_indent = None
        if re.match(r"^\s*-\s+(name|uses|run|id):", raw):
            current = {"attrs": {}, "commands": [], "indent": indent}
            steps.append(current)
        if current is None or stripped.startswith("#"):
            continue
        found = re.match(r"^\s*-?\s*(\w[\w-]*):\s*(.*)$", raw)
        if not found:
            continue
        key, value = found.group(1), found.group(2).strip()
        if key == "run":
            if value in ("|", ">", "|-", ">-"):
                block_indent = indent
            elif value and not value.startswith("#"):
                current["commands"].append(value.split("#")[0].strip())
        else:
            current["attrs"][key] = value
    return steps


#: How a workflow says something leaves here that a person could install.
#: Not "uploads an artifact", which is too wide -- a workflow uploading a
#: diagnostic for a human to read publishes nothing.
PUBLISHES = ("pypi-publish", "gh release create")


def _publishes(path):
    text = path.read_text(encoding="utf-8")
    if any(marker in text for marker in PUBLISHES):
        return True
    return any("dist" in line.split("path:", 1)[1]
               for line in text.splitlines() if line.strip().startswith("path:"))


def _runs_the_gate(command):
    """Whether this command is the gate, however it has been weakened.

    Matching `make check` exactly missed `make check || true`, and the
    miss reads as "this workflow never runs the gate" -- true in effect
    and useless as a diagnosis, because it points at the wrong repair.
    The step is the gate; what was done to it is the finding.
    """
    return command.strip().split("||")[0].split("&&")[0].strip() == "make check"


def test_a_workflow_that_publishes_runs_the_gate_and_is_stopped_by_it():
    """Five ways to keep the release workflow looking protected while
    removing the protection, and the whole suite stayed green through
    every one: `continue-on-error: true` on the *step* rather than the
    job; `|| true` appended to the command; the command replaced with an
    echo; the command deleted; the step removed and its name left on
    something else.

    Nothing here read the release workflow at all. The gates in this file
    read `ci.yml`, so `make check` running before a publish was a claim
    the project made about itself and checked nowhere.

    Read by effect. A step is a gate when it *runs* the gate and its
    failure would stop the job -- the name on it is the part that
    survives every removal.
    """
    publishing = [w for w in _workflows() if _publishes(w)]
    assert publishing, ("no workflow publishes anything; this test is "
                        "looking in the wrong place")
    for workflow in publishing:
        steps = _steps(workflow)
        gates = [step for step in steps
                 if any(_runs_the_gate(command) for command in step["commands"])]
        assert gates, (
            "%s publishes and never runs `make check`. Its steps run: %s"
            % (workflow.name, [c for s in steps for c in s["commands"]]))
        for gate in gates:
            assert gate["attrs"].get("continue-on-error", "false") != "true", (
                "%s runs `make check` in a step marked continue-on-error, so "
                "the gate cannot stop the publish" % workflow.name)
            for command in gate["commands"]:
                assert not command.rstrip().endswith("|| true"), (
                    "%s appends `|| true` to a gate command: %s"
                    % (workflow.name, command))


def test_the_release_gate_is_not_a_step_that_only_looks_like_one(tmp_path):
    """The instrument, checked against workflows it should refuse.

    A reader that finds what it expects in the file as committed proves
    nothing about a file that has been edited, so this hands it the gate
    neutralised each way and asserts it says so. Without this the reader
    could match on the step's name and pass -- and the name is exactly
    what survives every removal.
    """
    body = (ROOT / ".github" / "workflows" / "release.yml").read_text("utf-8")
    assert "make check" in body, "the fixture below has nothing to neutralise"

    def gates_of(text):
        path = tmp_path / "probe.yml"
        path.write_text(text, "utf-8")
        return [s for s in _steps(path)
                if any(_runs_the_gate(c) for c in s["commands"])]

    (intact,) = gates_of(body)
    assert intact["attrs"].get("continue-on-error", "false") != "true"

    marked = body.replace("      - name: everything must be green first",
                          "      - name: everything must be green first\n"
                          "        continue-on-error: true", 1)
    assert marked != body
    (neutralised,) = gates_of(marked)
    assert neutralised["attrs"].get("continue-on-error") == "true", (
        "the reader cannot see continue-on-error on the step")

    for gone in (body.replace("          make check", "          echo skipping", 1),
                 body.replace("          make check", "          true", 1)):
        assert gone != body
        assert not gates_of(gone), "the reader still finds a gate that is not there"

    appended = body.replace("          make check", "          make check || true", 1)
    assert appended != body
    (weakened,) = gates_of(appended)
    assert any(c.rstrip().endswith("|| true") for c in weakened["commands"]), \
        "the reader cannot see `|| true` on the gate command"


def test_the_linter_runs_the_same_way_on_both_sides():
    """A gate that is not the same check on both sides is two gates.

    The flags are the part that drifts silently: a cache makes a linter
    answer about a file that has moved, so the local run can be green
    over a tree CI reads differently -- reported by a sibling project
    after a rename, and not reproducible on the ruff pinned here, which
    is why what is asserted is the sameness rather than the symptom.
    """
    recipe = [c for c in _commands_of("lint") if "ruff check" in c]
    assert recipe, "the lint target no longer runs ruff"
    workflow = [c for c in ci_commands_of_workflow("ci.yml")
                if c.startswith("ruff check")]
    assert workflow, "the CI lint job no longer runs ruff"

    def flags(command):
        return {word for word in command.split() if word.startswith("--")}

    for here in recipe:
        for there in workflow:
            assert flags(here) == flags(there), (
                "make runs `%s` and CI runs `%s`; the flags differ, so the "
                "two are not the same check" % (here.strip(), there.strip()))
    assert any("--no-cache" in flags(c) for c in recipe), \
        "the local lint may answer from a cache"


def ci_commands_of_workflow(name):
    return [c for step in _steps(ROOT / ".github" / "workflows" / name)
            for c in step["commands"]]
