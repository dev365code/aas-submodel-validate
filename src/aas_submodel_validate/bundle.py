"""The diagnostic bundle: what one run looked like, for a person to read and,
if they choose, attach to an issue -- and nothing from the files it read.

Nothing here opens a socket or sends anything. The bundle is a file on the
machine that ran the check, written after it has been shown. It carries
structure, counts, sizes, hashes and rule ids. It does not carry a member's
name, a path, an idShort, an identifier or a value from the file, a finding's
message, subject, detail or remedy, a byte of the document or of a file the
package holds, a ZIP comment or what an extra field holds, or a user or host
name; of the environment, only the names of the variables that change how this
tool writes, and the console's encoding as Python reports it. A defect escaping
the run adds its type, the frames inside this package, and a hash of its
message -- which, for a message as short as a missing key's name, can be
checked against a guess. Two entries with one name are
marked by the index of the first of them, not by the name or a hash of it: a
hash of a name that can be guessed can be checked against the guess.

What it reads again to describe the input is held to the bounds the run held
the input to: past the size bound the file is not hashed, and a central
directory past the directory bound is counted and not listed.

The layout is bundle schema 1, the one vdi2770-validate also writes. There is
no clock in it: the same input, run with the same options by the same release
on the same machine, gives the same bytes, apart from how long the run took,
which is kept in whole seconds rounded up.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import platform
import stat
import sys
import tempfile
import traceback
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

from . import container
from .model import PATH_STEPS

TOOL = "aas-submodel-validate"
SCHEMA = 1
#: The whole file, so that it can be carried out of a closed network on anything.
LIMIT = 256 * 1024
#: Members listed one by one; past this, only how many there were.
ROWS = 5000
#: The environment variables that change how this tool's output is written,
#: by name. Their values are not taken.
ENVIRONMENT = ("PYTHONIOENCODING", "PYTHONUTF8")
#: What a file kind is told by, and nothing else from its name.
KINDS = {".pdf": "pdf", ".xml": "xml", ".json": "json"}
#: A container inside the package, which this reader does not open.
CONTAINERS = (".aasx", ".zip")
#: A person's own sentence is kept, up to this many characters.
NOTE_LIMIT = 2000
#: What each member row holds, in order: one short array per member.
ROW_FIELDS = ["i", "size", "csize", "method", "flagBits", "nameLen", "sameNameAs",
              "sameFoldedNameAs", "extraIds", "utf8Flag"]
#: The package this tool is, by its directory: a traceback frame inside it is
#: public code and is kept, file, line and function; any other frame is not.
_PACKAGE = Path(__file__).resolve().parent


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


#: The extra-field header ids ZIP's application note publishes, PKWARE's and
#: the third-party ones it lists, and the one OPC writers add. Any other id
#: is told as -1: a field of records that hold nothing, each id two bytes of
#: text, would otherwise read the text back out two bytes at a time.
PUBLISHED_EXTRA_IDS = frozenset({
    0x0001, 0x0007, 0x0008, 0x0009, 0x000A, 0x000C, 0x000D, 0x000E, 0x000F,
    0x0014, 0x0015, 0x0016, 0x0017, 0x0018, 0x0019, 0x0020, 0x0021, 0x0022,
    0x0023, 0x0065, 0x0066, 0x4690, 0x07C8, 0x1986, 0x2605, 0x2705, 0x2805,
    0x334D, 0x4154, 0x4341, 0x4453, 0x4704, 0x470F, 0x4854, 0x4B46, 0x4C41,
    0x4D49, 0x4D63, 0x4F4C, 0x5356, 0x5455, 0x554E, 0x5855, 0x6375, 0x6542,
    0x6854, 0x7075, 0x7441, 0x756E, 0x7855, 0x7875, 0x9901, 0x9902, 0xA11E,
    0xA220, 0xCAFE, 0xD935, 0xE57A, 0xFD4A,
})


def _extra_ids(extra: bytes) -> List[int]:
    """The header ids of a member's extra field, and not what they hold --
    stopping at the first record whose declared size runs past the field."""
    ids, at = [], 0
    while at + 4 <= len(extra):
        header = int.from_bytes(extra[at:at + 2], "little")
        size = int.from_bytes(extra[at + 2:at + 4], "little")
        if at + 4 + size > len(extra):
            break
        ids.append(header if header in PUBLISHED_EXTRA_IDS else -1)
        at += 4 + size
    return ids


def _members(zf: zipfile.ZipFile) -> Dict:
    infos = zf.infolist()
    first_name: Dict[str, int] = {}
    first_folded: Dict[str, int] = {}
    rows = []
    for i, info in enumerate(infos[:ROWS]):
        name = info.filename
        same = first_name.setdefault(name, i)
        same_folded = first_folded.setdefault(name.casefold(), i)
        rows.append([i, info.file_size, info.compress_size, info.compress_type,
                     info.flag_bits, len(name), same if same != i else None,
                     same_folded if same_folded != i and same == i else None,
                     _extra_ids(info.extra), bool(info.flag_bits & 0x800)])
    kinds = {"pdf": 0, "xml": 0, "json": 0, "other": 0}
    inside = 0
    for info in infos:
        suffix = os.path.splitext(info.filename.lower())[1]
        kinds[KINDS.get(suffix, "other")] += 1
        inside += suffix in CONTAINERS
    return {"members": {"count": len(infos), "listed": len(rows), "rowFields": ROW_FIELDS,
                        "rows": rows},
            "containersInside": inside, "fileKinds": kinds}


#: Read in blocks this size, so that describing a file costs one block of
#: memory whatever the file weighs.
_BLOCK = 1 << 16


def _nothing(kind: str, size=None, sha256=None) -> Dict:
    # `depth` is 0 for every input: this reader opens no container inside
    # another, so there is no deeper level for it to have reached.
    return {"kind": kind, "size": size, "sha256": sha256, "depth": 0,
            "members": {"count": 0, "listed": 0, "rowFields": ROW_FIELDS, "rows": []},
            "containersInside": 0, "fileKinds": {"pdf": 0, "xml": 0, "json": 0, "other": 0}}


def fingerprint(path: Optional[str]) -> Dict:
    """The shape of what was given: size and hash, and for an archive what its
    directory lists -- sizes, methods and flags, never a name. Only a regular
    file is read again: a pipe was read once by the run, and opening it a
    second time waits for a writer that is gone."""
    if path is None:
        return _nothing("file")
    try:
        given = os.stat(path)
    except (OSError, ValueError):
        return _nothing("file")
    if stat.S_ISDIR(given.st_mode):
        return _nothing("dir")
    if not stat.S_ISREG(given.st_mode):
        return _nothing("stream")
    try:
        with container.open_regular(path) as handle:
            digest, read, bounded = hashlib.sha256(), 0, True
            for block in iter(lambda: handle.read(_BLOCK), b""):
                read += len(block)
                if read > container.MAX_TOTAL_PART_BYTES:
                    bounded = False       # past what the run takes in: not hashed
                    read = given.st_size
                    break
                digest.update(block)
            # What is read again has to be what the file says it holds. A
            # descriptor's name -- `/dev/stdin`, `/dev/fd/0` -- stats as the
            # regular file behind it, and on macOS and the BSDs opening it
            # again shares the offset the run left at the end: the read comes
            # back empty, and a bundle saying 0 bytes describes a file nobody
            # gave.
            if read != given.st_size:
                return _nothing("stream")
            shape = _nothing("file", given.st_size, digest.hexdigest() if bounded else None)
            handle.seek(0)
            _archive(handle, shape)
    except (OSError, MemoryError):
        return _nothing("file")
    return shape


def _archive(handle, shape: Dict) -> None:
    """An archive's directory, asked first how large it says it is -- through
    `zipfile`'s own end-of-directory reader, as the container reader asks it
    -- and listed only within the bound the run holds a directory to. Past
    it, how many entries it declares, and nothing else."""
    try:
        end = zipfile._EndRecData(handle)
    except Exception:                       # noqa: BLE001 -- not an archive zipfile reads
        return
    if end is None:
        return
    if end[zipfile._ECD_SIZE] > container.MAX_DIRECTORY_BYTES:
        shape["kind"] = "zip"
        shape["members"]["count"] = end[zipfile._ECD_ENTRIES_TOTAL]
        shape["fileKinds"] = dict.fromkeys(shape["fileKinds"])
        shape["containersInside"] = None
        return
    try:
        handle.seek(0)
        with zipfile.ZipFile(handle) as zf:
            shape.update(_members(zf), kind="zip")
    except Exception:                       # noqa: BLE001 -- not an archive, or not one zipfile lists
        return


def _where_kind(finding: Dict) -> str:
    """Where a finding points, by the last step of its route -- a name from
    this tool's own list, never the subject the file supplied."""
    route = finding.get("path") or []
    last = route[-1] if route else None
    return last if last in PATH_STEPS else "none"


