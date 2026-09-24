# The JSON report

`smtv -f json` writes one JSON object to stdout. This is what is in it,
and what the version number at the top of it promises.

Three runs write nothing there. `-q` asks for the exit code alone. A
command-line usage error -- an unknown option, a missing argument, a
value outside the choices, a second path, or two flags that contradict --
exits 64 (`EX_USAGE`) and writes no report, because no input was read.
And a `--template` file this reader refuses -- unreadable, not JSON, not
shaped like a template, over either bound -- leaves at 2 with no report
either: the file that would have been judged was readable, nothing was
written about it, and the template's own digest is recorded nowhere.

A usage error exited 2 before 0.4.0; 2 no longer covers it. Exit 2
otherwise always writes one: an input this reader refused comes back
with a report saying what was refused and what to do about it, and so
does a path it could not read at all -- that one names the path, carries
an `X6` finding, and has a null `provenance.inputSha256` because nothing
was opened to take a digest of. Both also write a line on stderr, so
read stdout when it is not empty. A reader that parses it
unconditionally meets its first `JSONDecodeError` on the case it most
needs to handle.

```json
{
  "schemaVersion": 1,
  "toolVersion": "0.7.1",
  "provenance": {
    "inputSha256": "9f2c\u2026",
    "engine": null,
    "envelope": null
  },
  "path": "machine-docs.aasx",
  "ok": false,
  "options": {
    "profile": null,
    "meta": "warning",
    "strictMeta": false,
    "allowUnmatched": false
  },
  "summary": {
    "errors": 1,
    "warnings": 0,
    "info": 0,
    "rulesChecked": 310,
    "complete": true,
    "judged": true,
    "submodelsSeen": 1,
    "submodelsJudged": 1,
    "submodelsSpecified": 0,
    "rulesNotAsked": [],
    "unmatchedElements": [],
    "scopeNotExamined": []
  },
  "notes": [],
  "findings": [
    {
      "rule": "HD-D8",
      "kind": "template",
      "severity": "error",
      "priority": "MUST",
      "message": "StatusSetDate is not a valid xs:date",
      "subject": "HandoverDocumentation/Documents/[0]/DocumentVersions/[0]",
      "detail": "'06.02.2020'",
      "fix": "Write StatusSetDate as YYYY-MM-DD (xs:date), e.g. 2020-02-06.",
      "title": "StatusSetDate is a calendar date",
      "spec": "IDTA 02004-2-0 \u00a72.8 (xs:date)",
      "fixability": null,
      "fixabilityWhy": null,
      "path": ["document", "submodel", "element"]
    }
  ]
}
```

## What `schemaVersion` promises

`schemaVersion` is the shape's number, not the tool's. It stays at `1`
while every key below keeps its name and its meaning. A key may be
*added* without the version moving — a consumer that does not know the
key reads exactly what it read before — so read by key and ignore what
you do not recognise. A key being renamed or removed, or a value
changing what it means, moves the version.

`toolVersion` is the producer's version, and answers the other question:
which build wrote this report. The two move independently, and a bug
report needs the second one.

## The top level

| key | type | |
|---|---|---|
| `schemaVersion` | integer | The shape. `1`. |
| `toolVersion` | string | The version of `aas-submodel-validate` that wrote the report. |
| `provenance` | object | What was judged, by what, and who vouches for it; see below. |
| `path` | string | The input, as it was given on the command line — or, under `--example`, the name of the example file carried in the package, because that is the file the verdict is about and no path was typed. |
| `ok` | boolean | No finding at `error` severity. `-W` raises the bar for the exit code without changing `ok`, and so does `summary.judged`: a run that judged nothing exits 2 whatever `ok` says. |
| `options` | object | What was asked of this run; see below. |
| `summary` | object | Counts; see below. |
| `notes` | array of string | Things worth saying once about the run rather than about the file — a `--profile` that named a template nothing here answers to, or an unmatched submodel that `--allow-unmatched` let through. A run given `--template` says several here: whether your template judged anything, which submodel of it the table came from where the file held more than one, which pack stood down for it and what that removed, and whether a `--profile` it overrode decided anything. Free text, one string per note; `provenance.template` is where the same run is recorded in fields a consumer can read. |
| `findings` | array of object | Every finding, in reading order; see below. |

