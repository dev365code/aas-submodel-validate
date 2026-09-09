# Changelog

## 0.1.4 — 2026-09-09

126 rules, 86 generated from the vendored template files. No rule is
added or removed here, and no count on the front page moves. Four said
something a reader could act on and be worse off for it, one of those
called a conformant package broken, and one let the order of a walk
decide a verdict. Paragraphs that move a verdict are marked
**`verdict`**.

What this reader takes in is unchanged: one document at 64 MiB, a
container's parts at 64 MiB each and 256 MiB together, and a container's
directory of names at 16 MiB.

**If you gate a build on the exit code, read this paragraph.** Measured
over the 52 corpus inputs against 0.1.3: none is judged differently. Two
shapes the corpus does not hold do move, both from 1 to 0. A container
whose `File` value differs from its archive entry only in ASCII case
stops drawing `HD-D7`, which is a MUST. And a battery passport stating
two categories stops drawing the `BAT-R8` rows that turn on one:
measured on such a file, the rows that were demanded are withdrawn, and
with `--meta info -W` the run goes from exit 1 to exit 0. At the default
`--meta` level that same file still exits 1 under `-W`, because the
findings relayed from the metamodel are counted as warnings — so whether
this moves your build depends on which channel you were failing on.

**A file stating two battery categories no longer has one chosen for
it.** **`verdict`** `declared_category` returned on the first category
element the walk reached, so a passport stating `ev` and then `lmt` drew
one set of `BAT-R8` findings and the same file with the two reversed
drew another — the verdict depended on the order the walk happened to
take, and nothing said a choice had been made. It answers now only when
the file states one category, and the coverage note names both and says
the run did not choose. The capacity threshold for exhaustion is
required for an electric vehicle and forbidden for light means of
transport, so guessing tells one of those two readers to add a field
their own guidance refuses. No corpus input states two categories, which
is why the corpus comparison above says nothing about this.

**A wrong-kind finding on a shared identifier says to wrap, not to
change.** The Handover template gives five lists and their own items one
semanticId: `DigitalFiles` and `DigitalFile` are both
`0173-1#02-ABK126#002`, and so are `Language`/`LanguageCode`,
`RefersToEntities`/`RefersTo`, `BasedOnReferences`/`BasedOn` and
`TranslationOfEntities`/`TranslationOf`. A file carrying the item alone
matches the *list's* row, and the remedy read "change this element from
a File to a SubmodelElementList" — which empties it, so the next run
reports `DigitalFile` missing instead. It now says to wrap the element
in the list it belongs to. The battery part has two of the five pairs;
`docs/divergences.md` #39 said it had none, and now says which.

**A `File` value that differs from the archive entry only in ASCII case
now finds its part.** ECMA-376 Part 2 (5th edition, December 2021)
6.2.2.3 says equivalence of part names is decided by ASCII
case-insensitive matching, and 7.2.5.5 maps a ZIP item to a part name
with an *equivalent* prefix rather than an identical one. A package
holding `aasx/files/Manual.pdf` against a value of
`/aasx/files/manual.pdf` is conformant, and `HD-D7` reported the
container as holding no part there — telling the author to add a file
already in the package. The folding is ASCII and stops there: the same
subclause keeps Unicode normalisation collisions under *should not*, as
advice to whoever writes a package, so `É` and `é` remain two names. It
is asked last, after every exact spelling, so an archive holding a name
in the case the document wrote still answers with that one. No verdict
in the corpus moves.

**`HD-D9` cites the clause with the condition that governs it.** The
rule reports a document or entity reference that resolves to nothing,
and quoted IDTA 02004-2-0 §2.2 as "the creation of an Entity element is
required" — a sentence which is conditional where it is written and read
as unconditional where it was quoted. The severity does not change; the
citation now carries the case the clause governs, and
`docs/divergences.md` #41 keeps the reading and the passage it rests on.

**`per` no longer cites the cardinality qualifier for a finding about an
element's type.** Every generated row's rule cites `SMT/Cardinality`,
correctly, for how many of an element there must be. The kind,
`valueType` and `typeValueListElement` findings were built beside it
without a citation of their own and inherited that one, sending a reader
arguing about a *type* to the provision about *counts*. They now cite
the declaration they actually read.

