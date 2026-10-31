"""Offline conformance validation of AAS submodel template instances.

The package root is the library's whole surface. `validate` judges one
input and returns the report `smtv -f json` prints, `exit_code` is the
number `smtv` would leave by, `list_rules` and `example_path` answer
`--rules` and `--example`, and `Report` and `TemplateRefused` are what
those return and raise. Nothing below the root is a contract.
"""
from __future__ import annotations

__version__ = "1.1.0"

__all__ = ("validate", "exit_code", "Report", "TemplateRefused", "example_path",
           "list_rules")


def __getattr__(name):
    # The library's names are imported when they are first asked for, not
    # with the package. Python runs this file before any module beneath it,
    # and the tools here import one of those from a bare source tree with
    # nothing installed -- the single-file builder among them, which is the
    # tool that fetches the one dependency. Imported here, the engine took
    # aas-core3.0 with it, and the builder died in CI before it could fetch
    # anything.
    if name in __all__:
        from . import api
        value = getattr(api, name)
        globals()[name] = value
        return value
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def __dir__():
    return sorted(set(globals()) | set(__all__))
