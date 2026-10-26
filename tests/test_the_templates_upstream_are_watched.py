"""Whether the vendored templates have moved upstream, asked and answered.

`tools/vendor_template.py` takes every vendored file from one commit of
admin-shell-io/submodel-templates, and the pin moves only when somebody
edits it -- so on its own this repository can say that the bytes here are
the bytes taken then, and nothing about what upstream has published since.
That question is upstream's to answer, and `tools/upstream_moved.py` asks
it from `.github/workflows/upstream.yml`. These tests hold its answers to
fixed responses, with no network, and the workflow to asking.
"""
from __future__ import annotations

import re
import sys
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "tools" / "vendor_template.py").exists():
    pytest.skip("no tools/ here (installed package, not a checkout)",
                allow_module_level=True)
sys.path.insert(0, str(ROOT / "tools"))

import upstream_moved  # noqa: E402
import vendor_template  # noqa: E402

PIN = vendor_template.COMMIT
HEAD = "b" * 40
WORKFLOW = ROOT / ".github" / "workflows" / "upstream.yml"


def _upstream(monkeypatch, head, then, now, trees=None):
    """Upstream as fixed answers: its default branch at `head`, the folders
    listed at the pin (`then`) and at the head (`now`) as path -> tree, and
    the files of a tree (`trees`, tree -> path -> blob). Anything else asked
    is a question upstream does not answer."""
    listed = {PIN: then, head: now}
    asked = []

    def api(path):
        asked.append(path)
        if path == "":
            return {"default_branch": "main"}
        if path == "commits/main":
            return {"sha": head}
        where, _, query = path.partition("?")
        ref = urllib.parse.parse_qs(query).get("ref", [None])[0]
        if where.startswith("contents/") and ref in listed:
            parent = urllib.parse.unquote(where[len("contents/"):])
            return [{"type": "dir", "path": folder, "sha": tree}
                    for folder, tree in listed[ref].items()
                    if folder.rsplit("/", 1)[0] == parent]
        if where.startswith("git/trees/") and query == "recursive=1":
            files = (trees or {}).get(where[len("git/trees/"):])
            if files is not None:
                return {"truncated": False,
                        "tree": [{"type": "blob", "path": name, "sha": blob}
                                 for name, blob in files.items()]}
        raise upstream_moved.Unanswered("nothing answers %s" % path)

    monkeypatch.setattr(upstream_moved, "api", api)
    return asked


def _same(tree="t"):
    return {folder: tree + str(n) for n, folder in enumerate(upstream_moved.watched())}


def test_every_vendored_file_comes_from_a_folder_that_is_watched():
    """The folders asked about are derived from the files vendored, each cut
    where the edition begins, so the folder holds every edition of that
    template: the one the pin chose and any published after it."""
    folders = upstream_moved.watched()
    for source in vendor_template.FILES.values():
        holding = [folder for folder in folders if source.startswith(folder + "/")]
        assert len(holding) == 1, (source, holding)
        rest = source[len(holding[0]) + 1:].split("/")
        assert rest[0].isdigit(), (
            "%s is cut at %r, not where its edition begins" % (source, holding[0]))
    assert all(any(source.startswith(folder + "/")
                   for source in vendor_template.FILES.values())
               for folder in folders), "a folder is watched that no vendored file comes from"


def test_at_the_pin_nothing_has_moved(monkeypatch, capsys):
    asked = _upstream(monkeypatch, PIN, {}, {})
    assert upstream_moved.main([]) == 0
    assert "is at the pin" in capsys.readouterr().out
    assert asked == ["", "commits/main"], "nothing needs comparing at the pin"


def test_upstream_that_moved_elsewhere_has_not_moved_what_is_vendored(monkeypatch, capsys):
    _upstream(monkeypatch, HEAD, _same(), _same())
    assert upstream_moved.main([]) == 0
    out = capsys.readouterr().out
    assert PIN[:12] in out and HEAD[:12] in out
    assert "none of the %d folders" % len(upstream_moved.watched()) in out


