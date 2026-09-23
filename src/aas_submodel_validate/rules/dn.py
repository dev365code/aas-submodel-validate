"""IDTA 02006 Digital Nameplate: the pack.

The structural layer is generated from the vendored template, one rule
per row -- the cardinalities and semanticIds the template file itself
declares.

Whether a Nameplate submodel is present at all is *not* here: that
question belongs to the tool rather than to this template, and it is
asked once for every template in `rules/detect.py`.
"""
from __future__ import annotations

import re

from ..model import Violation
from ..registry import rule
from . import dn_tables
from .engine import analyze, install_file_rule, instances_of, matched_submodels

#: The template's own identity -- one authority, the generated table.
TEMPLATE_SEMANTIC_ID = dn_tables.TEMPLATE_SEMANTIC_ID


# -- the generated structural layer ------------------------------------------
#
# One registered rule per template row, each reading its slice of the
# single cached walk. The table is generated from the vendored official
# template (tools/extract_smt_rules.py); the walk lives in engine.

def _row_check(row_id: str):
    def check(ctx):
        if not matched_submodels(ctx, dn_tables):
            return  # SMT-D1's finding; empty scopes would double-report it
        yield from analyze(ctx, dn_tables)["violations"].get(row_id, ())
    return check


for _row in dn_tables.ROWS:
    rule(_row["id"], kind="template", prio="MUST",
         title="'%s' as the template declares it (%s)"
               % (_row["label"], _row["sid"] or "by structure"),
         spec="%s, SMT/Cardinality qualifier" % dn_tables.TEMPLATE_CITATION,
         fix=_row["fix"],
         # A generated row always speaks about an element inside a
         # submodel of this document, so the route is the same for
         # every one of them. The grade is not: one row reports a
         # count, a kind, a list's item type, a valueType and a
         # present element with no value, and those are not equally
         # repairable, so each is graded where it is produced.
         path=("document", "submodel", "element"),
         )(_row_check(_row["id"]))


# -- the hand rule: what the template file cannot express --------------------
#
# RFC 3986 §3.1: scheme = ALPHA *( ALPHA / DIGIT / "+" / "-" / "." ). A
# value carrying one is absolute; one without is a relative reference
# (§4.2), which is not a global identification.
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


@rule("DN-D1", kind="template", prio="MUST",
     path=("document", "submodel", "element"),
     # The value is present and is not an absolute URI. What the
     # absolute form should be is a fact about the product this
     # nameplate describes, not about the string.
     fixability=4,
     fixability_why=("the identifier's absolute form is a fact about the product and is not derivable from the value written here"),
      title="URIOfTheProduct is an absolute URI",
      spec="IDTA 02006-3-0 (URIOfTheProduct: 'unique global identification "
           "... using a URI'); RFC 3986 §3.1 (scheme)",
      fix="Give URIOfTheProduct an absolute URI -- one with a scheme, e.g. "
          "https://example.com/model-1234/serial-5678. A relative reference "
          "or an empty value is not the unique global identification the "
          "template's definition asks for.")
def dn_d1_uri_of_the_product_is_absolute(ctx):
    """The generated row checks the declared valueType (xs:anyURI); this
    checks that the value is absolute. `xs:anyURI` admits a relative
    reference and an empty string, and the relayed metamodel channel
    passes both -- but the template's own definition is a "unique global
    identification", which a relative reference is not. A missing value is
    the generated row's finding (docs/divergences.md #40), not this one's,
    so an absent value is left to it.

    What is deliberately *not* checked here are the finer constraints
    IEC 61406-1 places on an identification link: it is a paid standard
    and this project has not bought its text, so this stops at the
    absolute-URI floor the template's public definition and RFC 3986
    establish (docs/divergences.md #47).
    """
    for subject, element in instances_of(ctx, "URIOfTheProduct", dn_tables):
        value = getattr(element, "value", None)
        if value is None:
            continue  # absence is the generated row's finding, not this one's
        if not _SCHEME.match(value.strip()):
            yield Violation("URIOfTheProduct is not an absolute URI",
                            subject=subject, detail="%r" % value)


# The one question in this file that is not a reading of this
# template: whether the files its File rows name are in the package.
# The body is shared and was called from 02004's family alone, so a
# package of this kind naming parts it does not hold was judged clean.
install_file_rule("DN-D2", dn_tables, dn_tables.TEMPLATE_CITATION)
