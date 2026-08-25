"""IDTA 02004 Handover Documentation: the hand-written rules.

The generated structural layer (cardinality, types, per-element
semanticIds) arrives with the vendored template; what lives here is what
a template file cannot express — the mandatory VDI 2770 classification,
the status vocabulary, dates that are dates, files that exist.

Whether a Handover submodel is present at all is *not* here: that
question belongs to the tool rather than to this template, and it is
asked once for every template in `rules/detect.py`.
"""
from __future__ import annotations

import re

from ..model import Violation
from ..registry import rule
from . import hd_tables
from .hd_engine import analyze, matched_submodels

#: The template's own identity — one authority, the generated table.
TEMPLATE_SEMANTIC_ID = hd_tables.TEMPLATE_SEMANTIC_ID


# -- the generated structural layer ------------------------------------------
#
# One registered rule per template row, each reading its slice of the
# single cached walk. The table is generated from the vendored official
# template (tools/extract_smt_rules.py); the walk lives in hd_engine.

def _row_check(row_id: str):
    def check(ctx):
        if not matched_submodels(ctx):
            return  # SMT-D1's finding; empty scopes would double-report it
        yield from analyze(ctx)["violations"].get(row_id, ())
    return check


for _row in hd_tables.ROWS:
    rule(_row["id"], kind="template", prio="MUST",
         title="'%s' as the template declares it (%s)"
               % (_row["label"], _row["sid"] or "by structure"),
         spec="IDTA 02004-2-0-1 template, SMT/Cardinality qualifier",
         fix=_row["fix"])(_row_check(_row["id"]))


# -- the hand rules: what a template file cannot express ---------------------

from .hd_engine import child_of, children_of, instances_of, property_value  # noqa: E402

#: VDI 2770 Blatt 1:2020, Table 1 -- the exact spelling the specification
#: says identifies the mandatory classification system, and its twelve
#: document classes.
VDI2770_SYSTEM = "VDI 2770 Blatt 1:2020"
#: The template's own ExampleValue -- and therefore the official example --
#: spells it "VDI2770:2020", contradicting §2.3's identifying value. Both
#: are recognised as the mandatory system; the non-canonical spelling
#: draws HDL5. docs/divergences.md #9.
VDI2770_SPELLINGS = frozenset((VDI2770_SYSTEM, "VDI2770:2020"))
VDI2770_CLASS_IDS = frozenset((
    "01-01", "02-01", "02-02", "02-03", "02-04",
    "03-01", "03-02", "03-03", "03-04", "03-05", "03-06", "04-01"))


def _vdi_classifications(document):
    classifications = children_of(child_of(document, "DocumentClassifications")
                                  or document, "DocumentClassification")
    return [c for c in classifications
            if property_value(c, "ClassificationSystem") in VDI2770_SPELLINGS]


@rule("HD-D2", kind="template", prio="MUST",
      title="every Document carries a VDI 2770 classification",
      spec="IDTA 02004-2-0 §2.3",
      fix="Add a DocumentClassification whose ClassificationSystem property "
          "holds exactly '%s'; pick its ClassId from the twelve VDI 2770 "
          "classes (e.g. 03-02, Operation)." % VDI2770_SYSTEM)
def hd_d2_vdi_classification(ctx):
    """§2.3: "The classification according to VDI 2770 Blatt 1:2020 is
    mandatory in the Submodel Handover Documentation," identified by
    exactly that ClassificationSystem value."""
    for subject, document in instances_of(ctx, "Document"):
        if not _vdi_classifications(document):
            yield Violation("no DocumentClassification declares the mandatory "
                            "VDI 2770 classification system", subject=subject)


@rule("HD-D3", kind="template", prio="MUST",
      title="VDI 2770 ClassId comes from the twelve published classes",
      spec="IDTA 02004-2-0 §2.3, Table 1",
      fix="Replace the ClassId with one of the twelve VDI 2770 Blatt 1:2020 "
          "ids: 01-01, 02-01..02-04, 03-01..03-06 or 04-01.")
def hd_d3_class_id(ctx):
    for subject, document in instances_of(ctx, "Document"):
        for classification in _vdi_classifications(document):
            class_id = property_value(classification, "ClassId")
            if class_id is not None and class_id not in VDI2770_CLASS_IDS:
                yield Violation("ClassId is not a VDI 2770 Blatt 1:2020 class",
                                subject=subject, detail="saw %r" % class_id)


