"""The Handover Documentation hand rules, written once for every table
that can answer them.

IDTA 02004 and IDTA 02035-2 publish the same submodel semanticId over the
same vocabulary of elements (docs/divergences.md #26), so what a template
file cannot say is the same sentence for both: the VDI 2770
classification is mandatory, its ClassId comes from twelve published
classes, a date is a date, a File names a part the container holds.
Copying those bodies into a second module would put the same requirement
in two places to be right, which is the failure the generated tables
exist to avoid.

What differs between the two is not the sentence but the *reach*:
02035-2 drops sixteen of 02004's rows, so three of these rules navigate
to elements it does not have. A rule that asked its table for a row the
table has no name for would raise `KeyError`, which `runner.execute`
turns into a finding at the rule's own severity saying "the rule itself
could not run" -- a conformant battery passport being told to report a
defect in the validator. So each rule declares the labels it navigates,
and a pack that installs one whose labels its table lacks is refused at
import: `SystemExit`, in the same voice the generator uses when two rows
share a label.

The refusal runs in both directions. A pack that *omits* a rule its table
could have answered is refused too, because a silently narrower pack is
the shape this repository keeps finding in its own gates.
"""
from __future__ import annotations

from ..model import Violation
from ..registry import rule
from .engine import (
    analyze,
    child_of,
    children_of,
    instances_of,
    matched_submodels,
    property_value,
    resolve_in_submodel,
)
from .values import valid_xs_date

#: VDI 2770 Blatt 1:2020, Table 1 -- the exact spelling the specification
#: says identifies the mandatory classification system, and its twelve
#: document classes.
VDI2770_SYSTEM = "VDI 2770 Blatt 1:2020"
#: The template's own ExampleValue -- and therefore the official example --
#: spells it "VDI2770:2020", contradicting §2.3's identifying value. Both
#: are recognised as the mandatory system; the non-canonical spelling
#: draws the L5 lint. docs/divergences.md #9. IDTA 02035-2's template
#: carries the same ExampleValue, which is one of the three ways its own
#: bytes say it keeps the VDI 2770 classification (divergences #29).
VDI2770_SPELLINGS = frozenset((VDI2770_SYSTEM, "VDI2770:2020"))
VDI2770_CLASS_IDS = frozenset((
    "01-01", "02-01", "02-02", "02-03", "02-04",
    "03-01", "03-02", "03-03", "03-04", "03-05", "03-06", "04-01"))

#: PDF/A is a profile of PDF; a content type proves a file is PDF, not that
#: it conforms to PDF/A -- so D10 stays a warning even though VDI 2770
#: states the requirement, and a legitimate non-PDF rendition (a CAD model)
#: draws it rather than an error.
PDF_CONTENT_TYPES = frozenset(("application/pdf",))


def _vdi_classifications(document, tables):
    classifications = children_of(child_of(document, "DocumentClassifications", tables)
                                  or document, "DocumentClassification", tables)
    return [c for c in classifications
            if property_value(c, "ClassificationSystem", tables) in VDI2770_SPELLINGS]


def _file_labels(tables):
    """The rows this template declares as Files, in template order.

    02004 has two (DigitalFile, PreviewFile) and 02035-2 has one. Reading
    them from the table rather than naming them is what carries D7 across
    to the second pack instead of crashing it on the row that is not
    there -- and what stops a reader assuming the narrowing was an
    oversight.
    """
    return tuple(row["label"] for row in tables.ROWS if row["kind"] == "File")


# -- the bodies ---------------------------------------------------------------

def _d2(tables):
    def check(ctx):
        """§2.3: "The classification according to VDI 2770 Blatt 1:2020 is
        mandatory in the Submodel Handover Documentation," identified by
        exactly that ClassificationSystem value."""
        for subject, document in instances_of(ctx, "Document", tables):
            if not _vdi_classifications(document, tables):
                yield Violation("no DocumentClassification declares the mandatory "
                                "VDI 2770 classification system", subject=subject)
    return check


def _d3(tables):
    def check(ctx):
        for subject, document in instances_of(ctx, "Document", tables):
            for classification in _vdi_classifications(document, tables):
                class_id = property_value(classification, "ClassId", tables)
                if class_id is not None and class_id not in VDI2770_CLASS_IDS:
                    yield Violation("ClassId is not a VDI 2770 Blatt 1:2020 class",
                                    subject=subject, detail="%r" % class_id)
    return check


def _d4(tables):
    def check(ctx):
        for subject, document in instances_of(ctx, "Document", tables):
            for classification in _vdi_classifications(document, tables):
                name = child_of(classification, "ClassName", tables)
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
    return check


