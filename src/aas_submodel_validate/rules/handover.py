"""The Handover Documentation hand rules, written once for every table
that can answer them.

IDTA 02004 and IDTA 02035-2 publish the same submodel semanticId over the
same vocabulary of elements (docs/divergences.md #26), so what a template
file cannot say is the same sentence for both: the VDI 2770
classification is mandatory, its ClassId comes from twelve published
classes, a File names a part the container holds. (Not every row: the
date, status and reference rules are among the three 02035-2 drops.)
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

import aas_core3.verification as verification
from aas_core3.types import MultiLanguageProperty

from ..model import Violation
from ..registry import rule
from .engine import (
    analyze,
    child_of,
    children_of,
    dangling_violation,
    file_part_violations,
    idshort_remedy,
    instances_of,
    matched_submodels,
    near_miss_violations,
    property_value,
    reftype_violations,
    resolve_in_submodel,
)
from .values import valid_xs_date

#: The exact spelling IDTA 02004-2-0 §2.3 says identifies the mandatory
#: classification system.
VDI2770_SYSTEM = "VDI 2770 Blatt 1:2020"
#: The template's own ExampleValue -- and therefore the official example --
#: spells it "VDI2770:2020", contradicting §2.3's identifying value. Both
#: are recognised as the mandatory system; the non-canonical spelling
#: draws the L5 lint. docs/divergences.md #9. IDTA 02035-2's template
#: carries the same ExampleValue, which is one of the three ways its own
#: bytes say it keeps the VDI 2770 classification (divergences #29).
VDI2770_SPELLINGS = frozenset((VDI2770_SYSTEM, "VDI2770:2020"))
#: The twelve document classes of that edition, read from IDTA 02004-2-0
#: §2.3, Table 1 -- freely published, and the document this validates
#: against -- and cross-checked against the DDC reference implementation.
#: VDI 2770 Blatt 1:2020-04 itself is sold by DIN Media and was not
#: opened; the comment here used to name it as the source, which claimed
#: a primary reading for a secondary one. docs/divergences.md #33, which
#: also records why a thirteenth class in a later edition is not how this
#: fails a conformant file: `_vdi_classifications` reads only what the
#: file has already declared to be *this* edition.
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
            if (property_value(c, "ClassificationSystem", tables) or "").strip()
            in VDI2770_SPELLINGS]


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
        that ClassificationSystem value -- which this project reads as
        either of the two spellings the official material uses, not only
        the one this sentence quotes (docs/divergences.md #9)."""
        for subject, document in instances_of(ctx, "Document", tables):
            if not _vdi_classifications(document, tables):
                yield Violation("no DocumentClassification declares the mandatory "
                                "VDI 2770 classification system", subject=subject)
    return check


def _d3(tables):
    def check(ctx):
        for subject, document in instances_of(ctx, "Document", tables):
            for classification in _vdi_classifications(document, tables):
                # Folded like the system name beside it. Both are
                # `xs:string` in the same collection and both feed a
                # MUST; folding one and not the other made the same
                # whitespace forgivable in one property and an error in
                # the next.
                class_id = property_value(classification, "ClassId", tables)
                class_id = class_id.strip() if isinstance(class_id, str) else class_id
                if class_id is not None and class_id not in VDI2770_CLASS_IDS:
                    yield Violation("ClassId is not a VDI 2770 Blatt 1:2020 class",
                                    subject=subject, detail="%r" % class_id)
    return check


#: "Is this tag English?" is a question the metamodel already answers, so
#: this asks it rather than deciding it: `is_bcp_47_for_english` is
#: aas-core3's own predicate, `^(en|EN)(-.*)?$`, the one it applies where
#: the metamodel requires something in English (AASc-3a-002).
#:
#: Borrowed rather than copied. A copy is a fork that looks like
#: agreement, and this project has already reversed itself once here on
#: the strength of a wider reading it had not checked against this
#: function (docs/divergences.md #35). If aas-core3's answer moves, this
#: moves with it, and the tag fixture in the suite says what the answer
#: is today -- including its costs: the pattern is case-exact on the
#: primary subtag, so `eN` and `En`, legal case-insensitive BCP 47, draw
#: the MUST. The remedy names the two spellings it takes.
#:
#: Note this is *narrower* than `matches_bcp_47`, which is
#: well-formedness only and admits `eng`, `enm` and `english` alike --
#: a language tag being well-formed says nothing about which language it
#: names.
def _english(tag: str) -> bool:
    """aas-core3's predicate, asked of the tag in its folded form.

    Its pattern is `^(en|EN)(-.*)?$`, which takes all-lower and
    all-upper and refuses `En` and `eN`. RFC 5646 §2.1.1 says the
    opposite in as many words: subtags "are to be treated as case
    insensitive ... there exist conventions for the capitalization of
    some of the subtags, but these MUST NOT be taken to carry meaning."
    A file writing `En` was told it had no English entry, on a line
    that printed `languages present: En, de` directly above it -- a
    finding on a conformant file, which is the one direction with no
    second opinion.

    Still borrowed, not copied. The question is the same function's;
    what changed is that it is handed the spelling the standard says
    means the same thing. `eng` stays refused: it is well-formed, it
    means English, and IANA marks `en` as its preferred value -- that
    is a different argument and it is in docs/divergences.md #35.
    """
    return verification.is_bcp_47_for_english((tag or "").lower())


