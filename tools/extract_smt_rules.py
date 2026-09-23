#!/usr/bin/env python3
"""Generate the structural rule tables from the vendored official templates.

Every element in an IDTA submodel template carries its own machine-readable
constraints -- an SMT/Cardinality qualifier, a semanticId, a valueType,
sometimes an AllowedIdShort pattern -- so the structural rule layer is
extracted, not hand-written: hand-copying 189 rows is how one of them
silently goes stale. This sentence's number is pinned against the
generator's own list of packs, and the README's beside it
(`tests/test_readme_front.py`) -- pinned because it has been wrong
twice, saying sixty-four through a third table and 142 through a sixth,
which makes it, twice, an instance of the thing it warns about. `--check` regenerates and
byte-compares, the same contract the sibling validators use for their
generated files.

One generator, one row shape, one table per template (PACKS below).

What is deliberately interpreted rather than copied:

- **Match values.** A list item's identity is one key whose value joins
  the list IRDI and the item IRDI with "/" (e.g.
  `0173-1#02-ABI500#003/0173-1#01-AHF579#003`) -- a single key, the same
  in the template and the official example. A row matches on the union of
  that whole value, its supplemental spellings (ECLASS-CDP URLs
  normalised to IRDIs, `~N` cardinality suffixes admitted bare), and the
  "/"-join of any genuinely multi-key reference. The composite is kept
  whole -- not split into its components (docs/divergences.md #8).
- **AllowedIdShort.** The template writes `RefersTo[\\d{2,3}]`, which as
  a regular expression is a character class matching "RefersTo" plus one
  character. The evident intent `^RefersTo(?:\\d{2,3})?$` is what lands in
  the table -- the digits are the multiple-instance suffix and so optional
  (docs/divergences.md #5) -- and it is only ever an informational lint
  (Annex A lets any unique idShort stand).
- **Open content is not a rule.** 02003 §3.5 says "the set of suitable
  semanticIds is not restricted": its thirty-six placeholder elements
  describe what a manufacturer *may* add. Generating rules from them would
  demand the unconstrained, and all thirty-six carry the same identifier
  -- six of them siblings in one scope -- so the first row would claim
  every arbitrary element the walk met. `skip_sids`
  drops the subtree before it is numbered.
- **A missing cardinality is 0..\\*, not an error and not One.** 02004
  qualified every element; 02003 leaves four list items unqualified, and
  its PDF element tables give each of them 0..*. Assuming One there would
  invent an obligation the standard does not state.
- **Several example values, one remedy.** 02003 gives one element four
  ExampleValue qualifiers, one per classification system. Keeping the
  first would tell a reader ECLASS is the answer when the template offers
  four, so they are joined in template order.
- **A list child that carries an idShort.** AASd-120 forbids one on a
  direct child of a SubmodelElementList, which is the whole reason
  `item_names` exists. 02035-2 breaks it on four of its six list
  children, so those four rows are labelled with the name the artefact
  itself carries. Each pack names all of its list items anyway, using
  02004's word where the element is 02004's, so an upstream repair of
  that defect would rename nothing -- a row suddenly called
  "DocumentsItem" would announce a divergence where none had appeared.
"""
from __future__ import annotations

import argparse
import json
import pathlib as _pathlib
import sys
import sys as _sys
from pathlib import Path

# The package, from wherever this script is. `make` exports
# PYTHONPATH and the lint job installs the package first, but
# CI's wheel job installs nothing and an unpacked sdist has no
# install at all -- and `MANIFEST.in` grafts this directory for
# exactly that reader. Two scripts here already did this; the
# import added to all eight assumed the other six were as
# lucky.
_TOOLS_SRC = str(_pathlib.Path(__file__).resolve().parent.parent / "src")
if _TOOLS_SRC not in _sys.path:
    _sys.path.insert(0, _TOOLS_SRC)

from aas_submodel_validate._terminal import survive  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aas_submodel_validate import tablegen  # noqa: E402

#: Item labels for elements a template leaves unnamed (AASd-120 forbids a
#: list child an idShort; 02004 obeys it, 02035-2 does not -- see the
#: module docstring). These labels are chosen to be
#: readable in a finding; most match the PDF's element names, a few
#: (LanguageCode, EntityForDocumentation) are our own where the PDF uses a
#: different word. Without one, a row would be called "DocumentsItem".
HD_ITEM_NAMES = {
    "Documents": "Document",
    "DocumentIds": "DocumentId",
    "DocumentClassifications": "DocumentClassification",
    "DocumentVersions": "DocumentVersion",
    "Language": "LanguageCode",
    "RefersToEntities": "RefersTo",
    "BasedOnReferences": "BasedOn",
    "TranslationOfEntities": "TranslationOf",
    "DigitalFiles": "DigitalFile",
    "DocumentedEntities": "DocumentedEntity",
    "Entities": "EntityForDocumentation",
}

