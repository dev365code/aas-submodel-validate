"""Every claim on the README's front is re-derivable, or it rots.

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
from aas_submodel_validate.rules import hd_tables
from builders import env_json

README = (Path(__file__).resolve().parents[1] / "README.md").read_text("utf-8")


def test_the_rule_counts_are_the_registrys():
    assert len(all_rules()) == 57
    assert len(hd_tables.ROWS) == 38
    assert "57 rules" in README
    assert "38 generated" in README


def test_the_console_sample_is_what_the_tool_prints(tmp_path, monkeypatch):
    (tmp_path / "machine-docs.json").write_bytes(env_json("urn:somecompany:docs"))
    monkeypatch.chdir(tmp_path)
    sample = render(runner.run("machine-docs.json"))
    assert "```text\n%s\n```" % sample in README, \
        "the README's console sample went stale; regenerate it"
