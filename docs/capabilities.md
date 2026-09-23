| Axis | Now | 1.0 condition |
|---|---|---|
| Coverage | 02004, 02003, 02035-2, 02006, 02023, 02002 | + 02011, 02007 |
| Explanation | what is wrong, remedy, specification | + evidence, the line in the file |
| Report contract | schemaVersion, exit codes, schema page | + a golden report |
| Entrances | command line, single file | + Python library, GitHub Action, browser |
| Input safety | read budgets, advisory, own mutations, encodings | met |
| Upstream | pinned by commit | + checked for upstream change, one pin move shipped |

**Coverage** — 6 of 8:
- IDTA 02004 Handover Documentation — done (`docs/scope.md`: "IDTA 02004 Handover Documentation")
- IDTA 02003 Technical Data — done (`docs/scope.md`: "02003 Technical Data")
- IDTA 02035-2 Digital Battery Passport, part 2 — done (`docs/scope.md`: "02035-2 Digital Battery Passport part 2")
- IDTA 02006 Digital Nameplate — done (`docs/scope.md`: "02006 Digital Nameplate")
- IDTA 02023 Carbon Footprint — done (`docs/scope.md`: "02023 Carbon Footprint")
- IDTA 02002 Contact Information — done (`docs/scope.md`: "02002 Contact Information")
- IDTA 02011 Hierarchical Structures — not yet
- IDTA 02007 Software Nameplate — not yet

**Explanation** — 3 of 5:
- what is wrong, in one sentence — done (`README.md`: "Every finding says what is wrong")
- the evidence as read from the file — not yet
- a remedy, for every rule — done (`README.md`: "A rule without a remedy sentence does not ship")
- the specification each rule enforces — done (`docs/report-schema.md`: "Where the requirement lives, and always present")
- the line in the file — not yet

**Report contract** — 3 of 4:
- schemaVersion in every report — done (`README.md`: "document with a `schemaVersion`")
- a golden report held by a test — not yet
- exit codes 0, 1, 2 and 64 under test — done (`docs/scope.md`: "exits **64** and writes no report")
- a field-by-field schema page — done (`README.md`: "described field by field in")

**Entrances** — 2 of 5:
- command line — done (`pyproject.toml`: "smtv = "aas_submodel_validate.cli:main"")
- Python library — not yet
- single file, nothing to install — done (`README.md`: "carry `smtv.pyz`, run `python3 smtv.pyz file.aasx`")
- GitHub Action — not yet
- browser, nothing installed — not yet

**Input safety** — 4 of 4:
- read budgets, per file and per run — done (`SECURITY.md`: "one document at 64 MiB")
- a security fix ships with an advisory — done (`SECURITY.md`: "A security fix that shipped in a release has a GitHub security advisory")
- tests verified against their own mutations — done (`Makefile`: "mutation that makes the mistake and checks a test fails")
- declared encodings read without loss — done (`tests/test_xml_encoding.py`: "written in any encoding it declares")

**Upstream** — 1 of 3:
- upstream templates pinned by commit — done (`THIRD_PARTY.md`: "Taken from commit `11ef3353124626e2dba4cb50767024df9a39928a` and hash-verified")
- checked for upstream change — not yet
- one pin move shipped — not yet

Before it calls a release 1.0, this project asks of itself — Coverage: IDTA 02004 Handover Documentation · IDTA 02003 Technical Data · IDTA 02035-2 Digital Battery Passport, part 2 · IDTA 02006 Digital Nameplate · IDTA 02023 Carbon Footprint · IDTA 02002 Contact Information · IDTA 02011 Hierarchical Structures · IDTA 02007 Software Nameplate; Explanation: what is wrong, in one sentence · the evidence as read from the file · a remedy, for every rule · the specification each rule enforces · the line in the file; Report contract: schemaVersion in every report · a golden report held by a test · exit codes 0, 1, 2 and 64 under test · a field-by-field schema page; Entrances: command line · Python library · single file, nothing to install · GitHub Action · browser, nothing installed; Input safety: read budgets, per file and per run · a security fix ships with an advisory · tests verified against their own mutations · declared encodings read without loss; Upstream: upstream templates pinned by commit · checked for upstream change · one pin move shipped.