**Contributors: `make dev` works inside a virtualenv, and the battery
readers are declared.** It used `pip install --user`, which pip refuses
in a virtualenv, and installed neither the package nor the two readers
the battery-passport gate imports -- so `make check` straight after
`make dev` could not pass. Those readers are now a `battery` extra with
bounds, rather than an unpinned `pip install` line inside two workflows.

**Every GitHub Action this project runs is pinned to a commit digest.**
The release attaches signed provenance and publishes with a short-lived
token, and each step doing that was fetched by a name its owner can
move -- including the publisher, which was referenced by a *branch*.

**A tag only releases a commit CI has judged.** The release ran
`make check` on the tag's tree — one Python on one Linux — and nothing
asked what CI concluded about that commit across its ten rows. It now
does, and no completed run for the commit is a refusal rather than a
pass. A push to `main` is no longer cancelled by the next one either: a
cancelled run is the absence of a verdict, and this gate needs one.

## 0.1.3 — 2026-09-08

126 rules, 86 generated from the vendored template files. One rule is
new (`X6`, below). Paragraphs that move a verdict are marked
**`verdict`**.

**If you gate a build on the exit code, read this paragraph.** Measured
over 52 inputs against 0.1.2: seven are judged differently. Three
battery passports go from 1 to 0 -- they were failing for a reason that
was not about them, see the first item below. One goes from **0 to 1**:
a file whose required property is present and carries no value, which
this release started reporting. Two paths this reader cannot open now
produce a report where they produced none, at the same exit code. And an
`.aasx` whose LZMA member is damaged goes from **1 to 2**, which is a
correction of what the code meant rather than of the file.

**The example on the front page was wrong, and this release replaces
it.** `verdict` Until now this tool led with
`EnergyRoundTripEfficiencyFade` as an element "the law requires of every
battery category and the template permits absent". Regulation (EU)
2023/1542 Annex IV Part A (4) reads *"Where applicable, energy round
trip efficiency and its fade (in %)"*, and the Commission's own
data-point guidance marks the same attribute *if applicable* for all
three categories it names. That reading never reached the table: the
join behind it matches attribute names as token sets, and the two words
in front of the guidance text kept it from matching, so the only source
still speaking about that element was one spreadsheet mark.

**On the evidence this project indexes, there is no element the template
permits absent that the regulation requires of every battery category.**
The one that appeared to be was the mistake. `BAT-R8` now reports a row
only where the file states its own battery category, which it already
did for the other eight. The front page leads with `RemainingCapacity`
for an LMT battery, the one row where the clause carries no qualifier,
the Commission's guidance reads it required for LMT, and the long list
agrees -- and that agreement is asserted in the test suite, so a
re-pinned source that breaks it goes red rather than quietly restoring
the shape of the old mistake. See `docs/divergences.md` #37.

**Where the clause a finding cites qualifies itself, the finding says
so.** Three of the seven findings an LMT passport draws cite provisions
that read "where possible" or "where appropriate", and said nothing
about it. The guidance can mark an attribute mandatory for a category
while the provision behind it is qualified; both are printed, because
settling that between two published documents is not this tool's to do.

**A battery passport no longer fails by default.** `verdict` A passport
of IDTA 02035-1, -4 and -5 printed `no submodel declares a semanticId
this tool has a template table for` at error severity, then eight
`BAT-R8` findings about those same submodels, then `judged 0 of 3`, and
left by 1. `SMT-D1` asks whether anything here was judged and was
measuring whether anything matched a template *table*.

**A required element that carries no value is reported.** `verdict` A
Technical Data file with the `value` key deleted from all nine of its
properties drew no finding at all and left by 0. Cardinality is one
question and content is another, and this fell between them. `value: ""`
is deliberately not this rule's business -- the empty string is a value
of that type -- and `docs/divergences.md` #40 says why.

**A file this reader could not read no longer looks like a verdict.**
`verdict` An `.aasx` whose LZMA member had one byte changed raised
through every handler: the process left by 1, which is the code for *a
verdict with findings*, with nothing on stdout. Deeply nested JSON was
reported as "the file is not JSON" with a remedy telling you to fix the
syntax -- it is JSON, and this reader's stack ran out. A path under a
directory this reader cannot enter left by 1 with a traceback.

