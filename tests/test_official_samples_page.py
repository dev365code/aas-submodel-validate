"""docs/official-samples.md: every official sample in this repository, and
what this tool says about it.

The page is generated (`tools/gen_official_samples.py`), and `make check`
and CI run its `--check`, which fails when the committed page and a run
disagree. These tests ask what `--check` cannot: that the page covers
every sample vendored here and nothing that is not a sample, and that
what it prints of one sample is what the tool prints.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import gen_official_samples  # noqa: E402
import vendor_template  # noqa: E402

PAGE = ROOT / "docs" / "official-samples.md"


def test_the_committed_page_is_what_a_run_writes():
    assert PAGE.read_text("utf-8") == gen_official_samples.render()


def test_every_official_sample_here_is_on_the_page_and_no_template_is():
    """Read off the vendoring table, not listed again here, and not through
    the generator's own idea of a sample: everything vendored that is not a
    template's JSON is a sample, and a sample vendored tomorrow is on the
    page or this fails."""
    page = PAGE.read_text("utf-8")
    templates = [rel for rel in vendor_template.FILES if rel.endswith("/template.json")]
    samples = [rel for rel in vendor_template.FILES if rel not in templates]
    assert samples and templates
    assert [rel for rel in vendor_template.FILES if gen_official_samples.is_sample(rel)] \
        == samples
    for rel in samples:
        assert "`%s`" % rel in page, rel
        assert vendor_template.FILES[rel] in page, rel
    for rel in templates:
        assert rel not in page, rel


def test_what_the_page_says_of_a_refused_sample_is_what_the_tool_says():
    from aas_submodel_validate import runner
    rel = "tests/corpus/idta/02003/sample-2.0.1-for-aas-3.1.aasx"
    report = runner.run(ROOT / rel)
    section = PAGE.read_text("utf-8").split("## `%s`" % rel, 1)[1].split("\n## ", 1)[0]
    assert "exit 2" in section and "refused, not judged" in section, section
    [finding] = report.findings
    assert "| %s |" % finding.id in section, section
    assert report.as_dict()["findings"][0]["severity"] in section


def test_every_exit_code_on_the_page_is_the_command_line_s(capsys):
    """The exit code is the generator's own reckoning, and every sample
    here either passes or is refused -- none is judged with an error -- so
    a reckoning that swapped 0 and 1 wrote a page `--check` accepts and
    the test above cannot see into. Each code is asked of the command
    line itself, the thing the page says it reports."""
    from aas_submodel_validate.cli import main
    rows = {line.split("`")[1]: line for line in PAGE.read_text("utf-8").splitlines()
            if line.startswith("| `")}
    samples = [rel for rel in vendor_template.FILES if gen_official_samples.is_sample(rel)]
    assert sorted(rows) == sorted(samples)
    for rel in samples:
        code = main(["-q", str(ROOT / rel)])
        capsys.readouterr()
        assert "| exit %d -- " % code in rows[rel], (rel, code, rows[rel])


def test_the_front_page_links_the_page():
    readme = (ROOT / "README.md").read_text("utf-8")
    assert "docs/official-samples.md" in readme
