# Where the battery passport sources differ

Four documents describe the same obligation: the regulation, the Commission's
guidance table, the consortium longlist, and the IDTA submodel templates. Read
against each other they do not line up everywhere. This is the list of places
where they differ.

**These are observations, not verdicts.** Each entry says what was read, in which
exact bytes, and what a conformance check would have to decide because of it.
Where two documents can both be read as correct, the entry says so. Nothing here
claims that any publisher made a mistake.

Every file was read at the hash recorded in `sources.sha256`. The submodel
templates were read at one commit of the public template repository,
`a9664731a903b29ac5f45e23ab3a25c581f3d92f`, so "the template says" means those
bytes. Counts come from the index files beside this one; none are typed by hand.

---

## 1. Two battery passport parts share a submodel identifier with the template they extend

**Read:** The submodel `semanticId` of Digital Battery Passport Part 2 is
`0173-1#01-AHF578#003`, the same identifier carried by the Handover Documentation
template V2.0. Part 3 carries
`https://admin-shell.io/idta/CarbonFootprint/CarbonFootprint/1/0`, the same
identifier as the Carbon Footprint template V1.0.

**Where:** `idta/02035-2_v1.0/…HandoverDocumentation.json` `c7124116` against
`idta/_base_02004_v2.0/…json` `1be559fb`; `idta/02035-3_v1.0/…ProductCarbonFootprint.json`
`1555443c` against `idta/_base_02023_v1.0/…json` `a6f19f6e`.

**What a checker has to decide:** A submodel is identified by its `semanticId`;
an `idShort` is a label the specification does not constrain. So a checker given
a submodel with one of these identifiers cannot determine from the identifier
alone which specification to apply, and choosing by label would make the answer
depend on something free to vary. Reusing the identifier is a coherent choice —
each part is a profile of the base template — and the cost of it falls on the
checker rather than on the author.

## 2. Two parts declare a template identifier belonging to the template they derive from

**Read:** Part 3's `administration.templateId` is
`https://admin-shell.io/idta-02023-1-0`; Part 4's is `IDTA-02003-2-0`. Parts 1,
2, 5, 6 and 7 each name their own number. Part 4's value is also the only one
that is not a URI.

**Where:** `requirements-idta.json`, `counts.templates`, field `template_id`.

**What a checker has to decide:** `templateId` is where a file states which
specification it implements. In these two files that statement points at the base
template rather than at the document the file was published as, so a checker
cannot use the field on its own to select a rule set. Both a deliberate claim of
conformance to the base and an unchanged inherited value would produce what is
observed; the file does not distinguish them.

## 3. Within one file, the submodel and its elements carry different namespace versions

**Read:** Part 6 V1.0.1 — submodel `semanticId` ends
`material_composition:1.0.0#MaterialComposition`, every element ends `:1.0.1#…`.
Part 5 V1.0.1 — submodel `:1.0.0#`, elements `:1.0.1#`. Part 5 V1.0.2 — submodel
`:1.0.2#`, elements `:1.0.2#`. In all three, `administration.version` and
`revision` read `1.0`.

**Where:** `requirements-idta.json`, `counts.templates`, fields
`semantic_id_version` and `element_semantic_id_versions`.

**What a checker has to decide:** Three places state a version and they do not
all agree, so "which version is this file" has more than one answer. A checker
keyed on the submodel identifier and a checker keyed on element identifiers will
reach different conclusions about the same file, and each will be following what
the file says.

## 4. A version in which nothing machine-readable changed

**Read:** For Digital Product Passport Part 1, the template JSON published as
V1.0 and the one published as V1.0.1 are the same bytes, `541cfd52`. So is the
AASX package: at the pinned commit both directories reference the same object.
What differs between the two directories is the PDF, the documentation source,
the README and the documentation configuration.

**Where:** both files in `sources.sha256`; package identity from the repository
tree at the pinned commit.

**What a checker has to decide:** Nothing, for the file itself. It matters for
anyone tracking the template by version: fetching V1.0.1 in expectation of a
machine-readable change yields none. Publishing a documentation correction under
a patch version is ordinary practice; the difference is between what the version
number changes and what a consumer of the JSON might expect it to mean.

## 5. One part is packaged differently from the other six

**Read:** Each Digital Battery Passport part ships the template twice, once with
example values and once without, together with a README. Part 5 V1.0.2 ships
neither the file without example values nor a README.

