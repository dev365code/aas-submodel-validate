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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from aas_core3 import jsonization, types, xmlization

from .container import AasxPackage, ContainerError, PartTooLarge, UnreadablePart

_DOCTYPE = re.compile(rb"<!DOCTYPE", re.IGNORECASE)


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


@dataclass
class Loaded:
    path: str
    form: str                     # aasx | environment-json | environment-xml | submodel-json
    submodels: List[types.Submodel] = field(default_factory=list)
    environment: Optional[types.Environment] = None
    container: Optional[AasxPackage] = None
    errors: List[LoadError] = field(default_factory=list)


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8-sig")


def _parse_environment(loaded: Loaded, raw: bytes, *, part: Optional[str], form: str) -> None:
    """One environment document (JSON or XML) into loaded.submodels."""
    if not form.endswith("json") and _DOCTYPE.search(raw):
        loaded.errors.append(LoadError(
            "payload", "the XML declares a DOCTYPE, which is refused",
            subject=part or loaded.path))
        return
    try:
        if form.endswith("json"):
            environment = jsonization.environment_from_jsonable(json.loads(_decode(raw)))
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

    suffix = path.suffix.lower()
    if suffix == ".aasx":
        return _load_aasx(path)
    if suffix == ".json":
        return _load_json(path)
    if suffix == ".xml":
        loaded = Loaded(path=str(path), form="environment-xml")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise UnreadablePath("cannot read %s: %s" % (path, exc)) from exc
        _parse_environment(loaded, raw, part=None, form="environment-xml")
        return loaded
    raise UnreadablePath("cannot tell what %s is: expected .aasx, .json or .xml" % path)


def _load_json(path: Path) -> Loaded:
    loaded = Loaded(path=str(path), form="environment-json")
    try:
        document = json.loads(_decode(path.read_bytes()))
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

    _parse_environment(loaded, path.read_bytes(), part=None, form="environment-json")
    return loaded


def _load_aasx(path: Path) -> Loaded:
    loaded = Loaded(path=str(path), form="aasx")
    try:
        package = AasxPackage(path)
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
        form = "environment-json" if part.lower().endswith(".json") else "environment-xml"
        _parse_environment(loaded, raw, part=part, form=form)
    return loaded