def _d4(tables):
    def check(ctx):
        for subject, document in instances_of(ctx, "Document", tables):
            for classification in _vdi_classifications(document, tables):
                name = child_of(classification, "ClassName", tables)
                if name is None:
                    continue  # absence is the generated cardinality rule's finding
                # A MultiLanguageProperty's value is a list of tagged
                # strings; a file that declares this element a `Property`
                # gives a bare one. Iterating it walked its characters
                # and raised, which the isolation turned into "the rule
                # itself could not run -- a defect in the validator, not
                # in your file". It is a defect in the file, and the
                # generated rule beside this one already names the
                # element and the kind it should be, so this one has
                # nothing to add and says nothing. An *absent* value is
                # a different thing -- the metamodel allows it and the
                # row accepts it -- and still has to be reported as no
                # English entry, so only the wrong kind is passed over.
                # By kind, not by what the value happens to look like.
                # A `Property` gives a bare string here and a `Range` or
                # a `Capability` has no `value` at all -- the first was
                # guarded against and the second still raised, and both
                # were reported as "the rule itself could not run: a
                # defect in the validator, not in your file". The defect
                # is in the file, and the generated rule beside this one
                # says which element and which kind. An element of the
                # wrong kind is that rule's to report, so this one stays
                # silent; an *empty* one is this rule's, because the
                # metamodel allows it and the row accepts it.
                if not isinstance(name, MultiLanguageProperty):
                    continue
                languages = {entry.language for entry in (name.value or [])}
                english = any(_english(lang) for lang in languages)
                if not english:
                    yield Violation("ClassName has no English entry",
                                    subject=subject,
                                    detail="languages present: %s"
                                           % (", ".join(sorted(languages)) or "none"))
    return check


#: Case-folded and trimmed before reading, so `TRUE` and a padded value
#: are taken as the author meant them. What makes that safe is not a
#: backstop -- docs/divergences.md #34, which records the argument that
#: was tried and does not hold.
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
            # Folded like the three beside it. The spelling is exact on
            # purpose -- the official example writes `released` and
            # draws this five times, which is a recorded choice -- and
            # the whitespace is not part of that choice.
            status = property_value(version, "StatusValue", tables)
            status = status.strip() if isinstance(status, str) else status
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
                yield from file_part_violations(container, subject,
                                                getattr(element, "value", None))
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



def dangling_remedy(label: str) -> str:
    """Per label, because the rule reads four and only one of them is
    about Entities. The standing sentence told the author of a dangling
    `BasedOn` -- a document-to-document reference -- to add an Entity to
    a list that has nothing to do with it.
    """
    return ("Add the element this %s names to the submodel, or correct "
            "the reference's key path; a reference that resolves to "
            "nothing points the document at nothing." % label)


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
            # Literal, not a module constant: `test_pack_roster` reads
            # these out of the AST to check them against the roster's own
            # `needs` tuple, and a name puts them where it cannot look.
            # The roster is the copy anything else reads.
            for label in ("DocumentedEntity", "RefersTo", "BasedOn", "TranslationOf"):
                for subject, element in instances_of(ctx, label, tables):
                    reference = getattr(element, "value", None)
                    keys = getattr(reference, "keys", None) or []
                    if not keys or reference.type.value != "ModelReference":
                        continue
                    if keys[0].type.value != "Submodel" or keys[0].value != submodel.id:
                        continue
                    if not resolve_in_submodel(submodel, keys):
                        yield dangling_violation(subject, keys, label)
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
        for subject, id_short, pattern, in_list in analyze(ctx, tables)["idshort_drift"]:
            yield Violation("idShort does not follow the template's suggestion",
                            subject=subject,
                            detail="%r does not match %s" % (id_short, pattern),
                            fix=idshort_remedy(in_list, pattern))
    return check


def _l2(tables):
    def check(ctx):
        yield from near_miss_violations(ctx, tables)
    return check


def _l3(tables):
    def check(ctx):
        yield from reftype_violations(ctx, tables)
    return check


def _folded(value):
    """A vocabulary value with its whitespace taken off.

    Four rules read a value this way and three learned to fold; the
    fourth compares two documents' identifier pairs, which are plain
    `xs:string` and get no second opinion from the metamodel channel,
    so a space at the end of one of them made two identical pairs look
    different. Rows 31 and 34 of the divergences fold for that reason.
    """
    return value.strip() if isinstance(value, str) else value