def _counted(summary: Dict) -> Dict:
    """The report's summary as numbers: a count or a flag is kept, a list is
    kept as how long it is -- its entries name places in the file -- and a
    string is not kept at all."""
    kept = {}
    for key, value in summary.items():
        if isinstance(value, (bool, int)):
            kept[key] = value
        elif isinstance(value, list):
            kept[key] = len(value)
    return kept


def outcome(report: Optional[Dict], exit_code: int, seconds: float) -> Dict:
    """What the run said, by rule id and count; no finding's words."""
    findings: Dict[str, Dict] = {}
    for f in (report or {}).get("findings", []):
        slot = findings.setdefault(f["rule"], {
            "severity": f["severity"], "count": 0,
            "whereKinds": dict.fromkeys(list(PATH_STEPS) + ["none"], 0)})
        slot["count"] += 1
        slot["whereKinds"][_where_kind(f)] += 1
    summary = (report or {}).get("summary", {})
    return {
        "exitCode": exit_code,
        # Whole seconds, rounded up: how long, and no clock -- a run that takes
        # a fraction of a second says 1 every time, so the bundle stays the same bytes.
        "wallSeconds": math.ceil(seconds),
        "findings": findings,
        "summary": _counted(summary),
        # The JSON report lists every finding, and so does this -- unless
        # what fired would take the bundle past its limit, when the rules
        # that fired least are left out and their findings counted here.
        "notListed": 0,
        "scopeNotExamined": len(summary.get("scopeNotExamined", [])),
        "rulesNotAsked": len(summary.get("rulesNotAsked", [])),
        # The reader's own bound on how much it takes in, where it was met.
        "budgets": {"hit": sorted({"X5"} & set(findings))},
    }