def _d5(tables):
    def check(ctx):
        """§2.6 defines the flag against "a collection of at least two
        DocumentId's" -- so only the several-ids-none-primary case is a
        finding; a lone id needs no flag."""
        for subject, document in instances_of(ctx, "Document", tables):
            ids = children_of(child_of(document, "DocumentIds", tables) or document,
                              "DocumentId", tables)
            primaries = [d for d in ids
                         if (property_value(d, "DocumentIsPrimary", tables) or "").strip().lower()
                         in ("true", "1")]
            if len(ids) >= 2 and not primaries:
                yield Violation("%d DocumentIds and none is marked primary" % len(ids),
                                subject=subject)
    return check


def _d6(tables):
    def check(ctx):
        for subject, version in instances_of(ctx, "DocumentVersion", tables):
            status = property_value(version, "StatusValue", tables)
            if status is not None and status not in ("InReview", "Released"):
                yield Violation("StatusValue is outside the vocabulary",
                                subject=subject, detail="%r" % status)
    return check


def _d7(tables):
    labels = _file_labels(tables)

    def check(ctx):
        """Only answerable when the input *is* a container; an environment
        JSON names files this rule cannot see, and silence there is honesty,
        not laxity -- the finding would name a defect in the packaging, and
        there is no packaging."""
        container = ctx.loaded.container
        if container is None:
            return
        for label in labels:
            for subject, element in instances_of(ctx, label, tables):
                value = getattr(element, "value", None)
                if not isinstance(value, str) or not value.strip() or "://" in value:
                    continue  # an empty value names nothing -- a different defect
                from ..container import canonical_part_name
                if canonical_part_name(value) is None:
                    yield Violation("this File's value is not a part name",
                                    subject=subject,
                                    detail="%s climbs out of the package" % value)
                elif container.part(value) is None:
                    yield Violation("the container holds no part at this File's value",
                                    subject=subject, detail=value)
    return check


def _d8(tables):
    def check(ctx):
        """The generated rule checks the *declared* valueType; this one checks
        the value itself, because 'xs:date' declared over '06.02.2020' is the
        commoner mistake."""
        for subject, version in instances_of(ctx, "DocumentVersion", tables):
            value = property_value(version, "StatusSetDate", tables)
            if value is not None and not valid_xs_date(value):
                yield Violation("StatusSetDate is not a valid xs:date",
                                subject=subject, detail="%r" % value)
    return check


def _d9(tables):
    def check(ctx):
        """§2.2 requires the creation of an Entity element for DocumentedEntity;
        for RefersTo/BasedOn/TranslationOf this is the same check applied as a
        general dangling-reference integrity lint (their §2.8 wording is about
        document-to-document references, not Entity creation). Resolution is
        attempted only for ModelReferences whose first key names *this*
        submodel: a reference into another AAS is a promise this tool cannot
        check offline, and §2.2 says such references "can span multiple AAS",
        so silence there is honesty, not a miss."""
        for submodel in matched_submodels(ctx, tables):
            for label in ("DocumentedEntity", "RefersTo", "BasedOn", "TranslationOf"):
                for subject, element in instances_of(ctx, label, tables):
                    reference = getattr(element, "value", None)
                    keys = getattr(reference, "keys", None) or []
                    if not keys or reference.type.value != "ModelReference":
                        continue
                    if keys[0].type.value != "Submodel" or keys[0].value != submodel.id:
                        continue
                    if not resolve_in_submodel(submodel, keys):
                        yield Violation(
                            "the reference walks to nothing in this submodel",
                            subject=subject,
                            detail="no element at key path %s"
                                   % " / ".join(key.value for key in keys[1:]))
    return check


def _d10(tables):
    def check(ctx):
        for subject, version in instances_of(ctx, "DocumentVersion", tables):
            files = children_of(child_of(version, "DigitalFiles", tables) or version,
                                "DigitalFile", tables)
            if not files:
                continue                      # absence is the cardinality rule's finding
            content_types = {(getattr(f, "content_type", "") or "").lower() for f in files}
            if not content_types & PDF_CONTENT_TYPES:
                yield Violation(
                    "no DigitalFile is a PDF; VDI 2770 requires a PDF/A rendition",
                    subject=subject,
                    detail="content types present: %s"
                           % (", ".join(sorted(content_types)) or "none"))
    return check


def _l1(tables):
    def check(ctx):
        for subject, id_short, pattern in analyze(ctx, tables)["idshort_drift"]:
            yield Violation("idShort does not follow the template's suggestion",
                            subject=subject,
                            detail="%r does not match %s" % (id_short, pattern))
    return check


def _l2(tables):
    def check(ctx):
        for subject, seen, expected in analyze(ctx, tables)["near_misses"]:
            yield Violation("semanticId almost matches the template",
                            subject=subject,
                            detail="%s, where the template says %s" % (seen, expected))
    return check


