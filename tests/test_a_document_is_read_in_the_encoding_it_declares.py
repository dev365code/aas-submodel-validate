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
import encodings.aliases
import io
import json
import re
import sys
import zipfile
from pathlib import Path
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
    # A declared-byte refusal offers the UTF-8 route before redeclaring.
    assert error.fix == ("Save the document as UTF-8 and drop the declaration, or declare the "
                         "encoding the file is in, by the name the IANA charset registry gives "
                         "it. %s" % loader.REFUSED_NOT_JUDGED)


#: A name a Python may know and the registry does not give, and the
#: registered name the remedy asks for instead.
UNREGISTERED = [("UTF8", "UTF-8"), ("utf8", "UTF-8"), ("utf_8", "UTF-8"), ("ascii", "US-ASCII"),
                ("ASCII", "US-ASCII"), ("latin-1", "ISO-8859-1"), ("iso8859-1", "ISO-8859-1"),
                ("cp1252", "windows-1252"), ("sjis", "Shift_JIS"), ("shift-jis", "Shift_JIS"),
                ("cp932", "Windows-31J"), ("euc_kr", "EUC-KR"), ("cp949", "EUC-KR"),
                ("windows_31j", "Windows-31J")]


@pytest.mark.parametrize("declared,instead", UNREGISTERED, ids=[u[0] for u in UNREGISTERED])
def test_a_name_the_registry_does_not_give_is_refused_naming_the_one_it_does(
        tmp_path, declared, instead):
    """The same refusal and the same remedy on every Python, word for word --
    where a document declaring `sjis` was read on all of them and one
    declaring `Windows-31J` on some. `cp949` has no registration of its own;
    a file that holds only EUC-KR's characters reads the same as EUC-KR.
    `windows_31j` is the registry's Windows-31J with an underscore, which
    3.13.2 knows as a spelling and 3.9.6 does not: the remedy names it on
    both. Every other document here holds ASCII alone, its bytes the same
    under every name in the list."""
    path = tmp_path / "declared.xml"
    path.write_bytes(_environment(declared, "기술" if declared == "cp949" else "a")
                     .encode("cp949" if declared == "cp949" else "ascii"))
    (error,) = loader.load(path).errors
    assert error.message == ("the document declares %s, which is not a name the IANA "
                             "charset registry gives a charset this reader reads" % declared)
    assert error.fix == ("Declare it as %s, the name the IANA charset registry gives that "
                         "charset, or save the document as UTF-8 and drop the declaration. %s"
                         % (instead, loader.REFUSED_NOT_JUDGED))


#: Spellings no registration gives and CPython 3.9 does not know as any
#: charset's: the remedy names nothing, on every Python -- 3.13.15 knows
#: `pc_multilingual_850_euro` as IBM00858 and 3.13.2 does not.
NAMED_BY_NEITHER = ["pc_multilingual_850_euro", "a_spelling_a_later_python_adds"]


@pytest.mark.parametrize("declared", NAMED_BY_NEITHER)
def test_a_spelling_a_later_python_adds_draws_the_remedy_it_draws_on_every_python(
        tmp_path, monkeypatch, declared):
    """The running Python is not asked what a spelling means, so knowing one
    more than CPython 3.9 does phrases no remedy differently. The second
    spelling is given a charset here, the way a later Python's alias table
    gives one, and the remedy does not hear of it either."""
    monkeypatch.setitem(encodings.aliases.aliases, "a_spelling_a_later_python_adds", "cp858")
    path = tmp_path / "declared.xml"
    path.write_bytes(_environment(declared, "a").encode("ascii"))
    (error,) = loader.load(path).errors
    assert error.fix == ("Declare the encoding the file is in, by the name the IANA charset "
                         "registry gives it, or save the document as UTF-8 and drop the "
                         "declaration. %s" % loader.REFUSED_NOT_JUDGED)


def test_a_remedy_asks_nothing_of_the_python_that_runs_it(monkeypatch):
    """Every name in the list above, with the running Python's codec lookup
    made to refuse every question: the same registered name each time."""
    raws = [(declared, instead, _environment(declared, "기술" if declared == "cp949" else "a")
             .encode("cp949" if declared == "cp949" else "ascii"))
            for declared, instead in UNREGISTERED]

    def asked(name):
        raise AssertionError("the running Python was asked what %r means" % name)

    monkeypatch.setattr(codecs, "lookup", asked)
    for declared, instead, raw in raws:
        with pytest.raises(EncodingNotRead) as refused:
            xml_as_utf8(raw)
        assert refused.value.instead == instead, declared


def _spelled():
    return sorted((spelling, codec) for codec, spellings in container._PYTHON_SPELLINGS.items()
                  for spelling in spellings)


