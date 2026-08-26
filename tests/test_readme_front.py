"""Every claim on the front of a document here is re-derivable, or it rots.

The console sample is regenerated here and compared byte-for-byte; the
rule counts are counted, not trusted. A README that says 56 while the
registry says 57 is the kind of small lie that outlives its excuse.
"""
from __future__ import annotations

from pathlib import Path

from aas_submodel_validate import (
    rules,  # noqa: F401 - importing registers
    runner,
)
from aas_submodel_validate.registry import all_rules
from aas_submodel_validate.report import render
from aas_submodel_validate.rules import dbp_tables, hd_tables, td_tables
from builders import env_json

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text("utf-8")
CHANGELOG = (ROOT / "CHANGELOG.md").read_text("utf-8")


def test_the_rule_counts_are_the_registrys():
    generated = len(hd_tables.ROWS) + len(td_tables.ROWS) + len(dbp_tables.ROWS)
    assert len(all_rules()) == 123
    assert (len(hd_tables.ROWS), len(td_tables.ROWS), len(dbp_tables.ROWS)) == (38, 26, 22)
    assert "123 rules" in README
    assert "%d generated" % generated in README
    # Each template's own row count is on the front page too, in the
    # table: a total alone would let one template's rows vanish into
    # another's without the number moving.
    assert "| 38 |" in README
    assert "| 26 |" in README
    assert "| 22 |" in README


def test_the_generator_counts_the_rows_it_warns_about():
    """The generator's docstring warns that a hand-copied row count goes
    stale, and was one: it said sixty-four from when two tables existed and
    went on saying it through a third. The warning is worth keeping and the
    number belongs where the others are."""
    generated = len(hd_tables.ROWS) + len(td_tables.ROWS) + len(dbp_tables.ROWS)
    source = (ROOT / "tools" / "extract_smt_rules.py").read_text("utf-8")
    assert "hand-copying %d rows" % generated in source


def test_the_console_sample_is_what_the_tool_prints(tmp_path, monkeypatch):
    (tmp_path / "machine-docs.json").write_bytes(env_json("urn:somecompany:docs"))
    monkeypatch.chdir(tmp_path)
    sample = render(runner.run("machine-docs.json"))
    assert "```text\n%s\n```" % sample in README, \
        "the README's console sample went stale; regenerate it"


def test_the_changelog_counts_what_it_would_ship():
    """The entry is still unreleased, so its numbers describe the present
    and have to move with it. Once a version is tagged its entry is
    history and must not be edited -- which is why this looks only at the
    unreleased one."""
    _, _, entries = CHANGELOG.partition("\n## ")     # past the file's title
    unreleased, _, _ = entries.partition("\n## ")     # the newest entry alone
    assert "unreleased" in unreleased.lower(), "the first entry is no longer a draft"
    generated = len(hd_tables.ROWS) + len(td_tables.ROWS) + len(dbp_tables.ROWS)
    assert "%d rules" % len(all_rules()) in unreleased
    assert "%d are" % generated in unreleased or "%d generated" % generated in unreleased
