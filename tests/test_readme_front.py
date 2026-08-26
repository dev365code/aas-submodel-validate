"""Every claim on the front of a document here is re-derivable, or it rots.

The console sample is regenerated here and compared byte-for-byte; the
rule counts are counted, not trusted. A README that says 56 while the
registry says 57 is the kind of small lie that outlives its excuse.
"""
from __future__ import annotations

import re
from pathlib import Path

from aas_submodel_validate import (
    rules,  # noqa: F401 - importing registers
    runner,
)
from aas_submodel_validate.registry import all_rules
from aas_submodel_validate.report import render
from aas_submodel_validate.rules import dbp_tables, hd_tables, td_tables
from builders import build_aasx, env_json

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


def _x_rules_drawn_by(paths):
    drawn = set()
    for path in paths:
        drawn |= {f.id for f in runner.run(path).findings if f.id.startswith("X")}
    return drawn


def _bare_documents(tmp_path):
    """Documents with no container around them, of every shape this reader
    reads and several it does not.

    Broken input alone is not a measurement. A rule that answers for bare
    files might do it on a *well-formed* one, or on one that carries a
    File element, or on bytes that happen to be a ZIP -- and a corpus of
    three broken files would go on reporting the same answer while the
    front page went stale. Each of these was chosen for something a
    packaging rule might key on."""
    written = []
    for name, data in (
            ("bad.json", b"{ not json"),
            ("bad.xml", b"<nope"),
            ("valid.json", env_json("urn:x")),
            ("valid.xml", b'<?xml version="1.0"?>'
                          b'<environment xmlns="https://admin-shell.io/aas/3/0">'
                          b"<submodels /></environment>"),
            ("submodel.json", b'{"modelType": "Submodel", "id": "urn:x"}'),
            ("empty.json", b""),
            # Bytes that are an archive, under a name that is not.
            ("zip.json", b"PK\x03\x04" + b"\x00" * 60),
    ):
        path = tmp_path / name
        path.write_bytes(data)
        written.append(path)
    return written


def _packaged_documents(tmp_path):
    """The positive control. Without it, "X1 never answers for a bare
    file" cannot be told from "this measurement cannot see X1 at all"."""
    broken_zip = tmp_path / "notazip.aasx"
    broken_zip.write_bytes(b"not a zip at all")
    return [
        broken_zip,
        build_aasx(tmp_path / "nochain.aasx", root_rels=False),
        build_aasx(tmp_path / "suppl.aasx", suppl_targets=("aasx/files/absent.png",)),
    ]


def _x_rules_a_bare_document_can_draw(tmp_path, monkeypatch):
    """Measured, not read off the code."""
    from aas_submodel_validate import container

    drawn = _x_rules_drawn_by(_bare_documents(tmp_path))
    monkeypatch.setattr(container, "MAX_PART_BYTES", 512)
    over = tmp_path / "big.json"
    over.write_bytes(b" " * 600)
    return drawn | _x_rules_drawn_by([over])


def test_the_readme_names_the_rules_that_are_about_packaging(tmp_path, monkeypatch):
    """The front page said five of the X rules were about the AASX/OPC
    package, then four. Both counted X3, which answers for a bare .json
    that will not parse, and the second also stopped counting X5 on the
    commit that gave X5 bare files to answer for.

    The sentence is derived here rather than compared to a remembered
    one: whichever ids a document with no container can draw are not the
    packaging rules, and the README says so in those words."""
    every_x = sorted(rule.id for rule in all_rules() if re.fullmatch(r"X\d+", rule.id))
    bare = _x_rules_a_bare_document_can_draw(tmp_path, monkeypatch)
    packaging = [rule_id for rule_id in every_x if rule_id not in bare]
    # The control, and the reason the sentence means anything: every id
    # the README calls a packaging rule is one this measurement has seen
    # fire, from a container. "Never drawn bare" is only interesting
    # about a rule the instrument can draw at all.
    packaged = _x_rules_drawn_by(_packaged_documents(tmp_path))
    assert set(packaging) <= packaged, (
        "the front page names %s as packaging rules and this measurement "
        "never saw them fire at all" % sorted(set(packaging) - packaged))
    # Whitespace-normalised: the README wraps at seventy-two columns and a
    # sentence straddles the break wherever it happens to fall. What is
    # pinned is what it says.
    assert "%s and %s are about the AASX/OPC package" % (
        ", ".join(packaging[:-1]), packaging[-1]) in " ".join(README.split())


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
    # The bounds are on this page too, and were the only prose numbers on
    # it with nothing watching them: SECURITY.md derives its copy and this
    # one would have gone quietly stale beside it.
    from aas_submodel_validate import container
    assert ("one document at %d MiB, a container's parts at %d MiB each and %d MiB"
            % (container.MAX_PART_BYTES // 1024 ** 2,
               container.MAX_PART_BYTES // 1024 ** 2,
               container.MAX_TOTAL_PART_BYTES // 1024 ** 2)) in " ".join(unreleased.split())