@pytest.mark.parametrize("spelling,codec", _spelled(), ids=[s for s, _ in _spelled()])
def test_every_spelling_the_remedy_reads_is_read_the_same_on_this_python(spelling, codec):
    """The table was written on CPython 3.9; it is only worth reading where
    this Python still means by each spelling the charset 3.9 meant."""
    info = codecs.lookup(spelling)
    assert info.name == codec and getattr(info, "_is_text_encoding", True), (spelling, info.name)


def test_the_table_holds_only_what_the_tool_that_writes_it_would_write_here():
    """Every spelling the table holds is one `tools/python_spellings.py`, run
    on this Python, gives the same charset and keeps -- a text codec, and not
    a spelling the registry's own names answer. The tool writes the table on
    CPython 3.9 and `--check` holds it to that Python; a later one gives more
    spellings, which is why the table is not asked of it."""
    tools = Path(__file__).resolve().parents[1] / "tools"
    if not (tools / "python_spellings.py").exists():
        pytest.skip("no tools/ here (installed package, not a checkout)")
    sys.path.insert(0, str(tools))
    try:
        import python_spellings
    finally:
        sys.path.remove(str(tools))
    made = python_spellings.spellings()
    for codec, spellings in container._PYTHON_SPELLINGS.items():
        assert set(spellings) <= set(made.get(codec, ())), (codec, sorted(
            set(spellings) - set(made.get(codec, ()))))


def test_no_spelling_names_two_charsets():
    """Folded the way the remedy folds a name -- no case, none of EncName's
    punctuation -- the registry's names and the spellings each name one
    charset, and no spelling is one the registry's names already answer."""
    registry = [(container._folded(name), codec)
                for codec, names in container._REGISTERED.items() for name in names]
    spelled = [(container._folded(spelling), codec)
               for codec, spellings in container._PYTHON_SPELLINGS.items()
               for spelling in spellings]
    for pairs in (registry, spelled):
        named = {}
        for key, codec in pairs:
            assert named.setdefault(key, codec) == codec, key
    assert not {key for key, _ in spelled} & {key for key, _ in registry}


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


def _rels(declared):
    return ('<?xml version="1.0" encoding="%s"?><Relationships xmlns="%s">'
            '<Relationship Type="%s" Target="/aasx/aasx-origin" Id="R0"/></Relationships>'
            % (declared, RELS_NS, ORIGIN_REL))


#: UTF-16 by its mark or by its shape, declared by one of the registry's
#: names for it that the parser does not know, and holding bytes that are not
#: UTF-16: a lone surrogate, or an odd byte at the end. Handed on as they came,
#: the parser asked Python what the name meant -- and stopped the run with a
#: traceback inside a relationships part.
UNDECODABLE = [
    ("a little-endian mark, csUTF16, a lone surrogate",
     lambda text: b"\xff\xfe" + text("csUTF16").encode("utf-16-le") + b"\x00\xd8"),
    ("a little-endian mark, csUTF16LE, an odd last byte",
     lambda text: b"\xff\xfe" + text("csUTF16LE").encode("utf-16-le") + b"\x00"),
    ("a big-endian mark, csUTF16BE, a lone surrogate",
     lambda text: b"\xfe\xff" + text("csUTF16BE").encode("utf-16-be") + b"\xd8\x00"),
    ("no mark, little-endian, csUTF16LE, a lone surrogate",
     lambda text: text("csUTF16LE").encode("utf-16-le") + b"\x00\xd8"),
    ("no mark, little-endian, csUTF16, a lone surrogate",
     lambda text: text("csUTF16").encode("utf-16-le") + b"\x00\xd8"),
]


@pytest.mark.parametrize("label,make", UNDECODABLE, ids=[u[0] for u in UNDECODABLE])
def test_utf16_under_a_name_the_parser_does_not_know_is_refused_for_bytes_that_are_not_it(
        label, make):
    """Refused here, for the bytes, rather than handed to a parser that would
    have to ask what the name means."""
    with pytest.raises(EncodingNotRead) as refused:
        xml_as_utf8(make(lambda name: _DECLARING % name))
    assert refused.value.kind == "bytes", label


@pytest.mark.parametrize("label,make", UNDECODABLE, ids=[u[0] for u in UNDECODABLE])
def test_a_relationships_part_like_that_is_filed_as_the_chain_and_not_a_traceback(
        tmp_path, label, make):
    path = tmp_path / "p.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", make(_rels))
        archive.writestr("aasx/aasx-origin", b"")
    (error,) = loader.load(path).errors
    # Repaired, not redeclared: the name already agrees with the first bytes.
    assert error.stage == "chain" and error.fix.startswith("The file is in UTF-16"), (label, error)


