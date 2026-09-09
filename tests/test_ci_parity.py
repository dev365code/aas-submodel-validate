"""`make check` and CI must run the same commands.

The sibling repositories learned this the loud way: a gate that exists in
one place and not the other fails quietly in the dangerous direction — a
gate only in the Makefile means CI is not checking something somebody
believes it checks, and nothing says so. This is a text comparison, not a
build system, on purpose: something that understood both files would be a
third thing to keep in step.
"""
from __future__ import annotations

import ast
import fnmatch
import os
import re
import shutil
import subprocess
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
    # Anchored. `"ruff==0.16.3" in text` is satisfied by a file
    # installing `ruff==0.16.30`, so this said three files pinned one
    # linter while two of them pinned different ones.
    pin = re.escape("ruff==%s" % version) + r"(?![\w.])"
    assert re.search(pin, workflow), "ci.yml ruff pin != Makefile RUFF_VERSION"
    assert re.search('"' + pin, pyproject), \
        "pyproject dev ruff pin != Makefile RUFF_VERSION"


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
#: Named rather than guessed at. A second clause used to sit behind this
#: list -- any `path:` mentioning `dist` -- which is the reading the
#: paragraph above disclaims, and the two disagreed silently until a
#: workflow appeared that moves `dist/` between jobs and publishes
#: nothing. An artifact handed to the next job expires with the run.
#: What belongs here is a name that sends bytes somewhere a person can
#: install them from, and adding one is a line rather than a heuristic.
PUBLISHES = ("pypi-publish", "gh release create", "action-gh-release",
             "upload-release-asset")


def _publishes(path):
    return any(marker in path.read_text(encoding="utf-8")
               for marker in PUBLISHES)


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


# -- the tag must name a commit CI judged, not merely a tree that builds ------

def _asks_ci_for_a_verdict(step):
    """Whether this step asks CI what it concluded, however it is spelled."""
    return any("gh run list" in command for command in step["commands"])


def _verdict_gates(path):
    return [s for s in _steps(path) if _asks_ci_for_a_verdict(s)]


def test_a_tag_only_releases_a_commit_ci_has_judged():
    """`make check` on the tag's tree is a weaker check than the one every
    push already survived, and it is the only one standing between a tag
    and PyPI.

    The release job runs on `ubuntu-latest` at one Python. CI runs ten
    rows, and the difference is not decorative: a change green locally
    and green on every ubuntu row has broken `windows-latest` alone. A
    tag pushed at that commit would have found `make check` green here
    and published it.

    Nothing else in this file covers it. The gates above ask whether the
    publishing workflow *runs* `make check` -- it does, which is exactly
    what makes the hole invisible: the step is present, unweakened, and
    answering a smaller question than the one the tag implies.
    """
    release = ROOT / ".github" / "workflows" / "release.yml"
    gates = _verdict_gates(release)
    assert gates, (
        "release.yml never asks CI what it concluded about the commit "
        "being released, so a tag on any commit publishes -- including "
        "one CI judged red on a platform this job does not run. Its "
        "steps run: %s" % [c for s in _steps(release) for c in s["commands"]])
    for gate in gates:
        assert gate["attrs"].get("continue-on-error", "false") != "true", (
            "the CI-verdict gate is marked continue-on-error, so it "
            "cannot stop the publish")
        for command in gate["commands"]:
            assert not command.rstrip().endswith("|| true"), (
                "`|| true` on the CI-verdict gate: %s" % command)


def test_the_verdict_gate_names_the_commit_and_the_workflow():
    """Two ways to write this step that look identical and are not.

    Asked without `--commit`, it answers about the repository's most
    recent CI run, which on a tag pushed minutes after a green main is
    almost always green -- the gate measuring the document instead of
    the paragraph, the shape that has cost this project five separate
    repairs. Asked without `--workflow`, any workflow's success counts,
    including this release run itself.
    """
    (gate,) = _verdict_gates(ROOT / ".github" / "workflows" / "release.yml")
    script = "\n".join(gate["commands"])
    assert "--commit" in script, (
        "the query does not name a commit, so it answers about whatever "
        "CI ran last rather than about the commit being released")
    assert "--workflow" in script, (
        "the query does not name a workflow, so any workflow concluding "
        "success satisfies it")