def test_a_new_edition_is_a_move_and_says_what_arrived(monkeypatch, capsys):
    folder = "published/Technical_Data"
    assert folder in upstream_moved.watched()
    now = dict(_same(), **{folder: "new"})
    old = _same()[folder]
    _upstream(monkeypatch, HEAD, _same(), now, trees={
        old: {"2/0/2/IDTA 02003_2-0-2_Template_TechnicalData.json": "a"},
        "new": {"2/0/2/IDTA 02003_2-0-2_Template_TechnicalData.json": "a",
                "2/0/3/IDTA 02003_2-0-3_Template_TechnicalData.json": "c"}})
    assert upstream_moved.main([]) == 1
    out = capsys.readouterr().out
    assert "1 of the %d folders" % len(upstream_moved.watched()) in out
    assert folder in out
    assert "added   2/0/3/IDTA 02003_2-0-3_Template_TechnicalData.json" in out
    assert "2/0/2" not in out.split(folder, 1)[1], "an unchanged file is not news"


def test_a_file_edited_in_place_is_a_move(monkeypatch, capsys):
    folder = "published/Contact Information"
    now = dict(_same(), **{folder: "new"})
    old = _same()[folder]
    name = "1/0/2/IDTA 02002-1-0-2_Template_ContactInformation.json"
    _upstream(monkeypatch, HEAD, _same(), now,
              trees={old: {name: "a"}, "new": {name: "b"}})
    assert upstream_moved.main([]) == 1
    assert "changed " + name in capsys.readouterr().out


def test_a_folder_gone_upstream_is_a_move(monkeypatch, capsys):
    folder = "published/Software Nameplate"
    now = {f: tree for f, tree in _same().items() if f != folder}
    _upstream(monkeypatch, HEAD, _same(), now)
    assert upstream_moved.main([]) == 1
    out = capsys.readouterr().out
    assert folder in out and "gone" in out


def test_a_long_list_of_changes_says_how_many_it_left_out(monkeypatch, capsys):
    folder = "published/Handover Documentation"
    now = dict(_same(), **{folder: "new"})
    old = _same()[folder]
    added = {"9/%d/x.json" % n: "a" for n in range(upstream_moved.SHOWN + 5)}
    _upstream(monkeypatch, HEAD, _same(), now, trees={old: {}, "new": added})
    assert upstream_moved.main([]) == 1
    assert "... and 5 more" in capsys.readouterr().out


def test_a_question_upstream_does_not_answer_is_neither_answer(monkeypatch, capsys):
    """No response is not "nothing moved", and it is not "something did"."""
    def api(path):
        raise upstream_moved.Unanswered("HTTP Error 503: Service Unavailable")

    monkeypatch.setattr(upstream_moved, "api", api)
    assert upstream_moved.main([]) == 2
    assert "upstream did not answer" in capsys.readouterr().out


def test_a_folder_the_pin_does_not_hold_is_not_called_unmoved(monkeypatch, capsys):
    folder = "published/Carbon Footprint"
    then = {f: tree for f, tree in _same().items() if f != folder}
    _upstream(monkeypatch, HEAD, then, _same())
    assert upstream_moved.main([]) == 2
    assert folder in capsys.readouterr().out


def test_a_listing_that_may_be_cut_short_is_not_read_as_whole(monkeypatch, capsys):
    """The contents API stops at a thousand entries, and a folder past that
    point would look gone."""
    def api(path):
        if path == "":
            return {"default_branch": "main"}
        if path == "commits/main":
            return {"sha": HEAD}
        return [{"type": "dir", "path": "published/%d" % n, "sha": "t"}
                for n in range(upstream_moved.LISTED)]

    monkeypatch.setattr(upstream_moved, "api", api)
    assert upstream_moved.main([]) == 2
    assert "cut short" in capsys.readouterr().out