## `provenance`

A report becomes evidence when it says three things: which bytes were
judged, which engine judged them, and who vouches for the result. This
tool can answer the first for certain, cannot answer the second about
itself in a way anyone should trust, and must not answer the third at
all — signing belongs to whoever issued the document being judged, the
way a declaration of conformity does. A validator that signed its own
verdicts would be selling an assurance it has no standing to give.

So one field is computed and two are reserved. They are present and
`null` rather than absent, because a key that appears in a later version
is a schema change and a key that is always `null` is a promise
something can be built against.

| key | type | |
|---|---|---|
| `inputSha256` | string or null | SHA-256 of the input file as it arrived — of the bytes on disk, whether or not any of them were judged. A refused input still gets one, and that is the point: the report names the file it refused. `null` in three cases: the file could not be opened at all; it is larger than the digest itself will read (256 MiB, the bound on a whole container); or the path is not a regular file — a pipe, a socket or a device is refused without being read, so there are no bytes to name. Before 0.4.1 a device hashed to the sha of zero bytes and a pipe made the run hang, which is why the third case reads as a widening rather than a correction. |
| `template` | object, absent | Present only when `--template` was given. `sha256` of the template file as it arrived, the `path` it was given under, the `semanticId` it claims, how many `rows` were generated from it, how many `submodels` that file declared, and `published`, which is always false and is the point of the key. The table is built from the first submodel in the file and the rest are not read, so `submodels` above 1 is the only field that distinguishes a template of yours that matched nothing from one this run never opened; `notes` says the same thing in a sentence. A verdict made against a template the caller supplied is not a statement about conformance to a published IDTA template, and a consumer that cannot tell the two apart has been told something untrue. Absent, rather than null, when the run used this project's own packs: a key that is there for every report says nothing, and the reader who needs this is the one who finds it present. |
| `engine` | null | Reserved: a reference to the engine build that produced the report, beyond the version string `toolVersion` already carries. Nothing fills it yet. |
| `envelope` | null | Reserved: the signed envelope a report may be wrapped in, and the signature over it. Nothing fills it yet, and nothing in this project will — the signer is the organisation issuing the document. |

## `options`

The same file comes back `ok` under one set of flags and not under
another, so a report that did not carry its flags could not be compared
with another report.

These are the flags that move what is *in* the report. Two others move
only the exit code and are deliberately absent: `-W` and
`--require-all-judged` change what the caller does with a verdict, not
what the verdict is, and a report that recorded them would be saying
something about its reader rather than about the file. Read
`summary.warnings` and the two `submodels` counts to see what those two
would have decided.

One flag that moves the report is deliberately **not** here either, and
for a different reason: `--template` is recorded in `provenance`. What
decides a verdict is the template's bytes, not the flag's spelling — the
same path can hold a different file tomorrow — so the record of it
belongs where this report names bytes, beside the hash of the input.
`provenance.template` carries that hash, the path, the identifier the
template claims and how many rows came out of it. Two reports of one
file are comparable on that, and comparable on a path alone they would
not be.

| key | type | |
|---|---|---|
| `profile` | string or null | The `--profile` value, or `null` when the choice was left to the default. |
| `meta` | string | `--meta`: the severity the relayed metamodel channel reported at — `error`, `warning` (the default) or `info`. At `info` it is still reported and still counted; it is `-W` that stops failing on it. |
| `strictMeta` | boolean | The older spelling of `meta == "error"`, kept because a reader written against 0.1.0 parses this one. Derived from `meta`, never set on its own — two independently-set fields for one setting is how they come to disagree. |
| `allowUnmatched` | boolean | `--allow-unmatched`: a submodel this tool does not recognise is a note rather than a finding. |

## `summary`