**`exit 2` always carries a report now.** `verdict` The same permission
denial gave an `.aasx` a finding and a parseable JSON document, and gave
`.json` and `.xml` an empty stdout. One contract, whatever the
extension, through the new `X6`. The remedy comes from the error and not
from the extension: a file that is merely unreadable is no longer told
to re-create itself with an AAS packaging tool.

**Large inputs are fast.** An environment with many submodels was
quadratic in their number: 4000 submodels in 5.4 MB took five and a half
minutes of CPU, well inside the 64 MiB bound this reader advertises. It
takes two seconds. Doubling the input doubles the work.

**What a run did not ask is accurate.** `rulesNotAsked` charged a near
miss in one branch to another -- dropping a collection reported nothing,
and dropping it while an unrelated element drifted reported twenty-three
-- and an intact submodel erased the claim that a different submodel
never asked a rule.

**On the screen.** Every finding's labels are explained on the screen
rather than only on the front page; the summary opens with the verdict,
which is what `$?` will be, so `--example` and `--example -W` no longer
print byte-identical screens at different exit codes; repeated findings
of one rule are grouped, which takes the bundled example from 88
terminal rows to 51 with nothing hidden; and a run that cites a
regulation says once that what it has is a published reading and not a
determination of compliance.

**Attribution.** The generated `battery_tables.py` ships in every
distribution and carries element descriptions, legal-reference cells and
the qualifying phrase of conditional provisions verbatim from three CC
BY sources. `NOTICE` names the file and states how the material was
modified. The long list is named by the edition that is CC BY.

**Corrections to the front page.** The drift figures said twelve and
thirty-three where the tool that measures them says eighteen and
eighteen of sixty-nine, and nothing pinned the old pair. The rule count,
the coverage sentence and `docs/scope.md` follow the change above.

## 0.1.2 — 2026-09-07

Still 125 rules, 86 generated from the vendored template files. No rule
was added and none was removed; several answer differently, and every
paragraph that moves a verdict is marked **`verdict`**.

**If you gate a build on the exit code, read this paragraph.** Measured
over 47 inputs against 0.1.1: eight are judged differently, and four of
those change an exit code. Three go from 0 to 1 -- a File value naming
the package's own content types stream, and two Technical Data lists
declaring an item type the template does not. One goes from 1 to 0: an
archive holding an entry whose name ends in a space, against a File
value naming it exactly, which was a refusal of a file that has what it
says it has. The other four move findings without moving the code: two
withdraw an `X4` warning, and two battery passports draw more of
`BAT-R8` because they state their own category.

So this release can turn a green build red, and the three ways it does
are all a document saying something it should not. It can also turn one
red build green, and that one was ours.

**One way into the normaliser where there were two orders.** Three call
sites turn a string into a part: supplemental relationship resolution
inside the package, the `X4` rule that reports a relationship naming a
part the archive does not hold, and the File rule. They did not ask in
the same order — `part()` tried what the archive literally holds and
interpreted afterwards, while the File rule folded the value's
surrounding whitespace and then asked, so the literal steps never saw
the spelling the archive holds. `docs/divergences.md` #18 recorded four
archives where they disagree.

The sharpest: an archive holding an entry named `aasx/files/manual.pdf `
and a File value naming it exactly. `part()` returns that entry and the
report said the container holds no part at that value. A reader that
contradicts itself on one page is worse to act on than either answer.

The folding is now inside `part()`, after the literal steps rather than
before, and every caller comes through it. What is deliberately not
folded is the archive's own entry names: an archive holding
`aasx/files/manual.pdf ` against a value of `/aasx/files/manual.pdf`
stays refused, because reading a value's whitespace is reading a
spelling and reading the archive's would be supplying a character the
value does not carry.

**`BAT-R8` asks the eight questions a passport's own category settles.**
Nine template elements are `ZeroToOne` while a published reading of the
regulation marks the same attribute mandatory. Eight of the nine were
withheld: their obligation depends on the battery's category, and no
rule read one. Firing them regardless would tell a light-means-of-
transport manufacturer to add `CapacityThresholdExhaustion`, which the
guidance marks *not to be filled* for exactly that category — over-
refusal wearing the shape of diligence.

