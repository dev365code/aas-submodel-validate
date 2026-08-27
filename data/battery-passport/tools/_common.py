# -*- coding: utf-8 -*-
"""Shared helpers for the battery-passport requirement extractors.

One extractor per canonical source. An extractor parses; it does not judge.
Where a source does not say whether something must be present, the record says
"unclear" rather than guessing, and the unclear ones are counted so they can be
looked at deliberately.

No extractor mirrors a source document. What is written out is a derived index:
identifiers, section references, short quotations, and the cardinality or
applicability the source itself states -- each pinned to the sha256 of the exact
file it was read from, so a moved or re-issued source shows up as a hash change
instead of a silent difference.

Output is deterministic: same input bytes, same output bytes. There is no
timestamp, no path and no machine name in an index file, so two runs on two
machines can be compared with a plain diff.
"""

import hashlib
import json
import os

# The unified record shape. Every extractor emits these keys, in this order,
# whether or not its source has something to say about them.
FIELDS = (
    "id",          # "<source>:<stable local id>" -- stable across runs
    "kind",        # attribute | sentence | element
    "section",     # where in the source: point, article, sheet row, idShort path
    "text",        # short quotation or the attribute name as the source writes it
    "mandatory",   # yes | conditional | no | unclear
    "condition",   # the source's own wording of the condition, when it gives one
    "access",      # public | legitimate-interest | authorities | n/a
    "applies_to",  # battery categories the source scopes this to
    "joins",       # ids in other indexes that state the same obligation
)

MANDATORY_VALUES = ("yes", "conditional", "no", "unclear")
ACCESS_VALUES = ("public", "legitimate-interest", "authorities", "n/a")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def squeeze(text):
    """Collapse whitespace; keep the wording, drop the layout."""
    return " ".join((text or "").split())


def provenance_path(path, keep=2):
    """How a source file is named inside an index.

    Only the last few path components survive, so an index never records where
    on someone's disk the file happened to sit -- an index is meant to be
    readable by anyone who has the same source, not to describe one machine.
    """
    parts = os.path.normpath(path).replace("\\", "/").split("/")
    parts = [p for p in parts if p not in ("", ".", "..")]
    return "/".join(parts[-keep:])


def record(id, kind, section, text, mandatory="unclear", condition="",
           access="n/a", applies_to=None, joins=None, **extra):
    if mandatory not in MANDATORY_VALUES:
        raise ValueError("mandatory=%r not in %r" % (mandatory, MANDATORY_VALUES))
    if access not in ACCESS_VALUES:
        raise ValueError("access=%r not in %r" % (access, ACCESS_VALUES))
    row = {
        "id": id,
        "kind": kind,
        "section": squeeze(section),
        "text": squeeze(text),
        "mandatory": mandatory,
        "condition": squeeze(condition),
        "access": access,
        "applies_to": list(applies_to or []),
        "joins": list(joins or []),
    }
    row.update(extra)
    return row


def tally(records, key):
    out = {}
    for r in records:
        v = r.get(key)
        if isinstance(v, list):
            for item in v:
                out[item] = out.get(item, 0) + 1
        else:
            out[str(v)] = out.get(str(v), 0) + 1
    return dict(sorted(out.items()))


def write_index(out_path, source, records, provenance, counts=None, notes=None):
    """Write one derived index.

    provenance: list of {"file", "sha256", "version", "url"} -- one entry per
    file actually read. The hashes are the pin; the urls say where the same
    bytes can be fetched again.
    """
    ids = [r["id"] for r in records]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError("duplicate record ids: %s" % duplicates[:5])
    doc = {
        "source": source,
        "provenance": provenance,
        "counts": dict(
            {
                "records": len(records),
                "by_kind": tally(records, "kind"),
                "by_mandatory": tally(records, "mandatory"),
                "by_access": tally(records, "access"),
            },
            **(counts or {})
        ),
        "notes": list(notes or []),
        "records": records,
    }
    directory = os.path.dirname(os.path.abspath(out_path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1, sort_keys=False)
        fh.write("\n")
    return doc


def report(doc, out_path):
    """One line per count, to stdout. The script does the counting; nobody
    types a number into a document by hand."""
    print("wrote %s" % out_path)
    print("  source   %s" % doc["source"])
    for p in doc["provenance"]:
        print("  read     %s  %s  (%s)" % (p["sha256"][:8], p["file"], p.get("version", "?")))
    for k, v in doc["counts"].items():
        if isinstance(v, dict):
            flat = json.dumps(v, ensure_ascii=False)
            v = flat if len(flat) <= 300 else "%d entries (see the index file)" % len(v)
        print("  %-8s %s" % (k, v))
    for n in doc["notes"]:
        print("  note     %s" % n)
