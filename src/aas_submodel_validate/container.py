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
import urllib.parse
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
#: below what exhausts an air-gapped machine.
#:
#: The archive's own account of a part's size is a fast way to refuse an
#: honest one, and nothing more: it is a number the file carries, not a
#: number this reader measured, and a part may declare a hundred bytes
#: and hold eight megabytes. What bounds the read is the read.
MAX_PART_BYTES = 64 * 1024 * 1024

#: And one container's parts, together. Every part may sit under the cap
#: while the whole does not -- an archive of forty honest parts costs
#: forty times one. Four times the single-part cap leaves room for a
#: container carrying several environments and refuses the pathological.
MAX_TOTAL_PART_BYTES = 4 * MAX_PART_BYTES
_DOCTYPE = __import__("re").compile(rb"<!DOCTYPE", __import__("re").IGNORECASE)

_RELATIONSHIP = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"


def canonical_part_name(value: str):
    """The archive entry a part name refers to, or None if it names none.

    OPC part names are absolute, use "/" as the only separator, escape
    reserved characters, and carry no empty, "." or ".." segments
    (ECMA-376 Part 2). Files in the wild are written by tools that were
    not all reading that: a leading "./", a doubled separator, a step up
    and back, the other slash on a Windows desktop. Those are spellings
    of the same name, and a reader that compares strings calls a
    conformant package broken.

    None means the value is not a part name -- it climbs out of the
    package, ends in a separator (which names a directory, not a part),
    or has nothing left of it. That is a different defect from a part
    being absent, and the rules say so separately.
    """
    if not value or not value.strip():
        return None
    text = value.replace("\\", "/")
    if text.endswith("/"):
        return None          # a directory is not named by any part
    text = urllib.parse.unquote(text)
    segments = []
    for segment in text.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if not segments:
                return None          # a name that climbs out of the package
            segments.pop()
            continue
        segments.append(segment)
    return "/".join(segments) or None


class ContainerError(Exception):
    """The file is not something this reader can follow as an AASX."""


class PartTooLarge(ContainerError):
    """The archive is well-formed and this reader will not read it all.

    Separate from its siblings because it is not a claim about the file.
    Nothing here is malformed; the file is simply larger than a validator
    meant for an air-gapped machine will take in, and the remedy is the
    author's choice of what to send, not a repair.
    """


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
        #: Bytes handed out so far, for MAX_TOTAL_PART_BYTES. One
        #: package object is one validation, so this is that run's total.
        self._read_total = 0
        #: Entry names by their normalised spelling, built on first need.
        self._canonical = None

    # -- files ---------------------------------------------------------------
    def names(self) -> List[str]:
        return self._zip.namelist()

    def has(self, name: str) -> bool:
        return name in self._names

    def part(self, value: str):
        """Which entry `value` names, or None.

        Exact first: an archive may hold an entry whose name really does
        contain a percent escape, and decoding it before looking would
        lose that file to a reader trying to be helpful. The normalised
        index answers only for what the literal did not.
        """
        if value in self._names:
            return value
        # And the same name written the way File values conventionally
        # are: with the leading slash OPC part names carry and archive
        # entry names do not. Without this the exact match almost never
        # fired, and an entry whose name really holds a percent escape
        # was reachable only by the decoded reading -- which is to say
        # the literal never won anything.
        literal = value.lstrip("/")
        if literal in self._names:
            return literal
        canonical = canonical_part_name(value)
        if canonical is None:
            return None
        if canonical in self._names:
            return canonical
        if self._canonical is None:
            self._canonical = {}
            for name in self._names:
                self._canonical.setdefault(canonical_part_name(name), name)
        return self._canonical.get(canonical)

    def read(self, name: str) -> bytes:
        if name not in self._names:
            raise ContainerError("%s names no part %s" % (self.path, name))
        info = self._zip.getinfo(name)
        if info.file_size > MAX_PART_BYTES:
            raise PartTooLarge(
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
            # One byte past the cap, so that reaching the cap and
            # exceeding it are distinguishable. Asking for a bounded
            # number is what bounds the decompressor: an unbounded read
            # hands it the whole stream and truncates the answer
            # afterwards, having already paid for it.
            with self._zip.open(name) as part:
                data = part.read(MAX_PART_BYTES + 1)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError,
                EOFError, OSError, zlib.error) as exc:
            raise UnreadablePart(
                "%s: %s cannot be read: %s: %s"
                % (self.path, name, type(exc).__name__, exc)) from exc
        if len(data) > MAX_PART_BYTES:
            raise PartTooLarge(
                "%s: %s holds more than %d bytes, whatever the archive says"
                % (self.path, name, MAX_PART_BYTES))
        self._read_total += len(data)
        if self._read_total > MAX_TOTAL_PART_BYTES:
            raise PartTooLarge(
                "%s: its parts come to more than %d bytes together"
                % (self.path, MAX_TOTAL_PART_BYTES))
        return data

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
            # Where the name starts from is the difference between the two
            # kinds of string; how it is spelled is not, so both branches
            # end in the same normaliser. The absolute branch used to skip
            # it, which left "/a/./b" resolving differently from "a/./b".
            if target.startswith("/"):
                name = canonical_part_name(target)
            else:
                name = canonical_part_name(posixpath.join(base_dir, target))
            if name is None:
                continue    # not a part name; X2 reports the chain it breaks
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