#: 02003's four unnamed list items. Three of these are the PDF's own word
#: for the item (Tables 3, 7 and 11); ProductClassification is ours -- the
#: PDF writes that one in the plural in both the list row and the item's
#: own table, and a row called "ProductClassifications" twice over would
#: be unreadable in a finding.
TD_ITEM_NAMES = {
    "ProductImages": "ProductImage",
    "ProductClassifications": "ProductClassification",
    "TechnicalPropertyAreas": "TechnicalPropertyArea",
    "SpecificDescriptions": "SpecificDescription",
}

#: 02035-2's six list items, in 02004's words -- it is a profile of that
#: template and every one of its elements is one of 02004's. Only two are
#: read today: the published file gives the other four an idShort, which
#: AASd-120 forbids and which therefore wins. They are named anyway so
#: that repairing that defect upstream renames nothing here.
DBP_ITEM_NAMES = {
    "Documents": "Document",
    "DocumentClassifications": "DocumentClassification",
    "DocumentIds": "DocumentId",
    "DocumentVersions": "DocumentVersion",
    "Language": "LanguageCode",
    "DigitalFiles": "DigitalFile",
}

#: 02006's two list items (Markings, GuidelineSpecificProperties).
DN_ITEM_NAMES = {
    "Markings": "Marking",
    "GuidelineSpecificProperties": "GuidelineSpecificProperty",
}

#: The open-content placeholders, read from the package so that the
#: generator and a table built at run time skip the same things. They
#: were three per-pack lists here, holding between them exactly the four
#: markers the package now names, while the run-time builder was handed
#: an empty one -- so one template read two ways stated two different
#: sets of obligations. See `tablegen.OPEN_CONTENT_MARKERS`.
ARBITRARY = tablegen.OPEN_CONTENT_MARKERS

#: Kept as names because the pack table below reads them, and because
#: what each template *uses* is worth saying even when what they skip is
#: one list: 02006 marks a manufacturer's additions under
#: AssetSpecificProperties and GuidelineSpecificProperties with the three
#: typed markers, and 02023 marks one `ArbitraryContent` property inside
#: PcfInformation with the untyped one.
#:
#: 02023's ProductOrSectorSpecificCarbonFootprints repeats the named
#: PcfCalculationMethods sub-structure that ProductCarbonFootprints
#: already carries (same semanticId, different scope). The generator
#: qualifies a label repeated across scopes by the shortest ancestor
#: suffix that distinguishes the copies (`_qualify_repeats`), so both
#: sections are judged; the placeholder is what is left out
#: (docs/divergences.md #19).
PCF_SKIP = ARBITRARY

PCF_ITEM_NAMES = {
    "ProductCarbonFootprints": "ProductCarbonFootprint",
    "PcfCalculationMethods": "PcfCalculationMethod",
    "LifeCyclePhases": "LifeCyclePhase",
    "ProductOrSectorSpecificCarbonFootprints": "ProductOrSectorSpecificCarbonFootprint",
}

DN_ARBITRARY = ARBITRARY

