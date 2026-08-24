# Divergences and chosen readings

Every place this project had to choose a reading of IDTA 02004 or of the
official material, with the evidence. Non-empty on day one: the official
template (2.0.1) and the official example disagree with each other in
the ways recorded below, so a validator has to decide whom to believe
before it can report anything.

| # | observation (all verified against the published files) | our reading |
|---|---|---|
| 1 | The official example's `Entities` list carries idShort `Entites` (sic). | idShort is not a matching key (Annex A: "A different idShort might be chosen"), so a typo there is not a finding. Matching is by semanticId throughout. |
| 2 | The example's Entities list uses semanticId `…/EntityForDocumentation` (the *child* element's singular IRI) where the template says `…/EntitiesForDocumentation`. | Reported as a template-conformance finding with a nearest-miss diagnosis, not silently matched. |
| 3 | The template's language list is idShort `Language`; the example says `Languages`. | Harmless under semanticId matching; recorded so nobody "fixes" matching to depend on names. |
| 4 | Only `OrganizationShortName`'s main semanticId is an ECLASS-CDP URL (`https://api.eclass-cdp.com/0173-1-02-ABI002-003`) where every sibling uses an IRDI — in the template *and* the PDF alike. | semanticId comparison normalises CDP URLs to IRDIs, both directions; an instance carrying either spelling matches. |
| 5 | The template's `AllowedIdShort` qualifier values are written like `RefersTo[\d{2,3}]` — as a regular expression this is a character class and matches "RefersTo" plus one character. | We implement the evident intent (`^RefersTo\d{2,3}$`) and only ever as an informational lint. |
| 6 | The official template 2.0.1 itself fails aas-core3.0 metamodel verification (duplicate-language displayNames on two conceptDescriptions). | The `meta` channel reports what the verifier finds, on official material as on anyone's. |
| 7 | The PDF names elements `RefersTo` / `BasedOn` / `TranslationOf`; the template's SML idShorts are `RefersToEntities` / `BasedOnReferences` / `TranslationOfEntities`. | Harmless under semanticId matching; recorded as evidence for divergence #1's policy. |
