# Changelog

## 0.1.1 — unreleased

Still 125 rules, 86 generated from the vendored template files as
before: no rule checks anything it did not check in 0.1.0, and no
verdict changes. Most of this is about *reaching* a verdict — what
someone who installed 0.1.0 from the package index, took it from the
release page, or read the front page could not do. The exceptions are
at the end: the line every run finishes with is spelled differently, so
that a terminal which cannot encode it stops killing the run; three
findings say something different from what they said, and each of them
was saying something untrue; and every finding now prints the clause it
answers for, which the JSON has carried since 0.1.0 and the screen
never showed.

**The first verdict needs nothing of your own.** IDTA's published example
travels in the package now, and `smtv --example` judges it — no file of
your own, no clone, no network. Installing from the index used to leave a
reader with a validator and nothing to validate: the front page's next
line named a path only a clone has. The example is unmodified, defects
and all; it raises findings, which is the point of shipping that one
rather than a clean file written to pass.

**`--meta error|warning|info` sets the relayed channel's severity**, and
`-W` can be used in a build without it deciding one. At `info` the
metamodel findings are still reported and still counted and `-W` no
longer fails on them — which is the caller saying so, rather than the
tool deciding it for them. `--strict-meta` is the older spelling of
`--meta error` and keeps working.

**`--require-all-judged`.** An environment holds submodels this tool has
no business judging, so `judged 1 of 3` stays a number and the run still
exits 0. A pipeline reading only the exit code saw success for a package
two thirds of which was never looked at; this makes that fail instead.

**The relayed channel is folded into one line** unless `--show-meta`.
On the official example that is 360 lines of output down to 53 — count
them with `smtv --example` and `smtv --example --show-meta` — with the
verdict no longer scrolled past. Counted, never dropped: the summary
totals them and the JSON report carries every one of
them, folded or not.

**The single file says what it needs.** `smtv.pyz` now names the Python
version it requires instead of failing with a syntax error on an old
one — the metadata that carries `Requires-Python` is not in the archive,
and a reader who has already carried the file into a plant cannot go and
look it up. Its releases are signed, so `gh attestation verify` says
which workflow built the bytes; a checksum file beside the artifacts it
vouches for cannot answer that. And a dependency's own build scripts
stopped travelling in it — dead code, and the only `subprocess` import
in the archive. `gh attestation verify` answers for releases from this
one on; the 0.1.0 artifacts were built before the workflow signed
anything and have no attestation to find.

**`--rules` refuses what it would have ignored.** It lists the rules and
judges nothing, so every flag about judging is a question it does not
answer: `-q`, `-f json`, `-W`, `--allow-unmatched`,
`--require-all-judged`, `--show-meta`, `--profile` and a path all exit 2
now, naming what would have been dropped. Six of those — `-q`,
`-f json`, `-W`, `--allow-unmatched`, `--profile` and a path — were
accepted and silently ignored in 0.1.0, so a command that worked may now
fail. The two flags not in that list are new in this release. `--meta` (and its older
spelling `--strict-meta`) is what `--rules` reads, because that changes
the listing.

**Documented:** `--allow-unmatched` and `--require-all-judged`, both of
which decide an exit code and were reachable only from `--help`; that the
JSON field for a channel is `kind`, so a reader filtering on `.channel`
no longer gets an empty result with nothing to explain it; and that the
installer may be `pip3`, that `smtv` may need a `PATH` entry pip prints
and nobody reads.

**The battery finding cites the clause its own row cites.** `per` was a
constant, `Annex VII`, on a rule whose reported row cites `Annex IV
Part A (4)`,
about a passport obligation that lives in Annex XIII: three provisions,
and the one printed was the one nothing chose. A row is the only thing
that knows where it came from, so a violation now carries its own
`spec` the way it already carried its own `fix`. The JSON field is the
same shape and a different value. The same finding no longer says the
provision "requires" the element — its authority is a published
industry reading, which is why the rule is a warning and why
`docs/divergences.md` #37 has been careful about it since the rule
landed. `at` named a path the walk never takes and now names the
element. And the coverage note said `1 of the 1`, a number divided by
itself wearing the look of complete coverage; the eight it withholds
belong in the denominator that frames them.

**A File value is checked against a scheme, not a substring.** The test
for "this names something outside the container" was `"://" in value`,
which is neither where a scheme is nor what one is made of (RFC 3986
§3.1). Five shapes of value are judged differently from 0.1.0, and only one
of them is judged more strictly.

Stricter: `files/a://absent.pdf` contains `://`, is a good part name
once normalised, and used to walk past the rule. It is asked about
again.

