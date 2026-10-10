"""The extractor gate parses scripts without needing the default bytecode cache."""
from __future__ import annotations

import sys

import pytest
from tools import battery_data_check


@pytest.mark.parametrize("source, expected", [("VALUE = 1\n", 0), ("VALUE = (\n", 1)])
def test_extractors_are_checked_when_the_default_bytecode_cache_is_unwritable(
        tmp_path, monkeypatch, capsys, source, expected):
    data = tmp_path / "battery-passport"
    scripts = data / "tools"
    scripts.mkdir(parents=True)
    (scripts / "battery_gate_reader.py").write_text(source, encoding="utf-8")
    blocked = tmp_path / "default-cache"
    blocked.write_text("a file cannot hold a bytecode directory", encoding="utf-8")
    monkeypatch.setattr(sys, "pycache_prefix", str(blocked))
    monkeypatch.syspath_prepend(str(scripts))
    monkeypatch.delitem(sys.modules, "battery_gate_reader", raising=False)
    monkeypatch.setattr(battery_data_check, "DATA", data)
    monkeypatch.setattr(battery_data_check, "INDEXES", ())
    monkeypatch.setattr(battery_data_check, "_ledger", lambda _problems: {})
    monkeypatch.setattr(battery_data_check, "_check_join", lambda *_args: None)
    monkeypatch.setattr(battery_data_check, "_check_parameters", lambda _problems: None)

    assert battery_data_check.main() == expected
    if expected:
        assert "battery_gate_reader.py does not parse" in capsys.readouterr().err
