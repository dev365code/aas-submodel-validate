#!/usr/bin/env python3
"""The spellings CPython 3.9 gives a charset, as the remedy for a refused name reads them.

    python3.9 tools/python_spellings.py            print the table
    python3.9 tools/python_spellings.py --write    write it into container.py
    python3.9 tools/python_spellings.py --check    exit 1 if container.py holds another

A document declaring a name the IANA charset registry does not give is refused,
and the remedy names the registered one to declare where one can be named --
`sjis` is Shift_JIS -- which needs to know what a spelling registered nowhere
means. Asked of the running Python, that was answered differently by different
ones: 3.13.2 knows `windows_31j` and 3.9.6 does not, and 3.13.15 knows
`pc_multilingual_850_euro` and 3.13.2 does not, so one document drew a
different remedy on each. The answer is a table now, written by this on CPython
3.9, the oldest Python this reader runs on -- 3.9.6 and 3.9.25 write the same
one -- and container.py reads the table and never the running Python. Left
out are the spellings the registry's own names already answer, compared
without case or the punctuation EncName allows. The tests hold the table
true on every Python they run on.
"""
from __future__ import annotations

import argparse
import codecs
import encodings
import encodings.aliases
import pkgutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from aas_submodel_validate import container  # noqa: E402

TARGET = _HERE.parent / "src" / "aas_submodel_validate" / "container.py"
BEGIN = "# -- the spellings CPython 3.9 gives: written by tools/python_spellings.py --\n"
END = "# -- end of the spellings CPython 3.9 gives --\n"
WIDTH = 100


def spellings() -> dict:
    """codec -> the spellings this Python gives it, as the table holds them."""
    named = {container._folded(name) for names in container._REGISTERED.values()
             for name in names}
    found = set(encodings.aliases.aliases) | set(encodings.aliases.aliases.values())
    found |= {module.name for module in pkgutil.iter_modules(encodings.__path__)}
    table = {}
    for spelling in sorted(found):
        key = container._folded(spelling)
        if key in named:
            continue
        try:
            info = codecs.lookup(spelling)
        except LookupError:
            continue
        if getattr(info, "_is_text_encoding", True):
            table.setdefault(info.name, []).append(spelling)
    return {codec: tuple(table[codec]) for codec in sorted(table)}


def _quoted(text: str) -> str:
    """A spelling as this file's literals are written; every one is ASCII and holds no quote."""
    assert text.isascii() and '"' not in text and "\\" not in text, text
    return '"%s"' % text


def block(table: dict) -> str:
    lines = [BEGIN, "_PYTHON_SPELLINGS = {\n"]
    for codec, spelled in table.items():
        line = "    %s: (%s),\n" % (_quoted(codec), ", ".join(_quoted(s) for s in spelled)
                                     + ("," if len(spelled) == 1 else ""))
        if len(line) - 1 <= WIDTH:
            lines.append(line)
            continue
        lines.append("    %s: (\n" % _quoted(codec))
        row = "       "
        for spelling in spelled:
            piece = " %s," % _quoted(spelling)
            if len(row) + len(piece) > WIDTH:
                lines.append(row + "\n")
                row = "       "
            row += piece
        lines.append(row + "\n    ),\n")
    lines += ["}\n", END]
    return "".join(lines)


def _parts():
    text = TARGET.read_text(encoding="utf-8")
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise SystemExit("%s holds the table's markers %d and %d times, not once each"
                         % (TARGET, text.count(BEGIN), text.count(END)))
    head, rest = text.split(BEGIN)
    _, tail = rest.split(END)
    return head, tail


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(64, "%s: error: %s\n" % (self.prog, message))


def main(argv=None) -> int:
    parser = _Parser(description=__doc__.splitlines()[0])
    act = parser.add_mutually_exclusive_group()
    act.add_argument("--write", action="store_true", help="write the table into container.py")
    act.add_argument("--check", action="store_true", help="exit 1 if container.py holds another")
    args = parser.parse_args(argv)
    if (args.write or args.check) and sys.version_info[:2] != (3, 9):
        parser.error("the table is CPython 3.9's; this is %d.%d" % sys.version_info[:2])
    text = block(spellings())
    if args.write:
        head, tail = _parts()
        TARGET.write_text(head + text + tail, encoding="utf-8")
        print("wrote %d spellings of %d charsets into %s"
              % (sum(map(len, spellings().values())), len(spellings()), TARGET.name))
        return 0
    if args.check:
        head, tail = _parts()
        held = TARGET.read_text(encoding="utf-8")[len(head):-len(tail) or None]
        if held != text:
            print("container.py holds another table than CPython %s gives; run --write"
                  % sys.version.split()[0])
            return 1
        print("the table is the one CPython %s gives" % sys.version.split()[0])
        return 0
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