IDTA 02035-4 makes `BatteryCategory` cardinality `One` and names its own
vocabulary in the element's description: `lmt`, `ev`, `industrial`,
`stationary`. A passport that states one has answered the question the
rows were waiting on, so this reads it and applies the guidance column
that value settles. Nothing is inferred: `not-to-be-filled`,
`voluntary`, `not-stated` and `certain-cases` draw nothing, and
`CapacityThresholdExhaustion` stays silent for `lmt` while firing for
`ev`.

`industrial` and `stationary` are deliberately left unanswered. They
reach only guidance columns named *above 2 kWh*, and a category is not a
capacity; the provision that would close the gap is Article 77(1), which
this repository does not index. Judging on a provision we have not read
is the thing this project refuses, so those files are judged exactly as
before and the coverage note counts what was withheld from *them* rather
than from the table.

**`verdict`** — eight of the 47 corpus inputs are judged differently.

`HD-D7` is no longer drawn on that archive and its exit code falls from
1 to 0: a false refusal withdrawn, because the file the value names is
in the package.

A passport declaring `ev` draws two more warnings and one declaring
`lmt` draws seven more; one declaring `industrial` is unchanged. The
corpus carried no battery passport at all, so three were added, and no
File value with an illegal character, so four more — twice over, a rule
could not be seen to move by an instrument with no input for it.

`X4` moved too, at a call site the corpus could not see. A
supplemental relationship whose target carries surrounding whitespace
(`/aasx/files/manual.pdf` followed by a tab) drew `an aas-suppl
relationship names a part the archive does not hold` and now draws
nothing, because the same folding reaches relationship resolution. The
exit code does not move — `X4` is a warning — but a report that named a
missing part stops naming it, and the part was never missing.

That second line was traced by hand to every caller of `part()`; the
corpus held no whitespace relationship target and reported one moved
verdict where there were two. Two inputs were added so the instrument
can see it. A comparison that has no case for the thing that changed
reports a confident zero, and this file exists to stop a release note
resting on one.

**A report cannot be grown without bound by what a file says.** Every
text field of a finding is capped at 1000 characters, and where one was
cut it says so and by how much. Measured before: a 200 KB `File` value
produced a 200,670-character report, and the only thing bounding it was
the 64 MiB limit on the input.

The cap is on `Violation`, which every finding is built through, and it
applies to all five of its text fields rather than the one that was
found carrying a value. Capping a single place is the mistake this
project has met before: the class stays and the next rule to interpolate
a value reopens it. It sits far above anything this tool writes -- the
longest remedy it ships is 403 characters -- so it can only ever cut
what a file supplied, and a test asserts that stays true.

This moves no verdict: the findings and their severities are what they
were, and only the length of what a report repeats back has changed.

**A list that declares it holds something the template does not.** The
generator has read `typeValueListElement` off the templates since the
tables existed -- twenty-one rows carry the item type their list is
declared for -- and no rule read one.

Mostly that cost nothing, and measuring says why: the metamodel asks
whether the items agree with the list's own declaration (`AASd-108`) and
whether a value type is present where one is needed (`AASd-109`), both
relayed here; and where those are silent, the item row's own cardinality
catches the file first, because a `1..*` item row cannot be satisfied by
an empty list.

Four Technical Data rows have a `0..*` item row. There a list that
declares the wrong item type and carries no items is metamodel-clean,
satisfies every row, and said nothing at all. Neither the metamodel nor
the item row can ask the question that is left, because it is not about
the items: it is whether the declaration agrees with the template.

Only a disagreement is reported. A list that declines to declare an item
type is not a case a document can reach -- the schema requires the field
and the payload does not parse -- which replaced a test asserting the
rule stays quiet for such a file. It did stay quiet, because nothing was
judged at all.

**`verdict`** -- a Technical Data list declaring `File` where the
template declares `SubmodelElementCollection` now draws its row's
finding. Two inputs added; the corpus reports eight of 47.

**A value that no part name can carry is told so, and which character
it was.** `canonical_part_name`'s first paragraph has said since 0.1.0
that part names "escape reserved characters", and nothing checked. RFC
3986 §3.3 builds a segment out of pchar and ECMA-376 Part 2 builds a
part name out of those segments, so `x?y.pdf`, `a<b>.pdf` and
`[Content_Types].xml` are not part names — and the first two were
reported as *a part the container does not hold*, which sent the author
to add a file, and the third drew nothing at all.

