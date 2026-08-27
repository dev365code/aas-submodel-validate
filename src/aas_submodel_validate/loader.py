"""Four ways a submodel arrives, one loaded shape coming out.

The metamodel types, JSON reading and XML reading all belong to
aas-core3.0 -- nothing about the AAS metamodel is re-invented here. What
this module owns is the plumbing around it: the OPC chain (container.py),
format sniffing, byte order marks, and the discipline that whatever
breaks on the way in becomes *data* for the container rules to report,
never an exception -- except a path that cannot be read at all, which is
the caller's mistake rather than the file's, and a different exit code.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from aas_core3 import jsonization, types, xmlization

from . import container
from .container import (
    AasxPackage,
    ContainerError,
    DirectoryTooLarge,
    NoRelationships,
    PartTooLarge,
    RefusedContent,
    UnreadablePart,
    declares_doctype,
    xml_as_utf8,
)

#: One sentence, two raise sites: a DTD in the package's own relationships
#: part and a DTD in a part's. They were copies, and a copy of a sentence
#: this project ships is a sentence that drifts (the reference-type lint
#: had the same shape and the copies had already diverged).
#: Two more this module ships. The first was guarded only by a substring
#: assertion, which is the shape this project has already measured as no
#: gate; the second by nothing at all -- and the second is the sentence
#: X5's own rule exists to prefer, the one that says a refusal for the
#: size of a directory of names is this reader's decision and not a defect
#: in what was sent. Rewriting either to blame the author left `make
#: check` green.
PAYLOAD_DOCTYPE_REMEDY = (
    "Remove the DTD and write out whatever it declared: a nested-entity "
    "DTD is a decompression-free way to exhaust a reader, so this one "
    "refuses the declaration rather than try to bound what it expands "
    "to. Nothing is wrong with the syntax; it is the declaration this "
    "reader will not take in.")


def directory_bound_remedy() -> str:
    """Built when the finding is, for the reason `_bounds_remedy` gives:
    the sentence names the bound this run applied, and a number frozen at
    import time disagrees with the one that refused the file."""
    return ("This reader indexes no archive whose directory of names "
            "comes to more than %d MiB -- a ZIP is indexed whole before "
            "any of it is read, so the cost is paid on the names alone, "
            "however little the entries hold. Remove what the package "
            "does not need to carry. Nothing is wrong with what you "
            "sent; it was refused, not judged."
            % (container.MAX_DIRECTORY_BYTES // 1024 ** 2))


RELATIONSHIP_DOCTYPE_REMEDY = (
    "Remove the DTD from the named relationships part and write out "
    "whatever it declared. The chain itself is intact -- it names the "
    "parts it should -- and a nested-entity DTD is a decompression-free "
    "way to exhaust a reader, so this one refuses the declaration rather "
    "than bound what it expands to.")

class UnreadablePath(Exception):
    """Nothing could be read from the path at all: absent, or not permitted."""


@dataclass(frozen=True)
class LoadError:
    """One thing that went wrong on the way in, as data.

    `stage` says which link failed -- "zip" (not a container), "chain"
    (the OPC relationships), "payload" (a part that would not parse) --
    and the container rules map stages to findings.
    """

    stage: str
    message: str
    subject: Optional[str] = None
    detail: Optional[str] = None
    #: What to do about *this* one, where the rule's standing advice
    #: would be wrong. The payload stage carries both a document that
    #: would not parse and one this reader refused to read, and "fix the
    #: syntax" is false of the second.
    fix: Optional[str] = None


@dataclass
class Loaded:
    path: str
    form: str                     # aasx | environment-json | environment-xml | submodel-json
    submodels: List[types.Submodel] = field(default_factory=list)
    environment: Optional[types.Environment] = None
    container: Optional[AasxPackage] = None
    errors: List[LoadError] = field(default_factory=list)

    @property
    def nothing_was_judged(self) -> bool:
        """Something broke on the way in, and no submodel came out of it.

        Not the same question as `errors`, which an archive with one bad
        part and two good ones also answers yes to: that run read
        something, walked it, and its findings are real. This one is
        whether the rules were handed anything at all.

        SMT-D1 has asked it since day one -- it stays silent rather than
        pile "no submodel this tool knows" on top of the X rules -- and
        spelled it out inline. Two readers of one question, so it lives
        here and both ask it.
        """
        return bool(self.errors) and not self.submodels


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8-sig")


def _read_bounded(loaded: Loaded, path: Path):
    """The document's bytes, or None with the refusal already recorded.

    The cap was the container's alone, so the same bytes were refused
    packaged and read whole bare -- and what a reader will take in has
    nothing to do with whether somebody zipped it first. Neither OPC nor
    the AAS specification says anything about how much a reader must
    accept, so the bound is this project's, and one that depends on the
    envelope is not a bound.

    `container.MAX_PART_BYTES`, and the module imported rather than the
    name, so the value is read when the question is asked rather than
    when this file was: one number in one place is the negation of the
    defect being fixed.

    Two steps, both load-bearing. The size the filesystem reports lets
    the refusal say what the document weighs -- "over the limit" is true
    of one byte over and of a hundred times over, and splitting it is
    different work in each case. The bounded read is what actually
    holds, because a stat describes the file as it was a moment ago and
    a supplier may still be writing it.
    """
    cap = container.MAX_PART_BYTES
    try:
        size = path.stat().st_size
        if size > cap:
            loaded.errors.append(LoadError(
                "bounds", "%s: %d bytes, above the %d byte limit" % (path, size, cap),
                subject=str(path)))
            return None
        with path.open("rb") as handle:
            raw = handle.read(cap + 1)
    except (OSError, MemoryError) as exc:
        # Not a defect in the file, so it leaves by the could-not-run code
        # rather than as a verdict about a document nobody managed to read.
        raise UnreadablePath("cannot read %s: %s: %s"
                             % (path, type(exc).__name__, exc)) from exc
    if len(raw) > cap:
        loaded.errors.append(LoadError(
            "bounds", "%s: more than %d bytes" % (path, cap), subject=str(path)))
        return None
    return raw


def _parse_environment(loaded: Loaded, raw: bytes, *, part: Optional[str], form: str,
                       document=None) -> None:
    """One environment document (JSON or XML) into loaded.submodels.

    `document` is the already-parsed JSON, for the one caller that had to
    parse it to decide what it was. Without it that caller handed the
    bytes on and this function built the same tree again, holding two at
    once -- on a reader whose whole bound is 64 MiB of bytes, and whose
    trees are several times the bytes they came from.
    """
    if not form.endswith("json"):
        # Decoded the way the parser will read it, before the guard reads a
        # byte of it. The refusal matched bytes, and a byte pattern finds
        # `<!DOCTYPE` in UTF-8 and nowhere else -- so the same declaration
        # written UTF-16 came back not as a refusal but as a clean read.
        raw = xml_as_utf8(raw)
        if declares_doctype(raw):
            loaded.errors.append(LoadError(
                "payload", "the XML declares a DOCTYPE, which is refused",
                subject=part or loaded.path,
                fix=PAYLOAD_DOCTYPE_REMEDY))
            return
    try:
        if form.endswith("json"):
            if document is None:
                document = json.loads(_decode(raw))
            environment = jsonization.environment_from_jsonable(document)
        else:
            environment = xmlization.environment_from_str(_decode(raw))
    except Exception as exc:
        loaded.errors.append(LoadError(
            "payload", "the document could not be read as an AAS environment",
            subject=part or loaded.path, detail="%s: %s" % (type(exc).__name__, exc)))
        return
    loaded.environment = environment
    loaded.submodels.extend(environment.submodels or [])


def load(path) -> Loaded:
    path = Path(path)
    if not path.exists():
        raise UnreadablePath("no such file: %s" % path)
    # Whether there is a file to read at all is one question, asked once,
    # before the extension decides anything. Asking it inside each branch
    # is how a directory came to exit 2 when it was called .xml and 1 --
    # a defect in a file nobody had opened -- when it was called .json.
    if not path.is_file():
        raise UnreadablePath("not a file: %s" % path)

    suffix = path.suffix.lower()
    if suffix == ".aasx":
        return _load_aasx(path)
    if suffix == ".json":
        return _load_json(path)
    if suffix == ".xml":
        loaded = Loaded(path=str(path), form="environment-xml")
        raw = _read_bounded(loaded, path)
        if raw is not None:
            _parse_environment(loaded, raw, part=None, form="environment-xml")
        return loaded
    raise UnreadablePath("cannot tell what %s is: expected .aasx, .json or .xml" % path)


def _load_json(path: Path) -> Loaded:
    loaded = Loaded(path=str(path), form="environment-json")
    # Read once, and bounded before the branch below decides what the
    # document is: a form added later cannot arrive without a bound by
    # being added to the wrong side of that question. The environment
    # case used to go back to disk for bytes it already had -- a second
    # read, and the only one in this module with nothing guarding it.
    raw = _read_bounded(loaded, path)
    if raw is None:
        return loaded
    try:
        document = json.loads(_decode(raw))
    except Exception as exc:
        loaded.errors.append(LoadError("payload", "the file is not JSON",
                                       subject=str(path),
                                       detail="%s: %s" % (type(exc).__name__, exc)))
        return loaded

    if isinstance(document, dict) and document.get("modelType") == "Submodel":
        loaded.form = "submodel-json"
        try:
            loaded.submodels.append(jsonization.submodel_from_jsonable(document))
        except Exception as exc:
            loaded.errors.append(LoadError("payload", "the document could not be read as a Submodel",
                                           subject=str(path),
                                           detail="%s: %s" % (type(exc).__name__, exc)))
        return loaded

    _parse_environment(loaded, raw, part=None, form="environment-json",
                       document=document)
    return loaded


def _load_aasx(path: Path) -> Loaded:
    loaded = Loaded(path=str(path), form="aasx")
    try:
        package = AasxPackage(path)
    except DirectoryTooLarge as exc:
        # Before its parent, and staged "bounds" rather than "zip": X1
        # would tell the author to re-create the package, and there is
        # nothing wrong with it to repair. This is a decision of ours.
        loaded.errors.append(LoadError(
            "bounds", str(exc), subject=str(path),
            fix=directory_bound_remedy()))
        return loaded
    except ContainerError as exc:
        loaded.errors.append(LoadError("zip", str(exc)))
        return loaded
    loaded.container = package

    # An unreadable part is staged as "zip", not "chain": the chain may
    # be perfect and the archive's account of one part wrong, and
    # "repair the chain" would then be a remedy for a defect that is not
    # there. Every finding this project makes carries a true remedy.
    try:
        parts = package.spec_parts
    except PartTooLarge as exc:
        loaded.errors.append(LoadError("bounds", str(exc)))
        return loaded
    except UnreadablePart as exc:
        loaded.errors.append(LoadError("zip", str(exc)))
        return loaded
    except RefusedContent as exc:
        loaded.errors.append(LoadError("chain", str(exc), fix=RELATIONSHIP_DOCTYPE_REMEDY))
        return loaded
    except ContainerError as exc:
        loaded.errors.append(LoadError("chain", str(exc)))
        return loaded

    for part in parts:
        try:
            raw = package.read(part)
        except PartTooLarge as exc:
            loaded.errors.append(LoadError("bounds", str(exc), subject=part))
            continue
        except UnreadablePart as exc:
            loaded.errors.append(LoadError("zip", str(exc), subject=part))
            continue
        except ContainerError as exc:
            loaded.errors.append(LoadError("chain", str(exc), subject=part))
            continue
        # Touch the part's own relationships here, where a failure can be
        # loaded as an error. The rules read this later (X4 walks it for
        # declared supplementary parts) and a rule cannot report a
        # container defect -- it can only skip. An archive that could not
        # yield those bytes used to come back with no findings at all.
        try:
            package.relationships(part)
        except PartTooLarge as exc:
            loaded.errors.append(LoadError("bounds", str(exc), subject=part))
        except UnreadablePart as exc:
            loaded.errors.append(LoadError("zip", str(exc), subject=part))
        except NoRelationships:
            pass        # this part declares none, which is not a defect
        except RefusedContent as exc:
            loaded.errors.append(LoadError("chain", str(exc), subject=part, fix=RELATIONSHIP_DOCTYPE_REMEDY))
        except ContainerError as exc:
            # Would not parse. Quiet here until now for sharing an
            # exception type with "declares none" above, which left a
            # container this reader would not read coming back `ok`.
            loaded.errors.append(LoadError("chain", str(exc), subject=part))
        form = "environment-json" if part.lower().endswith(".json") else "environment-xml"
        _parse_environment(loaded, raw, part=part, form=form)
    return loaded
