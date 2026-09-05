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

import codecs
import posixpath
import re
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

#: And the archive's own account of itself, which costs before either of
#: the caps above applies. `zipfile` builds one record per name the
#: central directory declares, inside `ZipFile()`, while nothing has been
#: decompressed and no part has been chosen. Measured on an archive that
#: is otherwise perfect -- valid chain, conformant payload, a full
#: verdict, only real template findings -- 800,000 empty entries weigh
#: 68.7 MiB on disk and 523 MiB in memory: about thirteen times the
#: directory's own bytes, linear, with no ceiling.
#:
#: The bound is on those bytes and not on the entry count, because the
#: count is a number the file carries and nothing checks: understating it
#: in the record and leaving the directory alone builds every entry
#: anyway. The size is what `zipfile` acts on -- it reads exactly that
#: many bytes and stops -- so understating *it* costs the attacker the
#: entries they were trying to smuggle.
#:
#: A quarter of the single-part cap, in the same proportion
#: `MAX_TOTAL_PART_BYTES` uses: thirteen times 16 MiB is about 208 MiB,
#: under the 256 MiB this reader already lets a container's parts
#: deliver. It admits a package declaring roughly 150,000 parts at
#: sixty-character names; the two official example containers declare 13
#: and 16, for directories of 1,119 and 1,331 bytes.
MAX_DIRECTORY_BYTES = MAX_PART_BYTES // 4

#: What zipfile raises for an archive it cannot make sense of.
#:
#: Named once because it was written twice and the two disagreed. Opening
#: the archive listed two of these; reading a part listed six. The
#: difference was reachable: the version an entry says it needs is read
#: while the *directory* is, inside `ZipFile()` itself, so a two-byte edit
#: to any .aasx raised `NotImplementedError` past every handler in this
#: project and printed a traceback -- against the one thing this reader
#: promises about hostile input, which is that a container defect is a
#: finding.
#:
#: Deliberately not `Exception`. A defect in this reader must not arrive
#: dressed as a defect in the supplier's file.
UNREADABLE = (zipfile.BadZipFile, NotImplementedError, RuntimeError,
              EOFError, OSError, zlib.error, ValueError)
# `ValueError` is here for `UnicodeDecodeError`, which is one of its
# children. An entry name written in a legacy code page with the header
# bit that claims UTF-8 set anyway -- what a packager on a Korean or
# Japanese Windows produces -- raised it past every handler, so a file
# nothing had read left by 1, which is the code for a verdict with
# findings. The comment above describes the same shape one exception
# family over, and the repair then named the family rather than the
# question. The question is "can this reader open it", and anything
# raised while trying is an answer to that.

