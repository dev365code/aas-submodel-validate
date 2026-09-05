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
totals them and the JSON report is unchanged.

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

**The verdict line survives a terminal that cannot spell it.** Every run
ended with an em dash, and cp949 — the default code page on Korean
Windows — has none, nor does cp932 on Japanese. Writing it raised, the
interpreter printed a traceback, and the process left by 1: so a clean
file and a file this reader refused came back as the same number, and
that number means *there are findings*. The exit code is the whole
contract for a pipeline that reads nothing else. What this tool writes
of its own is ASCII now — the summary reads `… info -- file.json;
judged 1 of 1 submodel` where it read `… info — file.json · judged …`
— and what it repeats from elsewhere, a section sign in a citation or
an idShort in any script, is escaped rather than raised on. The JSON
report is unchanged: it was always ASCII.

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
