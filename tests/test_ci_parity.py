"""`make check` and CI must run the same commands.

The sibling repositories learned this the loud way: a gate that exists in
one place and not the other fails quietly in the dangerous direction — a
gate only in the Makefile means CI is not checking something somebody
believes it checks, and nothing says so. This is a text comparison, not a
build system, on purpose: something that understood both files would be a
third thing to keep in step.
"""
from __future__ import annotations

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

#: Import name -> the distribution that provides it, where they differ.
DISTRIBUTION_OF = {"fitz": "pymupdf"}

#: Import names that are this project, its declared runtime dependency,
#: or the standard library's -- asked of the interpreter rather than
#: listed, except for the two that are ours by construction.
OURS_TO_IMPORT = {"aas_submodel_validate", "builders", "conftest"}


def _third_party_imports(where):
    """Every top-level module `where`'s Python files import."""
    import ast
    import sys as _sys

    #: `sys.stdlib_module_names` arrived in 3.10. Below that the set is
    #: empty and every `import argparse` reads as an undeclared
    #: dependency -- the same gate answering differently depending on
    #: which interpreter runs the suite, which is not a gate. The
    #: callers skip rather than guess; nine of CI's ten rows answer it.
    standard = getattr(_sys, "stdlib_module_names", None)
    if standard is None:
        return None
    found = {}
    for path in sorted(Path(where).rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                if name in standard or name in OURS_TO_IMPORT:
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
    imported = _third_party_imports(ROOT / "data" / "battery-passport" / "tools")
    if imported is None:
        pytest.skip("needs sys.stdlib_module_names (Python 3.10+) to tell a "
                    "standard-library import from a dependency")
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
