| Axis | Now | 1.0 condition |
|---|---|---|
| Coverage | 2002, 03, 04, 06, 07, 11, 23, 35-1, 35-2, 35-5 | met |
| Explanation | what is wrong, remedy, requirement | + evidence, the line in the file |
| Report contract | schemaVersion, golden report, exit codes, schema page | met |
| Entrances | command line, single file | + Python library, GitHub Action, browser |
| Input safety | read budgets, advisory | + own mutations, encodings |
| Upstream | pinned by commit | + checked for upstream change, one pin move shipped |

**Coverage** — 10 of 10:
- IDTA 02004 Handover Documentation — done (`docs/scope.md`: "Ten official templates are given rule tables: IDTA 02004 Handover Documentation")
- IDTA 02003 Technical Data — done (`docs/scope.md`: "Ten official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data")
- IDTA 02035-2 Digital Battery Passport, part 2 — done (`docs/scope.md`: "Ten official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2")
- IDTA 02006 Digital Nameplate — done (`docs/scope.md`: "Ten official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2, 02006 Digital Nameplate")
- IDTA 02023 Carbon Footprint — done (`docs/scope.md`: "Ten official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2, 02006 Digital Nameplate, 02023 Carbon Footprint")
- IDTA 02002 Contact Information — done (`docs/scope.md`: "Ten official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2, 02006 Digital Nameplate, 02023 Carbon Footprint, 02002 Contact Information")
- IDTA 02011 Hierarchical Structures — done (`docs/scope.md`: "Ten official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2, 02006 Digital Nameplate, 02023 Carbon Footprint, 02002 Contact Information, 02011 Hierarchical Structures")
- IDTA 02007 Software Nameplate — done (`docs/scope.md`: "Ten official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2, 02006 Digital Nameplate, 02023 Carbon Footprint, 02002 Contact Information, 02011 Hierarchical Structures, 02007 Software Nameplate")
- IDTA 02035-5 Digital Battery Passport, part 5 — done (`docs/scope.md`: "Ten official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2, 02006 Digital Nameplate, 02023 Carbon Footprint, 02002 Contact Information, 02011 Hierarchical Structures, 02007 Software Nameplate, 02035-5 Digital Battery Passport part 5")
- IDTA 02035-1 Digital Battery Passport, part 1 — done (`docs/scope.md`: "Ten official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2, 02006 Digital Nameplate, 02023 Carbon Footprint, 02002 Contact Information, 02011 Hierarchical Structures, 02007 Software Nameplate, 02035-5 Digital Battery Passport part 5, and 02035-1 Digital Battery Passport part 1")

**Explanation** — 3 of 5:
- what is wrong, in one sentence — done (`README.md`: "Every finding says what is wrong")
- the evidence as read from the file — not yet
- a remedy, for every rule — done (`README.md`: "A rule without a remedy sentence does not ship")
- where each rule's requirement lives — done (`docs/report-schema.md`: "Where the requirement lives, and always present")
- the line in the file — not yet

**Report contract** — 4 of 4:
- schemaVersion in every report — done (`README.md`: "document with a `schemaVersion`")
- a golden report held by a test — done (`README.md`: "is kept in `docs/golden-report.json`, and every build compares it with what the tool says now")
- exit codes 0, 1, 2 and 64 under test — done (`tests/test_what_a_pass_means.py`: "Each row there names an exit code and an `ok`")
- a field-by-field schema page — done (`README.md`: "described field by field in")

**Entrances** — 2 of 5:
- command line — done (`pyproject.toml`: "smtv = "aas_submodel_validate.cli:main"")
- Python library — not yet
- single file, nothing to install — done (`README.md`: "carry `smtv.pyz`, run `python3 smtv.pyz file.aasx`")
- GitHub Action — not yet
- browser, nothing installed — not yet

**Input safety** — 2 of 4:
- read budgets, per file and per run — done (`SECURITY.md`: "one document at 64 MiB, and a container's parts at 64 MiB each and 256 MiB together")
- a security fix ships with an advisory — done (`SECURITY.md`: "From 0.3.0 on, a security fix that ships in a release has a GitHub security advisory")
- tests verified against their own mutations — not yet
- declared encodings read without loss — not yet

**Upstream** — 1 of 3:
- upstream templates pinned by commit — done (`THIRD_PARTY.md`: "Taken from commit `11ef3353124626e2dba4cb50767024df9a39928a` and hash-verified")
- checked for upstream change — not yet
- one pin move shipped — not yet

Before it calls a release 1.0, this project asks of itself — Coverage: IDTA 02004 Handover Documentation · IDTA 02003 Technical Data · IDTA 02035-2 Digital Battery Passport, part 2 · IDTA 02006 Digital Nameplate · IDTA 02023 Carbon Footprint · IDTA 02002 Contact Information · IDTA 02011 Hierarchical Structures · IDTA 02007 Software Nameplate · IDTA 02035-5 Digital Battery Passport, part 5 · IDTA 02035-1 Digital Battery Passport, part 1; Explanation: what is wrong, in one sentence · the evidence as read from the file · a remedy, for every rule · where each rule's requirement lives · the line in the file; Report contract: schemaVersion in every report · a golden report held by a test · exit codes 0, 1, 2 and 64 under test · a field-by-field schema page; Entrances: command line · Python library · single file, nothing to install · GitHub Action · browser, nothing installed; Input safety: read budgets, per file and per run · a security fix ships with an advisory · tests verified against their own mutations · declared encodings read without loss; Upstream: upstream templates pinned by commit · checked for upstream change · one pin move shipped.
