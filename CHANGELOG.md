# Changelog

## 0.1.0 — unreleased

First release: 123 rules across three IDTA templates — *Handover
Documentation* 2.0.1, *Technical Data* 2.0.1 and *Digital Battery
Passport part 2* 1.0 — of which 86 are generated from the vendored
official template files. The `meta` channel
relays aas-core3.0's metamodel verification rather than restating it;
four input forms are read (.aasx with XML or JSON payload, environment
.json/.xml, bare Submodel .json); every finding carries a remedy
sentence; and the official example is pinned by name — defects and all.
IDTA 02035-2 shares 02004's submodel identifier, so `--profile` chooses
which of the two answers and SMT-D2 reports the choice; without the flag
02004 answers. `rulesChecked` in the JSON report counts every registered
rule, so it counts all 123 whichever template answered.