def test_utf16_under_the_parser_s_own_name_is_refused_here_too():
    """`UTF-16` the parser knows, and bytes it cannot decode under that name
    used to be handed to it for it to refuse. It does not always: expat
    reads a surrogate with no partner inside an attribute value, so the
    refusal is this reader's whatever the name."""
    raw = b"\xff\xfe" + (_DECLARING % "UTF-16").encode("utf-16-le") + b"\x00\xd8"
    with pytest.raises(EncodingNotRead) as refused:
        xml_as_utf8(raw)
    assert refused.value.kind == "bytes"


def _rels_with_a_lone_surrogate(declared, codec, mark=b""):
    """A relationships part in UTF-16 (`codec`), declaring `declared` or, for
    None, nothing, whose Id holds a surrogate with no partner -- the place
    expat takes one without a word."""
    head = '<?xml version="1.0"%s?>' % ("" if declared is None else ' encoding="%s"' % declared)
    before = ('%s<Relationships xmlns="%s"><Relationship Type="%s" Target="/aasx/aasx-origin" Id="'
              % (head, RELS_NS, ORIGIN_REL))
    surrogate = b"\x00\xd8" if codec == "utf-16-le" else b"\xd8\x00"
    return mark + before.encode(codec) + surrogate + 'R0"/></Relationships>'.encode(codec)


#: UTF-16 under the names the parser reads itself, or under none, holding
#: bytes that are not UTF-16. Handed on as they came, a relationships part
#: with a surrogate and no partner in an attribute was read and the package
#: judged; a document with no mark and an odd last byte came back as a
#: finding about its XML rather than a refusal of its bytes.
THE_PARSER_S_NAMES = [
    ("a little-endian mark, UTF-16, a lone surrogate in an attribute",
     _rels_with_a_lone_surrogate("UTF-16", "utf-16-le", b"\xff\xfe")),
    ("a big-endian mark, UTF-16, a lone surrogate in an attribute",
     _rels_with_a_lone_surrogate("UTF-16", "utf-16-be", b"\xfe\xff")),
    ("no mark, little-endian, UTF-16, a lone surrogate in an attribute",
     _rels_with_a_lone_surrogate("UTF-16", "utf-16-le")),
    ("no mark, big-endian, UTF-16, a lone surrogate in an attribute",
     _rels_with_a_lone_surrogate("UTF-16", "utf-16-be")),
    ("a little-endian mark, UTF-16LE, a lone surrogate in an attribute",
     _rels_with_a_lone_surrogate("UTF-16LE", "utf-16-le", b"\xff\xfe")),
    ("no mark, little-endian, UTF-16LE, a lone surrogate in an attribute",
     _rels_with_a_lone_surrogate("UTF-16LE", "utf-16-le")),
    ("a big-endian mark, UTF-16BE, a lone surrogate in an attribute",
     _rels_with_a_lone_surrogate("UTF-16BE", "utf-16-be", b"\xfe\xff")),
    ("no mark, big-endian, UTF-16BE, a lone surrogate in an attribute",
     _rels_with_a_lone_surrogate("UTF-16BE", "utf-16-be")),
    ("a little-endian mark, no declaration, a lone surrogate in an attribute",
     _rels_with_a_lone_surrogate(None, "utf-16-le", b"\xff\xfe")),
    ("a big-endian mark, no declaration, a lone surrogate in an attribute",
     _rels_with_a_lone_surrogate(None, "utf-16-be", b"\xfe\xff")),
]

#: The same names, a whole document and no mark, ending on an odd byte.
ODD_LAST_BYTE = [
    ("no mark, little-endian, UTF-16, an odd last byte", "UTF-16", "utf-16-le"),
    ("no mark, big-endian, UTF-16, an odd last byte", "UTF-16", "utf-16-be"),
    ("no mark, little-endian, UTF-16LE, an odd last byte", "UTF-16LE", "utf-16-le"),
    ("no mark, big-endian, UTF-16BE, an odd last byte", "UTF-16BE", "utf-16-be"),
]


@pytest.mark.parametrize("label,raw", THE_PARSER_S_NAMES, ids=[u[0] for u in THE_PARSER_S_NAMES])
def test_utf16_bytes_that_are_not_utf16_are_refused_whatever_the_name(label, raw):
    """Refused here, for the bytes -- the parser is not the one that does."""
    with pytest.raises(EncodingNotRead) as refused:
        xml_as_utf8(raw)
    assert refused.value.kind == "bytes", label