Looser, and worth reading if a pipeline of yours is green on this
today: a value whose colon really does open a scheme is somebody
else's file and is left alone. `urn:iso:std:iso:1234`,
`mailto:docs@example.com` and `data:application/pdf;base64,…` drew
`HD-D7` and `TD-D2` in 0.1.0 and draw nothing now. So does a part name
carrying whitespace at either end -- `" aasx/files/manual.pdf "` -- and
a File value that is only whitespace, which names nothing and is a
different defect. A Windows path like `C:\docs\manual.pdf` is asked
about exactly as it was: a single letter before a colon is a drive
letter, not a scheme.

Both rules move together. They were the same rule written twice, word
for word, and they share a body now.

**Two keys are added to the JSON report and none is removed.**
`summary.submodelsSpecified` counts the submodels set aside as
specifications, and `options.meta` records the level `--meta` was given
at. Both are additive, so `schemaVersion` stays 1 and a reader written
for 0.1.0 finds every field it looked for, unchanged --
`options.strictMeta` included, which is now derived from the level so
the two cannot disagree. Measured against 0.1.0 across twenty-four
inputs: nothing removed, nothing renamed, and no field carrying a
different kind of value. `finding.spec` is narrowed from "string or
null" to always present, which is the compatible direction.

**A submodel that says it is a template is no longer judged as an
instance.** `ModellingKind.Template` means a specification, and every
rule here is a requirement on an instance — so pointed at the published
IDTA templates, the ones this project generates its own rules from, the
tool used to report that they have no VDI 2770 classification and tell
the reader to add one. No flag escaped it, and a package holding a
conformant instance beside the template it was built from came back as
a failure. Templates are set aside, the report says which ones and why,
and they are out of the coverage figure rather than counted as
unjudged.

**An archive this reader cannot open leaves by 2, whatever stopped it.**
A ZIP entry name written in a legacy code page with the header bit that
claims UTF-8 set anyway — what a packager on a Korean or Japanese
Windows produces — raised past every handler and left by 1, which is the
code for *a verdict with findings* about a file nothing had read.

**`En` is English.** The metamodel's own predicate takes `en` and `EN`
and refuses the mixed spellings, and RFC 5646 §2.1.1 says capitalisation
must not be taken to carry meaning — so a file writing `En` was told it
had no English entry, on a line printing `languages present: En, de`
directly above. A trailing space no longer hides the mandatory VDI 2770
classification either. Both were findings on conformant files.

**Every finding prints the clause it answers for.** The JSON report has
carried `spec` since the first release and the terminal never showed it,
so the person writing "conforms: yes/no" into a report — who needs the
citation more than anyone — had to re-run with `-f json` to get it. It
prints now, under `per`. On the bundled official example that is a line
added to all 87 findings, which is the most visible difference between
this release and 0.1.0; nothing about a verdict changes.

**The verdict line survives a terminal that cannot spell it.** Every run
ended with an em dash, and cp949 — the default code page on Korean
Windows — has none, nor does cp932 on Japanese. Writing it raised, the
interpreter printed a traceback, and the process left by 1: so a clean
file and a file this reader refused came back as the same number, and
that number means *there are findings*. The exit code is the whole
contract for a pipeline that reads nothing else. What this tool writes
of its own is ASCII now, but for the section sign in an IDTA clause —
`§2.4` is how the standard spells it and how a reader has to spell it
back, so it stays and the escape hatch carries it — the summary reads `… info -- file.json;
judged 1 of 1 submodel` where it read `… info — file.json · judged …`
— and what it repeats from elsewhere, a section sign in a citation or
an idShort in any script, is escaped rather than raised on. One rule's
sentence changed with them and that one does reach the JSON: the note
about a submodel named for a template it does not declare joined its
halves with an em dash, so `SMT-D1`'s `detail` (and the same text as a
note under `--allow-unmatched`) now spells that `--`. Everything else
in the report is what 0.1.0 produced, but for the two keys added above, and all of it was
always ASCII — the encoder escapes, so a reader parsing JSON never saw
the em dash to begin with.

**A wrong-kind element is no longer told to add itself.** A generated
row's rule is about how many of an element there are and carries one
remedy: provide one. Two violations filed under the same rule id are
not about how many — an element that is present and is the wrong kind,
and one that declares the wrong valueType — and both inherited that
remedy, so the tool answered "provide a Version" to a reader looking at
one. Following it produces the cardinality violation the rule is really
for. Both now say what the element is today and what to change it to.

What this reader takes in is unchanged: one document at 64 MiB, a
container's parts at 64 MiB each and 256 MiB together, and a container's
directory of names at 16 MiB.

## 0.1.0 — 2026-09-04

First release: 125 rules, 116 of them across three IDTA templates — *Handover
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