The check names the character. Deliberately conservative in two places:
a lone `%` is not legal and is not refused, because tools do write
`discount50%.pdf`; and a character outside ASCII is not refused either,
because archives carry `Handbuch_Größe.pdf` unencoded, the literal
lookup finds those entries, and refusing them would fail a file over a
spelling nothing else here minds. Both are recorded rather than
enforced.

**The four reasons are now four sentences.** `canonical_part_name`
returning `None` already meant any of four things and the rule
attributed all of them to the first, so `/aasx/files/` — which names a
directory and climbs nowhere — was told it climbed out of the package.
The not-a-part-name finding also carries its own remedy now: the rule's
says to add the file under the name the value gives, which is right for
a missing part and wrong for a value no entry can be named after.

Asked only of a value a document wrote. An archive entry name is not a
part name; it is whatever a ZIP holds, and this reader's literal-first
arrangement exists so an oddly spelled entry stays reachable. Putting
the character rule inside the spelling walk took those entries out of
the canonical index and made `X4` report a part missing that was in the
archive — caught by the corpus, and the reason the check lives in
`part_name_problem` and not in `canonical_part_name`.

**`verdict`** — a File value of `[Content_Types].xml` now draws `HD-D7`
where it drew nothing. Values with an illegal character keep the same
finding and severity; what changes is which sentence and which remedy,
so the corpus records no movement for them and this paragraph does.

**`verdict`** — `X4` no longer reports a missing part for a supplemental
target whose only defect is surrounding whitespace. A target with a
leading space failed `startswith("/")`, took the relative branch and was
joined into `aasx/ /aasx/…`, a string naming nothing; the same target
with the space on the other end resolved. Two answers separated by which
side the whitespace fell on. The settled spelling is now tried *after*
the literal one, never before — settling first is the mistake #18 was
about, one layer out, and it makes an archive holding an entry whose
name ends in a space unreachable by the target that spells it exactly.

