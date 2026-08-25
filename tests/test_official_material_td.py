"""What this tool says about IDTA's own 02003 sample, pinned as it is.

The verdict on the official material is a regression surface: it may
only change when somebody means it to. Nothing here is repaired, and
nothing is asserted to be clean that is not.

02003 is the more interesting of the two corpora, because upstream
published the sample twice — beside the 2.0 template and again beside
2.0.1 — and the pair is a record of what IDTA itself considered wrong.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from aas_submodel_validate import runner

CORPUS = Path(__file__).resolve().parent / "corpus" / "idta" / "02003"
FIRST = CORPUS / "sample-2.0.json"
FIRST_AASX = CORPUS / "sample-2.0.aasx"
REPAIRED = CORPUS / "sample-2.0.1.aasx"


def _split(path):
    report = runner.run(path)
    meta = [f for f in report.findings if f.rule.kind == "meta"]
    own = [f for f in report.findings if f.rule.kind != "meta"]
    return report, meta, own


@pytest.mark.parametrize("path", (FIRST, FIRST_AASX, REPAIRED))
def test_no_rule_of_ours_fires_on_the_official_sample(path):
    """Both editions satisfy every template rule, generated and hand
    written, and the presence rule finds what it is looking for. That is
    the claim worth pinning: this tool does not call IDTA's own sample a
    non-conformant Technical Data submodel."""
    _report, _meta, own = _split(path)
    assert own == [], sorted(f.id for f in own)


def test_the_first_edition_carries_sixty_metamodel_findings():
    """Sixty, and they are the metamodel's rather than ours: empty
    values, idShorts outside the permitted character set (`IEC CDD` has
    a space in it), list children carrying an idShort the metamodel
    forbids. Relayed, never restated."""
    _report, meta, _own = _split(FIRST)
    assert len(meta) == 60


def test_both_serialisations_of_the_first_edition_agree():
    """The same sample as JSON and inside an AASX. A reader that answered
    differently would be reporting on its own parsing rather than on the
    submodel."""
    _r1, meta_json, own_json = _split(FIRST)
    _r2, meta_aasx, own_aasx = _split(FIRST_AASX)
    assert len(meta_json) == len(meta_aasx)
    assert [f.id for f in own_json] == [f.id for f in own_aasx]


def test_upstream_repaired_fifty_one_of_them_itself():
    """2.0.1 is the same sample with the empty values filled and the
    spaces taken out of the idShorts. Nine findings remain, all of them
    list children carrying an idShort or a description repeating a
    language -- which is why the 02004 corpus is pinned defects and all
    rather than repaired: upstream repairs on its own schedule, and a
    validator that quietly tracked it would stop being a witness."""
    _report, meta, _own = _split(REPAIRED)
    assert len(meta) == 9