def failure(exc: BaseException) -> Dict:
    """The type, and the frames inside this package: file, line and function,
    which are public code. The message is not taken -- it quotes values -- only
    its hash, so that two bundles from one defect can be told to be one."""
    frames = []
    for frame in traceback.extract_tb(exc.__traceback__):
        try:
            rel = Path(frame.filename).resolve().relative_to(_PACKAGE)
        except (ValueError, OSError):
            continue
        frames.append({"file": (Path(_PACKAGE.name) / rel).as_posix(),
                       "line": frame.lineno, "func": frame.name})
    return {"type": type(exc).__name__, "tracebackFrames": frames,
            "messageSha256": _sha256(str(exc).encode("utf-8", "replace"))}


def invocation(options: List[str], *, inputs: int, note: bool, out: bool,
               template: bool, example: bool) -> Dict:
    """What was asked for, rebuilt from the parsed options rather than copied
    from the command line: option names and the values they choose from, and a
    place-holder wherever a path or a sentence of the user's stood. Copied, a
    path written as `--bundle-out=DIR` or an option cut short would come
    through whole."""
    shown = ["smtv", *sorted(options)]
    if template:
        shown += ["--template", "<path-1>"]
    if note:
        shown += ["--note", "<note>"]
    if out:
        shown += ["--bundle-out", "<out-1>"]
    if example:
        shown.append("--example")
    shown += ["<input-%d>" % n for n in range(1, inputs + 1)]
    return {"argv": shown, "env": sorted(name for name in ENVIRONMENT if name in os.environ)}


def _engine() -> Dict:
    """The metamodel library this run read the file with, and its release."""
    version = ""
    try:
        from importlib import metadata
        for distribution in metadata.distributions():
            if (distribution.metadata.get("Name") or "").lower() == "aas-core3.0":
                version = distribution.version
                break
    except Exception:                       # noqa: BLE001 -- a bundle without the version is still a bundle
        version = ""
    return {"name": "aas-core3.0", "version": version}


def build(*, path: Optional[str], options: List[str], report: Optional[Dict],
          exit_code: int, seconds: float, trigger: str, note: Optional[str] = None,
          out: Optional[str] = None, template: bool = False, example: bool = False,
          error: Optional[BaseException] = None) -> Dict:
    from . import __version__
    bundle = {
        "bundle": {
            "bundleSchema": SCHEMA, "tool": TOOL, "toolVersion": __version__,
            "engine": _engine(),
            "python": {"version": platform.python_version(),
                       "implementation": platform.python_implementation()},
            "platform": {"system": platform.system(), "release": platform.release(),
                         "machine": platform.machine()},
            "console": {"encoding": getattr(sys.stdout, "encoding", None) or ""},
            "trigger": trigger,
        },
        "invocation": invocation(options, inputs=0 if example else 1, note=note is not None,
                                 out=out is not None, template=template, example=example),
        "input": fingerprint(path),
        "run": outcome(report, exit_code, seconds),
    }
    if error is not None:
        bundle["error"] = failure(error)
    if note:
        note = _as_text(note)
        kept = note if len(note) <= NOTE_LIMIT else (
            note[:NOTE_LIMIT] + f" [cut at {NOTE_LIMIT:,} characters]")
        bundle["user"] = {"note": kept}
    bundle["readable"] = readable(bundle)
    return _within_limit(bundle)


#: Rules named in the summary line, the most frequent first; past these, how many more.
READABLE_RULES = 20


