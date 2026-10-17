"""Offline conformance validation of AAS submodel template instances.

The package root is the library's whole surface. `validate` judges one
input and returns the report `smtv -f json` prints, `exit_code` is the
number `smtv` would leave by, `list_rules` and `example_path` answer
`--rules` and `--example`, and `Report` and `TemplateRefused` are what
those return and raise. Nothing below the root is a contract.
"""
from __future__ import annotations

__version__ = "0.13.0"

from .api import (  # noqa: E402 - after the version, which modules beneath read from here
    Report,
    TemplateRefused,
    example_path,
    exit_code,
    list_rules,
    validate,
)

__all__ = ("validate", "exit_code", "Report", "TemplateRefused", "example_path",
           "list_rules")