#: Byte order marks, longest first, because a UTF-32 mark begins with a
#: UTF-16 one and the order is what tells them apart.
#:
#: The UTF-32 rows are here to be *recognised*, not read. The parser
#: refuses UTF-32 whether it is marked or not, so decoding it here would
#: admit documents nothing else in the ecosystem will open -- and a
#: validator calling a file conformant that no other reader can parse has
#: done the worst thing it can do. Dropping the rows instead is not an
#: option either: `FF FE 00 00` would then match the UTF-16 mark two rows
#: below and be read as something it is not.
#:
#: The UTF-16 rows name `utf-16` rather than a byte order, because that
#: codec consumes the mark it just matched on. `utf-16-le` leaves it
#: behind as U+FEFF, in the one position where a leading character
#: changes what the rest of this module is looking at.
#: A UTF-8 mark is recognised for the same reason and read for none: the
#: bytes behind it already are what everything downstream wants, and the
#: parser skips the mark itself. Every official AASX in the corpus is
#: marked UTF-8, so this is the row most documents take -- and the one
#: where doing nothing is the whole job.
_BOMS = ((b"\xff\xfe\x00\x00", None), (b"\x00\x00\xfe\xff", None),
         (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16"),
         (b"\xef\xbb\xbf", None))

#: An encoding declaration that survived a decode would contradict the
#: bytes it is attached to, so it goes with the encoding it named.
#:
#: Anchored, because `count=1` takes the first match *anywhere*. A
#: document carrying a byte order mark and no declaration -- the shape
#: the official 02003 payload has -- offers no prolog to match, so the
#: first `encoding="..."` in its content was being deleted instead. This
#: project reads what it is given and transforms nothing (docs/scope.md).
_DECLARED_ENCODING = re.compile(
    r'\A(﻿?<\?xml[^?>]*?)\s+encoding\s*=\s*(["\'])[^"\']*\2')

#: The name itself, which the pattern above deliberately does not
#: capture -- it exists to remove the declaration, not to read it. The
#: first `=` in a prolog belongs to `version`, so taking the text after
#: it reads `1.0` and calls that an encoding.
_ENCODING_NAME = re.compile(
    r'\A﻿?<\?xml[^?>]*?\s+encoding\s*=\s*(["\'])(?P<name>[^"\']+)\1')


def _sniff(raw: bytes):
    """The encoding the parser will take an unmarked document for, or None.

    XML requires a byte order mark on UTF-16 and the parser does not
    insist, autodetecting instead -- so a document can be UTF-16 to the
    parser and opaque bytes to every guard below it. That is how a
    `<!DOCTYPE` written UTF-16 walked past a pattern that only ever
    matches UTF-8, and had its entities expanded by the parser that was
    supposed to never see it.

    Decided on the *shape* of the first four bytes, not on what they are.
    Keying on the document beginning with `<` is keying on the fixtures: a
    document may open with whitespace, a comment or a processing
    instruction, and may carry no declaration at all. Four bytes, not two,
    because unmarked UTF-32-LE also begins `3C 00` -- reading it as UTF-16
    would hand the parser text riddled with nulls and claim to understand
    an encoding it refuses.
    """
    if len(raw) < 4:
        return None
    null = tuple(byte == 0 for byte in raw[:4])
    # Named rather than folded into the fall-through below, and it does
    # not change the answer: neither UTF-32 shape equals either UTF-16
    # shape, so deleting these two lines leaves them reaching the same
    # `return None` at the end. What actually separates the two families
    # is asking four bytes instead of two -- `3C 00` opens both. This
    # says which four-byte shapes were considered and rejected, so that a
    # later reader does not have to re-derive it from the ones that were
    # accepted.
    if null in ((False, True, True, True), (True, True, True, False)):
        return None                                 # unmarked UTF-32
    if null == (False, True, False, True):
        return "utf-16-le"
    if null == (True, False, True, False):
        return "utf-16-be"
    return None


def xml_as_utf8(raw: bytes) -> bytes:
    """One XML document as UTF-8, decided the way the parser decides it.

    Everything downstream reads these bytes. If this disagrees with the
    parser about what the document says, every guard below is inspecting a
    different document from the one that gets parsed -- which is the whole
    defect this exists to close. Bytes that cannot be decoded as the
    encoding they claim come back untouched: the parser will refuse them
    too, and refusing here instead would be this reader inventing a
    verdict.

    Untouched is the common case and the intended one. Only a document
    the parser reads as UTF-16 is rewritten, because only there do the
    bytes downstream needs differ from the bytes that arrived.
    """
    for bom, encoding in _BOMS:
        if raw.startswith(bom):
            if encoding is not None:
                return _as_utf8(raw, encoding)
            # A UTF-8 mark says the bytes after it are UTF-8, and a
            # document may still declare something else -- ill-formed by
            # XML 1.0, and read by every parser, which is the standard
            # this function set for itself. Repairing only the branch
            # with no mark left a marked `ISO-8859-1` document refused,
            # with the same wrong remedy the repair was written to
            # remove.
            #
            # The mark comes off first. Left on, it decodes to three
            # stray characters in front of the prolog, the pattern that
            # strips the declaration no longer matches, and the bytes
            # go downstream as UTF-8 still claiming to be something
            # else -- which the parser then refuses for a different
            # reason than the one it arrived with.
            converted = _as_declared(raw[len(bom):])
            return converted if converted is not raw[len(bom):] else raw
    encoding = _sniff(raw)
    if encoding is not None:
        return _as_utf8(raw, encoding)
    return _as_declared(raw)


def _as_declared(raw: bytes) -> bytes:
    """A document that names its own encoding, decoded as it says.

    Without this the declaration was dropped and the bytes went on to a
    `utf-8` decode that raised, so an `ISO-8859-1` document carrying one
    accented character came back as "could not be read as an AAS
    environment" -- with a remedy telling the author to fix syntax that
    is not wrong. ElementTree reads it, aas-core3 reads it, and the
    docstring above says this is decided the way the parser decides it.
    UTF-32 is refused by that same standard and stays refused; the
    legacy code pages were in neither list, which is what made this a
    gap rather than a choice. German-language industrial documents are
    the likeliest place for one.

    Only the prolog is consulted, and only when it is ASCII -- which it
    must be, since a parser has to read the declaration before it knows
    the encoding.
    """
    # Long enough for a prolog nobody would write by hand: XML 1.0
    # bounds nothing here, and a 200-byte window silently stopped
    # reading a declaration a parser reads.
    declared = _ENCODING_NAME.match(raw[:4096].decode("ascii", "ignore"))
    if declared is None:
        return raw
    name = declared.group("name")
    if not name or name.lower().replace("_", "-") in ("utf-8", "us-ascii", "ascii"):
        return raw
    try:
        codecs.lookup(name)
    except LookupError:
        return raw                        # the parser will say what it is
    return _as_utf8(raw, name)


def _as_utf8(raw: bytes, encoding: str) -> bytes:
    """The bytes as UTF-8, or as they arrived if that cannot be done.

    This is the one transform here that can grow: a legacy code page is
    one byte per character and UTF-8 is up to four, so a part inside the
    bound can leave it twice the size. The bound is measured on the
    bytes that arrived, which was harmless while every conversion here
    shrank or was the identity. A converted document that would break
    it comes back unconverted -- the parser then answers for the bytes,
    which is what this function does with everything it cannot handle.
    """
    try:
        text = raw.decode(encoding)
    except (UnicodeError, LookupError):
        # `LookupError` because `codecs.lookup` accepts a dozen names
        # that are not text encodings -- `base64`, `rot13`, `zlib_codec`
        # -- and `bytes.decode` refuses them. One line in a prolog was
        # enough: traceback, no report, exit 1, which is the shape the
        # commit one round earlier said it had removed. `UnicodeError`
        # rather than its decode child because `punycode` raises the
        # parent.
        return raw
    converted = _DECLARED_ENCODING.sub(r"\1", text, count=1).encode("utf-8")
    return raw if len(converted) > MAX_PART_BYTES else converted


def declares_doctype(raw: bytes) -> bool:
    """Whether the document declares a DTD, asked of the prolog alone.

    Asked of bytes that have been through `xml_as_utf8`, and only of
    those: asked of the bytes as they arrived it answers for UTF-8 and
    guesses for everything else. Both readers ask it here so that neither
    can grow its own copy of the question and drift.

    The prolog is the only place a DTD can be declared, and a conformant
    document is allowed to *mention* one -- in a comment, in CDATA, in
    the text of a page about XML. Matching the token anywhere refuses a
    file for talking about the thing rather than doing it, and a finding
    against a conformant file is the one thing worse than silence.

    The walk skips processing instructions and comments rather than
    stopping at the first `<`, because a comment in the prolog may
    contain anything at all -- including something shaped like a start
    tag -- and stopping there would leave a real declaration behind it
    unread. That is the direction where being wrong is expensive.
    """
    i, end = 0, len(raw)
    while i < end:
        start = raw.find(b"<", i)
        if start < 0:
            return False
        if raw[start:start + 9].lower() == b"<!doctype":
            return True
        if raw[start:start + 4] == b"<!--":
            close = raw.find(b"-->", start)
            i = end if close < 0 else close + 3
        elif raw[start:start + 2] == b"<?":
            close = raw.find(b"?>", start)
            i = end if close < 0 else close + 2
        else:
            return False                    # the root element: prolog over
    return False

_RELATIONSHIP = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"


_SCHEME_FIRST = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
_SCHEME_REST = _SCHEME_FIRST | frozenset("0123456789+-.")


def has_scheme(value: str) -> bool:
    """Whether this string names something outside the container.

    The test was `"://" in value`, which is a substring and not a
    scheme: `files/a://absent.pdf` contains it, is a good part name once
    normalised, and walked past a MUST. RFC 3986 §3.1 says a scheme
    begins the reference and is `ALPHA *( ALPHA / DIGIT / "+" / "-" /
    "." )` -- US-ASCII, which `str.isalpha()` is not, so the letters are
    named rather than asked. A one-letter scheme is legal there and is a
    Windows drive letter every time it turns up in a File value.

    Here rather than beside the rule that first needed it, because two
    layers ask it and the lower one is this. A File value asks before
    the container is consulted; a relationship target has to be asked
    *before it is resolved*, since resolving is what turns a URI into a
    plausible part name -- and a copy in each place is a fork that
    agrees on the day it is written.
    """
    head, sep, _rest = value.partition(":")
    if not sep or len(head) < 2 or head[0] not in _SCHEME_FIRST:
        return False
    return all(character in _SCHEME_REST for character in head)


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


class RefusedContent(ContainerError):
    """This reader will not read this part, and nothing about it is wrong.

    A sibling of `PartTooLarge` in the one way that matters: it is this
    tool's decision, not a claim about the file, so the remedy is not a
    repair. Kept apart from its parent because the chain is intact -- it
    names the parts it should -- and telling an author to fix it is the
    kind of remedy this project promised not to write.
    """


class NoRelationships(ContainerError):
    """The archive holds no relationships part for this source.

    Kept apart because it means two different things depending on who
    asked. Walking the chain, a missing `.rels` is the chain going
    nowhere and X2's business. Asking one payload part what it declares,
    it means the part declares nothing -- which is ordinary, and the
    reason that call is allowed to fail quietly.

    Its siblings were failing quietly there too, sharing this type: a
    `.rels` refused for declaring a DTD, and one that would not parse,
    both came back as "declares nothing" and left a defective container
    reporting `ok` with no findings at all.
    """


class PartTooLarge(ContainerError):
    """The archive is well-formed and this reader will not read it all.

    Separate from its siblings because it is not a claim about the file.
    Nothing here is malformed; the file is simply larger than a validator
    meant for an air-gapped machine will take in, and the remedy is the
    author's choice of what to send, not a repair.
    """


class DirectoryTooLarge(ContainerError):
    """The archive declares more names than this reader will index.

    A sibling of PartTooLarge and for the same reason: nothing here is
    malformed. The archive may be perfectly well-formed and its parts all
    honest, and it is still more than a validator meant for an air-gapped
    machine will take in before it has read a byte of payload.
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


def _directory_bytes(path):
    """How many bytes of central directory `zipfile` is about to read, or
    None if it cannot be asked.

    Asked *through* `zipfile`'s own end-of-directory reader rather than by
    reading the record again here. That is the whole design: a second
    reading can disagree with the opener, and where it disagrees it
    refuses files the opener would have read. A file comment holding the
    end-of-directory signature is the case that decides it -- `zipfile`'s
    search lands inside the comment, reports a directory of nothing, and
    then builds nothing, so the two agree; a more careful reader would
    find the real record and refuse an archive `zipfile` opens happily.
    The same argument `xml_as_utf8` makes above, and `part` below.

    The entry point is private. Everything unexpected -- a file that is
    not an archive, a truncated one, a Python that has moved it -- comes
    back None and the archive is opened as it always was: the bound goes
    away before the reading does. `test_the_private_names_this_bound
    _leans_on_are_still_there` is what notices, in CI rather than at a
    user's.
    """
    try:
        with open(path, "rb") as handle:
            end = zipfile._EndRecData(handle)
        return None if end is None else end[zipfile._ECD_SIZE]
    except Exception:  # noqa: BLE001 - failing open is the point
        return None


class AasxPackage:
    """An opened .aasx. Use as a context manager, like ZipFile."""

    def __init__(self, path):
        self.path = Path(path)
        declared = _directory_bytes(self.path)
        if declared is not None and declared > MAX_DIRECTORY_BYTES:
            raise DirectoryTooLarge(
                "%s: its central directory declares %d bytes of names, above "
                "the %d byte limit" % (self.path, declared, MAX_DIRECTORY_BYTES))
        try:
            self._zip = zipfile.ZipFile(self.path)
        except UNREADABLE as exc:
            raise ContainerError("cannot open %s as a ZIP container: %s: %s"
                                 % (self.path, type(exc).__name__, exc)) from exc
        self._names = frozenset(self._zip.namelist())
        #: Distinct bytes handed out so far, for MAX_TOTAL_PART_BYTES.
        #: One package object is one validation, so this is that run's
        #: total -- and each part counts once however often it is read.
        self._read_total = 0
        self._counted = set()
        #: Entry names by their normalised spelling, built on first need.
        self._canonical = None

    # -- files ---------------------------------------------------------------
    def names(self) -> List[str]:
        return self._zip.namelist()

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
            # In the archive's own order, not the set's: two entries can
            # share a canonical spelling, and `setdefault` keeps the one
            # met first. Iterating the frozenset made "first" mean the
            # process's hash seed -- the same archive resolved a clashing
            # value to different entries on different runs. Measured: a
            # kill on this index landed on 12 of 20 seeds and survived
            # the other 8. Write order is the only order the archive has.
            self._canonical = {}
            for name in self._zip.namelist():
                key = canonical_part_name(name)
                if key is not None:
                    self._canonical.setdefault(key, name)
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
        # Asked before the decompressor runs, not only after. A container
        # already past its total went on paying a part's worth of work
        # for every part still to come, because the refusal was raised
        # after the read it exists to avoid -- and the caller walks all
        # of them. This changes no boundary: it is the same comparison,
        # reached earlier.
        if self._read_total > MAX_TOTAL_PART_BYTES:
            raise PartTooLarge(
                "%s: its parts come to more than %d bytes together"
                % (self.path, MAX_TOTAL_PART_BYTES))
        try:
            # Asking for a bounded number is what bounds the
            # decompressor: an unbounded read hands it the whole stream
            # and truncates the answer afterwards, having already paid
            # for it. A part declaring a hundred bytes and holding eight
            # megabytes cost eight megabytes of peak memory before this,
            # and costs the cap now.
            #
            # It is not a second gate. zipfile yields no more than the
            # entry declares, and an entry declaring more than the cap
            # was refused above, so the length that comes back can never
            # exceed it -- a check on `len(data)` here would be a branch
            # no input could reach.
            with self._zip.open(name) as part:
                data = part.read(MAX_PART_BYTES)
        except UNREADABLE as exc:
            raise UnreadablePart(
                "%s: %s cannot be read: %s: %s"
                % (self.path, name, type(exc).__name__, exc)) from exc
        if name not in self._counted:
            # Once per part. A rule may re-walk the chain -- X4 does --
            # and reading the same bytes a second time is not the
            # container growing. Counting it twice made the refusal
            # depend on which rule happened to cross the line.
            self._counted.add(name)
            self._read_total += len(data)
        if self._read_total > MAX_TOTAL_PART_BYTES:
            raise PartTooLarge(
                "%s: its parts come to more than %d bytes together"
                % (self.path, MAX_TOTAL_PART_BYTES))
        return data

    # -- the OPC chain -------------------------------------------------------
    def relationships(self, source: str = "") -> List[Tuple[str, str, bool]]:
        """(type, target, external) triples of `source`'s relationships part.

        A target that reads as a part name comes back without its
        leading slash, ready to use as a ZIP entry name -- whether or
        not the archive holds that part, because whether a name is
        well formed and whether it is present are two questions and
        `canonical_part_name` answers only the first. A target that
        reads as no part name at all -- a directory, a path that climbs
        out of the package -- comes back as it was written, slash and
        all, which matches no entry and so resolves to nothing. Real-world .rels files start with a UTF-8 byte order
        mark, and the parser reads several other encodings besides -- so
        the part is decoded the way the parser will read it before the
        guard below reads a byte of it.

        `external` is OPC's own answer to whether the target is a part
        of this package at all -- `TargetMode="External"`, which
        ECMA-376 Part 2 provides and a conformant AASX may carry for a
        supplementary file held on a server. It is carried out to the
        rules rather than guessed at from the spelling of the target,
        because the guess was wrong in a way nothing downstream could
        undo: resolved against the source part's own directory,
        `http://example.com/manual.pdf` became
        `aasx/http:/example.com/manual.pdf` -- a well-formed part name,
        matching no entry, present in no file, and printed at a reader
        as the part their package was missing, under a remedy telling
        them to add it or delete the relationship. Both would have them
        break a correct package.
        """
        rels = _rels_name(source)
        if rels not in self._names:
            raise NoRelationships("%s has no %s, so the chain from %r goes nowhere"
                                 % (self.path, rels, source or "the package root"))
        raw = xml_as_utf8(self.read(rels))
        # A relationships part has no legitimate use for a DTD, and a
        # nested-entity DTD is a decompression-free way to exhaust memory
        # (billion laughs; the parser expands it before any handler runs).
        # Refuse the declaration rather than try to bound the expansion.
        if declares_doctype(raw):
            raise RefusedContent("%s: %s declares a DOCTYPE, which is refused"
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
            # Nothing resolves a target that is not a part name, because
            # resolving is what manufactured the name in the docstring
            # above: joining a URI to a directory produces a string that
            # is a valid part name and names nothing. Both come back
            # exactly as written.
            #
            # Two questions, not one, and the flag answers only the
            # first. `TargetMode` is what OPC declared. A scheme is what
            # the target carries when nothing was declared -- a packager
            # writing an absolute URI and omitting the mode, which OPC
            # does not sanction and which still must not be resolved:
            # asked after the join, the scheme is gone, because
            # `aasx/http:/example.com/…` has none.
            external = el.get("TargetMode") == "External"
            if external or has_scheme(target):
                resolved.append((el.get("Type", ""), target, external))
                continue
            # Where the name starts from is the difference between the two
            # kinds of string; how it is spelled is not. The absolute
            # branch used to skip normalisation entirely, which left
            # "/a/./b" resolving differently from "a/./b".
            candidate = target[1:] if target.startswith("/") \
                else posixpath.join(base_dir, target)
            # Land on the entry the archive actually holds, so that a
            # payload whose name really contains an escape is readable:
            # `part` tries the literal before the normalised reading, and
            # the loader looks parts up by exact name.
            name = self.part(candidate) or canonical_part_name(candidate) or target
            resolved.append((el.get("Type", ""), name, False))
        return resolved

    @property
    def origin(self) -> str:
        """The aasx-origin part the package-level relationships name."""
        for rel_type, target, _external in self.relationships(""):
            if rel_type == ORIGIN_REL:
                return target
        raise ContainerError("%s declares no aasx-origin relationship" % self.path)

    @property
    def spec_parts(self) -> List[str]:
        """Every aas-spec payload the origin's relationships name."""
        # Once each, in the order first named. A part is a part however
        # many relationships point at it, and the total is bounded per
        # part -- so a repeated target bought a part's worth of work for
        # a relationship's worth of bytes and was counted once, which is
        # a bound that never arrives. Measured before this: sixty-four
        # declarations of a one-megabyte part reached sixteen times the
        # total from an archive of two kilobytes.
        targets = list(dict.fromkeys(
            target for rel_type, target, _external in self.relationships(self.origin)
            if rel_type == SPEC_REL))
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