**Package sizes, checked:** All three Part 5 packages were opened far enough to
list their members without extracting them. V1.0 holds seven members including a
124,110-byte cover image; V1.0.1 and V1.0.2 hold five and no image. The document
inside grew across the three: 160,908, then 163,838, then 166,758 bytes of AAS
XML. The smaller packages are smaller because a cover picture is absent, not
because content is missing.

**Where:** `requirements-idta.json` note for Part 5 V1.0.2; packages `6d637644`,
`3300dc71`, `151e1210` in `sources.sha256`.

**What a checker has to decide:** The file without example values is what a
document's shape can be compared against without example data in the way. Where
it is absent, the element tree has a single reading and nothing to check it
against.

## 6. One citation in the guidance does not resolve in the consolidated text

**Read:** The Commission guidance gives the source of data point 44 -- clear,
understandable and readable instructions for use -- as `BR Annex XIII 1 (t)`. In
the consolidated text read here, Annex XIII point 1 runs from (a) to (s).

**Where:** `requirements-join.json`, `citations_unresolved_in_consolidated_text`
and `citations_without_a_matching_annex_point`; the annex index
`requirements-annex-xiii.json` ends block 1 at `annex-xiii:1.s`. Consolidated
text `a90c0055`, guidance `e045a766`.

**Scope of the statement:** This is a statement about one text at one version,
CELEX 02023R1542-20250731. A later amendment adding a point (t) would not make it
wrong, and it says nothing about whether the guidance is mistaken -- only that
the two do not resolve against each other as read.

**What a checker has to decide:** Which text it is checking against, and to say
so. A checker built from this consolidated text alone has no rule for data point
44; one built from a later text might. It is the only citation in either
restatement that does not resolve, and it carries a substantive obligation.

## 7. The guidance and the longlist read ten provisions differently

**Read:** For ten provisions, the two restatements differ, and in one direction.
The guidance marks data points as not to be filled or displayed as of February
2027 — variously because a format awaits an implementing act, because
application is on hold, or because another article moves the date to August 2027
— while the longlist marks rows citing the same provision as required.
Provisions affected include Annex XIII 1(b), 1(c), 1(e), 1(g) and Annex VI A (1).

**Where:** `requirements-join.json`, `readings_that_differ_by_citation`; each
document's own wording is preserved per record in
`requirements-ec-datapoints.json` under `applicability` and in
`requirements-longlist.json`.

**What a checker has to decide:** Which question it is answering. The longlist
answers what the regulation requires; the guidance answers what has to be filled
in as of February 2027. Both are right about their own question, and a checker
cannot infer which one its user means. It has to be told.

## 8. Nine template elements are optional where the restatements call the data required

**Read:** Nine elements carry the cardinality `ZeroToOne` while an attribute of
the same name is marked required by the guidance, the longlist, or both. They
include capacity fade, capacity threshold for exhaustion, remaining capacity,
remaining power capability, remaining round trip energy efficiency, energy and
capacity throughput, round trip efficiency fade, and date of putting into
service.

**Where:** `requirements-join.json`, `readings_that_differ_by_name`;
cardinalities in `requirements-idta.json`.

**What a checker has to decide:** That template conformance and regulatory
conformance are two different answers, and to report which one it is giving. A
template may be permissive on purpose so that one file serves several battery
categories; if so, the condition that would make an element required is not
expressed in the template.

**How this was matched:** on name alone — the templates carry no citation — so
each pair should be read before being relied on.

## 9. Most of the template surface cannot be reached from the other three sources

**Read:** Of 221 indexed template elements, 42 match an attribute name in the
guidance or the longlist and 179 match nothing. In the other direction, 63 of 71
guidance data points and 63 of 100 longlist rows match no element.

**Where:** `requirements-join.json`, counts.

**What this actually says:** Mostly it is a statement about the join rather than
about the documents. Matching a nested `idShort` against a prose attribute name
is weak, and nothing joins the templates to the law by citation at all, because
the templates carry no citation. Read plainly the numbers would say the templates
and the restatements are largely disjoint, which cannot be true of documents
describing the same passport.

**Consequence, stated wherever coverage appears:** every coverage figure produced
here is **a floor, not a measurement**, and stays one until a citation-bearing
bridge exists.
