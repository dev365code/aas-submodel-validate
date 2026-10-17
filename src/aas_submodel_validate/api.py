"""The library: the judgement the command line makes, called from Python.

One engine and several ways in -- the command line, the single file, a
build step, and this. Each reaches `runner.run` through `validate` and
leaves by the number `exit_code` computes, so no entrance can judge a file
differently from another: the command line is a caller of these two
functions like any other, and a test holds every corpus input to one byte
between them.

The package root re-exports what is promised here, and the root is the
only place those names are promised (`tests/released_api.txt`). This
module, like everything below the root, is internal.
"""
from __future__ import annotations

import atexit
import contextlib
import os
import pathlib

from . import container, runner, tablegen
from .example import bundled_example
from .model import Report, Severity
from .registry import all_rules
from .rules import profiles
from .rules.battery import settles_only

#: What a template the caller supplied raises when this reader will not
#: build a table from it. The command line leaves by 2 on it, with no
#: report; here it is this exception, which is neither a `TypeError` nor a
#: `ValueError` -- nothing about the call was wrong.
TemplateRefused = tablegen.TemplateRefused

#: The formats bytes can be handed over as, each named by the extension a
#: file of that kind carries, which is how the command line chooses.
FORMATS = ("aasx", "json", "xml")

#: The levels `--meta` takes.
META_LEVELS = ("error", "warning", "info")

#: What a report calls bytes nobody named.
UNNAMED = "<bytes>"

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


def validate(source, *, format=None, name=None, meta="warning",
             allow_unmatched=False, profile=None, template=None) -> Report:
    """Judge one input and return the report `smtv -f json` prints.

    `source` is a path -- a `str` or `os.PathLike`, whose extension chooses
    the reader as it does at the command line -- or the bytes of a file
    (`bytes`, `bytearray`, `memoryview`) with `format` saying which kind
    ("aasx", "json" or "xml"), or a file opened in binary mode, read to
    its end and typed by its own `name` unless `format` says otherwise.
    `name` is what the report calls bytes or a file, where a path's own
    spelling would stand; a path takes neither keyword.

    The rest are the command line's flags that move the report: `meta` is
    `--meta`, `allow_unmatched` is `--allow-unmatched`, `profile` is
    `--profile` and `template` is `--template`, a path. The two flags that
    move only the exit code are keywords of `exit_code`.

    An input that cannot be judged -- missing, unreadable, malformed, over
    a bound -- comes back as a report saying so, with `judged` false, and
    `exit_code` gives it 2. A supplied template this reader will not read
    raises `TemplateRefused`. A call made wrong raises `TypeError` or
    `ValueError` before anything is read: those are the command line's 64.
    """
    _level(meta)
    if not isinstance(allow_unmatched, bool):
        raise TypeError("allow_unmatched is True or False, not %r" % (allow_unmatched,))
    # Asked here because the engine does not ask. `runner.run` reads a key
    # no pair publishes as no key at all, and judged as if none were given;
    # at the command line the parser's `choices` refuse it first, and a
    # library has no parser in front of it.
    choices = profiles.KEYS + settles_only()
    if profile is not None and profile not in choices:
        raise ValueError("no such profile: %r; the choices are %s"
                         % (profile, ", ".join(choices)))
    if template is not None:
        template = _path(template, "template")
    held = _held(source, format, name)
    return runner.run(held, strict_meta=meta, allow_unmatched=allow_unmatched,
                      profile=profile, template=template)


def exit_code(report, *, warnings_as_errors=False, require_all_judged=False) -> int:
    """The code `smtv` leaves by for this report: 0, 1 or 2.

    2 when nothing was judged, whatever else was asked -- 1 is the code for
    a verdict. Otherwise 1 when the report holds an error, and also, when
    asked, for a warning (`warnings_as_errors`, the command line's `-W`)
    or for a submodel that went unjudged (`require_all_judged`); 0 when
    none of those. The command line's 64 has no counterpart here: a call
    made wrong is a Python exception.
    """
    if not isinstance(report, Report):
        raise TypeError("exit_code takes the report validate returned, not %s"
                        % type(report).__name__)
    for keyword, value in (("warnings_as_errors", warnings_as_errors),
                           ("require_all_judged", require_all_judged)):
        if not isinstance(value, bool):
            raise TypeError("%s is True or False, not %r" % (keyword, value))
    if not report.judged:
        return EXIT_ERROR
    # Every warning, including the relayed ones. A version of this
    # exempted that channel, on the reasoning that no edit to a submodel
    # can clear a finding about the metamodel -- which is false, and the
    # example this project ships disproves it: 45 of its 77 relayed
    # findings are about `.submodels`, 33 of them an idShort that has
    # only to be deleted. A submodel with an empty `id` raises one
    # relayed finding and nothing else, and passed `-W` while the summary
    # line above it counted the warning. `--meta info` is the way to say
    # this channel should not decide a build, and it says so out loud.
    failed = (not report.ok
              or (require_all_judged and short_of_all_judged(report))
              or (warnings_as_errors and report.count(Severity.WARNING) > 0))
    return EXIT_FINDINGS if failed else EXIT_OK