def _concurrency(path):
    """The workflow's top-level `concurrency:` block as key -> value.

    A regex rather than a YAML parser, for the reason at the top of this
    file: something that understood the whole format would be a third
    thing to keep in step. Only the top-level block is read -- an
    indented one belongs to a job and cannot cancel the run.
    """
    block = re.search(r"(?m)^concurrency:\n((?:[ \t]+.*\n|\n)*)",
                      path.read_text(encoding="utf-8"))
    if not block:
        return {}
    settings = {}
    for line in block.group(1).splitlines():
        found = re.match(r"\s+([\w-]+):\s*(.*?)\s*$", line.split("#")[0])
        if found:
            settings[found.group(1)] = found.group(2)
    return settings


def _pushes_to_a_branch(path):
    head = path.read_text(encoding="utf-8").split("jobs:", 1)[0]
    return bool(re.search(r"(?m)^\s+push:\s*$", head)
                and re.search(r"(?m)^\s+branches:", head))


def test_a_push_to_a_branch_is_not_cancelled_by_the_next_push():
    """A cancelled run is not a verdict, and the release gate needs one.

    `cancel-in-progress: true` with a per-ref group means the second
    push to main kills the first run. That is right for a pull request,
    where only the newest commit matters, and wrong for a branch where
    every commit is a commit somebody may later tag: the abandoned one
    ends `completed`/`cancelled`, which is exactly what the release
    gate above refuses. So the commit cannot be released at all until
    CI is re-run for it, and nothing says so at the time.

    Measured in this repository's own history: `064b2201` on main
    concluded `cancelled`. It is not hypothetical, and it also empties
    the evidence for "every commit was green on its own" -- the claim
    a per-commit CI history exists to support.

    Pull requests keep the cancellation. Superseding your own push
    there is the normal case and the runner time is real.
    """
    for workflow in _workflows():
        if not _pushes_to_a_branch(workflow):
            continue
        setting = _concurrency(workflow).get("cancel-in-progress")
        if setting is None:
            continue
        assert setting != "true", (
            "%s cancels in progress for every event, so a push to a "
            "branch abandons the previous commit's run and leaves it "
            "`cancelled` -- a commit with no verdict, which the release "
            "gate cannot pass" % workflow.name)
        if setting.startswith("${{"):
            assert "pull_request" in setting, (
                "%s decides cancellation with %r, which does not "
                "distinguish a pull request from a branch push"
                % (workflow.name, setting))


#: What `gh` prints, and whether the gate may let the release through.
#: The empty string is the case that matters: no completed CI run for
#: this commit at all. A gate that treats absence as consent is the
#: whole of D7 written a second time.
VERDICTS = [("success\n", 0, "CI concluded success on this commit"),
            ("failure\n", 1, "CI concluded failure"),
            ("cancelled\n", 1, "the run was cancelled, which is not a pass"),
            ("", 1, "no completed run for this commit -- absence must fail"),
            ("\n", 1, "an empty line is not a verdict either")]


@pytest.mark.parametrize("printed,expected,why",
                         VERDICTS, ids=[v[2] for v in VERDICTS])
def test_the_verdict_gate_fails_closed(tmp_path, printed, expected, why):
    """The gate's own exit code, run against a stubbed `gh`.

    Reading the step and finding the words in it proves the step is
    there, not that it stops anything -- a gate whose text is right and
    whose exit code is 0 reads the same way in a log. So the script is
    lifted out of the workflow and run, with `gh` and `git` replaced by
    stubs on PATH, and only the exit code is believed.

    What this does not cover: the `--jq` expression that turns GitHub's
    JSON into the word the stub prints. That runs inside `gh` and is
    exercised on the next real release; the branch below it is what is
    pinned here.
    """
    if not shutil.which("sh"):
        pytest.skip("no POSIX shell here")
    (gate,) = _verdict_gates(ROOT / ".github" / "workflows" / "release.yml")

    stubs = tmp_path / "bin"
    stubs.mkdir()
    (stubs / "gh").write_text(
        "#!/bin/sh\nprintf '%s' \"$STUB_PRINTS\"\n", encoding="utf-8")
    (stubs / "git").write_text(
        "#!/bin/sh\necho deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n",
        encoding="utf-8")
    for stub in stubs.iterdir():
        stub.chmod(0o755)

    finished = subprocess.run(
        ["sh", "-c", "\n".join(gate["commands"])],
        cwd=tmp_path, capture_output=True, text=True,
        env={**os.environ,
             "PATH": "%s%s%s" % (stubs, os.pathsep, os.environ.get("PATH", "")),
             "STUB_PRINTS": printed})
    verdict = "released" if finished.returncode == 0 else "stopped"
    assert (finished.returncode == 0) == (expected == 0), (
        "gh printed %r (%s) and the gate %s.\nstdout: %s\nstderr: %s"
        % (printed, why, verdict, finished.stdout, finished.stderr))