def _l3(tables):
    def check(ctx):
        for subject, seen, expected in analyze(ctx, tables)["reftype_drift"]:
            yield Violation(
                "the reference type differs from the template's",
                subject=subject, detail="%s, where the template uses %s" % (seen, expected),
                fix="Use %s %s here, as the template does; the value matched, "
                    "so this is interoperability polish, not a failure."
                    % ("an" if expected[:1] in "AEIOU" else "a", expected))
    return check


def _l4(tables):
    def check(ctx):
        seen = {}
        for subject, document in instances_of(ctx, "Document", tables):
            for document_id in children_of(child_of(document, "DocumentIds", tables) or document,
                                           "DocumentId", tables):
                pair = (property_value(document_id, "DocumentDomainId", tables),
                        property_value(document_id, "DocumentIdentifier", tables))
                if None in pair:
                    continue
                if pair in seen and seen[pair] != subject:
                    yield Violation("two documents share one (domain, identifier) pair",
                                    subject=subject, detail="%s / %s" % pair)
                seen.setdefault(pair, subject)
    return check


def _l5(tables):
    def check(ctx):
        for subject, document in instances_of(ctx, "Document", tables):
            for classification in _vdi_classifications(document, tables):
                spelling = property_value(classification, "ClassificationSystem", tables)
                if spelling != VDI2770_SYSTEM:
                    yield Violation("ClassificationSystem spells the VDI system "
                                    "non-canonically",
                                    subject=subject, detail="%r" % spelling)
    return check


#: One entry per hand rule: the id suffix a pack's prefix is joined to, the
#: registration metadata, the labels the body navigates -- declared, not
#: discovered -- and the factory. `needs` is what `install` refuses on; it
#: is the roster's job to be complete, and tests/test_pack_roster.py reads
#: the module's own AST to say when it is not.
ROSTER = (
    ("-D2", "template", "MUST", "every Document carries a VDI 2770 classification",
     "IDTA 02004-2-0 §2.3",
     "Add a DocumentClassification whose ClassificationSystem property "
     "holds exactly '%s'; pick its ClassId from the twelve VDI 2770 "
     "classes (e.g. 03-02, Operation)." % VDI2770_SYSTEM,
     ("Document", "DocumentClassifications", "DocumentClassification",
      "ClassificationSystem"), _d2),
    ("-D3", "template", "MUST", "VDI 2770 ClassId comes from the twelve published classes",
     "IDTA 02004-2-0 §2.3, Table 1",
     "Replace the ClassId with one of the twelve VDI 2770 Blatt 1:2020 "
     "ids: 01-01, 02-01..02-04, 03-01..03-06 or 04-01.",
     ("Document", "DocumentClassifications", "DocumentClassification",
      "ClassificationSystem", "ClassId"), _d3),
    ("-D4", "template", "MUST", "the VDI 2770 ClassName speaks English",
     "IDTA 02004-2-0 §2.3 (\"EN is mandatory\")",
     "Add an 'en' entry to ClassName; Table 1 names each class in "
     "English (for 03-02 it is 'Operation').",
     ("Document", "DocumentClassifications", "DocumentClassification",
      "ClassificationSystem", "ClassName"), _d4),
    ("-D5", "template", "SHOULD", "one of several DocumentIds is marked primary",
     "IDTA 02004-2-0 §2.6 (DocumentIsPrimary)",
     "Set DocumentIsPrimary = true on exactly one DocumentId, so "
     "consumers know which identifier to file the document under.",
     ("Document", "DocumentIds", "DocumentId", "DocumentIsPrimary"), _d5),
    ("-D6", "template", "SHOULD", "StatusValue uses the two-word vocabulary",
     "IDTA 02004-2-0 §2.8",
     "Set StatusValue to 'InReview' or 'Released' (exact casing) -- "
     "the two values VDI 2770 names.",
     ("DocumentVersion", "StatusValue"), _d6),
    ("-D7", "template", "MUST", "files named by %s exist in the container",
     "IDTA 02004-2-0 §2.8; IDTA 01005 (AASX)",
     "Add the file to the .aasx (with a matching aas-suppl "
     "relationship) or correct the File value's path.",
     (), _d7),
    ("-D8", "template", "MUST", "StatusSetDate is a calendar date",
     "IDTA 02004-2-0 §2.8 (xs:date)",
     "Write StatusSetDate as YYYY-MM-DD (xs:date), e.g. 2020-02-06.",
     ("DocumentVersion", "StatusSetDate"), _d8),
    ("L1", "lint", "MAY", "idShorts follow the template's naming suggestion",
     "IDTA 02004-2-0 Annex A; template AllowedIdShort qualifiers",
     "Rename to the template's suggested pattern (base name plus an "
     "optional 2-3 digit suffix). Any unique idShort is legal; this "
     "is tidiness, not conformance.", (), _l1),
    ("L2", "lint", "SHOULD", "near-miss semantic identifiers are diagnosed, not ignored",
     "matching policy, docs/divergences.md",
     "Correct the semanticId to the template's spelling; a near-miss "
     "matches nothing, and every rule that would have applied to the "
     "element silently stops applying.", (), _l2),
    ("L3", "lint", "MAY", "reference types match the template's",
     "IDTA 02004-2-0 Annex A",
     "Use the reference type the template declares here; the value "
     "matched, so this is interoperability polish, not a failure.", (), _l3),
    ("L4", "lint", "SHOULD", "(DocumentDomainId, DocumentIdentifier) pairs are unique",
     "IDTA 02004-2-0 §2.6, Table 6 (DocumentDomainId: the domain \"in which the given DocumentId is unique\")",
     "Give each document a distinct identifier within its domain, or "
     "merge the entries if they describe one document.",
     ("Document", "DocumentIds", "DocumentId", "DocumentDomainId",
      "DocumentIdentifier"), _l4),
    ("-D9", "template", "SHOULD", "document/entity references resolve to an element that exists",
     "IDTA 02004-2-0 §2.2 (\"the creation of an Entity element is required\")",
     "Add the referenced Entity to the Entities list (or fix the "
     "reference's key path); a documented entity that does not exist "
     "leaves the document pointing at nothing.",
     ("DocumentedEntity", "RefersTo", "BasedOn", "TranslationOf"), _d9),
    ("L5", "lint", "SHOULD", "the VDI classification system uses §2.3's identifying value",
     "IDTA 02004-2-0 §2.3",
     "Write ClassificationSystem exactly as 'VDI 2770 Blatt 1:2020' -- "
     "the value §2.3 says identifies the mandatory system. "
     "'VDI2770:2020' is the template's example artefact and other tools "
     "matching on the specified string will not recognise it.",
     ("Document", "DocumentClassifications", "DocumentClassification",
      "ClassificationSystem"), _l5),
    ("-D10", "template", "SHOULD", "each DocumentVersion offers a PDF/A rendition",
     "IDTA 02004-2-0 §2.1 (\"PDF/A files are required\")",
     "Add a DigitalFile with contentType application/pdf (a PDF/A file, "
     "per VDI 2770) to this DocumentVersion. A content type cannot prove "
     "PDF/A conformance, so this is a warning, not an error.",
     ("DocumentVersion", "DigitalFiles", "DigitalFile"), _d10),
)