@rule("HD-D4", kind="template", prio="MUST",
      title="the VDI 2770 ClassName speaks English",
      spec="IDTA 02004-2-0 §2.3 (\"EN is mandatory\")",
      fix="Add an 'en' entry to ClassName; Table 1 names each class in "
          "English (for 03-02 it is 'Operation').")
def hd_d4_class_name_english(ctx):
    for subject, document in instances_of(ctx, "Document"):
        for classification in _vdi_classifications(document):
            name = child_of(classification, "ClassName")
            if name is None:
                continue  # absence is the generated cardinality rule's finding
            languages = {entry.language for entry in (name.value or [])}
            english = any(lang.lower() == "en" or lang.lower().startswith("en-")
                          for lang in languages)
            if not english:
                yield Violation("ClassName has no English entry",
                                subject=subject,
                                detail="languages present: %s"
                                       % (", ".join(sorted(languages)) or "none"))


@rule("HD-D5", kind="template", prio="SHOULD",
      title="one of several DocumentIds is marked primary",
      spec="IDTA 02004-2-0 §2.6 (DocumentIsPrimary)",
      fix="Set DocumentIsPrimary = true on exactly one DocumentId, so "
          "consumers know which identifier to file the document under.")
def hd_d5_primary_id(ctx):
    """§2.6 defines the flag against "a collection of at least two
    DocumentId's" -- so only the several-ids-none-primary case is a
    finding; a lone id needs no flag."""
    for subject, document in instances_of(ctx, "Document"):
        ids = children_of(child_of(document, "DocumentIds") or document, "DocumentId")
        primaries = [d for d in ids
                     if (property_value(d, "DocumentIsPrimary") or "").strip().lower()
                     in ("true", "1")]
        if len(ids) >= 2 and not primaries:
            yield Violation("%d DocumentIds and none is marked primary" % len(ids),
                            subject=subject)


@rule("HD-D6", kind="template", prio="SHOULD",
      title="StatusValue uses the two-word vocabulary",
      spec="IDTA 02004-2-0 §2.8",
      fix="Set StatusValue to 'InReview' or 'Released' (exact casing) -- "
          "the two values VDI 2770 names.")
def hd_d6_status_value(ctx):
    for subject, version in instances_of(ctx, "DocumentVersion"):
        status = property_value(version, "StatusValue")
        if status is not None and status not in ("InReview", "Released"):
            yield Violation("StatusValue is outside the vocabulary",
                            subject=subject, detail="saw %r" % status)


@rule("HD-D7", kind="template", prio="MUST",
      title="files named by DigitalFile/PreviewFile exist in the container",
      spec="IDTA 02004-2-0 §2.8; IDTA 01005 (AASX)",
      fix="Add the file to the .aasx (with a matching aas-suppl "
          "relationship) or correct the File value's path.")
def hd_d7_files_exist(ctx):
    """Only answerable when the input *is* a container; an environment
    JSON names files this rule cannot see, and silence there is honesty,
    not laxity -- the finding would name a defect in the packaging, and
    there is no packaging."""
    container = ctx.loaded.container
    if container is None:
        return
    for label in ("DigitalFile", "PreviewFile"):
        for subject, element in instances_of(ctx, label):
            value = getattr(element, "value", None)
            if not isinstance(value, str) or not value.strip() or "://" in value:
                continue  # an empty value names nothing -- a different defect
            if not container.has(value.lstrip("/")):
                yield Violation("the container holds no part at this File's value",
                                subject=subject, detail=value)


_XS_DATE = re.compile(r"^(-?\d{4,})-(\d{2})-(\d{2})(Z|[+-]\d{2}:\d{2})?$")


def _valid_xs_date(value: str) -> bool:
    """xs:date lexical space -- which is wider than datetime.date: the year
    may be negative or run past 9999, so it is checked lexically rather
    than by constructing a date (which would reject `-0001-01-01`, a value
    aas-core3 accepts). The timezone offset is bounded to +/-14:00."""
    matched = _XS_DATE.match(value)
    if not matched:
        return False
    year, month, day = int(matched.group(1)), int(matched.group(2)), int(matched.group(3))
    if not 1 <= month <= 12:
        return False
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    days_in = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[month - 1]
    if not 1 <= day <= days_in:
        return False
    offset = matched.group(4)
    if offset and offset != "Z":
        hours, minutes = int(offset[1:3]), int(offset[4:6])
        if minutes > 59 or hours * 60 + minutes > 14 * 60:
            return False
    return True


