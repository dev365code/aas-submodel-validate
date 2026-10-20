"""What a relayed finding read, in the words of the file it read.

aas-core3.0 reports a metamodel violation as a sentence and a path to the
object it is about. The path says where; this says what was there. Where
the path ends at a value, that is the value. Where it ends at an object,
the attributes shown are the ones the check's own condition names --
`relayed_reads.py`, generated from aas-core3.0's verification module --
so the finding shows what the check looked at and nothing this project
chose to add. A check that table does not know (a newer aas-core3.0)
still names the object it is about, by kind and name.

Attributes are spelt as the file spells them -- `isCaseOf`, not
`is_case_of` -- because the reader is about to go and look for them.
"""
from __future__ import annotations

import enum
import functools
from typing import Optional

from . import relayed_reads, upstream

#: How many items of a list are shown before the rest is counted.
SHOWN = 5
EACH = "*"


@functools.cache
def spelt(name: str) -> str:
    """`is_case_of` -> `isCaseOf`: the attribute as AAS JSON and XML name it."""
    head, *rest = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def _named(obj) -> str:
    """An object in a few words: what a reader would search the file for."""
    if upstream.is_reference(obj):
        keys = obj.keys or []
        shown = " / ".join(shown_value(key.value) for key in keys[:3])
        if len(keys) > 3:
            shown += " and %d more" % (len(keys) - 3)
        return "%s %s" % (obj.type.value, shown) if shown else obj.type.value
    if upstream.is_key(obj):
        return "%s %s" % (obj.type.value, shown_value(obj.value))
    language, text = getattr(obj, "language", None), getattr(obj, "text", None)
    if isinstance(language, str) and isinstance(text, str):
        return "%s %s" % (language, shown_value(text))
    kind = type(obj).__name__
    for attribute in ("id_short", "id", "name", "type"):
        value = getattr(obj, attribute, None)
        if isinstance(value, str):
            return "%s %s" % (kind, shown_value(value))
    return kind


def _listed(values) -> str:
    shown = ", ".join(shown_value(value) for value in values[:SHOWN])
    if len(values) > SHOWN:
        shown += " and %d more" % (len(values) - SHOWN)
    return shown


def shown_value(value) -> str:
    """One value as read, written so that its kind is not in doubt: a
    string quoted, absence said, a list bracketed."""
    if value is None:
        return "not set"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, enum.Enum):
        return str(value.value)
    if isinstance(value, (bytes, bytearray)):
        return "%d bytes" % len(value)
    if upstream.is_model_object(value):
        return _named(value)
    if isinstance(value, (list, tuple)):
        return "[%s]" % _listed(list(value))
    return repr(value)


def _followed(obj, path) -> str:
    """`path` read from `obj`, as `label: value`; a `*` step reads every
    item of the list it stands on, and the items are shown in order."""
    values, label, fanned = [obj], "", False
    for step in path:
        if step == EACH:
            label += "[*]"
            if not any(isinstance(value, (list, tuple)) for value in values):
                return "%s: %s" % (label[:-3], shown_value(values[0] if values else None))
            values = [item for value in values if isinstance(value, (list, tuple))
                      for item in value]
            fanned = True
        elif isinstance(step, int):
            label += "[%d]" % step
            values = [value[step] if isinstance(value, (list, tuple)) and len(value) > step
                      else None for value in values]
        else:
            label += ("." if label else "") + spelt(step)
            values = [getattr(value, step, None) if value is not None else None
                      for value in values]
    if fanned:
        return "%s: %s" % (label, _listed(values) if values else "[]")
    return "%s: %s" % (label, shown_value(values[0]))


def relayed(error, target) -> Optional[str]:
    """What aas-core3.0's `error` read, from the `target` it verified."""
    value, holder, index = upstream.pointed_at(error, target)
    label = spelt(holder) if holder else None
    if index is not None:
        label = "%s[%d]" % (label or "", index)
    if not upstream.is_model_object(value):
        return "%s: %s" % (label, shown_value(value))
    paths = relayed_reads.READS.get((type(value).__name__, error.cause))
    if paths is None:
        return _named(value)
    return "; ".join(_followed(value, path) for path in paths)