def _l4(tables):
    def check(ctx):
        seen = {}
        for subject, document in instances_of(ctx, "Document", tables):
            for document_id in children_of(child_of(document, "DocumentIds", tables) or document,
                                           "DocumentId", tables):
                pair = (_folded(property_value(document_id, "DocumentDomainId", tables)),
                        _folded(property_value(document_id, "DocumentIdentifier", tables)))
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
                # The same reading D2 does. D2 learned to fold the
                # whitespace and this did not, so a value that is the
                # canonical spelling with a space around it stopped
                # being a missing classification and became a
                # non-canonical one -- with a remedy naming a spelling
                # the file does not carry.
                spelling = (property_value(classification,
                                           "ClassificationSystem", tables) or "").strip()
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
     "names VDI 2770 -- '%s' is the spelling to prefer, and the "
     "template's own '%s' is accepted too (docs/divergences.md #9). "
     "Pick its ClassId from the twelve VDI 2770 classes "
     "(e.g. 03-02, Operation)." % (VDI2770_SYSTEM, "VDI2770:2020"),
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
     "Add an entry to ClassName tagged 'en' or 'EN' (a region subtag "
     "is fine); Table 1 names each class in English (for 03-02 it is "
     "'Operation').",
     ("Document", "DocumentClassifications", "DocumentClassification",
      "ClassificationSystem", "ClassName"), _d4),
    ("-D5", "template", "SHOULD", "one of several DocumentIds is marked primary",
     "IDTA 02004-2-0 §2.6 (DocumentIsPrimary)",
     "Mark one of these DocumentIds with DocumentIsPrimary = true, so "
     "consumers know which identifier to file the document under. This "
     "rule asks only that one is marked. The template states no "
     "cardinality on how many may carry the flag -- its own definition "
     "calls it 'the preferred ID', singular -- so several primaries are "
     "not reported here.",
     ("Document", "DocumentIds", "DocumentId", "DocumentIsPrimary"), _d5),
    ("-D6", "template", "SHOULD", "StatusValue uses the two-word vocabulary",
     "IDTA 02004-2-0 §2.8",
     "Set StatusValue to 'InReview' or 'Released' (exact casing). The "
     "vendored concept description is where those two come from, and it "
     "says they 'should be used' -- which is why this is a warning.",
     ("DocumentVersion", "StatusValue"), _d6),
    ("-D7", "template", "MUST", "files named by %s exist in the container",
     "IDTA 02004-2-0 §2.8; IDTA 01005 (AASX)",
     "Add the file to the .aasx under the name this File value gives, or "
     "correct the value's path. (Declaring an aas-suppl relationship for "
     "it is X4's question, not this one's.)",
     (), _d7),
    ("-D8", "template", "MUST", "StatusSetDate is a calendar date",
     "IDTA 02004-2-0 §2.8 (xs:date)",
     "Write StatusSetDate as YYYY-MM-DD (xs:date), e.g. 2020-02-06.",
     ("DocumentVersion", "StatusSetDate"), _d8),
    ("L1", "lint", "MAY", "idShorts follow the template's naming suggestion",
     "IDTA 02004-2-0 Annex A; template AllowedIdShort qualifiers",
     # Unreachable: `_l1` gives every violation its own remedy, and one
     # of the two says the opposite of this -- inside a SubmodelElementList
     # an idShort is not tidiness, it is AASd-120. Kept and pinned; see
     # `-D9`.
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
     # Unreachable: `_l3` gives every violation its own remedy, naming the
     # type, and `Finding.fix` prefers the violation's. This exists because
     # registration refuses a rule that names no remedy at all, and it says
     # the same thing so the two cannot drift into disagreeing.
     "Use the reference type the template declares here; the value "
     "matched, so this is interoperability polish, not a failure.", (), _l3),
    ("L4", "lint", "SHOULD", "(DocumentDomainId, DocumentIdentifier) pairs are unique",
     "IDTA 02004-2-0 §2.6, Table 6 (DocumentDomainId: the domain \"in which the given DocumentId is unique\")",
     "Give each document a distinct identifier within its domain, or "
     "merge the entries if they describe one document.",
     ("Document", "DocumentIds", "DocumentId", "DocumentDomainId",
      "DocumentIdentifier"), _l4),
    ("-D9", "template", "SHOULD", "document/entity references resolve to an element that exists",
     "IDTA 02004-2-0 §2.2 (DocumentedEntity: \"the creation of an Entity "
     "element is required\"); §2.8 for the DocumentVersion reference lists, "
     "where the same integrity question is asked of document-to-document "
     "references",
     # Unreachable: `_d9` gives every violation its own remedy, naming the
     # label that dangled, and `Finding.fix` prefers that one. Kept and
     # pinned rather than deleted -- standing advice that has stopped
     # shipping is worth being able to see. Same state as `-L3`.
     "Add the element the reference names to the submodel, or correct its "
     "key path; a reference that resolves to nothing points the document "
     "at nothing.",
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