#: One entry per vendored template. `source` names the file in the header
#: of the generated module, so a reader lands on the right upstream
#: artefact; `prefix` is the rule-id namespace the registry keeps unique.
#: `citation` is how a finding's `per` line names this template to a
#: reader who has to argue with it -- the document, without the file
#: extension, spelled the way the standard is cited rather than the way
#: the file is named. It was written out by hand in each rule module
#: until a finding needed to cite the same template for something other
#: than the cardinality qualifier, and two copies of a citation are two
#: chances to cite different documents for one reading.
PACKS = (
    {
        "template": ROOT / "src/aas_submodel_validate/data/smt/02004/2.0.1/template.json",
        "output": ROOT / "src/aas_submodel_validate/rules/hd_tables.py",
        "prefix": "HD-E",
        "source": "IDTA 02004-2-0-1 template.json",
        "citation": "IDTA 02004-2-0-1 template",
        "item_names": HD_ITEM_NAMES,
        "example_types": ("ExampleValue",),
        "skip_sids": ARBITRARY,
    },
    {
        "template": ROOT / "src/aas_submodel_validate/data/smt/02003/2.0.1/template.json",
        "output": ROOT / "src/aas_submodel_validate/rules/td_tables.py",
        "prefix": "TD-E",
        "source": "IDTA 02003_2-0-1 template.json",
        "citation": "IDTA 02003-2-0-1 template",
        "item_names": TD_ITEM_NAMES,
        "example_types": ("SMT/ExampleValue/ECLASS", "SMT/ExampleValue/CDD",
                          "SMT/ExampleValue/UNSPSC", "SMT/ExampleValue/CustomerSpecific"),
        "skip_sids": ARBITRARY,
    },
    # The Digital Battery Passport's part 2 is a second Handover
    # Documentation template and declares 02004's submodel semanticId
    # exactly, so its rows need their own id namespace and their own
    # table: one row cannot carry two remedy sentences. Its qualifier
    # vocabulary is 02004's -- bare `ExampleValue`, `SMT/Cardinality` on
    # every element, no open content -- so none of the readings 02003
    # forced apply here.
    {
        "template": ROOT / "src/aas_submodel_validate/data/smt/02035-2/1.0/template.json",
        "output": ROOT / "src/aas_submodel_validate/rules/dbp_tables.py",
        "prefix": "DBP2-E",
        "source": "IDTA 02035-2_DBP-Part-2_HandoverDocumentation.json",
        "citation": "IDTA 02035-2 1.0 template",
        "item_names": DBP_ITEM_NAMES,
        "example_types": ("ExampleValue",),
        "skip_sids": ARBITRARY,
    },
    {
        "template": ROOT / "src/aas_submodel_validate/data/smt/02006/3.0/template.json",
        "output": ROOT / "src/aas_submodel_validate/rules/dn_tables.py",
        "prefix": "DN-E",
        "source": "IDTA 02006-3-0_Template_Digital Nameplate.json",
        "citation": "IDTA 02006-3-0 template",
        "item_names": DN_ITEM_NAMES,
        "example_types": (),
        "skip_sids": DN_ARBITRARY,
    },
    {
        "template": ROOT / "src/aas_submodel_validate/data/smt/02023/1.0/template.json",
        "output": ROOT / "src/aas_submodel_validate/rules/pcf_tables.py",
        "prefix": "PCF-E",
        "source": "IDTA 02023 _Template_CarbonFootprint.json",
        "citation": "IDTA 02023 1.0 template",
        "item_names": PCF_ITEM_NAMES,
        "example_types": (),
        "skip_sids": PCF_SKIP,
    },
    # IDTA 02002 Contact Information 1.0.1 -- the edition this project
    # reads; 1.0 gives `IPCommunication` the submodel's own identifier,
    # which 1.0.1 repairs (docs/divergences.md). Every one of its
    # thirty-six elements states its cardinality with the older
    # `Multiplicity` qualifier and none with `SMT/Cardinality` (#50). It
    # holds no SubmodelElementList and no open content: repetition rides on
    # a collection's own cardinality instead, so there are no item names to
    # supply and nothing to skip.
    {
        "template": ROOT / "src/aas_submodel_validate/data/smt/02002/1.0.1/template.json",
        "output": ROOT / "src/aas_submodel_validate/rules/contact_tables.py",
        "prefix": "CI-E",
        "source": "IDTA 02002-1-0-1_Template_ContactInformation.json",
        "citation": "IDTA 02002-1-0-1 template",
        "item_names": {},
        "example_types": (),
        "skip_sids": ARBITRARY,
    },
    # IDTA 02011 Hierarchical Structures enabling Bills of Material 1.1.1:
    # eleven elements -- three Entities, six RelationshipElements, two
    # Properties -- each with `SMT/Cardinality`. `Node` holds a `Node` of
    # its own identifier, which the template writes out one level and the
    # generator marks rather than expands again (#48). No list, so no item
    # names; no open content.
    {
        "template": ROOT / "src/aas_submodel_validate/data/smt/02011/1.1.1/template.json",
        "output": ROOT / "src/aas_submodel_validate/rules/hs_tables.py",
        "prefix": "HS-E",
        "source": "IDTA 02011-1-1-1_Template_HSEBoM.json",
        "citation": "IDTA 02011-1-1-1 template",
        "item_names": {},
        "example_types": (),
        "skip_sids": ARBITRARY,
    },
)


















            # A row with no ancestor (top level) has no suffix to qualify
            # by, so it keeps its bare label rather than becoming `Label ()`.
            # Two such rows sharing a label stay identical and the backstop
            # reports them.

