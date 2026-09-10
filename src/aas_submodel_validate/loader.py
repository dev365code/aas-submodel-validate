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

import codecs
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
    OutOfMemory,
    PartTooLarge,
    RefusedContent,
    UnreadablePart,
    declares_doctype,
    ran_out_of_memory,
    xml_as_utf8,
)

#: What a refusal concludes, after the sentence saying why it refused: the
#: words the stop sentences below end on, for the refusals that are not
#: stops. Five of them said more than a refusal knows -- "Nothing is wrong
#: with what you sent", "Nothing is wrong with the syntax", "The chain
#: itself is intact" -- of a document this reader had declined to read,
#: and the last was measured false. One constant for the five, since
#: copies of a sentence are how they came to say different things.
REFUSED_NOT_JUDGED = "Nothing here is a verdict on the document -- it was refused, not judged."

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
    "to. %s" % REFUSED_NOT_JUDGED)


def directory_bound_remedy() -> str:
    """Built when the finding is, for the reason `_bounds_remedy` gives:
    the sentence names the bound this run applied, and a number frozen at
    import time disagrees with the one that refused the file."""
    return ("This reader indexes no archive whose directory of names "
            "comes to more than %d MiB -- a ZIP is indexed whole before "
            "any of it is read, so the cost is paid on the names alone, "
            "however little the entries hold. Remove what the package "
            "does not need to carry. %s"
            % (container.MAX_DIRECTORY_BYTES // 1024 ** 2, REFUSED_NOT_JUDGED))


RELATIONSHIP_DOCTYPE_REMEDY = (
    "Remove the DTD from the named relationships part and write out "
    "whatever it declared: a nested-entity DTD is a decompression-free "
    "way to exhaust a reader, so this one refuses the declaration rather "
    "than bound what it expands to. %s" % REFUSED_NOT_JUDGED)

class UnreadablePath(Exception):
    """Nothing could be read from the path at all: absent, or not permitted.

    It carries its own remedy. Every refusal here has a different one and
    they are not interchangeable: an author told to re-create an archive
    because the file is merely unreadable goes and rebuilds a document
    that was never wrong. Reporting this reader's difficulty as the
    author's defect is what X5 was written to stop, and this is the same
    sentence about the path instead of the payload.
    """

    def __init__(self, message, fix=None):
        super().__init__(message)
        self.fix = fix


@dataclass(frozen=True)
class LoadError:
    """One thing that went wrong on the way in, as data.

    `stage` says which link failed -- "zip" (not a container), "chain"
    (the OPC relationships), "payload" (a part that would not parse),
    "bounds" (refused for size, X5's stage) -- and the container rules
    map stages to findings.
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


#: Refusals that belong to this interpreter rather than to the document.
#: Two hundred thousand open brackets is well-formed JSON and
#: `json.loads` raises `RecursionError` on it; Python 3.11 refuses to
#: build an integer from more than `sys.get_int_max_str_digits()` digits
#: and raises a bare `ValueError`. Neither is a defect anybody can go and
#: fix, and both arrived as "the file is not JSON" with a remedy telling
#: the reader to open the document and correct the syntax its parser
#: rejects. There is no syntax to correct: the reader is sent looking for
#: something that is not there.
#:
#: Told apart by type. `json.JSONDecodeError` is itself a `ValueError`
#: and is the one failure here that really is about the document, so the
#: test is "a ValueError that is not a decode error" -- the message is
#: upstream prose and not ours to pattern-match. The digit limit arrived in 3.11 and
#: the 3.9.14 and 3.10.7 security releases, not before, which is why this is a classifier with no version
#: in it rather than a fixture that can only run on some of them.
#:
#: What the reader is told says only what is known: that this reader
#: stopped before the end of the document, and why. It used to say "This
#: document is JSON ... Nothing is wrong with what you sent", and neither
#: is known about a document nobody read to the end -- a thousand
#: brackets followed by text that is not JSON at all stops the parser at
#: the brackets, and was told both.
_STOPPED_BECAUSE = {
    "nesting": "it nests deeper than this interpreter's stack will follow",
    "number": "it carries a number longer than this interpreter will convert",
    "memory": "it needed more memory than this reader had",
}


def limit_remedy(reason: str, *, building: bool) -> str:
    """The remedy for a document this reader stopped short on.

    Two shapes, because there are two places to stop. Reading, the reader
    has not seen the rest of the document. Building, it has read all of it
    -- `json.loads` took the whole text -- and stopped turning it into the
    metamodel; "what comes after was not read" is false there, and what
    was not done is the checking."""
    if building:
        return ("This reader read the document to the end and stopped "
                "building it: %s. The rest was not built or checked, and "
                "nothing here is a verdict on the document -- it was refused, "
                "not judged." % _STOPPED_BECAUSE[reason])
    return ("This reader stopped before the end of the document: %s. The "
            "rest was not read, and nothing here is a verdict on the "
            "document -- it was refused, not judged." % _STOPPED_BECAUSE[reason])


#: For bytes that end halfway through a character: a copy or a download
#: that stopped early, not a file saved in the wrong encoding.
CUT_SHORT = (
    "The bytes end in the middle of a character, the way a copy or "
    "download that stopped early leaves a file. Send the whole file "
    "again; what arrived was not judged.")

#: The same bytes inside a package mean something else. An archive cut
#: short fails as an archive before any part is read, and a part that is
#: read has matched the archive's own checksum -- so these are the bytes the
#: packaging tool wrote, and sending the package again brings the same ones.
CUT_SHORT_IN_A_PACKAGE = (
    "This part ends in the middle of a character, and it matched the "
    "archive's own checksum: these are the bytes the packaging tool "
    "wrote, so sending the package again brings the same ones. Rebuild "
    "the package from a complete document; what arrived was not judged.")


#: For bytes that do not decode. Not the standing advice X3 gives -- "fix
#: the syntax its parser rejects" -- because there is no syntax to fix, and
#: 0.1.0 already recorded that sentence as wrong for an encoding problem,
#: one format over. Not the limit sentence either: something *is* wrong
#: with what was sent.
#:
#: And no more than that. It ended "and nothing else has to change", of a
#: document decoded as far as its first bad byte: one with a syntax error
#: further on was told so, and learned otherwise only after saving it
#: again. It also pointed at "the line above", which on the screen is the
#: clause and not the position. A package's part is not fixed by saving
#: the file, as the cut-short pair below says too.
NOT_UTF8 = (
    "JSON exchanged between systems is UTF-8 (RFC 8259, 8.1), and "
    "these bytes are not: decoding stopped at the position this "
    "finding names. Save the file as UTF-8 -- an editor's UTF-16 or "
    "ANSI setting is the usual cause. Nothing after that position was "
    "decoded, and nothing in the document was judged.")

NOT_UTF8_IN_A_PACKAGE = (
    "JSON exchanged between systems is UTF-8 (RFC 8259, 8.1), and "
    "this part is not: decoding stopped at the position this finding "
    "names. Save the document as UTF-8 and rebuild the package from "
    "it -- an editor's UTF-16 or ANSI setting is the usual cause. "
    "Nothing after that position was decoded, and nothing in the "
    "document was judged.")


def _is_an_interpreter_limit(exc) -> bool:
    """Whether this failure is ours rather than the document's.

    A bare `ValueError` is one of ours: the integer-digit limit. Its two
    subclasses that reach here are not. `JSONDecodeError` is bad syntax,
    and `UnicodeDecodeError` -- raised a step earlier, decoding the
    bytes -- is a file that is not UTF-8, which JSON exchanged between
    systems has to be (RFC 8259, 8.1). Counting the second as ours told
    its author that nothing was wrong with what they sent.
    """
    if isinstance(exc, (RecursionError, MemoryError)):
        return True
    return isinstance(exc, ValueError) and not isinstance(
        exc, (json.JSONDecodeError, UnicodeError))


def _cut_short(exc) -> bool:
    """Whether the bytes stop halfway through a character: the undecodable
    stretch reaches the end of the input and is the start of a character
    that has not finished. Asked of the bytes with the codec's own
    incremental decoder, not of the codec's message -- the reason string is
    upstream prose, which this module does not pattern-match."""
    if exc.end != len(exc.object):
        return False
    try:
        codecs.getincrementaldecoder("utf-8")().decode(exc.object[exc.start:], final=False)
    except UnicodeDecodeError:
        return False
    return True


def _out_of_room(exc, *, building: bool):
    """(message, remedy) where this interpreter ran out of stack or memory,
    or None. Its two limits, asked of either format: neither is something
    the document's author can go and fix, whatever the document is."""
    if isinstance(exc, RecursionError):
        return ("this reader could not build the document",
                limit_remedy("nesting", building=building))
    if ran_out_of_memory(exc):
        return ("this reader could not build the document",
                limit_remedy("memory", building=building))
    return None


def _failure(exc, *, decoding: bool, packaged: bool = False):
    """(message, remedy) for a JSON document that could not be read, or None
    where the failure is the document's and the rule's standing advice holds.

    One answer for every place a JSON document is read -- a bare file, a
    bare Submodel, the payload of a package -- so the same failure gets the
    same answer wherever it happens. `decoding` says which step raised:
    running out of stack or memory is this interpreter's at either step,
    but a `ValueError` is the digit limit, and a `UnicodeDecodeError` is
    about the bytes, only while the bytes are being decoded. Raised while
    building the environment they are the document's: a Blob value that is
    not base64 raises a `ValueError`, or a `UnicodeEncodeError` where it is
    not ASCII.
    """
    stopped = _out_of_room(exc, building=not decoding)
    if stopped is not None:
        return stopped
    if not decoding:
        return None
    if _is_an_interpreter_limit(exc):
        return "this reader could not build the document", limit_remedy("number", building=False)
    if isinstance(exc, UnicodeDecodeError):
        if _cut_short(exc):
            return "the file is not JSON", CUT_SHORT_IN_A_PACKAGE if packaged else CUT_SHORT
        return "the file is not JSON", NOT_UTF8_IN_A_PACKAGE if packaged else NOT_UTF8
    return None


#: What to do about an operating system saying no, by what it said.
#: Derived from the error and never from the extension: the same denial
#: reached `.aasx` through the container reader and `.json` through this
#: one, and an extension is not a reason.
def _access_remedy(exc) -> str:
    if isinstance(exc, PermissionError):
        return ("Check that this file and every directory above it are "
                "readable by the account running this. Nothing here is a "
                "defect in the document -- it was not read, so it was not "
                "judged.")
    if isinstance(exc, MemoryError):
        return ("This reader ran out of memory before it could read the "
                "path. %s" % REFUSED_NOT_JUDGED)
    return ("The operating system refused this path (%s). Nothing here is "
            "a defect in the document -- it was not read, so it was not "
            "judged." % type(exc).__name__)


def _cannot_reach(path, exc) -> UnreadablePath:
    """The refusal for an operating system saying no about a path.

    Two callers: bounding a read, and asking whether there is a file to
    read at all. Both meet the same family of answers -- a directory the
    process cannot traverse, a stale handle, a name too long for the
    filesystem, a symlink loop -- and both owe the reader the same
    sentence, because from where they stand it is the same fact. Built
    in one place so they cannot drift into two sentences about it.
    """
    return UnreadablePath("cannot read %s: %s: %s"
                          % (path, type(exc).__name__, exc),
                          fix=_access_remedy(exc))


@dataclass
class Loaded:
    path: str
    form: str                     # aasx | environment-json | environment-xml | submodel-json
    submodels: List[types.Submodel] = field(default_factory=list)
    #: Every environment document this input held, in the order the
    #: parts were read. A field rather than one slot: an AASX may
    #: declare more than one aas-spec part, and assigning a single
    #: `environment` per part meant each overwrote the one before it --
    #: so the relayed metamodel channel, which verifies environments,
    #: saw only the last. Its findings for every earlier part vanished
    #: with `complete` still true, because the template rules had walked
    #: them and only the relay was blind.
    environments: List[types.Environment] = field(default_factory=list)
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
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        # `utf-8-sig` counts from after the byte order mark it removed, and
        # the reader is told the position to look at in the file.
        if raw.startswith(codecs.BOM_UTF8) and len(exc.object) == len(raw) - 3:
            raise UnicodeDecodeError(exc.encoding, raw, exc.start + 3, exc.end + 3,
                                     exc.reason) from None
        raise


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
        raise _cannot_reach(path, exc) from exc
    if len(raw) > cap:
        loaded.errors.append(LoadError(
            "bounds", "%s: more than %d bytes" % (path, cap), subject=str(path)))
        return None
    return raw


def _payload_error(loaded: Loaded, part: Optional[str], exc, answered) -> None:
    """An environment document that did not come out, with the answer
    `_failure` or `_out_of_room` gave, or the standing one where they gave
    none."""
    message, fix = answered or ("the document could not be read as an AAS environment", None)
    loaded.errors.append(LoadError(
        "payload", message, subject=part or loaded.path,
        detail="%s: %s" % (type(exc).__name__, exc), fix=fix))


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
        #
        # And it is a copy of the whole document where it converts one, so
        # it can run out of memory where the parse below would have: a
        # UTF-16 document that did left by a traceback. Asked only that --
        # anything else this raises is a defect of ours, not the file's.
        try:
            raw = xml_as_utf8(raw)
            refused = declares_doctype(raw)
        except MemoryError as exc:
            _payload_error(loaded, part, exc, _out_of_room(exc, building=False))
            return
        except PartTooLarge as exc:
            # The document's UTF-8 form is over the bound. Its bytes on disk
            # were under it -- UTF-16 is narrower than UTF-8 for the CJK it
            # holds -- so `_read_bounded` and the container's own read let it
            # by, and the size shows only once it is converted the way the
            # parser reads it. Recorded as `_read_bounded` records a bound,
            # with no fix of its own, so X5 gives the per-form remedy.
            loaded.errors.append(LoadError(
                "bounds", str(exc), subject=part or loaded.path))
            return
        if refused:
            loaded.errors.append(LoadError(
                "payload", "the XML declares a DOCTYPE, which is refused",
                subject=part or loaded.path,
                fix=PAYLOAD_DOCTYPE_REMEDY))
            return
    decoding = True
    try:
        if form.endswith("json"):
            if document is None:
                document = json.loads(_decode(raw))
            decoding = False
            environment = jsonization.environment_from_jsonable(document)
        else:
            environment = xmlization.environment_from_str(_decode(raw))
    except Exception as exc:
        # Asked the way `_load_json` asks it of a bare file (`_failure`), so
        # the same failure gets the same answer zipped or not.
        #
        # XML is asked only about this interpreter's limits. It is read and
        # built in one pass -- aas-core3.0 builds each element as the parser
        # reaches it -- so a stop is a stop before the end, and a syntax
        # error past that point is never seen: 350 collections, one inside
        # the next, were told to fix the syntax their parser rejects. No
        # encoding branch: XML declares its own encoding, and a failure to
        # decode it is the document's, as any other failure to parse is.
        if form.endswith("json"):
            answered = _failure(exc, decoding=decoding, packaged=part is not None)
        else:
            answered = _out_of_room(exc, building=False)
        _payload_error(loaded, part, exc, answered)
        return
    loaded.environments.append(environment)
    loaded.submodels.extend(environment.submodels or [])


def load(path) -> Loaded:
    path = Path(path)
    if str(path) == "-":
        # Half the tools on a machine read standard input when given
        # this, and this one does not: it seeks inside archives and
        # bounds what it reads before reading it, neither of which a
        # pipe allows. "no such file: -" is true and teaches nothing --
        # a reader cannot tell a tool that has no such feature from one
        # that lost the file.
        raise UnreadablePath(
            "this reader does not take standard input: it seeks inside "
            "containers and bounds what it reads before reading it. "
            "Give it a path")
    # Whether there is a file to read at all is one question, asked once,
    # before the extension decides anything. Asking it inside each branch
    # is how a directory came to exit 2 when it was called .xml and 1 --
    # a defect in a file nobody had opened -- when it was called .json.
    #
    # And asking it can fail. `Path.exists()` raises when the parent
    # cannot be traversed, and neither question was guarded: a file
    # dropped into a directory whose mode the exporter set, or on a share
    # the build user cannot enter, left the process by 1 with nothing on
    # stdout and a raw `PermissionError` traceback -- 1 being the code
    # for a verdict with findings, over a file nobody had opened. The
    # same confusion `_read_bounded` has guarded against since it was
    # written, one layer earlier and with the same remedy: this reader
    # could not reach it, so it was refused rather than judged.
    #
    # `OSError` and not `PermissionError`. A locked directory is what a
    # reader meets, and a stale handle, a name too long for the
    # filesystem and a symlink loop reach these same two calls as other
    # members of the same family.
    try:
        there, a_file = path.exists(), path.is_file()
    except OSError as exc:
        raise _cannot_reach(path, exc) from exc
    if not there:
        raise UnreadablePath(
            "no such file: %s" % path,
            fix="Check the path. Nothing was opened, so nothing here is a "
                "statement about a document.")
    if not a_file:
        raise UnreadablePath(
            "not a file: %s" % path,
            fix="Point this at a file rather than at a directory. Nothing "
                "was opened, so nothing here is a statement about a "
                "document.")
    # And whether it opens, asked in the same place and for the same
    # reason. It was asked by whichever reader the extension chose, and
    # they answer differently: an unreadable `.aasx` reached
    # `AasxPackage`, which cannot tell a permission denial from a
    # malformed archive and reported one -- so its author was told to
    # re-create a package that was never wrong, which is the remedy X5
    # exists to refuse. The same file named `.json` reached the JSON
    # reader and raised.
    #
    # One byte, so a large file is not read to find out, and closed at
    # once.
    try:
        with open(path, "rb") as probe:
            probe.read(1)
    except OSError as exc:
        raise _cannot_reach(path, exc) from exc

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
    raise UnreadablePath(
        "cannot tell what %s is: expected .aasx, .json or .xml" % path,
        fix="Name the file .aasx for a package, .json or .xml for an AAS "
            "environment or a bare Submodel. The extension is how the "
            "format is chosen here; the contents were not looked at.")


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
        message, fix = _failure(exc, decoding=True) or ("the file is not JSON", None)
        loaded.errors.append(LoadError(
            "payload", message, subject=str(path),
            detail="%s: %s" % (type(exc).__name__, exc), fix=fix))
        return loaded

    if isinstance(document, dict) and document.get("modelType") == "Submodel":
        loaded.form = "submodel-json"
        try:
            loaded.submodels.append(jsonization.submodel_from_jsonable(document))
        except Exception as exc:
            message, fix = (_failure(exc, decoding=False)
                            or ("the document could not be read as a Submodel", None))
            loaded.errors.append(LoadError("payload", message, subject=str(path),
                                           detail="%s: %s" % (type(exc).__name__, exc),
                                           fix=fix))
        return loaded

    _parse_environment(loaded, raw, part=None, form="environment-json",
                       document=document)
    return loaded


def _ran_out(exc, subject=None) -> LoadError:
    """A package this reader ran out of memory reading, as X5's error.

    X5's because the question is X5's -- whether the input fits in what
    this reader will take in -- and with the sentence a document it stops
    short on gets anywhere else: that it stopped, where, and why, and
    nothing about the rest. One place, for the four places a package is
    read from. Where is the stop's own to say -- a relationships part
    parsed to its end and stopped while its targets were resolved was read,
    and told otherwise."""
    return LoadError("bounds", str(exc), subject=subject,
                     fix=limit_remedy("memory", building=exc.building))


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
    except OutOfMemory as exc:
        loaded.errors.append(_ran_out(exc, subject=str(path)))
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
    except OutOfMemory as exc:
        loaded.errors.append(_ran_out(exc))
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
        except OutOfMemory as exc:
            loaded.errors.append(_ran_out(exc, subject=part))
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
        #
        # Filed under the relationships part, which is what was refused.
        # Under the payload's name, the report judged a document and said
        # beside it that the same document was refused and not judged.
        rels = container.relationships_part_name(part)
        try:
            package.relationships(part)
        except PartTooLarge as exc:
            loaded.errors.append(LoadError("bounds", str(exc), subject=rels))
        except OutOfMemory as exc:
            loaded.errors.append(_ran_out(exc, subject=rels))
        except UnreadablePart as exc:
            loaded.errors.append(LoadError("zip", str(exc), subject=rels))
        except NoRelationships:
            pass        # this part declares none, which is not a defect
        except RefusedContent as exc:
            loaded.errors.append(LoadError("chain", str(exc), subject=rels, fix=RELATIONSHIP_DOCTYPE_REMEDY))
        except ContainerError as exc:
            # Would not parse. Quiet here until now for sharing an
            # exception type with "declares none" above, which left a
            # container this reader would not read coming back `ok`.
            loaded.errors.append(LoadError("chain", str(exc), subject=rels))
        form = "environment-json" if part.lower().endswith(".json") else "environment-xml"
        _parse_environment(loaded, raw, part=part, form=form)
    return loaded
