#!/usr/bin/env python3
"""Which verdicts moved since a released version, measured.

A release note's most consequential sentence is the one about what a
reader's pipeline will do differently, and it is the sentence hardest to
write by hand: the author knows what they changed, not what moved. Those
are different lists. A repair aimed at one shape moves four; a shape
named as newly-strict turns out to be judged exactly as before; and the
movements that matter most to a pipeline are the ones going the quiet
way -- a finding in the old version and silence in the new -- because
nothing downstream will notice them.

This runs the released version and the working tree over the same inputs
and prints what came out differently. The list it prints is the list the
CHANGELOG has to describe.

Nothing here is a gate: it reports, and a person decides which movements
are intended. It reads the old version out of git (`git archive`) rather
than an install, so it never depends on what happens to be on the
machine, and it runs each version in its own process, because two
versions of one package cannot share an interpreter.

    python tools/verdict_diff.py                 # against the latest tag
    python tools/verdict_diff.py --against v0.1.0
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "src/aas_submodel_validate/data/example/idta-02004-2.0.aasx"
TEMPLATES = sorted((ROOT / "src/aas_submodel_validate/data/smt").rglob("template.json"))


class Case(NamedTuple):
    """One input, and what the reader is asked to judge it with.

    A `(label, path)` pair can only ask one question: what does this
    version say about this file, with no flag but the format. So the
    release that introduced `--template` had no case for its own
    headline mode, and this comparison would have reported `0 moved`
    for anything that happened inside it -- the failure `_judge`'s
    docstring describes, in the one place that wrote it down.

    A third element rather than a field would have made every unpacking
    site change again the next time something joins, and there is a
    `--profile` waiting. A field means a consumer that does not care
    never mentions it: the budget layer takes `case.path` and is done.

    `template` is a path, not a bag of argv fragments, because two
    consumers read it -- the comparison builds a command line from it
    and a test hands it to `runner.run` -- and a bag would make one of
    them parse what the other wrote.
    """

    label: str
    path: object
    template: object = None


# -- the corpus ------------------------------------------------------------
#
# Every entry is a file on disk, built here rather than committed: an
# input that only exists to be judged twice is a fixture nobody would
# maintain, and one that goes stale reports "nothing moved" forever.
#
# Coverage is the honest limit of this tool and the reason it prints its
# own denominator. It cannot enumerate every shape a File value can
# take; what it can do is put the shapes this project has actually been
# wrong about through both versions, so a claim in the CHANGELOG is
# measured rather than believed.

FILE_VALUES = [
    "aasx/files/manual.pdf",            # the plain case, as a control
    "/aasx/files/manual.pdf",
    " aasx/files/manual.pdf ",
    "aasx/files/manual.pdf\n",
    "urn:iso:std:iso:1234",
    "mailto:docs@example.com",
    "data:application/pdf;base64,AAA=",
    "URN:ISO:STD:ISO:1234",
    "rev2:manual.pdf",
    "C:\\docs\\manual.pdf",
    "files/a://absent.pdf",
    "../outside.pdf",
    " ../outside.pdf ",
    "",
    "   ",
    "aasx/files/absent.pdf",
    # Characters no part-name segment may carry (RFC 3986 §3.3). The
    # first is the package's own content types stream, which is not a
    # part at all and drew nothing.
    "[Content_Types].xml",
    "aasx/files/man?ual.pdf",
    "aasx/files/man ual.pdf",
    "aasx/files/man%20ual.pdf",      # the legal spelling of the one above
]

#: Archives whose *entry name* is the odd spelling, paired with the value
#: that names it. Every File case above packs the same plain entry, so a
#: change to which spelling `part` tries first moves nothing in them --
#: the tool reported "0 of 32 moved" for a change that closes the four
#: disagreements in docs/divergences.md #18, because no input in it could
#: tell the two orders apart. An input that cannot distinguish the
#: versions is not coverage, and a denominator counting it says otherwise.
#: (entry the archive holds, value the File carries, must it resolve)
#: The third field is the point of the second row. Folding the value's
#: whitespace is reading a spelling; folding the *archive's* would be
#: inventing characters the value does not have, and a fix that resolved
#: that row would be over-accepting in a reader whose standing rule is
#: that refusing wrongly costs less than accepting wrongly.
HELD_SPELLINGS = [
    ("aasx/files/manual.pdf ", "/aasx/files/manual.pdf ", True),
    ("aasx/files/manual.pdf ", "/aasx/files/manual.pdf", False),
    ("aasx/files/manual.pdf", " /aasx/files/manual.pdf", True),
    ("aasx/files/manual.pdf", "/aasx/files/manual.pdf\t", True),
]

#: An identifier no pack answers for and none will: the corpus needs one
#: to ask what a table the caller brought decides, and a real IDTA number
#: would stop being unclaimed the day this project vendors it.
UNVENDORED = "urn:example:verdict-diff:no-pack-answers-for-this"

LANGUAGE_FOLDS = [("upper", str.upper), ("title", str.title), ("lower", str.lower)]
DECLARED_ENCODINGS = ["utf-8", "iso-8859-1", "windows-1252", "utf-16", "us-ascii"]


def _members(path):
    with zipfile.ZipFile(path) as archive:
        return [(item.filename, archive.read(item.filename))
                for item in archive.infolist()]


def _payload_of(members):
    candidates = [(name, data) for name, data in members
                  if name.endswith(".xml") and "_rels/" not in name
                  and not name.startswith("[")]
    return max(candidates, key=lambda pair: len(pair[1]))[0]


def _write(dest, members):
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members:
            archive.writestr(name, data)
    return dest


def _rewrite_payload(members, change):
    payload = _payload_of(members)
    return [(name, change(data) if name == payload else data)
            for name, data in members]


def build_corpus(into: Path):
    """A `Case` for everything both versions will be asked about."""
    cases = [Case("the official example, untouched", EXAMPLE)]

    for template in TEMPLATES:
        rel = template.relative_to(ROOT / "src/aas_submodel_validate/data/smt")
        cases.append(Case("the vendored template %s" % rel.parent, template))

    base = _members(EXAMPLE)

    for name, fold in LANGUAGE_FOLDS:
        def change(data, fold=fold):
            text = data.decode("utf-8-sig")
            return re.sub(r"<language>([^<]*)</language>",
                          lambda m: "<language>%s</language>" % fold(m.group(1)),
                          text).encode("utf-8")
        cases.append(Case("language tags in %s case" % name,
                      _write(into / ("lang-%s.aasx" % name),
                             _rewrite_payload(base, change))))

    for encoding in DECLARED_ENCODINGS:
        def change(data, encoding=encoding):
            text = data.decode("utf-8-sig")
            text = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", text)
            text = '<?xml version="1.0" encoding="%s"?>\n' % encoding + text
            return text.encode(encoding, "xmlcharrefreplace")
        cases.append(Case("the payload declares %s" % encoding,
                      _write(into / ("enc-%s.aasx" % encoding),
                             _rewrite_payload(base, change))))

    # A File value is where the most verdicts moved, so each shape gets
    # its own container rather than sharing one: two shapes in one file
    # produce one verdict and hide each other.
    sys.path.insert(0, str(ROOT / "tests"))
    from builders import build_aasx, hd_env  # noqa: E402
    for index, value in enumerate(FILE_VALUES):
        environment = hd_env()
        version = environment["submodels"][0]["submodelElements"][0]["value"][0]["value"][2]["value"][0]
        files = version["value"][-1]
        assert files["idShort"] == "DigitalFiles", files["idShort"]
        files["value"][0]["value"] = value
        cases.append(Case("a File value of %r" % value,
                      build_aasx(into / ("file-%02d.aasx" % index),
                                 payload=json.dumps(environment).encode("utf-8"),
                                 files=[("aasx/files/manual.pdf", b"%PDF-1.4 ")])))

    # And the same question on a pack outside 02004's family. Every File
    # case above is built on a Handover document, and Handover has asked
    # this since the rule existed -- so a change that gives the question
    # to another pack moves no case here and reports as nothing moved.
    # That is the shape this file's own docstring is about, met a second
    # time: an instrument with no case for the thing that changed.
    from builders import dn_env  # noqa: E402
    for index, (label, held) in enumerate((
            ("a Nameplate whose images are in the package",
             [("aasx/files/logo.png", b"\x89PNG\r\n"),
              ("aasx/files/ce.png", b"\x89PNG\r\n")]),
            ("a Nameplate naming images the package does not hold", []))):
        cases.append(Case(label,
                          build_aasx(into / ("nameplate-file-%d.aasx" % index),
                                     payload=json.dumps(dn_env()).encode("utf-8"),
                                     files=held, suppl_targets=[])))

    # The same question asked the other way round: the archive holds the
    # odd spelling and the value is ordinary, or the reverse. This is
    # where the two ways into the normaliser could disagree, so it is
    # where a change to their order has to be measurable.
    for index, (entry, value, _resolves) in enumerate(HELD_SPELLINGS):
        environment = hd_env()
        version = environment["submodels"][0]["submodelElements"][0]["value"][0]["value"][2]["value"][0]
        files = version["value"][-1]
        assert files["idShort"] == "DigitalFiles", files["idShort"]
        files["value"][0]["value"] = value
        cases.append(Case("the archive holds %r and the File says %r" % (entry, value),
                      build_aasx(into / ("held-%02d.aasx" % index),
                                 payload=json.dumps(environment).encode("utf-8"),
                                 files=[(entry, b"%PDF-1.4 ")])))

    # A Technical Data list that declares an item type the template does
    # not. Four rows have a `0..*` item row, and there a list carrying no
    # items is metamodel-clean and satisfies every row -- so nothing here
    # could see the check that reads the declaration.
    from builders import td_env  # noqa: E402

    def _wearing(node, sid):
        if isinstance(node, dict):
            for key in (node.get("semanticId") or {}).get("keys") or []:
                if key.get("value") == sid:
                    return node
            for value in node.values():
                found = _wearing(value, sid)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = _wearing(value, sid)
                if found is not None:
                    return found
        return None

    from aas_submodel_validate.rules import td_tables  # noqa: E402

    for label in ("ProductImages", "SpecificDescriptions"):
        environment = td_env()
        listed = _wearing(environment, td_tables.BY_LABEL[label]["sid"])
        listed["typeValueListElement"] = "File"
        listed.pop("value", None)
        written = into / ("listtype-%s.json" % label)
        written.write_text(json.dumps(environment), encoding="utf-8")
        cases.append(Case("a %s list declaring it holds File" % label, written))

    # A Digital Nameplate submodel. Nothing here carried one, so the
    # corpus could not see IDTA 02006 land: a version with no table for
    # it refuses it as unmatched (SMT-D1) and one with the table judges
    # it. A valid one, and one whose URIOfTheProduct is a relative
    # reference -- which DN-D1 reports and the metamodel passes.
    from builders import dn_env  # noqa: E402

    nameplate = into / "nameplate-valid.json"
    nameplate.write_text(json.dumps(dn_env()), encoding="utf-8")
    cases.append(Case("a valid Digital Nameplate submodel", nameplate))

    relative = dn_env()
    for _submodel in relative["submodels"]:
        for _element in _submodel.get("submodelElements", []):
            if _element.get("idShort") == "URIOfTheProduct":
                _element["value"] = "Model-1234/Serial-5678"
    relative_uri = into / "nameplate-relative-uri.json"
    relative_uri.write_text(json.dumps(relative), encoding="utf-8")
    cases.append(Case("a Digital Nameplate whose URIOfTheProduct is relative",
                  relative_uri))

    # A Carbon Footprint submodel. It wears an identifier 02023 and 02035-3
    # both claim, so it draws BAT-R2's caveat as well as 02023's rows -- the
    # movement this pack introduced, which no earlier corpus input can show.
    from builders import pcf_env  # noqa: E402
    carbon = into / "carbon-footprint-valid.json"
    carbon.write_text(json.dumps(pcf_env()), encoding="utf-8")
    cases.append(Case("a valid Carbon Footprint submodel", carbon))

    # A Contact Information submodel. Nothing here carried one, so the
    # corpus could not see IDTA 02002 land: a version with no table for it
    # refuses it as unmatched (SMT-D1) and exits 1, and one with the table
    # judges it against thirty-six rows and exits 0. Without this case the
    # "no verdict moved" gate is answered by a corpus that cannot see the
    # pack at all -- the same hole 02006 and 02023 left above.
    from builders import contact_env  # noqa: E402
    contact = into / "contact-information-valid.json"
    contact.write_text(json.dumps(contact_env()), encoding="utf-8")
    cases.append(Case("a valid Contact Information submodel", contact))

    # Two children of one scope carrying the same idShort. The metamodel
    # forbids it and this reader relays that as a warning rather than
    # refusing the file, so a file like this is judged -- and what it is
    # judged to have done is where a finding's subject stops being an
    # identity. 0.4.1 appends an index there, which is a change to a
    # string a consumer matches on, and no input here had two siblings
    # sharing a name, so the corpus could not see it move.
    twinned = contact_env()
    _children = twinned["submodels"][0]["submodelElements"][0]["value"]
    _twin = copy.deepcopy(
        next(c for c in _children if c.get("idShort") == "Phone"))
    # Standing in a kind the template does not declare, so a finding names
    # the *element* and not the scope it sits in. A plain duplicate draws
    # a cardinality finding whose subject is the parent, and the subject
    # this release changes is the element's -- measured: a plain duplicate
    # moved nothing here, which would have made this case a corpus entry
    # that watches the right file and asks the wrong question.
    _twin["modelType"] = "Property"
    _twin["valueType"] = "xs:string"
    _twin.pop("value", None)
    _children.append(_twin)
    twins = into / "contact-information-two-of-one-name.json"
    twins.write_text(json.dumps(twinned), encoding="utf-8")
    cases.append(Case("a Contact Information submodel with two elements of one name",
                  twins))

    # A battery passport that states its own category. `BAT-R8` withheld
    # eight rows because their obligation turns on a category and nothing
    # read one; the template makes the category mandatory and names its
    # vocabulary, so a file that states `ev` or `lmt` answers them. No
    # input here carried a battery passport at all, so the corpus could
    # not see that rule move.
    from aas_submodel_validate.rules import battery_tables  # noqa: E402

    def _ref(value):
        return {"type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": value}]}

    for category in ("ev", "lmt", "industrial"):
        by_submodel = {}
        for row in battery_tables.CONDITIONAL_ON_CATEGORY:
            by_submodel.setdefault(row["submodel_semantic_id"], [])
        submodels = []
        for index, sid in enumerate(sorted(by_submodel)):
            value = []
            if sid.endswith("TechnicalData/1/0"):
                value.append({
                    "idShort": "GeneralInformation",
                    "modelType": "SubmodelElementCollection",
                    "semanticId": _ref("urn:samm:io.admin-shell.idta.batterypass."
                                       "technical_data:1.0.0#generalInformation"),
                    "value": [{"idShort": "BatteryCategory", "modelType": "Property",
                               "valueType": "xs:string", "value": category,
                               "semanticId": _ref("urn:samm:io.admin-shell.idta."
                                                  "batterypass.technical_data:1.0.0"
                                                  "#batteryCategory")}]})
            submodels.append({"idShort": "Part%d" % index, "modelType": "Submodel",
                              "id": "urn:corpus:battery:%s:%d" % (category, index),
                              "kind": "Instance", "semanticId": _ref(sid),
                              "submodelElements": value})
        environment = {"assetAdministrationShells": [], "conceptDescriptions": [],
                       "submodels": submodels}
        # A bare environment, not a package: `BAT-R8` needs no container
        # and the question here is the category, not the packaging.
        written = into / ("battery-%s.json" % category)
        written.write_text(json.dumps(environment), encoding="utf-8")
        cases.append(Case("a battery passport declaring category %r" % category, written))

    # And one stating two of them. `BAT-R8` used to answer on whichever
    # category the walk reached first -- the same file with the two
    # reversed drew a different set of rows -- and it now answers only
    # when a file states one. That is a verdict change, and the corpus
    # could not see it: every input above states exactly one, so the
    # comparison for the release that made it read "none of these is
    # judged differently" while saying nothing about the only shape it
    # touched. A zero from a corpus that cannot hold the case reads
    # exactly like a zero from one that can.
    #
    # Both categories sit in one submodel. Two submodels each stating one
    # would also change how many Technical Data submodels the file has,
    # and then a difference could not be attributed to the categories.
    both = []
    for index, sid in enumerate(sorted(by_submodel)):
        value = []
        if sid.endswith("TechnicalData/1/0"):
            value.append({
                "idShort": "GeneralInformation",
                "modelType": "SubmodelElementCollection",
                "semanticId": _ref("urn:samm:io.admin-shell.idta.batterypass."
                                   "technical_data:1.0.0#generalInformation"),
                "value": [{"idShort": "BatteryCategory%d" % seat,
                           "modelType": "Property", "valueType": "xs:string",
                           "value": stated,
                           "semanticId": _ref("urn:samm:io.admin-shell.idta."
                                              "batterypass.technical_data:1.0.0"
                                              "#batteryCategory")}
                          for seat, stated in enumerate(("ev", "lmt"))]})
        both.append({"idShort": "Part%d" % index, "modelType": "Submodel",
                     "id": "urn:corpus:battery:both:%d" % index,
                     "kind": "Instance", "semanticId": _ref(sid),
                     "submodelElements": value})
    written = into / "battery-two-categories.json"
    written.write_text(json.dumps(
        {"assetAdministrationShells": [], "conceptDescriptions": [],
         "submodels": both}), encoding="utf-8")
    cases.append(Case("a battery passport declaring two categories", written))

    # And the shapes an aas-suppl relationship's target takes. The last
    # is the question the rule exists for and must not move; without it
    # the three above are equally satisfied by a rule switched off.
    payload = json.dumps(hd_env()).encode("utf-8")
    for label, kwargs in [
            ("external, absolute", {"suppl_external": ["http://example.com/m.pdf"]}),
            ("external, relative", {"suppl_external": ["../docs/m.pdf"]}),
            ("an absolute URI, no TargetMode",
             {"suppl_verbatim": ["http://example.com/m.pdf"]}),
            ("a part the archive does not hold",
             {"suppl_targets": ["aasx/files/absent.pdf"]}),
            # Surrounding whitespace on a target. `X4` answers through
            # the same `part()` as the File rule, so the entry-point
            # change reached it -- and no input here could see that, so
            # the tool reported one moved verdict where there were two.
            # The instrument having no case for the thing that changed
            # is the failure this file exists to prevent.
            # With the part packed: the question is whether the reader
            # finds it through the whitespace, not whether it is there.
            ("a target with a trailing tab, the part present",
             {"suppl_verbatim": ["/aasx/files/manual.pdf\t"],
              "files": [("aasx/files/manual.pdf", b"%PDF-1.4 ")]}),
            ("a target with a leading space, the part present",
             {"suppl_verbatim": [" /aasx/files/manual.pdf"],
              "files": [("aasx/files/manual.pdf", b"%PDF-1.4 ")]})]:
        cases.append(Case("an aas-suppl relationship: %s" % label,
                      build_aasx(into / ("suppl-%d.aasx" % len(cases)),
                                 payload=payload, **kwargs)))

    # The shapes 0.1.3 changed the answer for. A corpus that predates a
    # release measures the release against the questions somebody
    # thought to ask before it, and reports "three of forty-seven" while
    # four whole classes of input are not in it -- which reads as a
    # small change and is not the measurement it looks like.
    import json as _json

    from builders import hd_env as _hd_env

    def _value_removed(document, label):
        """The same document with one required property carrying nothing.

        The document is a parameter and the file name is the caller's,
        because a second case wanted this shape and a helper that wrote
        to `no-value-<label>.json` would have handed both cases one path
        -- two rows judging one file, and a budget layer timing it twice.
        """
        def strip(node):
            if isinstance(node, dict):
                if node.get("idShort") == label and node.get("modelType") == "Property":
                    node.pop("value", None)
                    return True
                return any(strip(v) for v in node.values())
            if isinstance(node, list):
                return any(strip(v) for v in node)
            return False
        assert strip(document), label
        return document

    no_value = into / "no-value-DocumentDomainId.json"
    no_value.write_text(_json.dumps(_value_removed(_hd_env(), "DocumentDomainId")),
                        "utf-8")
    cases.append(Case("a required property present and carrying no value", no_value))

    deep = into / "deeply-nested.json"
    deep.write_text("[" * 200000 + "]" * 200000, "utf-8")
    cases.append(Case("well-formed JSON this reader cannot build", deep))

    cases.append(Case("a path that is not there", into / "absent.json"))

    a_directory = into / "directory.json"
    a_directory.mkdir(exist_ok=True)
    cases.append(Case("a directory wearing a file's name", a_directory))

    lzma_broken = into / "lzma-stream-damaged.aasx"
    import zipfile as _zipfile
    source = build_aasx(into / "lzma-source.aasx", payload=_json.dumps(_hd_env()).encode())
    with _zipfile.ZipFile(source) as zin, \
            _zipfile.ZipFile(lzma_broken, "w", _zipfile.ZIP_LZMA) as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info.filename))
    raw = bytearray(lzma_broken.read_bytes())
    with _zipfile.ZipFile(lzma_broken) as archive:
        biggest = max(archive.infolist(), key=lambda i: i.compress_size)
    raw[biggest.header_offset + 30 + len(biggest.filename) + biggest.compress_size - 4] ^= 0xFF
    lzma_broken.write_bytes(bytes(raw))
    cases.append(Case("an LZMA member with a damaged stream", lzma_broken))

    # -- judged with a table the caller brought ----------------------------
    #
    # Everything above is judged with this reader's own packs, which was
    # every question there was to ask until a caller could hand in a
    # table of their own. A mode with no case here is a mode this tool
    # reports `0 moved` about forever, however much moves inside it.
    #
    # Four, not forty: every case is a pass in the time budget, and each
    # of these asks something the others cannot. None of them can be
    # compared against a release that predates the option -- `compare`
    # says so by name, above its count -- so their first comparison is
    # the one after this release, which is the point at which a corpus
    # that did not hold them would have been silent about a year of
    # changes to the mode.
    from builders import env_json  # noqa: E402

    def _a_table_of_our_own(path, identifier, child="SerialNumber"):
        def ref(value):
            return {"type": "GlobalReference",
                    "keys": [{"type": "GlobalReference", "value": value}]}

        path.write_text(json.dumps({"submodels": [{
            "kind": "Template", "idShort": "SomethingNobodyVendored",
            "id": "urn:example:verdict-diff:template",
            "semanticId": ref(identifier),
            "submodelElements": [{
                "modelType": "Property", "idShort": child,
                "semanticId": ref(identifier + "/" + child),
                "valueType": "xs:string",
                "qualifiers": [{"type": "SMT/Cardinality",
                                "valueType": "xs:string", "value": "One"}]}]}]}),
            encoding="utf-8")
        return path

    def _without_the_element(document, id_short):
        """The same document with one element gone from its scope."""
        def walk(node):
            if isinstance(node, dict):
                for key, value in list(node.items()):
                    if isinstance(value, list):
                        kept = [item for item in value
                                if not (isinstance(item, dict)
                                        and item.get("idShort") == id_short)]
                        if len(kept) != len(value):
                            node[key] = kept
                            return True
                    if walk(value):
                        return True
            elif isinstance(node, list):
                return any(walk(item) for item in node)
            return False
        assert walk(document), id_short
        return document

    # A table this project vendors, handed back in by the caller. Both
    # readers have one for this file and the question is which answers:
    # measured, the pack stands down and the same missing element comes
    # back as `TPL-E02` where the pack said `DN-E02`. An input that is
    # merely conformant could not show that -- both answer nothing.
    stand_down = into / "nameplate-for-a-table-handed-in.json"
    stand_down.write_text(
        json.dumps(_without_the_element(dn_env(), "ManufacturerName")), "utf-8")
    cases.append(Case(
        "a Digital Nameplate, judged by the vendored template handed in by hand",
        stand_down,
        template=ROOT / "src/aas_submodel_validate/data/smt/02006/3.0/template.json"))

    # The mode's reason to exist: a table no pack has, over a file that
    # declares it. Without the table this is `SMT-D1`, "nothing here
    # wears an identifier I have a table for"; with it, a verdict.
    ours = _a_table_of_our_own(into / "a-table-nobody-vendored.json", UNVENDORED)
    declares_it = into / "declares-a-template-nobody-vendored.json"
    declares_it.write_bytes(env_json(UNVENDORED))
    cases.append(Case("a submodel judged by a table no pack has",
                      declares_it, template=ours))

    # A supplied table that matches nothing, over a file with a defect
    # in it. The packs must go on answering: this row is the one that
    # goes quiet if a table standing down ever takes a file's own pack
    # with it, and quiet is the direction nothing downstream reports.
    beside_the_point = into / "handover-beside-a-table-that-matches-nothing.json"
    beside_the_point.write_text(json.dumps(_value_removed(_hd_env(), "DocumentDomainId")),
                                "utf-8")
    cases.append(Case("a defect beside a supplied table that matches nothing",
                      beside_the_point, template=ours))

    # A table that is not one. Not a verdict but an exit code, which is
    # what a build tool tells apart from "found something": this mode
    # refuses at 2 and the corpus is where that stays measured.
    not_a_table = into / "a-supplied-table-that-is-not-one.json"
    not_a_table.write_text('{"hello": "world"}', encoding="utf-8")
    judged_anyway = into / "handover-beside-a-table-that-is-not-one.json"
    judged_anyway.write_text(json.dumps(_hd_env()), encoding="utf-8")
    cases.append(Case("a supplied table that is not a template at all",
                      judged_anyway, template=not_a_table))

    return cases


# -- running both versions --------------------------------------------------

#: How long one input may take before the comparison calls it silence.
#: Far above anything the corpus costs -- the whole sixty run in about a
#: minute -- and far below a wait nobody notices.
_PATIENCE = 120


def _judge(src: Path, case: Case):
    """One version's verdict on one input: ids, severities, exit code --
    and what it did not ask.

    The last is not a verdict and does not move an exit code, which is
    exactly why it belongs here. A change that adds it reports as "0
    moved" against a comparison that cannot see it, and this tool's whole
    job is to stop a release note saying "nothing changed" on the
    strength of an instrument with no case for the thing that changed.
    A version that has no such key reports `None`. That is a change of
    shape and not of verdict, and it is counted apart: folding it in made
    every one of the thirty-six inputs "judged differently" the moment
    the key was added, which is true and buries the one whose verdict
    actually moved. An instrument that reports everything reports
    nothing."""
    argv = [sys.executable, "-m", "aas_submodel_validate", str(case.path), "-f", "json"]
    if case.template is not None:
        # The whole point of the case carrying it. A flag built here from
        # a list this function keeps would be a second place to state
        # what the corpus asks, and the two would drift the first time
        # one of them gained an entry.
        argv += ["--template", str(case.template)]
    try:
        run = subprocess.run(
            argv,
            capture_output=True, text=True, timeout=_PATIENCE,
            env={"PYTHONPATH": str(src), "PATH": "/usr/bin:/bin",
                 "PYTHONIOENCODING": "utf-8"})
    except subprocess.TimeoutExpired:
        # A deadline, because without one this tool stops when the reader
        # does. One input that never answers takes the whole comparison
        # with it and says nothing about which input it was -- and there
        # was such an input: until 0.4.1, a named pipe made the reader
        # wait for a writer that never came. The corpus is built on disk
        # and holds no pipe today, which is luck rather than a guarantee.
        return ((), 0, -1, None, None, "gave no answer in %ds" % _PATIENCE)
    try:
        report = json.loads(run.stdout)
    except ValueError:
        # The same shape as a verdict, with no findings in it. It used to
        # be a two-tuple carrying a sentence, and then `set(before[0])`
        # walked the characters of that sentence and the unpack below
        # died -- on the one comparison this release actually needed,
        # because 0.1.3 is the change that gives exit 2 a report. An
        # instrument that cannot compare "said nothing" with "said
        # something" is no instrument for a change of exactly that kind.
        return ((), 0, run.returncode, None, None, "no report")
    # The subject too. A finding names an element, and the name is what a
    # consumer suppressing a known finding matches on -- so a change that
    # renames one is a change that reaches them. It was left out, and the
    # release that started appending an index where two siblings share a
    # name reported "0 of 60 moved" against an instrument with no case
    # for it. This file's own docstring is about exactly that.
    findings = sorted(
        (f.get("rule"), f.get("severity"), f.get("subject"))
        for f in report.get("findings", []))
    ours = [f for f in findings if f[0] != "META"]
    relayed = len(findings) - len(ours)
    summary = report.get("summary") or {}
    not_asked = summary.get("rulesNotAsked")
    if not_asked is not None:
        not_asked = tuple(not_asked)
    # And the other statement of reach. `scopeNotExamined` reports what
    # the run did not open where nothing explains it, so it moves on
    # exactly the inputs `rulesNotAsked` stays silent about -- which is
    # to say, an instrument holding only the second cannot see the
    # change that introduced the first. Reported as a shape change the
    # same way and for the same reason: it fails no build.
    examined = summary.get("scopeNotExamined")
    if examined is not None:
        examined = tuple(sorted(
            (record.get("where"), record.get("rule"), record.get("because"))
            for record in examined))
    return (tuple(ours), relayed, run.returncode, not_asked, examined)


def _must_hold_a_reader(src: Path) -> Path:
    """`src` is a tree this comparison is about to import a reader from.

    `PYTHONPATH` is searched before site-packages, so a tree holding the
    package answers for it. A tree *not* holding it answers nothing and
    the question goes to whatever is installed on the machine -- and
    this project is installed on the machine that wrote this. Then both
    sides of the comparison are the same reader, every input agrees with
    itself, and the tool prints `0 moved` in the most convincing way it
    knows: an archive of a tag that predates the `src/` layout does this
    without a word.
    """
    if not (src / "aas_submodel_validate" / "cli.py").is_file():
        raise RuntimeError(
            "%s holds no reader to ask -- an installed copy would answer in "
            "place of the version meant, and agree with itself" % src)
    return src


#: One answer per source tree and option, because the question costs a
#: whole interpreter and does not change between inputs.
_OPTIONS: dict = {}


def _has_the_option(src: Path, option: str) -> bool:
    """Whether the version in `src` offers the option a case wants.

    Asked of the version rather than read off its number. A case judged
    with `--template` cannot be compared against a release that predates
    the flag: measured, v0.4.1 answers `unrecognized arguments` and exits
    64, which is not a verdict on anything. Counting that as a verdict
    that moved would put every such case in the moved list on the day the
    option landed -- true, and it buries whatever actually moved, which
    is the mistake this file already made once over `rulesNotAsked`.

    A probe that fails is not an absence. If the reader will not run, or
    prints no usage at all, this stops instead of answering False for
    every option -- False here empties the comparison quietly, and an
    instrument that goes silent when its own probe breaks is the failure
    this whole file is written against.
    """
    key = (str(src), option)
    if key not in _OPTIONS:
        _must_hold_a_reader(src)
        asked = subprocess.run(
            [sys.executable, "-m", "aas_submodel_validate", "--help"],
            capture_output=True, text=True, timeout=_PATIENCE,
            env={"PYTHONPATH": str(src), "PATH": "/usr/bin:/bin",
                 "PYTHONIOENCODING": "utf-8"})
        if asked.returncode != 0 or "usage:" not in asked.stdout:
            raise RuntimeError(
                "could not ask the version in %s which options it has "
                "(exit %d): %s" % (src, asked.returncode,
                                   (asked.stderr or asked.stdout).strip()[:200]))
        _OPTIONS[key] = option in asked.stdout
    return _OPTIONS[key]


def _comparable(src: Path, case: Case) -> bool:
    """Whether the version in `src` can be asked this case at all.

    The one place a case's field is turned into the option it needs, so
    that adding a field means adding it here and not in each of the two
    readers.
    """
    return case.template is None or _has_the_option(src, "--template")


def _verdict_of(judged):
    """The part a pipeline acts on. `rulesNotAsked` is deliberately not
    in here: it changes no exit code and fails no build."""
    # The marker counts. "Said nothing at exit 2" and "said one thing at
    # exit 2" are different answers to a consumer parsing stdout, and
    # comparing only the first three fields calls them the same.
    return judged[:3] + judged[5:]


def _named(finding):
    """A finding as one string: the rule, and the element if it names one."""
    rule, _severity, subject = finding
    return rule if not subject else "%s (%s)" % (rule, subject)


def _describe(verdict):
    if len(verdict) > 5:
        return "did not produce a report (exit %d)" % verdict[2]
    ours, relayed, code, not_asked, _examined = verdict
    counts = {}
    for _rule, severity, _subject in ours:
        counts[severity] = counts.get(severity, 0) + 1
    parts = ["%d %s" % (counts[k], k) for k in ("error", "warning", "info")
             if k in counts] or ["nothing"]
    if not_asked is None:
        unasked = ", says nothing about what it did not ask"
    elif not_asked:
        unasked = ", %d not asked (%s)" % (len(not_asked), ", ".join(not_asked))
    else:
        unasked = ", asked everything"
    return "%s, %d relayed (exit %d)%s" % (", ".join(parts), relayed, code, unasked)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--against", default=None,
                        help="the tag to compare with (default: the latest)")
    args = parser.parse_args(argv)

    tag = args.against
    if tag is None:
        # The newest tag, which is what "since the released version"
        # means while a release is being prepared -- unless a tag went
        # out and its release did not, and then the newest tag is a
        # reader nobody has. Run *on* the commit a release is cut from,
        # after its tag exists, that is this tree's own tag and the
        # comparison is a tree with itself: zero moved, trivially. Pass
        # `--against` in both places. The suite picks differently -- the
        # newest release the CHANGELOG dates below this tree's version
        # -- because a gate asking what an older reader says must not be
        # handed this one (`tests/test_verdict_diff.py`, `released_tree`).
        tags = subprocess.run(["git", "-C", str(ROOT), "tag", "--sort=-v:refname"],
                              capture_output=True, text=True, check=True)
        tag = tags.stdout.split("\n", 1)[0].strip()
        if not tag:
            sys.exit("no tag to compare against; pass --against")

    workspace = Path(tempfile.mkdtemp(prefix="verdict-diff-"))
    try:
        old = workspace / "old"
        old.mkdir()
        archive = subprocess.run(["git", "-C", str(ROOT), "archive", tag],
                                 capture_output=True, check=True)
        subprocess.run(["tar", "-x", "-C", str(old)], input=archive.stdout, check=True)
        # Before a single input is judged, because the answer to "did
        # that tag lay its package out this way" is not one to find out
        # from a column of zeroes.
        _must_hold_a_reader(old / "src")

        corpus = build_corpus(workspace)
        compare(tag, old / "src", corpus)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def compare(tag: str, old_src: Path, corpus, new_src: Path = None) -> dict:
    """Run both readers over the corpus, print what moved, and return the
    counts behind the sentences.

    Returned as well as printed because those sentences get copied into
    a release note: "0 of 61" is an arithmetic claim about a
    denominator, and until this came out of `main` nothing could ask it
    anything. The corpus is a parameter for the same reason -- a
    measurement of the summary that had to build all sixty-one inputs
    and run two readers over each would not be run.
    """
    new_src = new_src or (ROOT / "src")
    # How many carry a table, said in the header rather than in a
    # caveat at the bottom. The caveat that stood there -- "no case
    # here is judged with --template" -- was true and was written to be
    # deleted by whoever made it false; this is the same fact in the
    # form a reader can use, and it goes back to being a caveat by
    # itself if the count ever returns to zero.
    with_a_table = sum(1 for case in corpus if case.template is not None)
    print("%s -> working tree, over %d inputs%s\n"
          % (tag, len(corpus),
             ", %d of them judged with a table the caller supplied"
             % with_a_table if with_a_table else
             " -- none of them judged with a table the caller supplied"))

    moved = 0
    gained_the_key, reshaped = 0, 0
    gained_scope, moved_scope = 0, 0
    unanswerable = []
    for case in corpus:
        if not _comparable(old_src, case):
            # Judged by the working tree all the same. The comparison
            # has nothing to say about it, but a case that stopped
            # being judgeable at all is worth seeing on the way past.
            unanswerable.append((case, _judge(new_src, case)))
            continue
        before = _judge(old_src, case)
        after = _judge(new_src, case)
        # Counted apart, and stated once at the end. A key one
        # version does not have is a change of shape, and if it is
        # folded into "judged differently" every input moves the day
        # it lands.
        if len(before) > 3 and len(after) > 3:
            if before[3] is None and after[3] is not None:
                gained_the_key += 1
            elif before[3] != after[3]:
                reshaped += 1
        if before[4] != after[4]:
            if before[4] is None:
                gained_scope += 1
            else:
                moved_scope += 1
        if _verdict_of(before) == _verdict_of(after):
            continue
        moved += 1
        print("  %s" % case.label)
        print("      %-14s %s" % (tag, _describe(before)))
        print("      %-14s %s" % ("working tree", _describe(after)))
        gone = sorted(set(before[0]) - set(after[0]))
        new = sorted(set(after[0]) - set(before[0]))
        # Named with the element, because a finding can be the same
        # rule at the same severity and still be about a different
        # element -- which is the whole reason the subject is compared
        # at all. Without it this prints "no longer drawn: CI-E02"
        # directly above "newly drawn: CI-E02" and leaves a reader to
        # guess what moved.
        if gone:
            print("      no longer drawn: %s" % ", ".join(_named(f) for f in gone))
        if new:
            print("      newly drawn:     %s" % ", ".join(_named(f) for f in new))
        print()

    if unanswerable:
        # Above the count and not below it, because the count's
        # denominator is what this changes. A reader who takes "0 of
        # 65" and learns afterwards that four of them were never
        # asked has already quoted the first number.
        print("%d of %d are asked with an option %s does not have, so there "
              "is no earlier verdict for them to move from. They are not in "
              "the count below. What the working tree says about them:"
              % (len(unanswerable), len(corpus), tag))
        for case, after in unanswerable:
            print("  %s" % case.label)
            print("      %-14s %s" % ("working tree", _describe(after)))
        print()

    compared = len(corpus) - len(unanswerable)
    print("%d of %d inputs are judged differently." % (moved, compared))
    if gained_the_key:
        print("%d of %d gained `summary.rulesNotAsked`, which is additive and "
              "moves no verdict -- a consumer that does not read the key sees "
              "what it saw before." % (gained_the_key, compared))
    if gained_scope:
        print("%d of %d gained `summary.scopeNotExamined`, which is "
              "additive and moves no verdict -- a consumer that does not "
              "read the key sees what it saw before."
              % (gained_scope, compared))
    if moved_scope:
        print("%d of %d report a different `summary.scopeNotExamined` "
              "between two versions that both have it. Not a verdict "
              "either, and the one place a reader learns the run stopped "
              "opening a scope it used to open." % (moved_scope, compared))
    if reshaped:
        print("%d of %d report a different `summary.rulesNotAsked` between two "
              "versions that both have it. That is not a verdict either, and it "
              "is the one place a reader learns a rule stopped being put."
              % (reshaped, compared))
    print("Every one of them belongs in the CHANGELOG, and the ones whose "
          "exit code falls belong there twice: a pipeline that is red on "
          "them today goes quiet, and nothing downstream reports that.")
    return {"moved": moved, "compared": compared,
            "unanswerable": len(unanswerable),
            "gained_the_key": gained_the_key, "reshaped": reshaped,
            "gained_scope": gained_scope, "moved_scope": moved_scope}


if __name__ == "__main__":
    main()
