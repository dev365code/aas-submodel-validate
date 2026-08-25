"""IDTA 02003 Technical Data: the generated structural layer.

One registered rule per template row, each reading its slice of a walk
that runs once for this table. The engine is the same one 02004 uses;
only the table differs, which is the whole point of generating tables
rather than writing rules.

Whether a Technical Data submodel is present at all belongs to
`rules/detect.py` — that question is the tool's, not this template's.

Below the generated layer are the things a template file cannot say: a
value declared `xs:date` spelled like one, a File naming a part the
container holds, a reference that walks to something. And two lints the
engine had already computed for this table with nobody reading them.
"""
from __future__ import annotations

from ..model import Violation
from ..registry import rule
from . import td_tables
from .engine import (
    analyze,
    instances_of,
    matched_submodels,
    property_value,
    resolve_in_submodel,
)
from .values import valid_xs_date


def _row_check(row_id: str):
    def check(ctx):
        if not matched_submodels(ctx, td_tables):
            return  # SMT-D1's finding; empty scopes would double-report it
        yield from analyze(ctx, td_tables)["violations"].get(row_id, ())
    return check


for _row in td_tables.ROWS:
    rule(_row["id"], kind="template", prio="MUST",
         title="'%s' as the template declares it (%s)"
               % (_row["label"], _row["sid"] or "by structure"),
         # The four unnamed list items carry no qualifier at all; the
         # PDF's element tables are what give them 0..*.
         spec="IDTA 02003-2-0-1 template, SMT/Cardinality qualifier "
              "(unnamed list items: 0..* per the PDF's element tables)",
         fix=_row["fix"])(_row_check(_row["id"]))


# -- the hand rules: what a template file cannot express ---------------------

def _instances(ctx, label):
    return instances_of(ctx, label, td_tables)


@rule("TD-D1", kind="template", prio="MUST",
      title="ValidDate is a calendar date",
      spec="IDTA 02003-2-0-1 §3.7 (FurtherInformation, xs:date)",
      fix="Write ValidDate as YYYY-MM-DD (xs:date), e.g. 2025-03-15.")
def td_d1_valid_date(ctx):
    """The generated rule checks the declared valueType; this one checks
    the characters, because `xs:date` over `15.03.2025` is the commoner
    mistake and the one a reader of the file cannot see."""
    for subject, further in _instances(ctx, "FurtherInformation"):
        value = property_value(further, "ValidDate", td_tables)
        if value is not None and not valid_xs_date(value):
            yield Violation("ValidDate is not a valid xs:date",
                            subject=subject, detail="saw %r" % value)


@rule("TD-D2", kind="template", prio="MUST",
      title="files named by CompanyLogo/ImageFile exist in the container",
      spec="IDTA 02003-2-0-1 §3.2, §3.3; IDTA 01005 (AASX)",
      fix="Add the file to the .aasx (with a matching aas-suppl "
          "relationship) or correct the File value's path.")
def td_d2_files_exist(ctx):
    """Only answerable when the input is a container; an environment JSON
    names files this rule cannot see, and silence there is honesty rather
    than laxity -- the finding would name a defect in packaging that is
    not present to be defective."""
    container = ctx.loaded.container
    if container is None:
        return
    from ..container import canonical_part_name
    for label in ("CompanyLogo", "ImageFile"):
        for subject, element in _instances(ctx, label):
            value = getattr(element, "value", None)
            if not isinstance(value, str) or not value.strip() or "://" in value:
                continue
            if canonical_part_name(value) is None:
                yield Violation("this File's value is not a part name",
                                subject=subject,
                                detail="%s climbs out of the package" % value)
            elif container.part(value) is None:
                yield Violation("the container holds no part at this File's value",
                                subject=subject, detail=value)


@rule("TD-D3", kind="template", prio="SHOULD",
      title="ReferenceToTechnicalPropertyArea resolves to an element that exists",
      spec="IDTA 02003-2-0-1 §3.4, Table 6",
      fix="Point the reference at a TechnicalPropertyArea this submodel "
          "holds, or add the area it names; the list's children are "
          "addressed by position, so the last key is an index.")
def td_d3_area_references_resolve(ctx):
    """Resolution is attempted only for a ModelReference whose first key
    names *this* submodel: a reference into another AAS is a promise this
    tool cannot check offline, and silence there is honesty, not a miss.
    """
    for submodel in matched_submodels(ctx, td_tables):
        for subject, element in _instances(ctx, "ReferenceToTechnicalPropertyArea"):
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


@rule("TDL1", kind="lint", prio="SHOULD",
      title="near-miss semantic identifiers are diagnosed, not ignored",
      spec="matching policy, docs/divergences.md",
      fix="Correct the semanticId to the template's spelling; a near-miss "
          "matches nothing, and every rule that would have applied to the "
          "element silently stops applying.")
def tdl1_near_miss(ctx):
    for subject, seen, expected in analyze(ctx, td_tables)["near_misses"]:
        yield Violation("semanticId almost matches the template",
                        subject=subject,
                        detail="saw %s, the template says %s" % (seen, expected))


@rule("TDL2", kind="lint", prio="MAY",
      title="reference types match the template's",
      spec="IDTA 02003-2-0-1 Annex A",
      fix="Use the reference type the template declares here; the value "
          "matched, so this is interoperability polish, not a failure.")
def tdl2_reference_type(ctx):
    for subject, seen, expected in analyze(ctx, td_tables)["reftype_drift"]:
        yield Violation(
            "the reference type differs from the template's",
            subject=subject, detail="saw %s, template uses %s" % (seen, expected),
            fix="Use %s %s here, as the template does; the value matched, "
                "so this is interoperability polish, not a failure."
                % ("an" if expected[:1] in "AEIOU" else "a", expected))
