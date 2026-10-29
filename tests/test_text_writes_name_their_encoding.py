"""Text written by the repository has the same encoding on every machine."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_OTHER_OPEN = {"io", "codecs", "zipfile", "tarfile", "gzip", "os"}


def _mode(call, position):
    value = next((item.value for item in call.keywords if item.arg == "mode"),
                 call.args[position] if len(call.args) > position else None)
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else "r"


def _unnamed_writes(source):
    found = []
    for call in ast.walk(ast.parse(source)):
        if not isinstance(call, ast.Call):
            continue
        if any(item.arg == "encoding" for item in call.keywords):
            continue
        function = call.func
        if isinstance(function, ast.Name) and function.id == "open":
            mode = _mode(call, 1)
            if len(call.args) > 3:
                continue
        elif isinstance(function, ast.Attribute) and function.attr == "write_text":
            if len(call.args) == 1:
                found.append(call.lineno)
            continue
        elif isinstance(function, ast.Attribute) and function.attr == "open":
            if isinstance(function.value, ast.Name) and function.value.id in _OTHER_OPEN:
                continue
            mode = _mode(call, 0)
            if len(call.args) > 2:
                continue
        else:
            continue
        if "b" not in mode and any(letter in mode for letter in "wax+"):
            found.append(call.lineno)
    return sorted(found)


@pytest.mark.parametrize("mode", ["w", "a", "x", "r+"])
@pytest.mark.parametrize("function", ["open", "path.open"])
def test_each_text_write_mode_names_its_encoding(function, mode):
    """Append and update write text too; binary modes and other modules'
    streams do not ask Path or built-in open for a text encoding."""
    arguments = '\'out.txt\', ' if function == "open" else ""
    call = '%s(%s%r)' % (function, arguments, mode)
    assert _unnamed_writes(call) == [1]
    assert _unnamed_writes(call[:-1] + ', encoding="utf-8")') == []
    assert _unnamed_writes('%s(%s%r)' % (function, arguments, mode + "b")) == []


def test_text_write_forms_keep_their_argument_positions():
    assert _unnamed_writes('path.write_text("text")') == [1]
    assert _unnamed_writes('path.write_text("text", "utf-8")') == []
    assert _unnamed_writes('open("out", "w", -1, "utf-8")') == []
    assert _unnamed_writes('path.open("w", -1, "utf-8")') == []
    assert _unnamed_writes('open("out", mode="a")') == [1]
    assert _unnamed_writes('path.open(mode="a")') == [1]
    assert _unnamed_writes('open("out")') == []
    for module in _OTHER_OPEN:
        assert _unnamed_writes('%s.open("out", "w")' % module) == []


def test_repository_text_writes_name_their_encoding():
    """The tests and tools create text for readers that expect UTF-8;
    their output must not depend on the machine's locale."""
    found = []
    for directory in ("tests", "tools", "src"):
        for path in sorted((ROOT / directory).rglob("*.py")):
            for line in _unnamed_writes(path.read_text(encoding="utf-8")):
                found.append('%s:%d' % (path.relative_to(ROOT), line))
    assert not found, "text writes without encoding:\n" + "\n".join(found)
