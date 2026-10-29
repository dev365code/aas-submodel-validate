"""The capability generator accepts two names for its own data folder."""
from __future__ import annotations

import importlib.util
import os
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_capability_data_accepts_two_spellings_of_one_directory(tmp_path):
    """NFC and NFD may name the same folder: the data file belongs there
    even when its argument spells that folder differently from ROOT."""
    spec = importlib.util.spec_from_file_location("capability_card", ROOT / "tools/capabilities_svg.py")
    card = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(card)
    composed = tmp_path / unicodedata.normalize("NFC", "café")
    decomposed = tmp_path / unicodedata.normalize("NFD", "café")
    composed.mkdir()
    (composed / "docs").mkdir()
    if not decomposed.exists():
        try:
            decomposed.symlink_to(composed, target_is_directory=True)
        except OSError as error:
            pytest.skip("two names for one directory need a symbolic link here: %s" % error)
    assert str(composed) != str(decomposed)
    assert os.path.samefile(composed / "docs", decomposed / "docs")
    data = (ROOT / "docs/capabilities.json").read_bytes()
    (composed / "docs/capabilities.json").write_bytes(data)
    card.ROOT = str(decomposed)
    assert card.main(["capabilities_svg.py", str(composed / "docs/capabilities.json")]) == 0
    expected_svg = (ROOT / "docs/capabilities.svg").read_bytes()
    expected_md = (ROOT / "docs/capabilities.md").read_bytes()
    assert (composed / "docs/capabilities.svg").read_bytes() == expected_svg
    assert (composed / "docs/capabilities.md").read_bytes() == expected_md