def readable(bundle: Dict) -> str:
    run, shape = bundle["run"], bundle["input"]
    ranked = sorted(run["findings"].items(), key=lambda item: (-item[1]["count"], item[0]))
    fired = ", ".join("%s x%d" % (rule, slot["count"])
                      for rule, slot in ranked[:READABLE_RULES]) or "none"
    if len(ranked) > READABLE_RULES:
        fired += ", and %d more rule ids" % (len(ranked) - READABLE_RULES)
    if run["notListed"]:
        fired += "; %d findings of rules not listed here" % run["notListed"]
    lines = [
        "%s %s on Python %s (%s), trigger: %s" % (
            bundle["bundle"]["tool"], bundle["bundle"]["toolVersion"],
            bundle["bundle"]["python"]["version"], bundle["bundle"]["platform"]["system"],
            bundle["bundle"]["trigger"]),
        "input: %s, %s, %d members" % (
            shape["kind"], "size unknown" if shape["size"] is None else "%d bytes" % shape["size"],
            shape["members"]["count"]),
        "exit code %d; findings: %s" % (run["exitCode"], fired),
        "not examined: %d; rules not asked: %d; budgets hit: %s" % (
            run["scopeNotExamined"], run["rulesNotAsked"],
            ", ".join(run["budgets"]["hit"]) or "none"),
    ]
    if "error" in bundle:
        lines.append("stopped by %s in this tool" % bundle["error"]["type"])
    return "\n".join(lines)


#: Stands where the member rows go while the rest is laid out.
_ROWS_HERE = "\u0000rows\u0000"


def dumps(bundle: Dict) -> str:
    """Laid out for a person to read, with each member's row on a line of its own."""
    rows = bundle["input"]["members"]["rows"]
    held = {**bundle, "input": {**bundle["input"],
                                "members": {**bundle["input"]["members"], "rows": _ROWS_HERE}}}
    text = json.dumps(held, sort_keys=True, indent=2, ensure_ascii=False)
    lines = ",\n".join("        " + json.dumps(row, separators=(",", ":")) for row in rows)
    block = "[\n" + lines + "\n      ]" if rows else "[]"
    return text.replace(json.dumps(_ROWS_HERE), block) + "\n"


def _as_text(note: str) -> str:
    """The note as UTF-8 can carry it. A byte the locale could not decode -- a
    name typed in Latin-1, Korean from a script saved in CP949 -- arrives as a
    lone surrogate, which UTF-8 cannot encode; it goes out as U+FFFD."""
    try:
        raw = note.encode("utf-8", "surrogateescape")
    except UnicodeEncodeError:
        raw = note.encode("utf-8", "replace")
    return raw.decode("utf-8", "replace")


def _largest(count: int, fits) -> int:
    """The largest n in 0..count for which `fits(n)` holds, `fits` holding for
    every n below one it holds for."""
    low, high = 0, count
    while low < high:
        middle = (low + high + 1) // 2
        if fits(middle):
            low = middle
        else:
            high = middle - 1
    return low


def _within_limit(bundle: Dict) -> Dict:
    """Past the limit, member rows go first -- as many kept as fit, and the
    count stays -- then the rules that fired least, their findings counted in
    `notListed`. A caller's template can declare ten thousand rows, and every
    one of them can fire."""
    def fits(_n=None) -> bool:
        return len(dumps(bundle).encode("utf-8")) <= LIMIT
    if fits():
        return bundle
    members = bundle["input"]["members"]
    rows = members["rows"]

    def keep_rows(n: int) -> bool:
        members["rows"], members["listed"] = rows[:n], n
        return fits()
    keep_rows(_largest(len(rows), keep_rows))
    if fits():
        return bundle
    run = bundle["run"]
    ranked = sorted(run["findings"].items(), key=lambda item: (-item[1]["count"], item[0]))

    def keep_rules(n: int) -> bool:
        run["findings"] = dict(ranked[:n])
        run["notListed"] = sum(slot["count"] for _rule, slot in ranked[n:])
        bundle["readable"] = readable(bundle)
        return fits()
    keep_rules(_largest(len(ranked), keep_rules))
    return bundle


def file_name(bundle: Dict) -> str:
    sha = bundle["input"]["sha256"] or _sha256(b"")
    return "bug-report-%s-%s-%s.json" % (TOOL, bundle["bundle"]["toolVersion"], sha[:8])


def write(bundle: Dict, out_dir: Optional[str]) -> Path:
    """Written beside its name and moved over it, never written through it:
    the name is predictable from the input's hash, and one planted in a shared
    directory as a link to somebody's file would otherwise have that file
    overwritten with this one. `os.replace` replaces the link itself."""
    folder = Path(out_dir or ".")
    target = folder / file_name(bundle)
    handle, temporary = tempfile.mkstemp(prefix=".bug-report-", suffix=".tmp", dir=str(folder))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(dumps(bundle))
        os.replace(temporary, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise
    return target