def answerable(tables) -> frozenset:
    """The suffixes this table has a row for every label of.

    D7 is not in `needs` because the labels it navigates are the table's
    own File rows; it is answerable when there is at least one.
    """
    out = {suffix for suffix, _k, _p, _t, _s, _f, needs, _m in ROSTER
           if all(label in tables.BY_LABEL for label in needs)}
    if not _file_labels(tables):
        out.discard("-D7")
    return frozenset(out)


def install(prefix: str, tables, omit=(), inherits: str = None) -> None:
    """Register every hand rule this table can answer, under `prefix`.

    Refused at import in both directions: a rule whose labels the table
    lacks, and a rule named in `omit` that the table could have answered.
    The second is the one this repository keeps learning it needs -- a
    pack that quietly checks less is the shape every gate here has failed
    at least once.
    """
    can = answerable(tables)
    unknown = sorted(set(omit) - {suffix for suffix, *_rest in ROSTER})
    if unknown:
        raise SystemExit(
            "%s omits %s, which is not a rule this module has; `omit` is where "
            "somebody says a loss was meant, and a name that means nothing "
            "says nothing" % (prefix, ", ".join(unknown)))
    for suffix in omit:
        if suffix in can:
            raise SystemExit(
                "%s omits %s, but %s has a row for every label it navigates"
                % (prefix, suffix, tables.__name__.rpartition(".")[2]))
    for suffix, kind, prio, title, spec, fix, needs, make in ROSTER:
        if suffix in omit:
            continue
        if suffix not in can:
            missing = sorted(set(needs) - set(tables.BY_LABEL)) or ["a File row"]
            raise SystemExit(
                "%s%s navigates %s, which %s has no row for; give the table a "
                "row or name %r in this pack's `omit`"
                % (prefix, suffix, ", ".join(missing),
                   tables.__name__.rpartition(".")[2], suffix))
        rule(prefix + suffix, kind=kind, prio=prio,
             title=title % "/".join(_file_labels(tables)) if "%s" in title else title,
             spec=spec if inherits is None
                  else "%s; %s inherits it (docs/divergences.md #26)" % (spec, inherits),
             fix=fix)(make(tables))