@pytest.mark.parametrize("label,raw", THE_PARSER_S_NAMES, ids=[u[0] for u in THE_PARSER_S_NAMES])
def test_a_relationships_part_with_a_lone_surrogate_is_refused_and_not_read(tmp_path, label, raw):
    path = tmp_path / "p.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", raw)
        archive.writestr("aasx/aasx-origin", b"")
    (error,) = loader.load(path).errors
    assert error.stage == "chain" and error.fix.startswith("The file is in UTF-16"), (label, error)


def test_a_declaration_of_utf16_over_ascii_bytes_still_asks_for_the_right_declaration(tmp_path):
    """The bytes do not settle UTF-16: this is the declared-byte remedy,
    whose first option is UTF-8 before changing the declaration."""
    path = tmp_path / "declared.xml"
    path.write_bytes(_environment("UTF-16", "a").encode("ascii"))
    (error,) = loader.load(path).errors
    # A declared-byte refusal offers the UTF-8 route before redeclaring.
    assert error.fix == ("Save the document as UTF-8 and drop the declaration, or declare the "
                         "encoding the file is in, by the name the IANA charset registry gives "
                         "it. %s" % loader.REFUSED_NOT_JUDGED)


@pytest.mark.parametrize("label,declared,codec", ODD_LAST_BYTE, ids=[u[0] for u in ODD_LAST_BYTE])
def test_a_document_with_no_mark_and_an_odd_last_byte_is_refused_for_its_bytes(
        tmp_path, capsys, label, declared, codec):
    path = tmp_path / "odd.xml"
    path.write_bytes(_environment(declared, "a").encode(codec) + b"\x00")
    (error,) = loader.load(path).errors
    assert error.fix.startswith("The file is in UTF-16"), (label, error)
    code, _ = _judged(path, capsys)
    assert code == 2, label


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


def test_the_library_and_the_command_give_one_refusal_word_for_word(tmp_path, capsys):
    """The remedy is part of the answer: what the command prints for a
    document it refuses, the library returns, fix and all."""
    from aas_submodel_validate import validate

    raw = _environment("sjis", "a").encode("ascii")
    path = tmp_path / "declared.xml"
    path.write_bytes(raw)
    code, printed = _judged(path, capsys)
    returned = [{key: value for key, value in finding.as_dict().items() if key != "subject"}
                for finding in validate(raw, format="xml", allow_unmatched=True).findings]
    assert code == 2 and printed == returned
    assert "Declare it as Shift_JIS" in printed[0]["fix"]


@pytest.mark.parametrize("declared,codec,mark,ending,lines", [
    ("UTF-16", "utf-16-le", b"\xff\xfe", b"\x00\xd8", 1),
    ("csUTF16LE", "utf-16-le", b"", b"\x00", 2),
    ("windows-1252", "cp1252", b"", b"\x81", 3),
], ids=["surrogate", "odd-byte", "charset-byte"])
def test_a_relationships_refusal_keeps_its_message_line(
        tmp_path, capsys, declared, codec, mark, ending, lines):
    """X2 carries the line the encoding refusal names, through the chain
    loader and the command's report, even when decoding stops at the end."""
    text = _rels(declared).replace('Target="/aasx/', 'Target="aasx/')
    raw = mark + (text + "\n" * lines).encode(codec) + ending
    path = tmp_path / "input.aasx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", raw)
        archive.writestr("aasx/aasx-origin", b"")
    code, findings = _judged(path, capsys)
    assert code == 2
    (finding,) = [f for f in findings if f["rule"] == "X2"]
    (named,) = re.findall(r"\bline (\d+)\b", finding["message"])
    assert finding["line"] == int(named) == lines + 1


@pytest.mark.parametrize("declared,codec,value", [
    ("KS_C_5601-1987", "cp949", "똠"),
    ("EUC-KR", "cp949", "똠"),
    ("csASCII", "utf-8", "é"),
    ("Shift_JIS", "latin-1", "ÿ"),
    ("csUTF8", "latin-1", "ÿ"),
    ("windows-1252", "latin-1", "\x81"),
])
def test_declared_byte_refusal_offers_utf8_first(tmp_path, declared, codec, value):
    path = tmp_path / "input.xml"
    raw = _environment(declared, value).encode(codec)
    path.write_bytes(raw)
    with pytest.raises(EncodingNotRead) as refused:
        xml_as_utf8(raw)
    assert refused.value.kind == "bytes" and not refused.value.settled
    assert refused.value.instead is None
    (error,) = loader.load(path).errors
    assert error.fix.startswith("Save the document as UTF-8 and drop the declaration, or declare ")
    assert error.fix == ("Save the document as UTF-8 and drop the declaration, or declare the "
                         "encoding the file is in, by the name the IANA charset registry gives "
                         "it. %s" % loader.REFUSED_NOT_JUDGED)
