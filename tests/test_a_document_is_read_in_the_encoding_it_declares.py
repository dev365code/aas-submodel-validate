"""A document is read in the encoding it declares, by the name the registry gives it.

XML 1.0 lets a document name its own encoding in its declaration (4.3.3) and
asks a processor to read a registered name, compared without regard to case,
as the charset registered under it -- or to stop, because bytes that are not
legal in the declared encoding are a fatal error, and so is an encoding the
processor does not read. This reader turns a declared charset into UTF-8
before anything else reads the document, and it used to ask the running
Python what a name meant. So `Windows-31J`, which the IANA registry gives and
Python 3.9 does not know, was refused as though the document's syntax were
wrong, and `cp1252`, which Python knows and the registry does not, was read
-- on this Python, and not on every one: the page this project publishes runs
another.

The condition this project set itself before 1.0 is held here as far as the
table of names goes -- `_REGISTERED`, in `aas_submodel_validate/container.py`,
the IANA charset registry's names for the charsets this reader decodes: a
document declared under any name the table in container.py holds is read,
and what the report quotes from it comes back unchanged. A name outside the
table is refused, naming the registered one where one can be named, and a
document in UCS-4 or EBCDIC is refused saying which it is in. What the
declaration says is still the whole question: bytes that are not the
encoding it names are refused at the line they are on.
"""
from __future__ import annotations

import codecs
import io
import json
import re
import zipfile
from xml.etree import ElementTree

import pytest

from aas_submodel_validate import container, loader
from aas_submodel_validate.cli import main
from aas_submodel_validate.container import EncodingNotRead, xml_as_utf8
from builders import CONTENT_TYPES, ORIGIN_REL

RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _registered():
    return sorted(((name, codec) for codec, names in container._REGISTERED.items() for name in names),
                  key=lambda pair: pair[0].lower())


@pytest.mark.parametrize("name,codec", _registered(), ids=[n for n, _ in _registered()])
def test_every_name_the_registry_gives_is_read_on_this_python(name, codec):
    """A name is read as the registry registers it, the same way on every
    Python: the names are this reader's, not the running Python's, and each
    is read here on whichever Python runs this -- each of the ones this
    package supports, in CI. A Python that lacked a codec the table names
    would fail here rather than read one document two ways."""
    out = xml_as_utf8(('<?xml version="1.0" encoding="%s"?>\n<a>read</a>' % name).encode(codec))
    assert out.endswith(b"<a>read</a>"), out
    if name.lower() not in container._PARSER_READS:
        assert b"encoding=" not in out, "%s was handed on undecoded: %r" % (name, out)


def test_the_table_names_one_charset_once_and_only_names_a_declaration_can_hold():
    """Compared without regard to case, as XML 1.0 asks, no name may lead to
    two codecs; each is one a declaration can be written with (production
    81, `EncName`); and each codec is named as Python names it, which is
    what a remedy asks the running Python for."""
    seen = {}
    for codec, names in container._REGISTERED.items():
        assert codecs.lookup(codec).name == codec, codec
        assert container.registered_name(codec) in names, codec
        for name in names:
            assert re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]*", name), name
            assert seen.setdefault(name.lower(), codec) == codec, name


#: What the registry says and Python's own table does not: `MS_Kanji` is an
#: alias of Shift_JIS, which Python reads as Windows-31J; ISO-8859-11 is an
#: alias of TIS-620; Windows-31J is a name Python 3.9 does not know; and
#: windows-874 is the code page Python calls cp874.
REGISTRY_READS = [("Windows-31J", "cp932"), ("csWindows31J", "cp932"), ("MS_Kanji", "shift_jis"),
                  ("ISO-8859-11", "tis-620"), ("windows-874", "cp874"), ("ISO-8859-8-I", "iso8859-8")]


@pytest.mark.parametrize("name,codec", REGISTRY_READS, ids=[n for n, _ in REGISTRY_READS])
def test_a_registered_name_is_read_as_the_charset_registered_under_it(name, codec):
    assert {n.lower(): c for n, c in _registered()}[name.lower()] == codec