**A report says what it could not ask.** A generated rule sits inside a
scope, and a scope opens only when an element matches the row that names
it, so what is below an unentered scope leaves the run — quietly, with
nothing wrong in what remained (`docs/divergences.md` #23).

`summary.rulesNotAsked` lists the rule ids that happened to. It draws no
finding, moves no exit code, and makes no claim about the file. The
terminal line says the same thing: `; 1 rule not asked -- an element
matched no row of the template, so this run did not look inside it`.

**It reports a loss only where this reader has already said something is
wrong**, and that narrowing is what makes it true. Two such places: a
row matched an element of the *wrong kind*, so the walk reported the
kind and did not recurse; or the near-miss lint fired in that scope, so
the reader has already said an identifier there looks like one it knows.
Every proposal is then checked against the walk's own record of the rows
it looked at, because the same rows are walked once per item of a list.

The first version of this did none of that and was wrong in both
directions at once. It guessed that any unclaimed
element with a truthy `value` meant a lost subtree — which is a
`Property`'s own string, so one manufacturer property on a conformant
file reported a rule unasked, and `docs/divergences.md` #19 promises
those pass without comment. And it accumulated per-scope misses run-wide
without subtracting: a two-item list reported 26 rules unasked with 22
of them run, one of which printed as an error in the same report. Both
are pinned now.

What it deliberately does not cover: a typo in the middle of a path
segment, which defeats the near-miss lint (#22). `tools/scope_silence.py`
measures that at **18 of the 69** generated rows the fixtures carry — a
version bump, the last character, leaves none of them silent because the
lint catches all 18 it touches. Reporting the middle-segment case means
deciding an unidentifiable element is evidence of a defect, and the
template states a minimum and not a whitelist. That is the policy
question #23 names and it is still open.

**The one file it speaks about today is our own reference material.**
IDTA's 02004 example carries a list whose `semanticId` is the item's
identifier where the template names the list's (divergence #2, recorded
since 0.1.0, and the lint has reported the element every run). What no
report said is that `HD-E38` — mandatory inside that list — was never
put. The example still passes on ten findings, none of them an error,
and now says: one rule not asked.

`entry_points.txt` is compared against `pyproject.toml`. It is exempt
from the distribution gate's tracked-files rule by name and is the one
member of a distribution that becomes an executable on a PATH; nothing
read it. Seven tampered wheels are reported, including a payload in
`[gui_scripts]`, which the first version of that check passed because it
read `console_scripts` by name.

What this reader takes in is unchanged: one document at 64 MiB, a
container's parts at 64 MiB each and 256 MiB together, and a container's
directory of names at 16 MiB.


## 0.1.1 — 2026-09-05

Still 125 rules, 86 generated from the vendored template files as
before, and no rule checks anything it did not check in 0.1.0. Most of
this release is about *reaching* a verdict — what someone who installed
0.1.0 from the package index, took it from the release page, or read
the front page could not do.

**Some verdicts do change, and if you run this in a pipeline they are
the part to read.** Every paragraph below that moves what this tool
reports is marked **`verdict`**, so you can find them without reading
the rest.

Thirty-two inputs were put through both versions and sixteen come back
judged differently. Fifteen of the sixteen go the quiet way — a finding
in 0.1.0 and silence here, an exit code that falls — which is the
direction nothing downstream reports: a build that is red on one of
these today goes green without saying so, and all but one of them was a
finding on a file that was conformant all along. The sixteenth is the
one new refusal, and it is named as such where it appears.

That is measured rather than recalled: `tools/verdict_diff.py` runs the
released version and this one over the same inputs and prints what came
back different. Earlier drafts of this section were written from what
had been *changed*, which is a different list from what *moved* — they
undercounted these shapes, named one as having moved when it had not,
told a reader to check whether their build was green when it would have
been red, and missed the largest un-refusal here entirely.

The corpus is not every input in the world, and a shape it does not
carry is one this note cannot speak for.

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

**A check that could not run fails the run.** **`verdict`** — a rule
that raises has always become a finding rather than a crash, so that
one broken rule cannot hide the others. It was reported at the rule's
own severity, which for the 23 registered rules asking for less than a
MUST meant a warning or an info, and the run left by 0: a clean exit
for a file this tool stopped checking, which is the one thing a
pipeline reading nothing but the exit code cannot survive. Those
findings are errors now. What the rule asks for is unchanged and still
reads `SHOULD` under `priority` in the JSON — the severity is about the
run, not about the file.

The same holds for the relayed channel when it stops, and the sentence
it prints no longer says the file is at fault. That call can end for
reasons that are nothing to do with the input, and the remedy said
"stopped on this input" about all of them; it also told the reader to
look at "the value it names", where an environment gives it no value to
name. It now says what is true in every case: the channel is quiet, the
report is short of an answer rather than carrying a wrong one, the rest
of the verdict stands, and what stopped it is recorded beside the
finding.

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

**`--rules` refuses what it would have ignored.** **`verdict`** — it
lists the rules and judges nothing, so every flag about judging is a
question it does not answer: `-q`, `-f json`, `-W`, `--allow-unmatched`,
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
§3.1). **`verdict`** — eight shapes of value are judged differently from
0.1.0, and one of the eight is judged more strictly.

Stricter, and the only new refusal in this release:
`files/a://absent.pdf` contains `://`, is a good part name once
normalised, and used to walk past the rule. It is asked about again,
and if the archive does not hold that part this now draws `HD-D7` at
MUST and exits 1 where 0.1.0 exited 0.

Looser — **read this if a pipeline of yours is red on any of them
today, because it will go green without saying so.** All seven drew
`HD-D7` and `TD-D2` at MUST in 0.1.0, so they failed a build, and each
was a conformant file:

- a value whose colon really does open a scheme is somebody else's
  file and is left alone: `urn:iso:std:iso:1234`,
  `mailto:docs@example.com`, `data:application/pdf;base64,…`;
- the same written in capitals, `URN:ISO:STD:ISO:1234`, because RFC
  3986 §3.1 says a scheme is compared case-insensitively;
- a scheme that is not a URL and not registered anywhere,
  `rev2:manual.pdf` — the rule asks whether the value is a part name,
  and a scheme means it is not, whatever the scheme turns out to name;
- a part name carrying whitespace at either end,
  `" aasx/files/manual.pdf "`, or ending in a newline.

Unchanged, and named because an earlier draft of this note said
otherwise: a File value that is only whitespace names nothing, and
0.1.0 passed over it exactly as this version does. A Windows path like
`C:\docs\manual.pdf` is asked about exactly as it was — a single letter
before a colon is a drive letter, not a scheme — and so is a value that
climbs out of the package, `../outside.pdf`.