@rule("HD-D8", kind="template", prio="MUST",
      title="StatusSetDate is a calendar date",
      spec="IDTA 02004-2-0 §2.8 (xs:date)",
      fix="Write StatusSetDate as YYYY-MM-DD (xs:date), e.g. 2020-02-06.")
def hd_d8_status_date(ctx):
    """The generated rule checks the *declared* valueType; this one checks
    the value itself, because 'xs:date' declared over '06.02.2020' is the
    commoner mistake."""
    for subject, version in instances_of(ctx, "DocumentVersion"):
        value = property_value(version, "StatusSetDate")
        if value is not None and not _valid_xs_date(value):
            yield Violation("StatusSetDate is not a valid xs:date",
                            subject=subject, detail="saw %r" % value)


@rule("HDL1", kind="lint", prio="MAY",
      title="idShorts follow the template's naming suggestion",
      spec="IDTA 02004-2-0 Annex A; template AllowedIdShort qualifiers",
      fix="Rename to the template's suggested pattern (base name plus an "
          "optional 2-3 digit suffix). Any unique idShort is legal; this "
          "is tidiness, not conformance.")
def hdl1_idshort_pattern(ctx):
    for subject, id_short, pattern in analyze(ctx)["idshort_drift"]:
        yield Violation("idShort does not follow the template's suggestion",
                        subject=subject,
                        detail="%r does not match %s" % (id_short, pattern))


@rule("HDL2", kind="lint", prio="SHOULD",
      title="near-miss semantic identifiers are diagnosed, not ignored",
      spec="matching policy, docs/divergences.md",
      fix="Correct the semanticId to the template's spelling; a near-miss "
          "matches nothing, and every rule that would have applied to the "
          "element silently stops applying.")
def hdl2_near_miss(ctx):
    for subject, seen, expected in analyze(ctx)["near_misses"]:
        yield Violation("semanticId almost matches the template",
                        subject=subject,
                        detail="saw %s, the template says %s" % (seen, expected))


@rule("HDL3", kind="lint", prio="MAY",
      title="reference types match the template's",
      spec="IDTA 02004-2-0 Annex A",
      fix="Use the reference type the template declares here; the value "
          "matched, so this is interoperability polish, not a failure.")
def hdl3_reference_type(ctx):
    for subject, seen, expected in analyze(ctx)["reftype_drift"]:
        yield Violation(
            "the reference type differs from the template's",
            subject=subject, detail="saw %s, template uses %s" % (seen, expected),
            fix="Use %s %s here, as the template does; the value matched, "
                "so this is interoperability polish, not a failure."
                % ("an" if expected[:1] in "AEIOU" else "a", expected))


@rule("HDL4", kind="lint", prio="SHOULD",
      title="(DocumentDomainId, DocumentIdentifier) pairs are unique",
      spec="IDTA 02004-2-0 §2.6, Table 6 (DocumentDomainId: the domain \"in which the given DocumentId is unique\")",
      fix="Give each document a distinct identifier within its domain, or "
          "merge the entries if they describe one document.")
def hdl4_duplicate_ids(ctx):
    seen = {}
    for subject, document in instances_of(ctx, "Document"):
        for document_id in children_of(child_of(document, "DocumentIds") or document,
                                       "DocumentId"):
            pair = (property_value(document_id, "DocumentDomainId"),
                    property_value(document_id, "DocumentIdentifier"))
            if None in pair:
                continue
            if pair in seen and seen[pair] != subject:
                yield Violation("two documents share one (domain, identifier) pair",
                                subject=subject, detail="%s / %s" % pair)
            seen.setdefault(pair, subject)


