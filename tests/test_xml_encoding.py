"""What a document's own encoding declaration is allowed to do to it.

`xml_as_utf8` is the narrowest place in this reader: every guard
downstream inspects the bytes it returns, so if it disagrees with the
parser about what a document says, every one of them is reading a
different document from the one that gets parsed.

It is also the place with the least test cover in the repository, which
is how it came to hold a branch that has never once run as written. The
guards below were each added for a failure that had already happened --
a traceback and no report on a one-line prolog, a document refused for
syntax that was not wrong, a declaration a hundred bytes too far in --
and every one of them could be deleted with the whole suite staying
green. A guard whose absence nothing notices is a guard the next reader
deletes, and this file exists so that each of them is noticed.

Every case here is a conformant document. XML 1.0 §4.3.3 lets one be
written in any encoding it declares, and refusing it is the failure
this project ranks worst.
"""
from __future__ import annotations

import pytest

from aas_submodel_validate import container
from aas_submodel_validate.container import xml_as_utf8

BOM = b"\xef\xbb\xbf"


def _document(encoding, body="<root>café</root>", declare=True):
    prolog = '<?xml version="1.0" encoding="%s"?>' % encoding if declare else ""
    return (prolog + body).encode(encoding, "xmlcharrefreplace")


def test_a_document_written_in_the_encoding_it_declares_is_read(
        ):
    """The gap this whole layer was added for.

    0.1.0 decoded every payload as UTF-8, met a byte that is not, and
    reported that the document could not be read -- telling the author
    to fix syntax that was not wrong. What a German, Korean or Japanese
    Windows editor writes without being asked.
    """
    for encoding in ("iso-8859-1", "windows-1252", "latin-1"):
        out = xml_as_utf8(_document(encoding))
        assert "café" in out.decode("utf-8"), encoding
        assert b"encoding=" not in out, (
            "the declaration must go with the encoding it named, or the "
            "bytes downstream claim to be something they are not: %r" % out)


def test_a_prolog_naming_a_codec_that_is_not_a_text_encoding_does_not_raise():
    """`codecs.lookup` accepts a dozen names `bytes.decode` refuses --
    `base64`, `rot13`, `zlib_codec`, `hex`. One line in a prolog was
    enough for a traceback, no report and exit 1, against the one thing
    this reader promises about hostile input.

    `punycode` is in the list on purpose: it raises `UnicodeError`
    rather than the decode child everything else raises, which is why
    the guard names the parent.
    """
    for codec in ("base64", "rot13", "zlib_codec", "hex", "punycode",
                  "quopri_codec", "uu_codec"):
        raw = ('<?xml version="1.0" encoding="%s"?><root/>' % codec).encode("ascii")
        assert xml_as_utf8(raw) == raw, codec


def test_a_prolog_naming_no_codec_at_all_does_not_raise():
    """And the other half: a name Python has never heard of. The parser
    is the one that gets to say so."""
    raw = b'<?xml version="1.0" encoding="not-a-real-encoding"?><root/>'
    assert xml_as_utf8(raw) == raw


def test_a_declaration_further_in_than_a_short_window_is_still_read():
    """The window was 200 bytes, which a real prolog clears and a
    padded one does not. XML 1.0 bounds nothing here, so a declaration
    that a parser reads must be a declaration this reads."""
    padded = ('<?xml version="1.0"' + " " * 300 + ' encoding="iso-8859-1"?>'
              '<root>café</root>').encode("iso-8859-1")
    assert "café" in xml_as_utf8(padded).decode("utf-8")


def test_a_marked_document_that_declares_a_legacy_encoding_is_read():
    """A UTF-8 mark says the bytes after it are UTF-8 and a document may
    still declare something else -- ill-formed by XML 1.0 and read by
    every parser, which is the standard this function set itself.
    Repairing only the unmarked branch left this one refused, with the
    same wrong remedy the repair existed to remove.

    The mark has to come off before the declaration is looked for: left
    on, the pattern that strips the declaration no longer matches and
    the bytes go downstream as UTF-8 still claiming to be something
    else.
    """
    out = xml_as_utf8(BOM + _document("iso-8859-1"))
    assert "café" in out.decode("utf-8")
    assert b"encoding=" not in out


def test_a_marked_utf8_document_is_handed_on_exactly_as_it_arrived():
    """The row most real documents take, where doing nothing is the
    whole job -- every official AASX in the corpus is marked UTF-8.

    The guard for it compared `_as_declared`'s answer with a *freshly
    sliced* copy of its own argument, so the identity test was true
    whatever happened and the branch that returns the document untouched
    could never run: every marked document had its mark taken off. No
    reader downstream minded, which is exactly why nothing caught it.
    """
    raw = BOM + b'<?xml version="1.0" encoding="utf-8"?><root>caf\xc3\xa9</root>'
    assert xml_as_utf8(raw) == raw
    unmarked = BOM + b"<root>hello</root>"
    assert xml_as_utf8(unmarked) == unmarked


def test_a_document_declaring_utf8_is_not_round_tripped():
    """Declaring what is already true is not a reason to rewrite the
    bytes. The shortcut is what keeps the common case identical, and
    `us-ascii` is a subset that needs no more work than `utf-8`."""
    for encoding in ("utf-8", "UTF-8", "us-ascii", "ASCII", "utf_8"):
        raw = ('<?xml version="1.0" encoding="%s"?><root/>' % encoding).encode("ascii")
        assert xml_as_utf8(raw) == raw, encoding


def test_a_conversion_that_would_break_the_part_bound_is_not_made(monkeypatch):
    """The one transform here that can grow: a legacy code page is one
    byte per character and UTF-8 is up to four, so a part inside the
    bound can leave it several times the size. The bound is measured on
    the bytes that arrived, which was harmless while every conversion
    shrank or was the identity.

    A document that would break it comes back unconverted, and the
    parser answers for the bytes -- what this layer does with everything
    else it cannot handle.
    """
    raw = _document("iso-8859-1", body="<root>" + "é" * 400 + "</root>")
    assert xml_as_utf8(raw) != raw, "the fixture must be one that converts"
    monkeypatch.setattr(container, "MAX_PART_BYTES", len(raw))
    assert xml_as_utf8(raw) == raw


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be"])
def test_utf16_is_rewritten_because_downstream_cannot_read_it(encoding):
    """The one shape where the bytes downstream needs really do differ
    from the bytes that arrived."""
    raw = ("<root>café</root>").encode(encoding)
    if encoding != "utf-16":
        raw = (b"\xff\xfe" if encoding.endswith("le") else b"\xfe\xff") + raw
    assert "café" in xml_as_utf8(raw).decode("utf-8")


def test_utf32_stays_refused_marked_or_not():
    """Refused by the parser whether it is marked or not, so decoding it
    here would admit documents nothing else in the ecosystem opens -- and
    a validator calling a file conformant that no other reader can parse
    has done the worst thing it can do."""
    raw = ("<root/>").encode("utf-32")
    assert xml_as_utf8(raw) == raw