Both rules move together. They were the same rule written twice, word
for word, and they share a body now.

**A supplementary file kept outside the package is no longer reported
missing.** **`verdict`** — OPC gives a relationship a `TargetMode`, and
`External` says the target is not a part of this package -- how a
conformant AASX points at a document held on a server. Nothing read it.
The target was
resolved against the source part's directory as though it were a
relative part name, so `http://example.com/manual.pdf` became
`aasx/http:/example.com/manual.pdf`: a well-formed part name, matching
no entry, printed on the `at` line of an `X4` warning under a remedy
telling the reader to add that part or delete the relationship. Both
would have them break a correct package, and `-W` turned it into a
failed build. `TargetMode` is read now, and a target carrying a URI
scheme is left unresolved whether the mode was declared or not -- asked
after that join, every scheme is gone. A relationship naming a part the
archive genuinely does not hold is reported exactly as before.

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
instance.** **`verdict`** — `ModellingKind.Template` means a
specification, and every rule here is a requirement on an instance — so
pointed at the published IDTA templates, the ones this project generates
its own rules from, the
tool used to report that they have no VDI 2770 classification and tell
the reader to add one. No flag escaped it, and a package holding a
conformant instance beside the template it was built from came back as
a failure. Templates are set aside, the report says which ones and why,
and they are out of the coverage figure rather than counted as
unjudged.

**An XML document written in a legacy code page is read instead of
refused.** **`verdict`** — and this is the largest un-refusal in the
release. A payload declaring `ISO-8859-1` or `windows-1252`, written in
it, is a well-formed XML document: §4.3.3 lets a document be written in
any encoding it declares, and this is what a German, Korean or Japanese
Windows editor produces without being asked. 0.1.0 decoded every
payload as UTF-8, met a byte that is not, and stopped — `X3: the
document could not be read as an AAS environment`, **exit 2**, nothing
judged, under a remedy telling the author to *open the named document
and fix the syntax its parser rejects*. The syntax was not wrong, there
was nothing for them to fix, and no flag reached past it.

The declaration is read now and the document is decoded the way it says
to. Measured on the official example rewritten into each: **exit 2 → exit
0**, and the verdict is the one the UTF-8 original gets. Because the
file is judged at all now, findings appear that 0.1.0 never reached —
on the example, `HD-D6`, `HD-D10`, `HDL2` and `HDL5`. They are not new
rules and not stricter reading; they are what was always there behind a
document that was never opened. UTF-8 and UTF-16, marked or not, are
read exactly as before.

**An archive this reader cannot open leaves by 2, whatever stopped it.**
**`verdict`** — a ZIP entry name written in a legacy code page with the
header bit that claims UTF-8 set anyway — what a packager on a Korean or
Japanese
Windows produces — raised past every handler and left by 1, which is the
code for *a verdict with findings* about a file nothing had read.

**`En` is English.** **`verdict`** — the metamodel's own predicate takes
`en` and `EN` and refuses the mixed spellings, and RFC 5646 §2.1.1 says
capitalisation must not be taken to carry meaning — so a file writing
`En` was told it had no English
entry, on a line printing `languages present: En, de` directly above. A
trailing space no longer hides the mandatory VDI 2770 classification
either. Both were findings on conformant files.

The relayed channel has not moved with it. aas-core3 asks
`is_bcp_47_for_english`, which is `^(en|EN)(-.*)?$`, so it accepts `EN`
and refuses `En` — and that channel carries its reading, not ours. On
the official example rewritten into title case that is sixty-five
further relayed findings, reported and counted as upstream's and never
as this tool's. `--meta info` is where a caller says what to do with
them.

**Every finding prints the clause it answers for.** The JSON report has
carried `spec` since the first release and the terminal never showed it,
so the person writing "conforms: yes/no" into a report — who needs the
citation more than anyone — had to re-run with `-f json` to get it. It
prints now, under `per`. On the bundled official example that is a line
added to all 87 findings, which is the most visible difference between
this release and 0.1.0; nothing about a verdict changes.

**The verdict line survives a terminal that cannot spell it.**
**`verdict`** — every
run ended with an em dash, and cp949 — the default code page on Korean
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