def test_a_tree_too_large_to_list_is_not_read_as_whole(monkeypatch, capsys):
    folder = "published/Digital nameplate"
    now = dict(_same(), **{folder: "new"})
    _upstream(monkeypatch, HEAD, _same(), now)
    real = upstream_moved.api

    def api(path):
        if path.startswith("git/trees/"):
            return {"truncated": True, "tree": []}
        return real(path)

    monkeypatch.setattr(upstream_moved, "api", api)
    assert upstream_moved.main([]) == 2
    assert "too large" in capsys.readouterr().out


def test_a_failed_request_is_a_question_not_answered(monkeypatch):
    def refuse(request, timeout):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(upstream_moved.urllib.request, "urlopen", refuse)
    with pytest.raises(upstream_moved.Unanswered):
        upstream_moved.api("commits/main")


def test_the_token_is_sent_only_when_one_is_given(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert upstream_moved.request("").get_header("Authorization") is None
    monkeypatch.setenv("GH_TOKEN", "read-only")
    request = upstream_moved.request("commits/main")
    assert request.get_header("Authorization") == "Bearer read-only"
    assert request.full_url == ("https://api.github.com/repos/%s/commits/main"
                                % vendor_template.REPO)


def test_another_commit_can_be_asked_about_and_a_wrong_one_is_a_wrong_call(monkeypatch, capsys):
    other = "c" * 40
    _upstream(monkeypatch, other, {}, {})
    assert upstream_moved.main(["--pin", other]) == 0
    with pytest.raises(SystemExit) as stopped:
        upstream_moved.main(["--pin", "abc"])
    assert stopped.value.code == 64


def _on_block(text):
    match = re.search(r"(?ms)^on:\n(.*?)(?=^\S)", text)
    assert match, "the workflow has no `on:` block"
    return match.group(1)


def test_the_workflow_asks_every_week_and_when_the_pin_or_the_check_changes():
    text = WORKFLOW.read_text(encoding="utf-8")
    on = _on_block(text)
    assert "workflow_dispatch:" in on
    cron = re.search(r'(?m)^\s+- cron: "(\d+) (\d+) \* \* (\d)"\s+# (.+)$', on)
    assert cron, "the workflow asks on no schedule"
    minute, hour, day, said = cron.groups()
    days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    assert said == "%02d:%02d UTC every %s" % (int(hour), int(minute), days[int(day)]), (
        "the comment says %r and the schedule is %s %s * * %s" % (said, minute, hour, day))
    push = on.split("push:", 1)[1]
    for path in (".github/workflows/upstream.yml", "tools/upstream_moved.py",
                 "tools/vendor_template.py"):
        assert '"%s"' % path in push, "a push that changes %s does not ask" % path
    assert re.search(r"(?m)^permissions:\n  contents: read\n", text)
    assert not re.search(r"(?m)^\s+[a-z-]+: write\s*$", text), "the check asks for more than it reads"
    assert "secrets." not in text
    assert re.search(r"(?m)^\s+- run: python tools/upstream_moved.py$", text)
    assert "GH_TOKEN: ${{ github.token }}" in text


def test_a_moved_pin_names_the_steps_to_refresh_it(monkeypatch, capsys):
    """The moved answer ends with the steps that keep the pin, hashes,
    attribution, generated documents and changed verdicts together."""
    folder = "published/Technical_Data"
    now = {f: tree for f, tree in _same().items() if f != folder}
    _upstream(monkeypatch, HEAD, _same(), now)
    assert upstream_moved.main([]) == 1
    assert capsys.readouterr().out.splitlines()[-1] == (
        "Moving the pin is a decision, made in one commit that says why: edit COMMIT in "
        "tools/vendor_template.py, run it with --refresh (which writes every sha256sums.txt "
        "again), change the commit THIRD_PARTY.md names, write again what is generated "
        "from the templates -- make check names each generated file that no longer "
        "matches, docs/official-samples.md among them -- and name in the CHANGELOG every "
        "verdict the move changed.")
