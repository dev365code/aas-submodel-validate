| Axis | Now | 1.0 condition |
|---|---|---|
| Coverage | 2002, 03, 04, 06, 07, 11, 23, 35-1, -2, -4, -5, -7 | met |
| Explanation | what is wrong, evidence, remedy, requirement, line | met |
| Report contract | schemaVersion, golden report, exit codes, schema page | met |
| Entrances | command line, library, single file, Action, browser | met |
| Input safety | read budgets, advisory, own mutations | + encodings |
| Upstream | pinned by commit, one pin move shipped | + checked for upstream change |

**Coverage** — 12 of 12:
- IDTA 02004 Handover Documentation — done (`docs/scope.md`: "Twelve official templates are given rule tables: IDTA 02004 Handover Documentation")
- IDTA 02003 Technical Data — done (`docs/scope.md`: "Twelve official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data")
- IDTA 02035-2 Digital Battery Passport, part 2 — done (`docs/scope.md`: "Twelve official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2")
- IDTA 02006 Digital Nameplate — done (`docs/scope.md`: "Twelve official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2, 02006 Digital Nameplate")
- IDTA 02023 Carbon Footprint — done (`docs/scope.md`: "Twelve official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2, 02006 Digital Nameplate, 02023 Carbon Footprint")
- IDTA 02002 Contact Information — done (`docs/scope.md`: "Twelve official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2, 02006 Digital Nameplate, 02023 Carbon Footprint, 02002 Contact Information")
- IDTA 02011 Hierarchical Structures — done (`docs/scope.md`: "Twelve official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2, 02006 Digital Nameplate, 02023 Carbon Footprint, 02002 Contact Information, 02011 Hierarchical Structures")
- IDTA 02007 Software Nameplate — done (`docs/scope.md`: "Twelve official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2, 02006 Digital Nameplate, 02023 Carbon Footprint, 02002 Contact Information, 02011 Hierarchical Structures, 02007 Software Nameplate")
- IDTA 02035-5 Digital Battery Passport, part 5 — done (`docs/scope.md`: "Twelve official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2, 02006 Digital Nameplate, 02023 Carbon Footprint, 02002 Contact Information, 02011 Hierarchical Structures, 02007 Software Nameplate, 02035-5 Digital Battery Passport part 5")
- IDTA 02035-1 Digital Battery Passport, part 1 — done (`docs/scope.md`: "Twelve official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2, 02006 Digital Nameplate, 02023 Carbon Footprint, 02002 Contact Information, 02011 Hierarchical Structures, 02007 Software Nameplate, 02035-5 Digital Battery Passport part 5, 02035-1 Digital Battery Passport part 1")
- IDTA 02035-4 Digital Battery Passport, part 4 — done (`docs/scope.md`: "Twelve official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2, 02006 Digital Nameplate, 02023 Carbon Footprint, 02002 Contact Information, 02011 Hierarchical Structures, 02007 Software Nameplate, 02035-5 Digital Battery Passport part 5, 02035-1 Digital Battery Passport part 1, 02035-4 Digital Battery Passport part 4")
- IDTA 02035-7 Digital Battery Passport, part 7 — done (`docs/scope.md`: "Twelve official templates are given rule tables: IDTA 02004 Handover Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport part 2, 02006 Digital Nameplate, 02023 Carbon Footprint, 02002 Contact Information, 02011 Hierarchical Structures, 02007 Software Nameplate, 02035-5 Digital Battery Passport part 5, 02035-1 Digital Battery Passport part 1, 02035-4 Digital Battery Passport part 4, and 02035-7 Digital Battery Passport part 7")

**Explanation** — 5 of 5:
- what is wrong, in one sentence — done (`README.md`: "Every finding says what is wrong")
- the evidence as read from the file — done (`README.md`: "and shows what it read")
- a remedy, for every rule — done (`README.md`: "A rule without a remedy sentence does not ship")
- where each rule's requirement lives — done (`docs/report-schema.md`: "Where the requirement lives, and always present")
- the line in the file — done (`docs/report-schema.md`: "The line in the file the subject begins on")

**Report contract** — 4 of 4:
- schemaVersion in every report — done (`README.md`: "document with a `schemaVersion`")
- a golden report held by a test — done (`README.md`: "is kept in `docs/golden-report.json`, and every build compares it with what the tool says now")
- exit codes 0, 1, 2 and 64 under test — done (`tests/test_what_a_pass_means.py`: "Each row there names an exit code and an `ok`")
- a field-by-field schema page — done (`README.md`: "described field by field in")

**Entrances** — 5 of 5:
- command line — done (`pyproject.toml`: "smtv = "aas_submodel_validate.cli:main"")
- Python library — done (`README.md`: "from aas_submodel_validate import exit_code, validate")
- single file, nothing to install — done (`README.md`: "carry `smtv.pyz`, run `python3 smtv.pyz file.aasx`")
- GitHub Action — done (`action.yml`: "installs the released validator from PyPI")
- browser, nothing installed — done (`browser/page.html`: "once this page has loaded it makes no network request")

**Input safety** — 3 of 4:
- read budgets, per file and per run — done (`SECURITY.md`: "one document at 64 MiB, and a container's parts at 64 MiB each and 256 MiB together")
- a security fix ships with an advisory — done (`SECURITY.md`: "From 0.3.0 on, a security fix that ships in a release has a GitHub security advisory")
- tests verified against their own mutations — done (`.github/workflows/ci.yml`: "every mutation in the table dies")
- declared encodings read without loss — not yet

**Upstream** — 2 of 3:
- upstream templates pinned by commit — done (`THIRD_PARTY.md`: "Taken from commit `f3790038b6c9c2d7e5ebbb4609997468fadf3e85` (commit date 2026-10-05T14:26:16Z) and hash-verified")
- checked for upstream change — not yet
- one pin move shipped — done (`CHANGELOG.md`: "The template pin moves to upstream main commit")

Before it calls a release 1.0, this project asks of itself — Coverage: IDTA 02004 Handover Documentation · IDTA 02003 Technical Data · IDTA 02035-2 Digital Battery Passport, part 2 · IDTA 02006 Digital Nameplate · IDTA 02023 Carbon Footprint · IDTA 02002 Contact Information · IDTA 02011 Hierarchical Structures · IDTA 02007 Software Nameplate · IDTA 02035-5 Digital Battery Passport, part 5 · IDTA 02035-1 Digital Battery Passport, part 1 · IDTA 02035-4 Digital Battery Passport, part 4 · IDTA 02035-7 Digital Battery Passport, part 7; Explanation: what is wrong, in one sentence · the evidence as read from the file · a remedy, for every rule · where each rule's requirement lives · the line in the file; Report contract: schemaVersion in every report · a golden report held by a test · exit codes 0, 1, 2 and 64 under test · a field-by-field schema page; Entrances: command line · Python library · single file, nothing to install · GitHub Action · browser, nothing installed; Input safety: read budgets, per file and per run · a security fix ships with an advisory · tests verified against their own mutations · declared encodings read without loss; Upstream: upstream templates pinned by commit · checked for upstream change · one pin move shipped.
