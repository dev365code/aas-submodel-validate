"""Reading an .aasx container: the OPC chain, followed link by link.

An AASX is an OPC package (ECMA-376 Part 2), and OPC's rule is that the
payload is *found*, never guessed: the package-level `_rels/.rels` names an
`aasx-origin` part, whose own relationships name the `aas-spec` payload.
A container whose chain is broken has no payload, however plausible its
entry names look — so this reader follows the chain and refuses at the
first missing link, naming it.

Deliberately stdlib only (zipfile + ElementTree): the official test
tooling reads AASX the same way, and this project exists for machines
where every wheel crosses an air gap by hand.
"""
from __future__ import annotations

import posixpath
import zipfile
from pathlib import Path
from typing import List, Tuple
from xml.etree import ElementTree

#: The OPC relationship vocabulary AASX uses, exactly as the official
#: IDTA example files spell it.
ORIGIN_REL = "http://admin-shell.io/aasx/relationships/aasx-origin"
SPEC_REL = "http://admin-shell.io/aasx/relationships/aas-spec"
SUPPL_REL = "http://admin-shell.io/aasx/relationships/aas-suppl"

_RELATIONSHIP = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"


class ContainerError(Exception):
    """The file is not something this reader can follow as an AASX."""


def _rels_name(source: str) -> str:
    """Where OPC keeps the relationships of `source` ("" = the package)."""
    if not source:
        return "_rels/.rels"
    directory, base = posixpath.split(source)
    return posixpath.join(directory, "_rels", base + ".rels")


class AasxPackage:
    """An opened .aasx. Use as a context manager, like ZipFile."""

    def __init__(self, path):
        self.path = Path(path)
        try:
            self._zip = zipfile.ZipFile(self.path)
        except (OSError, zipfile.BadZipFile) as exc:
            raise ContainerError("cannot open %s as a ZIP container: %s"
                                 % (self.path, exc)) from exc
        self._names = frozenset(self._zip.namelist())

    # -- files ---------------------------------------------------------------
    def names(self) -> List[str]:
        return self._zip.namelist()

    def has(self, name: str) -> bool:
        return name in self._names

    def read(self, name: str) -> bytes:
        if name not in self._names:
            raise ContainerError("%s names no part %s" % (self.path, name))
        return self._zip.read(name)

    # -- the OPC chain -------------------------------------------------------
    def relationships(self, source: str = "") -> List[Tuple[str, str]]:
        """(type, target) pairs of `source`'s relationships part.

        Targets come back without their leading slash, ready to use as ZIP
        entry names. Real-world .rels files start with a UTF-8 byte order
        mark; ElementTree's expat handles that on bytes input, so the raw
        part is handed over undecoded.
        """
        rels = _rels_name(source)
        if rels not in self._names:
            raise ContainerError("%s has no %s, so the chain from %r goes nowhere"
                                 % (self.path, rels, source or "the package root"))
        try:
            root = ElementTree.fromstring(self.read(rels))
        except ElementTree.ParseError as exc:
            raise ContainerError("%s: %s does not parse: %s" % (self.path, rels, exc)) from exc
        return [(el.get("Type", ""), el.get("Target", "").lstrip("/"))
                for el in root.iter(_RELATIONSHIP)]

    @property
    def origin(self) -> str:
        """The aasx-origin part the package-level relationships name."""
        for rel_type, target in self.relationships(""):
            if rel_type == ORIGIN_REL:
                return target
        raise ContainerError("%s declares no aasx-origin relationship" % self.path)

    @property
    def spec_parts(self) -> List[str]:
        """Every aas-spec payload the origin's relationships name."""
        targets = [target for rel_type, target in self.relationships(self.origin)
                   if rel_type == SPEC_REL]
        if not targets:
            raise ContainerError("%s declares no aas-spec relationship on its origin"
                                 % self.path)
        return targets

    # -- lifecycle -----------------------------------------------------------
    def close(self) -> None:
        self._zip.close()

    def __enter__(self) -> AasxPackage:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __repr__(self) -> str:
        return "AasxPackage(%r)" % str(self.path)