# -- a pin that is a substring is not a pin -----------------------------------

def _ruff_version():
    return re.search(r"RUFF_VERSION\s*:=\s*(\S+)", MAKEFILE).group(1)


def _the_version_guard():
    """The Makefile's `ruff --version` guard, as a runnable shell line."""
    found = re.search(
        r"(?m)^\t@\$\(PYTHON\) -m ruff --version \| (grep.*?)\s*\\\n\s*(\|\|.*)$",
        MAKEFILE)
    assert found, "the lint target no longer guards the ruff version"
    return "%s %s" % (found.group(1), found.group(2))


#: Versions that are not the pinned one, and share a prefix or a suffix
#: with it. `0.16.30` is the next release the pin will meet.
def _near_misses(version):
    return (version + "0", "1" + version, version + ".1")


@pytest.mark.parametrize("suffix", ["0", ".1"])
def test_the_makefile_version_guard_rejects_a_longer_version(tmp_path, suffix):
    """`grep -q 0.16.3` says yes to `ruff 0.16.30`.

    The guard exists because a local `make lint` and a CI `ruff check`
    running different linters are two gates wearing one name. A pin that
    matches any version containing it as a substring is the same failure
    one layer down: the day ruff 0.16.30 ships, this guard goes on
    saying the pinned linter is installed.
    """
    version = _ruff_version()
    guard = _the_version_guard().replace("$(RUFF_VERSION)", version)
    script = 'echo "ruff %s%s" | %s' % (version, suffix, guard)
    finished = subprocess.run(["sh", "-c", script],
                              capture_output=True, text=True)
    assert finished.returncode != 0, (
        "the guard accepts ruff %s%s while pinning %s: %s"
        % (version, suffix, version, guard))


def test_the_makefile_version_guard_accepts_the_pinned_version():
    """The other direction, so the repair above cannot be `exit 1`."""
    version = _ruff_version()
    guard = _the_version_guard().replace("$(RUFF_VERSION)", version)
    finished = subprocess.run(
        ["sh", "-c", 'echo "ruff %s" | %s' % (version, guard)],
        capture_output=True, text=True)
    assert finished.returncode == 0, (
        "the guard rejects the version it pins: %s" % finished.stderr)


@pytest.mark.parametrize("where,pattern", [
    ("ci.yml", 'ruff==%s'),
    ("pyproject.toml", '"ruff==%s"'),
])
def test_the_declared_pins_are_not_matched_by_a_longer_version(where, pattern):
    """The same substring hole in the file comparison.

    `"ruff==0.16.3" in workflow` is satisfied by a workflow installing
    `ruff==0.16.30`, so the assertion that the three files pin one
    linter passes while two of them pin different ones.
    """
    version = _ruff_version()
    text = (ROOT / (".github/workflows/" + where if where.endswith(".yml")
                    else where)).read_text("utf-8")
    for near in _near_misses(version):
        assert pattern % near not in text, (
            "%s carries %r, which is not the pinned %s"
            % (where, pattern % near, version))
    assert re.search(re.escape(pattern % version) + r"(?![\w.])", text), (
        "%s does not pin ruff %s" % (where, version))


# -- what the pipeline actually runs -----------------------------------------

def _action_uses():
    """(workflow, line number, reference) for every action a job runs."""
    found = []
    for workflow in _workflows():
        for number, line in enumerate(
                workflow.read_text(encoding="utf-8").splitlines(), 1):
            bare = line.split("#", 1)[0].strip()
            match = re.match(r"^-?\s*uses:\s*(\S+)", bare)
            if match:
                found.append((workflow.name, number, match.group(1)))
    return found


def test_every_action_is_pinned_to_a_commit():
    """A tag and a branch are names somebody else can move.

    This project's release attaches signed provenance and publishes with
    a short-lived OIDC token, and every one of those steps is somebody
    else's code fetched by a name at the moment the tag is pushed.
    `@v5` is a tag the owner can repoint; `@release/v1` -- which is what
    received the publishing token -- is a *branch*, so it is whatever
    was pushed to it last. Pinning the rest and leaving that one is the
    version of this that looks done.

    A digest is the only reference that means the same bytes tomorrow.
    The readable version goes in a comment beside it, which is what a
    person updating this needs and what a resolver must not read.
    """
    unpinned = ["%s:%d %s" % row for row in _action_uses()
                if not re.search(r"@[0-9a-f]{40}$", row[2])]
    assert not unpinned, (
        "these run by a name its owner can move:\n  " + "\n  ".join(unpinned))