def generate(pack) -> str:
    """Render one pack's table module.

    Reading the template is `aas_submodel_validate.tablegen`'s now, so
    that an installed copy and the single-file build can do it too; what
    is here is the writing, which is the build's.
    """
    document = json.loads(pack["template"].read_text("utf-8-sig"))
    try:
        built = tablegen.build(document, pack)
    except tablegen.TemplateRefused as refused:
        # A build tool leaves by 1 with a sentence. The core raises
        # instead of exiting, because a caller handed a template by
        # somebody else owes the code that means "could not judge this
        # input" and that is not this caller.
        #
        # The whole class, not `DuplicateLabel` alone. `DuplicateLabel`
        # is a subclass, so naming it caught one refusal and let its
        # siblings out as a traceback -- twelve frames, no pack named,
        # for a re-vendored template above the row bound or carrying a
        # qualifier this reader cannot build. Measured on both.
        raise SystemExit("%s: %s" % (pack["output"].name, refused)) from None
    # A vendored template whose own qualifier this reader cannot read is
    # this project's problem and not a user's, so the build tool stops
    # rather than emitting a table with the value quietly dropped. A
    # caller's template gets the opposite treatment -- a note and the
    # rest of the verdict -- because there nobody here can fix the file.
    unreadable = [(row["label"], row["allowed_idshort_unreadable"])
                  for row in tablegen._flatten(built["tree"], [])
                  if "allowed_idshort_unreadable" in row]
    if unreadable:
        raise SystemExit(
            "%s: AllowedIdShort cannot be read on %s; IDTA's spelling is "
            "`Name[\\d{2,3}]`, lower bound first"
            % (pack["output"].name,
               # The value as the template spells it. `%r` doubles the
               # backslash, and whoever reads this is about to look for
               # the string in a vendored file.
               ", ".join("%s (`%s`)" % pair for pair in unreadable)))
    tree = built["tree"]
    submodel_sid = built["submodel_sid"]
    submodel_sid_type = built["submodel_sid_type"]
    supplemental = built["supplemental"]

    lines = [
        '"""GENERATED by tools/extract_smt_rules.py from the vendored official',
        "template -- edit the generator, regenerate, never this file.",
        "",
        "Source: %s (CC BY 4.0, (c) IDTA and" % pack["source"],
        'contributors; pin and hashes in THIRD_PARTY.md)."""',
        "",
        "TEMPLATE_CITATION = %r" % pack["citation"],
        "TEMPLATE_SEMANTIC_ID = %r" % submodel_sid,
        "TEMPLATE_SUBMODEL_SID_TYPE = %r" % submodel_sid_type,
        "TEMPLATE_SUPPLEMENTAL_SEMANTIC_IDS = %r" % (tuple(sorted(supplemental)),),
        "",
        "TREE = %s" % _fmt(tree, 0),
        "",
        "",
        "def _flatten(rows, out):",
        "    for row in rows:",
        "        out.append(row)",
        "        _flatten(row[\"children\"], out)",
        "    return out",
        "",
        "",
        "ROWS = tuple(_flatten(TREE, []))",
        "BY_ID = {row[\"id\"]: row for row in ROWS}",
        "BY_LABEL = {row[\"label\"]: row for row in ROWS}",
        "",
    ]
    return "\n".join(lines)


def _fmt(value, depth):
    pad = "    " * depth
    if isinstance(value, tuple) and value and isinstance(value[0], dict):
        inner = ",\n".join(pad + "    " + _fmt(v, depth + 1) for v in value)
        return "(\n%s,\n%s)" % (inner, pad)
    if isinstance(value, dict):
        inner = ",\n".join('%s    %r: %s' % ("    " * depth, k, _fmt(v, depth + 1))
                           for k, v in value.items())
        return "{\n%s,\n%s}" % (inner, "    " * depth)
    return repr(value)


def main() -> int:
    survive()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    bad = 0
    for pack in PACKS:
        output = pack["output"]
        text = generate(pack)
        if args.check:
            if not output.exists() or output.read_text("utf-8") != text:
                print("rules/%s is stale: run tools/extract_smt_rules.py"
                      % output.name, file=sys.stderr)
                bad = 1
                continue
            print("%s matches its generator (%d rows)"
                  % (output.name, text.count("'id':")))
        else:
            output.write_text(text, "utf-8")
            print("wrote %s" % output)
    return bad


if __name__ == "__main__":
    sys.exit(main())