def short_of_all_judged(report) -> bool:
    """Whether a submodel this input holds went unjudged, or it held none:
    what `--require-all-judged` fails on.

    The number compared is the submodels seen less those declared kind
    Template, because nothing turns a specification into an instance.
    `judged < seen` alone read `0 < 0` as satisfied, so the flag failed a
    file with one unjudged submodel and passed one with none at all: the
    risk ordering backwards, on the input an exporter is most likely to
    produce by accident. Not part of the root's surface; the command line
    reads it to say which of the two it was.
    """
    expected = report.submodels_seen - report.submodels_specified
    return report.submodels_judged < expected or not report.submodels_seen


def list_rules(*, meta="warning") -> list:
    """Every rule this build registers, then the relayed metamodel channel
    at `meta`'s level: what `smtv --rules` lists, one dict per line, each
    with the line's `id`, `kind`, `severity` and `title`.

    Not `rules`: that name is a package beneath the root, and a root name
    that is also a module there is a different object depending on what
    was imported first.
    """
    _level(meta)
    return [{"id": rule.id, "kind": rule.kind, "severity": str(rule.severity),
             "title": rule.title}
            for rule in list(all_rules()) + [runner._meta_rule(meta)]]


#: Held open for the life of the interpreter once `example_path` is asked,
#: and closed at exit -- which removes the copy a single file had to write.
_EXAMPLE = contextlib.ExitStack()
_EXAMPLE_PATH = []


def example_path() -> pathlib.Path:
    """The official IDTA 02004 example this package carries -- the file
    `smtv --example` judges -- as a real path.

    From an installed package that is the file itself. From the single
    file, where the bytes sit inside the archive and no `open()` reaches
    them, they are written out on the first call and removed when the
    interpreter exits. A report on it names the path; the command line,
    given no path, names the example by its file name instead.
    """
    if not _EXAMPLE_PATH:
        _EXAMPLE_PATH.append(_EXAMPLE.enter_context(bundled_example()))
        atexit.register(_EXAMPLE.close)
    return _EXAMPLE_PATH[0]


def _level(meta) -> None:
    if meta not in META_LEVELS:
        raise ValueError("no such meta level: %r; the levels are %s"
                         % (meta, ", ".join(META_LEVELS)))


def _path(value, keyword: str) -> str:
    if not isinstance(value, (str, os.PathLike)):
        raise TypeError("%s is a path, not %s" % (keyword, type(value).__name__))
    spelled = os.fspath(value)
    return os.fsdecode(spelled) if isinstance(spelled, bytes) else spelled


def _named(name) -> str:
    if name is None:
        return UNNAMED
    if not isinstance(name, str):
        raise TypeError("name is a string, not %s" % type(name).__name__)
    return name


def _suffix(form) -> str:
    if form not in FORMATS:
        raise ValueError("no reader for format %r; the formats are %s"
                         % (form, ", ".join(FORMATS)))
    return "." + form


def _held(source, form, name):
    """What `runner.run` is handed: a path as the caller spelled it, or
    the bytes, held with a name and a format.

    Bytes are not a path even where they could spell one: `bytes` is the
    content of a file here, which is what a caller holding a download has.
    """
    if isinstance(source, (bytes, bytearray, memoryview)):
        if form is None:
            raise ValueError("bytes carry no name to tell their format by; "
                             "give format, one of %s" % ", ".join(FORMATS))
        return container.InMemory(source, _named(name), _suffix(form))
    if isinstance(source, (str, os.PathLike)):
        if form is not None:
            raise ValueError("a path's extension chooses its reader, as it does "
                             "at the command line; format is for bytes and "
                             "open files")
        if name is not None:
            raise ValueError("a report calls a path by its own spelling; name is "
                             "for bytes and open files")
        return _path(source, "source")
    if not callable(getattr(source, "read", None)):
        raise TypeError("validate reads a path, bytes or a file opened in binary "
                        "mode, not %s" % type(source).__name__)
    own = getattr(source, "name", None)
    own = own if isinstance(own, str) else None
    if form is None and own is None:
        raise ValueError("this file has no name to tell its format by; give "
                         "format, one of %s" % ", ".join(FORMATS))
    data = source.read()
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("the file gave %s rather than bytes; open it in binary "
                        "mode ('rb')" % type(data).__name__)
    # Its own name's extension, with the same answer a path of that name
    # gets when it is not one this reader reads.
    suffix = _suffix(form) if form is not None else pathlib.PurePath(own).suffix
    return container.InMemory(data, _named(name if name is not None else own), suffix)