def test_each_pin_says_which_version_it_is():
    """A digest nobody can read is a digest nobody updates."""
    for workflow in _workflows():
        for line in workflow.read_text(encoding="utf-8").splitlines():
            if not re.search(r"uses:\s*\S+@[0-9a-f]{40}", line):
                continue
            assert re.search(r"#\s*v?\d+(\.\d+)*\s*$", line), (
                "%s pins a digest and does not say which version it is, so "
                "nobody can tell what updating it would change: %s"
                % (workflow.name, line.strip()))


# -- what the tools import, and what declares it ------------------------------

#: An unpacked sdist carries `PKG-INFO` at its root; a checkout does not
#: (it is written at build time and nothing tracks it). The gate below
#: reads sources `MANIFEST.in` deliberately does not ship, so it has a
#: subject only in a checkout -- and the way to say so has to be a fact
#: about the tree that is *present*, never the absence of the directory
#: being read. Absence is also what a deleted directory looks like, and
#: a gate that reads the two the same way goes quiet exactly where it is
#: needed. This is the shape the suite already fell for elsewhere.
FROM_AN_SDIST = (ROOT / "PKG-INFO").exists()

#: Import name -> the distribution that provides it, where they differ.
DISTRIBUTION_OF = {"fitz": "pymupdf"}

#: Import names that are this project's own.
OURS_TO_IMPORT = {"aas_submodel_validate", "builders", "conftest"}

#: The standard-library modules these seven scripts import, listed rather
#: than asked of the interpreter. `sys.stdlib_module_names` arrived in 3.10,
#: so asking meant this gate could not run on the floor the front page
#: names -- and worse, the answer moves with the version, because a module
#: that is the standard library's on one release was a dependency on the
#: one before it. Asking gave the same tree different verdicts on different
#: rows; a list gives one verdict everywhere. It is short because the
#: scripts are small, and a name arriving here that is not in the standard
#: library has to be written into a set that says it is.
STANDARD_LIBRARY = {
    "argparse", "hashlib", "html", "importlib", "json", "os", "re", "sys",
    "warnings",
}


