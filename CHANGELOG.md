# Changelog

## 0.1.0 — unreleased

First release: 125 rules, 123 of them across three IDTA templates — *Handover
Documentation* 2.0.1, *Technical Data* 2.0.1 and *Digital Battery
Passport part 2* 1.0 — of which 86 are generated from the vendored
official template files. The `meta` channel
relays aas-core3.0's metamodel verification rather than restating it;
four input forms are read (.aasx with XML or JSON payload, environment
.json/.xml, bare Submodel .json); XML arrives in whichever encoding the
parser reads — UTF-8 or UTF-16, marked or not — and is decoded that way
before the DTD refusal looks at it, so the refusal covers what the
parser covers; every finding carries a remedy
sentence; and the official example is pinned by name — defects and all.
What this reader takes in is bounded whichever way a document arrives —
one document at 64 MiB, a container's parts at 64 MiB each and 256 MiB
together, and a container's directory of names at 16 MiB, which is a
different kind of cost: a ZIP is indexed whole before any of it is read,
so it falls on how many names an archive declares rather than on what its
entries hold — and what it refuses to read, it does not judge: `summary.complete`
in the JSON report and a clause on the terminal summary say when the
counts describe less than the whole input. `summary.judged` says the
sharper thing beside it — whether anything reached the rules at all — and
an input that was refused rather than judged leaves by the could-not-run
exit code, 2, where it used to leave by the code for a verdict. Both
fields are additive, so `schemaVersion` stays 1.
IDTA 02035-2 shares 02004's submodel identifier, so `--profile` chooses
which of the two answers and SMT-D2 reports the choice; without the flag
02004 answers. `rulesChecked` in the JSON report counts every registered
rule, so it counts all 125 whichever template answered.
Two rules read the battery passport against Regulation (EU) 2023/1542
rather than against a template, from a table generated out of the
requirements indexes published in `data/battery-passport/`: `BAT-R2`
names a submodel identifier two published templates claim and this tool
has a table for neither of, and `BAT-R8` reports an element the template
permits to be absent that a legal reading requires of every battery
category. Eight further disagreements are known and not reported,
because whether the law requires them depends on a category no rule here
reads; the report counts them rather than keeping quiet about them. Both
rules are warnings — two published readings of applicability exist and
this pack cannot yet be told which to answer for.

The JSON report's shape is written down in `docs/report-schema.md`, and
carries two more fields: `toolVersion`, because the shape's number and
the producer's are different numbers and a defect report needs the
second; and `options`, because the flags move the verdict — the same file
comes back `ok` under one set and not another — and two reports that did
not say which run they were could not be compared.