| key | type | |
|---|---|---|
| `errors` | integer | Findings at `error` severity. |
| `warnings` | integer | Findings at `warning` severity. |
| `info` | integer | Findings at `info` severity. |
| `rulesChecked` | integer | Every rule registered in this build. Not how many applied to your file — a Technical Data file is not judged by 02004's rules, and the number does not move when a different template answers — and not the number of findings. The relayed `meta` channel is not registered and is not counted. |
| `judged` | boolean | Whether anything reached the rules at all. `false` means the input was refused or could not be opened, so there is no verdict here — only the reason. The run exits 2. |
| `complete` | boolean | Whether everything this run was handed was read and built. `false` means something did not come out: a path that could not be opened, an archive that would not open, a relationship chain that went nowhere, a part refused for its size or for a DTD, a document that would not parse or could not be built, or a stop for this interpreter's stack or memory — what did not come out was not judged, and a report that only said `ok: false` could not tell you which. The container findings (`X1`–`X6`) say which. |
| `submodelsSeen` | integer | How many submodels the input holds. |
| `submodelsSpecified` | integer | How many of `submodelsSeen` declared `kind: Template`. A template is a specification, and every rule here is a requirement on an instance, so those are set aside rather than judged and a note names them. Subtract this from `submodelsSeen` to get the number a caller can do something about — which is what `--require-all-judged` compares against. Additive under `schemaVersion` 1, like `options` before it. |
| `unmatchedElements` | array of object | The same loss as `rulesNotAsked`, with the element that explains it named: one object per element whose `semanticId` matched no row while rules beneath an unentered row went unasked, as `subject` (where it sits), `seen` (the identifier it carries), `rulesNotAskedHere` (the ids it kept from being put -- named apart from the run total above, because the per-element arrays overlap -- one row's rules, lost in two items of a list, are listed under the element in each -- so together they cover the total and adding them up is not a number of anything) and `resembles` (the row identifier the walk found this one close to, or the row it claimed outright when the kind was wrong -- always present). One known limit: records are deduplicated by subject and identifier, and a subject is not unique when two elements' parents share an idShort (a metamodel violation this project relays rather than refuses), so two such elements are reported as one (`docs/divergences.md` #53). `rulesNotAsked` above answers *how many*; this answers *which element did it*, which is the question a reader has once the count is not zero. Recorded only where the walk found this identifier close to a row's -- the same comparison the near-miss lint publishes, and the sole trigger. Every pack registers that lint since 0.8.0 (until then 02002 and the other generated-only packs did not); a table built from a template of the caller's (`--template`) registers none, so there this record is the only place it is said rather than an addition to something already reported. A typo inside a path segment that is not the last is not close by that comparison and appears here not at all (`docs/divergences.md` #22, #23) -- because the template states a minimum and not a whitelist (#19) and an element of the supplier's own, resembling nothing, explains no absence. **Not a claim about the file and it moves no verdict**: a pipeline that wants to fail on it reads it here, and no flag was added to make it a verdict. Additive under `schemaVersion` 1. |
| `rulesNotAsked` | array of string | Rule ids this run never put. A generated rule sits inside a scope, and a scope opens only when an element matches the row that names it; an element whose `semanticId` matches no row is not recursed into, and every rule beneath it leaves the run (`docs/divergences.md` #23). Empty unless the walk found something in that scope that explains the loss — a row matched an element of the wrong kind, or an element carries an identifier close to that of the row the rules sit beneath. The near-miss lint reports that element in every pack (until 0.8.0 only in 02004's, 02003's and 02035-2's; in the others it was said only in `summary`: this key, `unmatchedElements`, and `scopeNotExamined` where its row went unentered). A near miss claims the rows it resembles and no others: a section the file omits beside it is a place not examined (`scopeNotExamined`) and not a rule the near miss kept from being asked. Of the rows it resembles, it claims those a walk entering it would have asked -- every row directly beneath, and below those only what the element holds -- less any rule some other scope in the submodel asked. An element of the wrong kind is not entered, and claims everything beneath the row, as an element of the wrong kind carrying the row's identifier outright does -- less, again, what some other scope asked. A row that copies an element above it has no rows of its own in the table, so an element of the wrong kind there claims nothing, as one carrying the copy's identifier outright claims nothing either. **A non-empty value does not mean the file is wrong and does not imply a finding of any severity**: the bundled official example passes with no error and one rule unasked, because a list there wears the wrong identifier and the lint says so. **Not a claim about the file and it moves no verdict**: the template states a minimum and not a whitelist (#19), so an element matching no row is not by itself a defect; what this reports is that the run did not look inside it. Read it when a report has no findings: `errors: 0` with a non-empty `rulesNotAsked` is a different answer from `errors: 0` with an empty one, and until this key existed the two serialised identically. Additive under `schemaVersion` 1. |
| `scopeNotExamined` | array of object | One object per place where a row of a template table was not entered — a list's items are separate places, so the same row can have a record per item — with `where` (the place), `rule` (the container row's id), `label` (its name in the template), `rulesNotAskedHere` (the ids beneath it that went unasked), `because`, `unclaimedHere` and `unclaimedHereCount`. `because` is `unclaimed-element-present` where an element of the kind the row asks for, carrying an identifier (a key that normalises to nothing is not one), matched no row in that place, and `absent` otherwise: the file carries no such section there, or carries only elements of other kinds, which are extensions (`docs/divergences.md` #19), or elements with no identifier at all. Those last are not counted on purpose — a container with no identifier is the commonest shape of a manufacturer's own, and counting it made conformant files speak — so a template container that lost its `semanticId` reads as a section the file does not carry. An `absent` record lists only rules not put anywhere else in that submodel, so a section one list item omits is not reported when the next item has it; an `unclaimed-element-present` record lists them all, because what sat there is a fact about that place whatever a sibling did. `unclaimedHere` names the elements that sat there, at most five, in path order, as `subject` (where it sits) and `seen` (its own `semanticId` as this reader matches it, keys joined by `/`; failing that the first supplemental identifier the file gives it), and `unclaimedHereCount` says how many there were; the list is empty exactly when `because` is `absent`. A row's own container under a drifted identifier and a row the file omits beside an unrelated container of the same kind are opposite situations, and what sat there is the one fact that tells them apart. **That value is two facts side by side and not a cause.** A different identifier may be a legitimate extension (#19) and nothing distinguishes that from a typo by looking (#22, #23), so this names no culprit and `rulesNotAsked`/`unmatchedElements` above keep their narrower trigger. It overlaps `rulesNotAsked`, which is a set of ids across the run: a rule is in both where a near miss in the same place resembles the row it sits beneath, a walk entering that element as the row would have asked the rule (any rule beneath the row, for an element of the wrong kind), and it was not asked elsewhere in that submodel -- the near-missed element is sitting there, so such a record is `unclaimed-element-present` where that element is of the row's kind and `absent` where it is not; in `rulesNotAsked` alone where a row matched an element of the wrong kind, and so was entered but not walked; here alone where nothing explains the place, including a place whose row a sibling entered, and where a near-missed element explains the place but does not hold the section the rule sits in, which a walk entering the element would not have opened either; and in both for two different places losing the same rule. The per-record arrays repeat an id across places, so a sum of them counts checks not made rather than rules, and the screen does not count them: it names the sections not opened and the elements beside them for `unclaimed-element-present` records only, leaving out, element by element, what the clause about rules not asked already names or counts, and a section whose every neighbour that clause names. A place is named by its path, which is not unique where two submodels share an idShort (#53). **Not a claim about the file and it moves no verdict.** Before it existed, a container of the kind a row asks for, wearing an identifier the template does not name, passed with every published number identical to a clean run. Additive under `schemaVersion` 1. |
| `submodelsJudged` | integer | How many of them a template this tool has a table for answered for. The difference is not a defect — an environment carries submodels this tool has no business judging — but without the number a report is silent about them: `SMT-D1` speaks only when *nothing* matched. This is the coverage figure that means something here; the fraction of rules that ran does not, because most rules are about other templates and their silence says nothing. |

The two are ordered, and both are worth gating on. `judged: false`
implies `complete: false`; the reverse does not hold — an archive with
one unreadable part among three good ones is incomplete and judged, and
its findings are real. Three outcomes, then: a full verdict, a partial
one, and no verdict at all. Without them a refused input arrived as
`ok: false` with one error and every rule counted, which is exactly what
a judged file that failed looks like.

## `findings`

Sorted for a person reading top to bottom: `error` before `warning`
before `info`; within a severity, `container` before `template` before
`lint` before `meta`, because a file can draw dozens of relayed
metamodel messages and they must not bury the template findings the
reader came for. The order is total, so two runs over one file cannot
differ.

| key | type | |
|---|---|---|
| `rule` | string | The rule id — the thing to filter on, and stable for the rules this build registers. A `--template` run is the exception: its table is built from the caller's file and mints `TPL-E…` ids for that run, so `TPL-E22` means whatever row 22 of *that* file is and means something else for the next file. Those ids are not registered and are not published. |
| `kind` | string | `container`, `template`, `lint` or `meta`. The prose above calls these *channels*; this field is spelled kind, and a reader who filters on `.channel` gets null for every finding with nothing to say why. |
| `severity` | string | `error`, `warning` or `info` — this project's reading of the priority. |
| `priority` | string | The rule's own priority word, one of `MUST`, `MUST NOT`, `REQUIRED`, `SHALL`, `RECOMMENDED`, `SHOULD`, `MAY` or `OPTIONAL` — the RFC 2119 keywords this project maps to a severity. The set is closed and wider than what today's rules use, so accept all eight. Both fields are published so a consumer that wants to re-derive the severity can. |
| `message` | string | What is wrong. |
| `subject` | string or null | Where: a path of idShorts, an identifier, or a part name. `null` where the finding is about the document as a whole. The path joins its segments with `/`, gives a list item a segment of its own, and appends an index to a name only where a sibling shares it (`docs/divergences.md` #53): `HandoverDocumentation/Documents[1]/[0]` is one this reader printed. That is this report's spelling and not the metamodel's `IdShortPath`, which joins with `.`; a relayed `meta` finding carries a third, the one that channel uses (`.submodels[0]`). Three spellings of *where* reach one report, and a consumer matching on this field is matching the first of them. |
| `detail` | string or null | Context — usually the value that was seen. |
| `fix` | string | What to do about it — usually one imperative sentence: what to change so this stops being reported. Where this reader refused a document rather than judged it (past one of its bounds, past what this interpreter can build, or bytes that are cut short or not UTF-8), it says why and that nothing was judged, and asks for a change only where one is known. Every finding carries one. |
| `title` | string | The rule's standing description, the same for every finding it produces. |
| `fixability` | integer or null | What repairing **this** finding would take, on the five-step scale below. Not a severity: a file can hold a loud defect nobody can repair beside a quiet one repaired by rewriting a string, and folding the two into one number is how a tool comes to promise repairs it cannot perform. `null` where this reader makes no claim: a shape it has not graded, or a finding that asks nothing of the file -- which of two tables answered (`SMT-D2`, `BAT-R2`), a bound this reader sets (`X5`), an identifier of a template it has no table for (`SMT-D1`), a rule that could not run. An absence of a claim, not a claim that the defect is unfixable. Additive under `schemaVersion` 1. |
| `fixabilityWhy` | string or null | One sentence saying what the reader found that makes that grade true: how many candidates it saw where it looked, or what the template does and does not give. Present exactly when `fixability` is -- a grade with no reason reads as a measurement nobody can check, and a reason with no grade is about nothing. |
| `path` | array of string | What `subject` names, as one of five routes. `["document", "submodel", "element"]`: an element, by its path of idShorts (`BAT-R8` names an element that is absent by its idShort alone, having no place to give it). `["document", "submodel"]`: a submodel, by its idShort or identifier. `["container", "part"]`: a part of the package, by name. `["container"]` and `["document"]`: the package or the document the caller gave, by the path as given -- or, where `subject` is null, the package or the document as a whole. Per finding and not per rule, because one rule's subject can be either: `X3` names a bare JSON document's own path and the part of a package that would not parse. Empty only for a relayed `meta` finding, whose `subject` is the upstream library's own expression and can name a shell, a concept description or an attribute, which no route here spells. Additive under `schemaVersion` 1. |
| `spec` | string | Where the requirement lives, and always present. It is prose, not a key: a template and section for most rules; a provision of the regulation for the rules that read one, built from the row being reported rather than fixed per rule; the OPC or AASX standard for the rules about the container; the metamodel standard and its schemas for the ones about what a document must be, and the metamodel constraints for the relayed `meta` channel; a pointer to this project's own documented bounds for the limits it puts on what it will read; for the lints and for the rule about two templates sharing an identifier, a pointer to `docs/divergences.md` for the reading being applied; and, for a table built from a template the caller supplied, the words "a template you supplied" and the field the row was read from — `the element's declared valueType`, `the list's declared typeValueListElement`, `the element's declared modelType`, or the cardinality qualifier. |

### What `fixability` means

Five steps, from a repair the input settles on its own to one it cannot
supply. Each is shown with a finding this reader produces, in the words
it prints.

| step | what it means | a finding of this reader's |
|---|---|---|
| 1 | determined by the input alone | none today: every repair this reader can see still rests on something a person has to confirm |
| 2 | determined once a premise is confirmed | `HD-D7`'s `the container holds no part at this File's value` where one part of the package carries the file name the value ends in, or several do and the archive records the same size and checksum for each: the corrected value follows once that part is confirmed to be the file meant. And a generated row's `'Version' must carry valueType xs:string`: the template states the type, and the rewrite follows once the value is confirmed to fit it |
| 3 | candidates exist and a person must choose | a generated row's `the template expects exactly one 'Version' here; found 2`: every copy is present, and which to keep is a person's call |
| 4 | context or domain knowledge is needed | `DN-D1`'s `URIOfTheProduct is not an absolute URI` on a value with no scheme: which absolute URI identifies the product is a fact about the product, not about the string |
| 5 | not recoverable without material or authority this run does not have | `the template expects exactly one 'Version' here; found 0` with nothing at that place resembling it, and `HD-D7` where no part of the package carries the file name at all |

**The grade belongs to the finding, not to the rule.** One generated row
reports five different shapes -- a count, a kind, a list's item type, a
`valueType`, a present element carrying no value -- and they are not
equally repairable. One message can even be two grades: `found 0` beside
an element that carries the row's idShort, or an identifier one version
suffix off, is a 2, and with nothing like it there a 5.

**A grade is judged from what the reader looked at**: the place the
finding names, and for a File value the package it is in. It looks
there for what could supply the repair -- one candidate is a 2, several
a 3, and several the archive records as one size and one checksum a 2
again, the archive recording them as one file under several names -- and the reason says what it
found. Content the file carries
somewhere else, such as the same element one level up, is not searched
for; where it exists, the repair is easier than the grade says, and
never harder.

A grade is not permission to rewrite a file. Step 1 changes its meaning
the moment a signature or an external digest covers the bytes, and this
reader writes prescriptions rather than repairs.

Every text field of a finding — `message`, `subject`, `detail`, `fix`, `spec`, `fixabilityWhy` — is bounded at 2000 characters. A report repeats what a file said, and a file can say a great deal: a 200 KB `File` value produced a 200,670-character report before the bound existed. Where a field was cut it says so and by how much (`... (198000 more characters, not shown)`), so a short value and a shortened one are never the same thing on the page. The bound sits far above anything this tool writes — the longest remedy it ships is 883 characters — so it can only ever cut what a file supplied.

`kind` is `meta` for findings relayed from
[aas-core3.0](https://github.com/aas-core-works/aas-core3.0-python)'s
metamodel verification, which this project delegates to and never
re-implements. Those carry the rule id `META`, with the constraint's own
name in the message where aas-core3.0's sentence states one -- not every
sentence does, so match on the rule id, never on the prose.
