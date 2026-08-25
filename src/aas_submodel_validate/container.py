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
import zlib
from pathlib import Path
from typing import List, Tuple
from xml.etree import ElementTree

#: The OPC relationship vocabulary AASX uses, exactly as the official
#: IDTA example files spell it.
ORIGIN_REL = "http://admin-shell.io/aasx/relationships/aasx-origin"
SPEC_REL = "http://admin-shell.io/aasx/relationships/aas-spec"
SUPPL_REL = "http://admin-shell.io/aasx/relationships/aas-suppl"

#: A package arrives from a supplier, so what it decompresses to is
#: untrusted. 64 MiB is far above any real AAS metadata document and far
#: below what exhausts an air-gapped machine; the check runs off the ZIP
#: directory, so an oversized part is refused without being read.
MAX_PART_BYTES = 64 * 1024 * 1024
_DOCTYPE = __import__("re").compile(rb"<!DOCTYPE", __import__("re").IGNORECASE)

_RELATIONSHIP = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"


class ContainerError(Exception):
    """The file is not something this reader can follow as an AASX."""


class UnreadablePart(ContainerError):
    """The archive names a part but cannot yield its bytes.

    Kept apart from its parent because the remedy differs: a chain that
    does not reach a payload is repaired by fixing the relationships,
    while this archive's relationships may be perfect and its own
    description of a part wrong. The loader routes the two differently.
    """


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
        info = self._zip.getinfo(name)
        if info.file_size > MAX_PART_BYTES:
            raise ContainerError(
                "%s refuses %s: %d bytes uncompressed, above the %d byte limit"
                % (self.path, name, info.file_size, MAX_PART_BYTES))
        # zipfile raises for a part the archive describes wrongly: a
        # method no reader implements, an encryption flag, a checksum
        # that does not match what came out. Those are defects in the
        # file, and this reader's promise is that a defect in the file
        # is a finding. zlib.error is in the list because the failure
        # can also happen a layer below zipfile, in the decompressor,
        # where nothing wraps it -- which the first version of this
        # tuple missed.
        try:
            return self._zip.read(name)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError,
                EOFError, OSError, zlib.error) as exc:
            raise UnreadablePart(
                "%s: %s cannot be read: %s: %s"
                % (self.path, name, type(exc).__name__, exc)) from exc

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
        raw = self.read(rels)
        # A relationships part has no legitimate use for a DTD, and a
        # nested-entity DTD is a decompression-free way to exhaust memory
        # (billion laughs; expat expands it before any handler runs). Refuse
        # the declaration rather than try to bound the expansion.
        if _DOCTYPE.search(raw):
            raise ContainerError("%s: %s declares a DOCTYPE, which is refused"
                                 % (self.path, rels))
        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError as exc:
            raise ContainerError("%s: %s does not parse: %s" % (self.path, rels, exc)) from exc
        # OPC resolves a target that begins with "/" against the package
        # root and any other target against the source part's own directory
        # (ECMA-376 Part 2). Treating every target as root-relative rejected
        # conformant packages that use relative targets.
        base_dir = posixpath.dirname(source)
        resolved = []
        for el in root.iter(_RELATIONSHIP):
            target = el.get("Target", "")
            if target.startswith("/"):
                name = target[1:]
            else:
                name = posixpath.normpath(posixpath.join(base_dir, target))
            resolved.append((el.get("Type", ""), name))
        return resolved

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