def test_ms_kanji_is_shift_jis_and_not_what_python_calls_it():
    """NEC's row 13 is in Windows-31J and not in Shift_JIS. Python reads
    `MS_Kanji` as Windows-31J and would read the circled one; the registry
    makes it Shift_JIS, which has no such character, so the bytes are not
    the encoding declared."""
    raw = '<?xml version="1.0" encoding="MS_Kanji"?>\n<a>①</a>'.encode("cp932")
    with pytest.raises(EncodingNotRead) as refused:
        xml_as_utf8(raw)
    assert refused.value.kind == "bytes" and refused.value.line == 2


#: A declared name, the codec that writes it, and an idShort in its script.
#: The idShort is not a legal one, so the metamodel finding quotes it -- and
#: the quotation is what has to come back as the characters the file holds.
SCRIPTS = [
    ("UTF-8", "utf-8", "Größe技術"),
    ("ISO-8859-1", "iso8859-1", "Technische Größe"),
    ("ISO-8859-2", "iso8859-2", "Specyfikacja łódź"),
    ("ISO-8859-5", "iso8859-5", "Техническая"),
    ("ISO-8859-7", "iso8859-7", "Τεχνική"),
    ("windows-1252", "cp1252", "Größe €"),
    ("KOI8-R", "koi8-r", "Техника"),
    ("Shift_JIS", "shift_jis", "技術仕様書"),
    ("Windows-31J", "cp932", "技術仕様書①"),
    ("EUC-JP", "euc_jp", "技術仕様書"),
    ("ISO-2022-JP", "iso2022_jp", "技術仕様書"),
    ("EUC-KR", "euc_kr", "기술 사양서"),
    ("GB2312", "gb2312", "技术规格书"),
    ("GBK", "gbk", "技术规格书"),
    ("GB18030", "gb18030", "技术规格书"),
    ("Big5", "big5", "技術規格書"),
    ("TIS-620", "tis-620", "เทคนิค"),
]


def _environment(declared, id_short):
    return ('<?xml version="1.0" encoding="%s"?>\n'
            '<environment xmlns="https://admin-shell.io/aas/3/0">\n'
            '<submodels><submodel>\n<idShort>%s</idShort><id>urn:a:b</id>\n'
            '</submodel></submodels></environment>' % (declared, id_short))


def _judged(path, capsys):
    code = main(["-f", "json", "--allow-unmatched", str(path)])
    report = json.loads(capsys.readouterr().out)
    return code, [{key: value for key, value in finding.items() if key not in ("subject",)}
                  for finding in report["findings"]]


@pytest.mark.parametrize("declared,codec,id_short", SCRIPTS, ids=[s[0] for s in SCRIPTS])
def test_each_script_reads_as_its_utf8_twin_and_is_quoted_back_unchanged(
        tmp_path, capsys, declared, codec, id_short):
    """The same document in UTF-8 and in the charset it declares: the same
    exit, the same findings, lines included -- and the idShort the finding
    quotes is the characters the file holds."""
    twin = tmp_path / "twin.xml"
    twin.write_bytes(_environment("UTF-8", id_short).encode("utf-8"))
    declared_path = tmp_path / "declared.xml"
    declared_path.write_bytes(_environment(declared, id_short).encode(codec))
    assert _judged(declared_path, capsys) == _judged(twin, capsys)
    _, findings = _judged(declared_path, capsys)
    assert any(finding["detail"] == "idShort: %r" % id_short for finding in findings), findings


def test_bytes_that_are_not_the_declared_charset_are_refused_where_they_are(tmp_path):
    raw = _environment("Shift_JIS", "技術").encode("shift_jis").replace(
        b"<id>", b"<id>\xff\xfe", 1)
    path = tmp_path / "broken.xml"
    path.write_bytes(raw)
    (error,) = loader.load(path).errors
    assert error.message == "the document declares Shift_JIS, and the bytes on line 4 are not Shift_JIS: ff"
    assert error.line == 4
    assert error.fix.startswith("Declare the encoding the file is in, by the name the IANA "
                                "charset registry gives it, or save the document as UTF-8")


#: A name a Python may know and the registry does not give, and the
#: registered name the remedy asks for instead.
UNREGISTERED = [("UTF8", "UTF-8"), ("utf8", "UTF-8"), ("utf_8", "UTF-8"), ("ascii", "US-ASCII"),
                ("ASCII", "US-ASCII"), ("latin-1", "ISO-8859-1"), ("iso8859-1", "ISO-8859-1"),
                ("cp1252", "windows-1252"), ("sjis", "Shift_JIS"), ("shift-jis", "Shift_JIS"),
                ("cp932", "Windows-31J"), ("euc_kr", "EUC-KR"), ("cp949", "EUC-KR")]