def _third_party_imports(where):
    """Every top-level module `where`'s Python files import that is neither
    this project's nor the standard library's."""
    found = {}
    for path in sorted(Path(where).rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            #: A dependency fetched by name at runtime is still a
            #: dependency. Measured: without this, a file that reached
            #: `openpyxl` through `importlib.import_module` satisfied the
            #: gate while declaring nothing. Only a literal is readable
            #: here -- a name assembled at runtime is not something this
            #: file can see, and saying so is better than implying the
            #: reading is complete.
            elif (isinstance(node, ast.Call)
                    and _called_name(node.func) in ("import_module",
                                                    "__import__")
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                names = [node.args[0].value.split(".")[0]]
            for name in names:
                if name in STANDARD_LIBRARY or name in OURS_TO_IMPORT:
                    continue
                #: A module sitting beside the file that imports it is
                #: not a package anybody installs. `_common` is one, and
                #: reading it as a dependency made the gate demand that
                #: pyproject declare this directory's own helper.
                if ((path.parent / (name + ".py")).exists()
                        or (path.parent / name / "__init__.py").exists()):
                    continue
                found.setdefault(DISTRIBUTION_OF.get(name, name), set()).add(
                    str(path))
    return found


def test_every_reader_the_battery_tools_import_is_declared():
    """A dependency named only inside a CI step is a dependency nobody
    installing this project can discover.

    `openpyxl` and `pymupdf` were installed by one unpinned `pip
    install` line in two workflows and declared in no metadata at all,
    so the gate that reads the battery indexes passes locally by
    skipping -- and a contributor who wants to run it has to read the
    workflow to find out what to install. Declared as an extra, the
    answer is `pip install -e ".[battery]"` and the pin is in one place.
    """
    pyproject = (ROOT / "pyproject.toml").read_text("utf-8")
    tools = ROOT / "data" / "battery-passport" / "tools"
    if FROM_AN_SDIST and not tools.is_dir():
        pytest.skip("no data/battery-passport here (unpacked sdist); "
                    "MANIFEST.in does not ship it")
    assert tools.is_dir(), (
        "data/battery-passport/tools is missing from a tree that is not an "
        "unpacked sdist; the gate reads it, so its absence is a failure and "
        "not a reason to stay quiet")
    imported = _third_party_imports(tools)
    assert imported, "no third-party imports found; the probe is looking nowhere"
    for distribution, files in sorted(imported.items()):
        assert re.search(r'"%s[>=<~!\[]' % re.escape(distribution), pyproject), (
            "%s is imported by %s and declared in no dependency group"
            % (distribution, ", ".join(sorted(
                Path(f).name for f in files))))


def test_the_workflows_install_the_readers_by_the_name_that_declares_them():
    """Two files listing the same two packages by hand is the drift the
    extra exists to remove; the pin has to be the one metadata states."""
    for name in ("ci.yml", "release.yml"):
        text = (ROOT / ".github" / "workflows" / name).read_text("utf-8")
        assert "pip install openpyxl pymupdf" not in text, (
            "%s installs the readers by hand, so their versions are "
            "whatever resolved that morning" % name)
# -- gates the floor cannot run -----------------------------------------------

#: Tests allowed to skip because the interpreter running them is too old.
#: Empty, and it needs to stay empty. A test gated on the version does not
#: run on the floor this project supports, so the suite on the floor
#: answers less than the suite above it and reports the difference as a
#: number. One did: the gate reading what the battery tools import asked
#: `sys.stdlib_module_names`, which arrived in 3.10, and skipped below it.
#: It therefore never ran on the floor row, nor on a maintainer's 3.9 --
#: `make check` said "1 skipped" and nothing said which, or that what had
#: gone quiet was a gate. An entry here is a deliberate exemption and needs
#: justifying beside the CI row that does run the test.
VERSION_GATED_SKIPS: dict = {}

#: What a skip's own source looks like when the interpreter version is what
#: decided it. A text rule, like the rest of this file: it catches the shape
#: that appeared here and does not claim to catch a version test written
#: without naming a version.
_DECIDED_BY_VERSION = re.compile(
    r"version_info|stdlib_module_names|Python \d+\.\d+|\b\d+\.\d+\+")


def _called_name(func):
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _skip_calls():
    """Every `skip(...)` and `skipif(...)` the suite makes, as
    (identifier, source).

    The identifier names the file and the call's own text, never its line
    number. An exemption keyed to a line moves to a different skip the
    first time somebody inserts a paragraph above it -- measured here: an
    entry written for one skip stopped covering it, and had a second skip
    been sitting on that line it would have been excused instead, with
    nobody having justified it. Keying on the text costs the opposite
    thing, which is the one worth paying: edit the skip and the exemption
    stops applying, so it has to be argued again. Two textually identical
    skips share an identifier, and one entry excuses both -- they say the
    same thing, so the same justification answers for them.
    """
    for path in sorted((ROOT / "tests").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(text, str(path))):
            if not (isinstance(node, ast.Call)
                    and _called_name(node.func) in ("skip", "skipif")):
                continue
            segment = ast.get_source_segment(text, node)
            assert segment is not None, (
                "%s:%d: could not read the source of this skip, so nothing "
                "below can say what decided it" % (path.name, node.lineno))
            yield "%s  %s" % (path.name, " ".join(segment.split())), segment


def test_no_gate_goes_quiet_because_the_python_is_older():
    """A skip decided by the interpreter version is a gate the floor never
    runs.

    Every other skip in this suite is about what the tree has -- no
    `data/`, no `git`, no POSIX shell -- and those answer the same way for
    everyone standing in the same place. A version skip does not: it makes
    the floor row and the newest row check different things, while the
    summary line says only how many. The remedy is to decide the question
    without asking the interpreter, so the gate runs everywhere, rather
    than to let it run in eight rows out of ten and stay silent in the two
    that matter most for a project whose front page names 3.9.
    """
    gated = sorted({identifier for identifier, source in _skip_calls()
                    if _DECIDED_BY_VERSION.search(source)
                    and identifier not in VERSION_GATED_SKIPS})
    assert not gated, (
        "these skip on the interpreter version, so they do not run on the "
        "floor this project supports. Each line below is the key an entry "
        "in VERSION_GATED_SKIPS would need:\n  " + "\n  ".join(gated))

# -- what the signature covers ------------------------------------------------


def _dist_at_release():
    """`(what this project builds, what it only carries)`, as the release
    workflow leaves them in `dist/` before signing."""
    version = re.search(r'(?m)^version = "([^"]+)"',
                        (ROOT / "pyproject.toml").read_text("utf-8")).group(1)
    ours = ("dist/aas_submodel_validate-%s-py3-none-any.whl" % version,
            "dist/aas_submodel_validate-%s.tar.gz" % version,
            "dist/smtv.pyz")
    #: The dependency wheel the workflow downloads so the offline route
    #: has something to install from. A representative name rather than a
    #: pin: what matters is that a wheel this project did not build sits
    #: in the same directory as the ones it did.
    theirs = ("dist/aas_core3_0-1.1.4-py3-none-any.whl",)
    return ours, theirs


def _subject_paths():
    """The paths the signing step offers for attestation."""
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text("utf-8")
    block = re.search(r"\n(\s+)subject-path: \|\n((?:\1  .*\n)+)", text)
    assert block is not None, "release.yml offers no subject-path to attest"
    return [line.strip() for line in block.group(2).splitlines() if line.strip()]


def test_the_signature_covers_what_this_project_built_and_nothing_else():
    """A build attestation says these bytes came out of this workflow.
    Saying it about a file the workflow downloaded is a claim this
    project has no standing to make, and it is one directory listing
    away: the dependency wheel for the offline route is written into
    `dist/` beside the three built here, so `dist/*.whl` would sign it.

    The patterns are checked by applying them, not by reading them. Two
    of the three contain a `*` -- they are anchored to this project's own
    distribution name rather than spelled out -- so a rule about glob
    characters would fail on the correct file and pass on
    `dist/aas_core3_0-*.whl`. What the release has to be true of is which
    names come out matched, and that is a question with an answer.

    Measured on 0.1.3: the three built here verify against this
    repository, and `gh attestation verify` answers 404 for the
    dependency wheel, which is the shape this asserts.
    """
    ours, theirs = _dist_at_release()
    patterns = _subject_paths()
    matched = tuple(name for name in ours + theirs
                    if any(fnmatch.fnmatch(name, p) for p in patterns))
    assert matched == ours, (
        "the signing step attests %s; it must attest exactly what this "
        "workflow built:\n  offered: %s" % (list(matched), patterns))
# -- what the release directory is allowed to hold -----------------------------


def _dist_manifest_script():
    """The step that says what `dist/` must hold, lifted so it can run
    here.

    Both the checksum file and the Release are made from `dist/*`: the
    step above sums whatever is in the directory, and the one that
    attaches the assets passes the same glob. So a file that arrives
    there by accident is checksummed and published, and nothing said
    what belonged. This runs the step's own script against directories
    built here, rather than reading it, for the reason the harness
    measured: a gate read is a gate assumed.
    """
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text("utf-8")
    found = re.search(
        r"- name: dist holds exactly what this release publishes\n"
        r"(?:\s+#.*\n)*"
        r"\s+run: \|\n((?:[ ]{10}[^\n]*\n|\n)+)", text)
    assert found is not None, (
        "release.yml has no step saying what dist/ must hold, so `dist/*` "
        "is whatever the build left there")
    return "".join(line[10:] if line.startswith(" " * 10) else line
                   for line in found.group(1).splitlines(keepends=True))


def _dist(tmp_path, names, records=None, sums_lists_itself=False):
    """A `dist/` built by hand, and the exit code the step gives it."""
    import subprocess
    root = tmp_path
    dist = root / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    for name in names:
        (dist / name).write_bytes(b"x")
    if records is not None:
        lines = ["%064d  %s" % (0, n) for n in records]
        if sums_lists_itself:
            lines.append("%064d  SHA256SUMS" % 0)
        (dist / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    script = root / "step.sh"
    script.write_text(_dist_manifest_script())
    return subprocess.run(["sh", str(script)], cwd=str(root),
                          capture_output=True, text=True)


BUILT = ["aas_submodel_validate-0.1.3-py3-none-any.whl",
         "aas_submodel_validate-0.1.3.tar.gz",
         "smtv.pyz",
         "aas_core3_0-1.1.4-py3-none-any.whl"]


def test_the_release_directory_holds_what_the_release_publishes(tmp_path):
    """The five that go out, and nothing else."""
    done = _dist(tmp_path, BUILT + ["SHA256SUMS"], records=BUILT)
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_file_nobody_built_does_not_ride_out_with_them(tmp_path):
    """`dist/*` would checksum and publish it."""
    done = _dist(tmp_path, BUILT + ["notes.md", "SHA256SUMS"], records=BUILT)
    assert done.returncode != 0
    assert "6" in done.stdout, done.stdout


def test_an_empty_checksum_file_is_not_a_passing_one(tmp_path):
    """`sha256sum -c` on a file with no records exits 0 where it is not
    GNU's, so a checksum file that vouches for nothing reads as one that
    vouches for everything. The count is asserted rather than assumed."""
    done = _dist(tmp_path, BUILT + ["SHA256SUMS"], records=[])
    assert done.returncode != 0
    assert "0 record" in done.stdout or "not 4" in done.stdout, done.stdout


def test_a_missing_artifact_is_caught_before_it_is_published(tmp_path):
    """One of the four absent means the offline route ships incomplete."""
    done = _dist(tmp_path, BUILT[:-1] + ["SHA256SUMS"], records=BUILT[:-1])
    assert done.returncode != 0


def test_the_checksum_file_does_not_vouch_for_itself(tmp_path):
    """A record for SHA256SUMS inside SHA256SUMS can never verify."""
    done = _dist(tmp_path, BUILT + ["SHA256SUMS"], records=BUILT[:-1],
                 sums_lists_itself=True)
    assert done.returncode != 0
def test_pypi_gets_the_two_files_that_belong_to_this_project(tmp_path):
    """The index and the Release publish different sets, and only one of
    them is a package index.

    `dist/` holds five things by the time the Release is made: the two
    this project uploads, the single file, the dependency wheel carried
    for the offline route, and the checksums. The publisher uploads a
    *directory*, so pointing it at `dist` would offer PyPI a wheel
    belonging to another project and a file that is not a distribution
    at all. It points at one built for the purpose instead -- and
    nothing said so until here.
    """
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text("utf-8")
    directory = re.search(r"packages-dir:\s*(\S+)", text)
    assert directory is not None, "release.yml names no packages-dir"
    assert directory.group(1) != "dist", (
        "the publisher would offer PyPI everything in dist, including a "
        "wheel this project did not build")

    #: Build the named directory the way the workflow does, from a `dist`
    #: holding all five, and see what ends up in it.
    import subprocess
    copy = re.search(r"run: (mkdir \S+ && cp [^\n]+)", text)
    assert copy is not None, "release.yml has no step filling that directory"
    dist = tmp_path / "dist"
    dist.mkdir()
    for name in BUILT + ["SHA256SUMS"]:
        (dist / name).write_bytes(b"x")
    done = subprocess.run(["sh", "-c", copy.group(1)], cwd=str(tmp_path),
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    uploaded = sorted(q.name for q in (tmp_path / directory.group(1)).iterdir())
    assert uploaded == sorted(n for n in BUILT
                              if n.startswith("aas_submodel_validate-")), (
        "PyPI would be offered %s" % uploaded)
# -- who is allowed to do what, and where ------------------------------------


def _jobs(path):
    """Each job in a workflow, as name -> its block."""
    text = path.read_text(encoding="utf-8")
    body = text.split("\njobs:\n", 1)[1]
    starts = [(m.start(), m.group(1))
              for m in re.finditer(r"(?m)^  ([a-z][\w-]*):$", body)]
    jobs = {}
    for index, (offset, name) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(body)
        jobs[name] = body[offset:end]
    return jobs


def _release_jobs():
    return _jobs(ROOT / ".github" / "workflows" / "release.yml")


def _granted(block):
    """The `permissions:` a block declares, as name -> level."""
    found = re.search(r"(?m)^(\s+)permissions:\n((?:\1  .*\n|\s*#.*\n|\n)+)",
                      block)
    if found is None:
        return None
    return dict(re.findall(r"(?m)^\s+([a-z-]+):\s*(\S+)\s*$", found.group(2)))


def test_the_workflow_floor_is_read_and_a_job_asks_for_more_itself():
    """A token minted at the top of a file is one every job holds,
    including the ones that only read. The floor here is `contents:
    read`, and the two lifts above it are declared by the job that needs
    them -- which is also where a reader looks to ask why."""
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text("utf-8")
    floor = re.search(r"(?m)^permissions:\n((?:  .*\n)+)", text)
    assert floor is not None, "release.yml declares no floor, so it inherits one"
    assert dict(re.findall(r"(?m)^\s+([a-z-]+):\s*(\S+)\s*$",
                           floor.group(1))) == {"contents": "read"}, (
        "the floor is not `contents: read`: %r" % floor.group(1))


def test_only_the_job_that_signs_and_the_one_that_publishes_mint_a_token():
    """`id-token: write` is the credential that speaks for this
    repository to a service that has never seen it. Two steps need it --
    the attestation and the upload to PyPI -- and a third job holding it
    is a third place it can leak from."""
    minting = sorted(name for name, block in _release_jobs().items()
                     if (_granted(block) or {}).get("id-token") == "write")
    assert minting == ["build", "publish"], minting


def test_the_publishing_job_is_allowed_to_do_one_thing():
    """It uploads. It does not need to write to this repository, read
    what CI concluded, or attest anything -- those happened before it
    ran, in a job that cannot upload."""
    granted = _granted(_release_jobs()["publish"])
    assert granted == {"id-token": "write"}, granted


def test_the_publishing_job_does_not_rebuild_what_it_uploads():
    """The bytes on the index have to be the bytes the Release carries
    and the attestation covers. A job that checked the source out and
    built again would produce its own, and every hash published beside
    them would be a hash of something else."""
    block = _release_jobs()["publish"]
    for forbidden in ("actions/checkout", "python -m build", "pip install -e",
                      "make check"):
        assert forbidden not in block, (
            "the publishing job runs `%s`, so what it uploads need not be "
            "what was signed" % forbidden)
# -- the release path, rehearsed ---------------------------------------------

#: The steps `release.yml` runs between building and signing. Each one is
#: rehearsed on every push, because a tag is the worst place to learn that
#: one of them is broken -- the tag exists, the version is spent, and the
#: fix needs a new one.
REHEARSED = ("build the wheel and the sdist",
             "no distribution carries what it must not",
             "the dependency travels too, or the offline route is a lie",
             "build the single file twice; the hashes must match",
             "the package index will accept the description",
             "one checksum file beside them",
             "dist holds exactly what this release publishes")


def _step_bodies(block):
    """Each named step in one job's block, as name -> the command it runs.

    Asked of a job and never of a whole file. Two jobs may legitimately
    run a step of the same name -- `twine check` is rehearsed here and
    also runs against the wheel built for the install test -- and a
    reading that collapsed them would compare one job's paragraph while
    claiming something about another's. It did: the first version of this
    took the file, kept the first of each name, and a step deleted from
    the rehearsal went unnoticed because a different job still had one
    spelled the same way.
    """
    bodies = {}
    for found in re.finditer(
            r"      - name: ([^\n]+)\n(?:\s+#[^\n]*\n)*"
            r"        run: (\|\n(?:(?:[ ]{10}[^\n]*)?\n)+|[^\n]+\n)", block):
        name = found.group(1).strip()
        assert name not in bodies, (
            "one job runs two steps named %r, so neither can be pointed at"
            % name)
        bodies[name] = found.group(2).rstrip("\n")
    return bodies


def test_the_release_path_is_rehearsed_on_every_push():
    """A copy that drifts from what it rehearses is worse than no
    rehearsal: it goes green while the thing it stands for changes.

    So the comparison is the commands themselves, not the step names. If
    a step here gains a line, the rehearsal fails until it gains the same
    one.
    """
    release = _step_bodies(_release_jobs()["build"])
    rehearsal = _step_bodies(
        _jobs(ROOT / ".github" / "workflows" / "ci.yml")["release-path"])
    missing = [name for name in REHEARSED if name not in rehearsal]
    assert not missing, (
        "the release path runs these and nothing rehearses them:\n  "
        + "\n  ".join(missing))
    drifted = [name for name in REHEARSED
               if release.get(name) != rehearsal.get(name)]
    assert not drifted, (
        "these run different commands in the release than in its "
        "rehearsal:\n  " + "\n  ".join(drifted))


def test_the_rehearsal_holds_no_credential_and_reads_no_tag():
    """It is a rehearsal because it cannot publish. A job that could
    would be the release, running on every push."""
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")
    for forbidden in ("id-token: write", "attestations: write",
                      "contents: write", "GITHUB_REF_NAME",
                      "pypa/gh-action-pypi-publish", "attest-build-provenance"):
        assert forbidden not in text, (
            "the rehearsal names `%s`, which makes it something other than "
            "a rehearsal" % forbidden)