def _resolve_in_submodel(submodel, keys) -> bool:
    """Can a ModelReference's key path be walked inside `submodel`?

    Children are found by idShort -- or by position when the containing
    element is a SubmodelElementList, whose children the metamodel
    addresses by index. Index resolution must work even when a list child
    carries an (illegal) idShort: the official example does exactly that,
    and the idShort is its AASd-120 violation, not the reference's.
    """
    scope = submodel.submodel_elements or []
    in_list = False
    steps = keys[1:]
    for position_in_path, key in enumerate(steps):
        found = None
        for position, element in enumerate(scope):
            if element.id_short == key.value or (in_list and str(position) == key.value):
                found = element
                break
        if found is None:
            return False
        if position_in_path == len(steps) - 1:
            return True                        # the last key resolved to an element
        value = getattr(found, "value", None)
        if not isinstance(value, list):
            return False                       # more keys, but this element is a leaf
        in_list = type(found).__name__ == "SubmodelElementList"
        scope = value
    return True


@rule("HD-D9", kind="template", prio="SHOULD",
      title="document/entity references resolve to an element that exists",
      spec="IDTA 02004-2-0 §2.2 (\"the creation of an Entity element is required\")",
      fix="Add the referenced Entity to the Entities list (or fix the "
          "reference's key path); a documented entity that does not exist "
          "leaves the document pointing at nothing.")
def hd_d9_entity_references_resolve(ctx):
    """§2.2 requires the creation of an Entity element for DocumentedEntity;
    for RefersTo/BasedOn/TranslationOf this is the same check applied as a
    general dangling-reference integrity lint (their §2.8 wording is about
    document-to-document references, not Entity creation). Resolution is
    attempted only for ModelReferences whose first key names *this*
    submodel: a reference into another AAS is a promise this tool cannot
    check offline, and §2.2 says such references "can span multiple AAS",
    so silence there is honesty, not a miss."""
    for submodel in matched_submodels(ctx):
        for label in ("DocumentedEntity", "RefersTo", "BasedOn", "TranslationOf"):
            for subject, element in instances_of(ctx, label):
                reference = getattr(element, "value", None)
                keys = getattr(reference, "keys", None) or []
                if not keys or reference.type.value != "ModelReference":
                    continue
                if keys[0].type.value != "Submodel" or keys[0].value != submodel.id:
                    continue
                if not _resolve_in_submodel(submodel, keys):
                    yield Violation(
                        "the reference walks to nothing in this submodel",
                        subject=subject,
                        detail="no element at key path %s"
                               % " / ".join(key.value for key in keys[1:]))


@rule("HDL5", kind="lint", prio="SHOULD",
      title="the VDI classification system uses §2.3's identifying value",
      spec="IDTA 02004-2-0 §2.3",
      fix="Write ClassificationSystem exactly as 'VDI 2770 Blatt 1:2020' -- "
          "the value §2.3 says identifies the mandatory system. "
          "'VDI2770:2020' is the template's example artefact and other tools "
          "matching on the specified string will not recognise it.")
def hdl5_vdi_spelling(ctx):
    for subject, document in instances_of(ctx, "Document"):
        for classification in _vdi_classifications(document):
            spelling = property_value(classification, "ClassificationSystem")
            if spelling != VDI2770_SYSTEM:
                yield Violation("ClassificationSystem spells the VDI system "
                                "non-canonically",
                                subject=subject, detail="saw %r" % spelling)


#: PDF/A is a profile of PDF; a content type proves a file is PDF, not that
#: it conforms to PDF/A -- so this stays a warning even though VDI 2770
#: states the requirement, and a legitimate non-PDF rendition (a CAD model)
#: draws it rather than an error.
PDF_CONTENT_TYPES = frozenset(("application/pdf",))


@rule("HD-D10", kind="template", prio="SHOULD",
      title="each DocumentVersion offers a PDF/A rendition",
      spec="IDTA 02004-2-0 §2.1 (\"PDF/A files are required\")",
      fix="Add a DigitalFile with contentType application/pdf (a PDF/A file, "
          "per VDI 2770) to this DocumentVersion. A content type cannot prove "
          "PDF/A conformance, so this is a warning, not an error.")
def hd_d10_pdfa_rendition(ctx):
    for subject, version in instances_of(ctx, "DocumentVersion"):
        files = children_of(child_of(version, "DigitalFiles") or version, "DigitalFile")
        if not files:
            continue                          # absence is HD-E33's cardinality finding
        content_types = {(getattr(f, "content_type", "") or "").lower() for f in files}
        if not content_types & PDF_CONTENT_TYPES:
            yield Violation(
                "no DigitalFile is a PDF; VDI 2770 requires a PDF/A rendition",
                subject=subject,
                detail="content types present: %s" % (", ".join(sorted(content_types)) or "none"))