@pytest.mark.parametrize("declared,instead", UNREGISTERED, ids=[u[0] for u in UNREGISTERED])
def test_a_name_the_registry_does_not_give_is_refused_naming_the_one_it_does(
        tmp_path, declared, instead):
    """The same refusal and the same remedy on every Python, word for word --
    where a document declaring `sjis` was read on all of them and one
    declaring `Windows-31J` on some. `cp949` has no registration of its own;
    a file that holds only EUC-KR's characters reads the same as EUC-KR."""
    path = tmp_path / "declared.xml"
    path.write_bytes(_environment(declared, "기술" if declared == "cp949" else "a")
                     .encode(codecs.lookup(declared).name))
    (error,) = loader.load(path).errors
    assert error.message == ("the document declares %s, which is not a name the IANA "
                             "charset registry gives a charset this reader reads" % declared)
    assert error.fix == ("Declare it as %s, the name the IANA charset registry gives that "
                         "charset, or save the document as UTF-8 and drop the declaration. %s"
                         % (instead, loader.REFUSED_NOT_JUDGED))


def test_cp949_beyond_euc_kr_names_no_charset_it_is_not(tmp_path):
    """U+B620 is in Windows' code page 949 and not in KS X 1001, so no
    registered charset reads the file as it is."""
    path = tmp_path / "declared.xml"
    path.write_bytes(_environment("cp949", "똠").encode("cp949"))
    (error,) = loader.load(path).errors
    assert error.fix.startswith("Declare the encoding the file is in, by the name the IANA "
                                "charset registry gives it")


@pytest.mark.parametrize("declared", ["base64", "rot13", "hex", "zlib_codec", "quopri_codec",
                                      "uu_codec", "not-a-real-encoding", "latin\x001"])
def test_a_name_that_is_no_charset_at_all_is_refused_by_name(declared):
    """Python's transforms, a name nobody has heard of, and one with a NUL in
    it: refused by name, with nothing to declare instead."""
    raw = ('<?xml version="1.0" encoding="%s"?><root/>' % declared).encode("ascii")
    with pytest.raises(EncodingNotRead) as refused:
        xml_as_utf8(raw)
    assert refused.value.kind == "name" and refused.value.instead is None
    assert (declared if "\x00" not in declared else repr(declared)) in str(refused.value)


#: XML 1.0, Appendix F: the first four bytes of a document in UCS-4, in each
#: byte order and with its mark or without, and in EBCDIC.
FIRST_BYTES = [("UCS-4", '<?xml version="1.0" encoding="UTF-32"?><a/>'.encode("utf-32")),
               ("UCS-4", '<?xml version="1.0"?><a/>'.encode("utf-32-le")),
               ("UCS-4", '<?xml version="1.0"?><a/>'.encode("utf-32-be")),
               ("UCS-4", b"\x00\x00\xfe\xff" + "<a/>".encode("utf-32-be")),
               ("UCS-4", b"\x00\x00\x3c\x00\x00\x00\x61\x00"),
               ("UCS-4", b"\x00\x3c\x00\x00\x00\x61\x00\x00"),
               ("EBCDIC", '<?xml version="1.0" encoding="IBM500"?><a/>'.encode("cp500")),
               ("EBCDIC", '<?xml version="1.0" encoding="IBM037"?><a/>'.encode("cp037"))]


@pytest.mark.parametrize("what,raw", FIRST_BYTES,
                         ids=["utf-32", "le", "be", "be-marked", "2143", "3412", "ibm500", "ibm037"])
def test_ucs4_and_ebcdic_are_refused_saying_which(tmp_path, what, raw):
    path = tmp_path / "doc.xml"
    path.write_bytes(raw)
    (error,) = loader.load(path).errors
    assert error.message == ("the document is in %s, as its first bytes say, and this reader "
                             "does not read %s" % (what, what))
    assert error.fix == ("Save the document as UTF-8, or as UTF-16 with its byte order mark -- "
                         "the two every XML processor reads (XML 1.0, 4.3.3). This reader does "
                         "not read %s, and aas-core3's own XML reader refuses it as well. %s"
                         % (what, loader.REFUSED_NOT_JUDGED))


