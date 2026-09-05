# Sources, attribution and licences

The indexes in this directory are **derived works**. Each one records
identifiers, section references, short quotations and the cardinality or
applicability its source states, reorganised into a machine-readable
shape and abridged. **None of them is the original, and none should be
read in place of it.** Where a reading matters, follow the address in
`sources.sha256` to the source and read it there.

Three of the four sources are published under Creative Commons
Attribution 4.0 International, whose §3(a) asks a reuser to retain the
creator, the copyright notice, the licence notice and its URI, and any
disclaimer notice, and to indicate that the material was modified. The
directory named the licences and stopped there. What follows is what
each source actually asks for, read out of the exact bytes
`sources.sha256` pins.

---

## Regulation (EU) 2023/1542, Annex XIII — `requirements-annex-xiii.json`

Consolidated text CELEX `02023R1542-20250731`, from EUR-Lex.
© European Union, 1998–2026. Reuse of EUR-Lex editorial content is
authorised under Creative Commons Attribution 4.0 International
(<https://creativecommons.org/licenses/by/4.0/>), provided the source is
acknowledged and changes are indicated.

**The consolidated text carries its own disclaimer, and it belongs with
any index built from it:**

> This text is meant purely as a documentation tool and has no legal
> effect. The Union's institutions do not assume any liability for its
> contents. The authentic versions of the relevant acts, including their
> preambles, are those published in the Official Journal of the European
> Union.

`requirements-annex-xiii.json` therefore states what a documentation
tool says, not what the law authentically says. Its `mandatory` values
are readings of that text and are not legal advice.

**Modified:** the annex was split into 34 numbered points, each carrying
a short verbatim quotation, a section reference, and fields for
cardinality, applicability and consolidation marker that the source does
not have.

---

## European Commission guidance, *Digital Batteries Passport — data points by category* — `requirements-ec-datapoints.json`

Version 2.0, 2nd Edition, manuscript completed August 2026.
**© European Union, 2026.** The Commission's reuse policy is implemented
under Commission Decision 2011/833/EU of 12 December 2011
(OJ L 330, 14.12.2011, p. 39,
ELI: <http://data.europa.eu/eli/dec/2011/833/oj>). Reuse is authorised
under Creative Commons Attribution 4.0 International
(<https://creativecommons.org/licenses/by/4.0/>) — "reuse is allowed,
provided appropriate credit is given and any changes are indicated."

**The document's own disclaimer, which the index does not repeat and a
reader of the index needs:**

> This document has been prepared for the European Commission however it
> reflects the views only of the authors, and the European Commission is
> not liable for any consequence stemming from the reuse of this
> publication.

It also states that it cannot prejudge any future actions the Commission
may take, including positions before the Court of Justice of the
European Union. It is guidance, not law: where `requirements-ec-datapoints.json`
records `mandatory: "no"`, that is the guidance's own instruction about
its table — often "not to be filled or displayed" because the same data
is already required elsewhere — and **is not a statement that the
regulation does not require the thing.**

**Modified:** the guidance table was transcribed into one record per data
point, with the applicability columns split per battery category.

---

## BatteryPass-Ready Data Attribute Longlist v1.3 — `requirements-longlist.json`

**Copyright © 2026 BatteryPass-Ready Consortium.** Made available under a
CC BY Licence (Attribution),
<https://creativecommons.org/licenses/by/4.0>.

**The Consortium supplies a recommended citation, and asks that it be
used:**

> BatteryPass-Ready Consortium (2026). Battery Passport Data Attribute
> Longlist v1.3.

The Consortium states that the document is provided for informational
purposes only, that it was prepared collaboratively and may include
information contributed by external sources and stakeholders, and that
while reasonable efforts were made it does not guarantee the accuracy or
completeness of the information.

Note the edition. Earlier Battery Pass material — the 2023 Content
Guidance and longlist v1.2 — is under a different, **non-commercial**
licence. This index is built from **v1.3 only**, which is CC BY. The
short name "Battery Pass longlist" belongs to the earlier series and is
avoided here for that reason.

**Modified:** the data sheet was transcribed into one record per
attribute. One column is deliberately not carried: the wording of
requirements and recommendations attributed to DIN DKE SPEC 99100 (see
below).

---

## IDTA submodel templates 02035-1…-7 and 02099-1 — `requirements-idta.json`

Published by the Industrial Digital Twin Association under Creative
Commons Attribution 4.0 International
(<https://creativecommons.org/licenses/by/4.0/>). The templates were read
from the `admin-shell-io/submodel-templates` repository at commit
`a9664731a903b29ac5f45e23ab3a25c581f3d92f`; the exact files and their
digests are in `sources.sha256`. IDTA's own licence file names no
copyright holder, so none is asserted here beyond IDTA as publisher.

**Modified:** the element trees were flattened into one record per
element, keeping `semanticId`, `idShort`, cardinality, model type and
value type, and the template's own description text.

### Identifiers and definitions that are not IDTA's

The templates identify elements with vocabularies published by others,
and those identifiers — and in places the definition text attached to
them — travel into `requirements-idta.json`:

- **ECLASS** IRDIs of the form `0173-1#…`, on 53 records, some carrying
  ECLASS definition text (a few in German). IDTA's Part-4 specification
  states that the ECLASS IRDIs referenced in the submodel are based on
  ECLASS Release 15 and that use of the submodels is free of charge.
  ECLASS publishes its own terms of use at <https://www.eclass.eu>; a
  reuser relying on this index for ECLASS content should read them
  rather than rely on this file.
- **IEC Common Data Dictionary** identifiers of the form
  `0112/2///61987#…` and `0112/2///61360_7#…`, on 12 records.
- **Eclipse ESMF / SAMM aspect-model** URNs of the form
  `urn:samm:io.admin-shell.idta.*`, on 140 records. These are the
  identifiers the templates themselves declare; they are recorded
  because a conformance check matches on `semanticId` and dropping them
  would make the index unusable for the purpose it exists for.

## DIN DKE SPEC 99100

The longlist categorises its attributes "in line with the battery
passport content clusters as described in the DIN DKE Spec 99100" (its
own Instructions sheet), and carries a column of clause numbers into
that document. **`requirements-longlist.json` records those clause
numbers** — 91 distinct values on 94 of its 100 records — in the field
`separate_spec_chapter`. The field name does not say which document the
chapters belong to, which is a defect: a pointer that does not name what
it points into is not a citation, and it also made the pointers
invisible to a search for the document's name.

**What is not carried:** the wording of the requirements and
recommendations attributed to that specification. That column of the
longlist is withheld from the public index deliberately, and the
extractor in `tools/` does not read it.

No DIN document was opened to build any index here; `sources.sha256`
lists every file that was, and none is DIN's. The clause numbers reach
this directory through the longlist and through IDTA's own template
descriptions, both CC BY 4.0.

---

## The indexes themselves

`requirements-*.json`, `requirements-join.md`, `divergences-public.md`
and the tools in `tools/` are part of this repository and are under its
licence, Apache-2.0 (see `LICENSE` at the repository root). That covers
the selection, the structure and the tooling — not the quoted material
from the sources above, which stays under the licence each source
carries.