def test_aas_core3_s_own_reader_refuses_them_as_the_remedy_says():
    """The remedy says aas-core3's own XML reader refuses UCS-4 and EBCDIC
    as well; this is that sentence, asked of the library. And the multi-byte
    charsets it refuses, which this reader reads."""
    from aas_core3 import xmlization

    document = '<environment xmlns="https://admin-shell.io/aas/3/0"><submodels/></environment>'
    assert xmlization.environment_from_stream(io.BytesIO(document.encode("utf-8"))) is not None
    for prolog, codec in (('<?xml version="1.0" encoding="UTF-32"?>', "utf-32"),
                          ('<?xml version="1.0" encoding="IBM500"?>', "cp500"),
                          ('<?xml version="1.0" encoding="Shift_JIS"?>', "shift_jis")):
        with pytest.raises(Exception):  # noqa: B017 - which one is the library's to choose
            xmlization.environment_from_stream(io.BytesIO((prolog + document).encode(codec)))


def test_a_relationships_part_in_a_name_this_reader_does_not_read_is_filed_with_its_remedy(tmp_path):
    """A relationships part is read the same way, and the remedy is the
    encoding's -- not "repair the chain", for a chain nothing says is broken."""
    rels = ('<?xml version="1.0" encoding="cp1252"?><Relationships xmlns="%s">'
            '<Relationship Type="%s" Target="/aasx/aasx-origin" Id="R0"/></Relationships>'
            % (RELS_NS, ORIGIN_REL)).encode("ascii")
    path = tmp_path / "p.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("aasx/aasx-origin", b"")
    (error,) = loader.load(path).errors
    assert "cp1252" in error.message
    assert error.fix.startswith("Declare it as windows-1252,")
    # Asked again -- the rules ask after the loader has -- it is the same
    # refusal, remembered, with what it named.
    with container.AasxPackage(path) as package:
        for _ in range(2):
            with pytest.raises(EncodingNotRead) as refused:
                _ = package.spec_parts
            assert refused.value.instead == "windows-1252"


#: The registry's names for UTF-8 and US-ASCII other than the two the parser
#: knows: expat reads `utf-8` and `us-ascii` by itself, has never heard of
#: these, and asks Python about a name it has not heard of -- and no Python
#: has heard of `csUTF8`, which stopped a relationships part with a traceback.
OTHER_SPELLINGS = sorted((name for name in container._REGISTERED["utf-8"] + container._REGISTERED["ascii"]
                          if name.lower() not in ("utf-8", "us-ascii")), key=str.lower)


@pytest.mark.parametrize("declared", OTHER_SPELLINGS)
def test_a_registered_name_the_parser_does_not_know_is_read_before_it_parses(declared):
    """What this hands on parses, on any Python: the bytes the table decoded,
    with no declaration left for the parser to look up."""
    raw = ('<?xml version="1.0" encoding="%s"?><root>a</root>' % declared).encode("ascii")
    assert ElementTree.fromstring(xml_as_utf8(raw)).text == "a"


def _package_whose_relationships_declare(tmp_path, declared):
    rels = ('<?xml version="1.0" encoding="%s"?><Relationships xmlns="%s">'
            '<Relationship Type="%s" Target="/aasx/aasx-origin" Id="R0"/></Relationships>'
            % (declared, RELS_NS, ORIGIN_REL)).encode("ascii")
    path = tmp_path / ("%s.aasx" % declared)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("aasx/aasx-origin", b"")
    return path


@pytest.mark.parametrize("declared", OTHER_SPELLINGS)
def test_a_relationships_part_in_any_registered_name_is_read_as_utf_8_s_is(tmp_path, declared):
    """A package whose relationships part declares one of them goes as far as
    the one that declares UTF-8 does, and stops where it stops."""
    def seen(name):
        path = _package_whose_relationships_declare(tmp_path, name)
        return [(error.stage, error.message.replace(str(path), "the package"))
                for error in loader.load(path).errors]

    assert seen(declared) == seen("UTF-8")


_DECLARING = '<?xml version="1.0" encoding="%s"?><root>a</root>'

#: A declaration the document's first bytes contradict: a byte order mark
#: that settles one encoding and a declaration that names another, or bytes
#: whose shape settles one. XML 1.0 makes each a fatal error (4.3.3), and
#: expat and aas-core3 refuse each one.
CONTRADICTED = [
    ("a UTF-16 mark, declaring ISO-8859-1", (_DECLARING % "ISO-8859-1").encode("utf-16"), "UTF-16"),
    ("a UTF-8 mark, declaring UTF-16", b"\xef\xbb\xbf" + (_DECLARING % "UTF-16").encode("ascii"),
     "UTF-8"),
    ("ASCII, declaring UTF-16", (_DECLARING % "UTF-16").encode("ascii"), None),
    ("ASCII, declaring csUTF16LE", (_DECLARING % "csUTF16LE").encode("ascii"), None),
    ("UTF-16 with no mark, declaring ISO-8859-1", (_DECLARING % "ISO-8859-1").encode("utf-16-le"),
     "UTF-16LE"),
]

#: And the ones the first bytes agree with, the registry's names among them.
AGREED = [
    ("a UTF-16 mark, declaring UTF-16", (_DECLARING % "UTF-16").encode("utf-16")),
    ("a UTF-16 mark, declaring csUTF16", (_DECLARING % "csUTF16").encode("utf-16")),
    ("a little-endian mark, declaring UTF-16LE", b"\xff\xfe" + (_DECLARING % "UTF-16LE").encode("utf-16-le")),
    ("a big-endian mark, declaring csUTF16BE", b"\xfe\xff" + (_DECLARING % "csUTF16BE").encode("utf-16-be")),
    ("UTF-16 with no mark, declaring UTF-16LE", (_DECLARING % "UTF-16LE").encode("utf-16-le")),
    ("a UTF-8 mark, declaring UTF-8", b"\xef\xbb\xbf" + (_DECLARING % "UTF-8").encode("ascii")),
    ("a UTF-8 mark, declaring csUTF8", b"\xef\xbb\xbf" + (_DECLARING % "csUTF8").encode("ascii")),
]


@pytest.mark.parametrize("label,raw,instead", CONTRADICTED, ids=[c[0] for c in CONTRADICTED])
def test_a_declaration_its_first_bytes_contradict_is_refused_as_the_parser_refuses_it(
        label, raw, instead):
    """Refused at line 1, as the bytes against the declaration -- the answer
    expat gives too, so no reader in the ecosystem and this one disagree
    about whether the document can be read. Where a mark or the bytes' shape
    settles the encoding, the remedy names it."""
    with pytest.raises(EncodingNotRead) as refused:
        xml_as_utf8(raw)
    assert refused.value.kind == "bytes" and refused.value.line == 1, label
    assert refused.value.instead == instead, label
    with pytest.raises((ElementTree.ParseError, LookupError)):
        ElementTree.fromstring(raw)


@pytest.mark.parametrize("label,raw", AGREED, ids=[a[0] for a in AGREED])
def test_a_declaration_its_first_bytes_agree_with_is_read(label, raw):
    assert ElementTree.fromstring(xml_as_utf8(raw)).text == "a", label


def test_a_mark_the_declaration_contradicts_is_refused_naming_the_mark_s_encoding(tmp_path):
    path = tmp_path / "declared.xml"
    path.write_bytes(_environment("ISO-8859-1", "a").encode("utf-16"))
    (error,) = loader.load(path).errors
    assert error.message == ("the document starts with a UTF-16 byte order mark and declares "
                             "ISO-8859-1; its declaration has to name the encoding the mark "
                             "says it is in")
    assert error.fix == ("Declare it as UTF-16, the name the IANA charset registry gives that "
                         "charset, or save the document as UTF-8 and drop the declaration. %s"
                         % loader.REFUSED_NOT_JUDGED)


def test_the_library_gives_the_same_answers():
    """`validate` is a published door to the same reader."""
    from aas_submodel_validate import exit_code, validate

    raw = _environment("Windows-31J", "技術①").encode("cp932")
    report = validate(raw, format="xml")
    assert any(f.violation.detail == "idShort: %r" % "技術①" for f in report.findings)
    refused = validate(_environment("sjis", "a").encode("shift_jis"), format="xml")
    assert exit_code(refused) == 2
