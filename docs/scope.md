# Scope

What this project is: an offline conformance validator for AAS submodel
template instances. Files in, findings out, a remedy sentence on every
finding.

## What it is not

- **Not a metamodel validator.** aas-core3.0's verification runs here
  and its findings are reported (the `meta` channel), but no AASd/AASc
  constraint is ever re-implemented as a rule of this project. The
  official test tooling for the metamodel, serialisation and APIs is
  admin-shell-io/aas-test-engines; duplicating it would be waste on our
  side and noise on theirs.
- **Not an AAS server, client or API test bench.** Files in, findings out.
- **Not a template authoring or editing tool.** It reads the official
  templates; it never writes one.
- **Not a converter.** AASX, XML and JSON are read; nothing is
  transformed, migrated or re-serialised as a product feature.
- **Not a Digital Product Passport platform.** IDTA 02035-2 is judged as
  what it is measured to be — a profile of the Handover Documentation
  template, twenty-two of its thirty-eight rows with two relaxed — and
  nothing more. `--profile` says which of the two answers, and the
  report says which answered whenever there was a choice to make. No DPP
  registry, no passport identifier resolution, no certificate of
  compliance with Regulation (EU) 2023/1542. This project is the
  submodel-conformance layer.
- **It does say where a template and the regulation disagree, and only
  that.** `BAT-R8` reports an element the template permits to be absent
  that a published legal reading requires, and says both halves in those
  words. It reports the disagreement, not a verdict on the battery:
  reading a category, deciding which applicability date applies, or
  concluding that a passport is compliant are all outside this. Of the
  nine such disagreements it knows, **none is required of every battery
  category the sources name** -- one appeared to be until its provision
  turned out to read "Where applicable" (`docs/divergences.md` #37) -- so
  it reports a row only where the file states its own battery category,
  and its coverage note says what was not asked and why.
- **Where a clause qualifies itself, the finding says so.** The
  Commission's guidance can mark an attribute mandatory for a category
  while the provision behind it reads "where possible"; both are
  printed, because settling that between two published documents is not
  this project's to do.
- **Not a certifier, and not a fixer.** It reports findings and names
  the remedy for each; deciding what a file was meant to say is the
  author's job. No `--fix`, no conformance certificates.
- **Not an unpacked-AASX checker (yet).** OPC relationship semantics on
  a loose directory are ambiguous; refused until a real need defines
  them.

**Deferred, not rejected**: IIFU composition — detecting an iiRDS
Information for Use submodel and handing its iiRDS payload to
iirds-validate, so the two standards' validators compose.

## What a pass means, run by run

`ok` and the exit code answer one question each, and neither is "this
file is conformant". `ok` is *no finding at error severity*. The exit
code is that, plus the flags that make other things fail the run -- so
the two can part company, and one of the rows below is where they do.
These are the shapes a run comes back in, each with what it says and
what it does not. No option here is new; they are the ones already
there.

| run | exit | `ok` | what it means |
|---|---|---|---|
| a file whose only complaint is from the metamodel | 0 | true | one `META` warning, `judged 1 of 1`. The metamodel relay is a warning by default, so a metamodel defect alone passes |
| the same file with `--meta error` | 1 | false | the same single `META`, promoted to an error. Nothing about the file changed; the policy did. (`--strict-meta` is the older spelling and still works) |
| a submodel of a template this build has no table for, and no `--template` | 1 | false | `SMT-D1`, `judged 0 of 1`. The file is not being called wrong -- nothing here judged it |
| the same with `--allow-unmatched` | 0 | true | no finding **from this run**, and still `judged 0 of 1`. **This is a pass that judged nothing** |
| the same again with `--require-all-judged` | 1 | true | **`ok` is true and the run failed.** The flag fails on the count, not on a finding, so a build reading `.ok` alone goes green here. `-W` parts them the same way |
| a supplied table that states no rule this reader can check | 0 | true | `judged 1 of 1` having compared **nothing**: every element the template declares is open content, so its table has no rows. `--require-all-judged` passes it, because the submodel *was* judged -- against nothing. `provenance.template.rows` is the number that says so, and a note says it in words |
| an input this reader refuses to read | 2 | false | `X1`, and a report naming the file and the bytes it refused. `ok` is **false** here and that does not mean the file is wrong: `summary.judged` is false, and that is what tells a refusal from a failure. 2 means "could not judge", not "judged and failed" |
| a `--template` this reader refuses to read | 2 | no report | the table could not be built, so there is no verdict to write and nothing is written. The reason goes to stderr |

A path that was never opened -- a name that is not there, a device, a
directory -- is also exit 2, with `X6` and no digest: `inputSha256` is
`null` because there were no bytes to name. `docs/report-schema.md` is
where the fields and their null cases are defined; this page shows the
runs.

A usage error -- an unknown option, a missing argument, flags that
contradict -- exits **64** and writes no report, because no input was
read.

Three of these come back `ok: true` and only one of them judged
anything against a rule. `summary.submodelsJudged` separates the first
four; it does **not** separate the fifth, where a table with no rows
judged a submodel against nothing. For that route the number is
`provenance.template.rows`. A build that gates on the exit code alone
cannot tell any of them apart, and one that gates on `.ok` alone misses
the row where the exit code is 1.

## Which templates it covers, and which it does not

Eight official templates are given rule tables: IDTA 02004 Handover
Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport
part 2, 02006 Digital Nameplate, 02023 Carbon Footprint, 02002 Contact
Information, 02011 Hierarchical Structures, and 02007 Software Nameplate. A submodel of any other template is reported as not
matched (`SMT-D1`), not judged; `--allow-unmatched` turns that from an
error into a note.

`--template FILE` is the other answer. Give it an IDTA-shaped template
of your own and a table is generated from it at run time and the
submodel judged against that. What that buys and what it does not:

- It checks **what a template states** — which elements, of which kind, under which identifiers, how many of each, the `valueType` each declares, and a list's item type. That is what a generator
  can read out of a template file and what a rule is made from.
- One thing a generator reads and no rule is made from: an
  `AllowedIdShort` pattern. The table carries it and the walk records an
  element whose name does not match, but only a pack's own lint reports
  that, and a table built at run time registers no lints. So a supplied
  template's `AllowedIdShort` is read and not said — unless it cannot be
  read at all, which is the template's defect rather than the file's and
  is named in a note.
- It does **not** bring the hand-written rules, which are readings of a
  specification rather than of a template: the battery passport against
  Regulation (EU) 2023/1542, `URIOfTheProduct` as an absolute URI, the
  readings recorded in `docs/divergences.md`, the corpus that pins them.
  Those exist per template and cannot be derived from one.
- The report says so. `provenance.template` carries the file's hash and
  `published: false`, and a line on the screen says the table came from
  your file and is not a published IDTA template. **A verdict against a
  template you supplied is not a statement about conformance to a
  published one.**
- Where your template claims an identifier one of the eight packs also
  answers for, yours answers and the pack stands down — the report says
  which identifier that was.
- The `TPL-E*` ids such a run uses are **not ids this project
  publishes**. They are numbered by position in your template, so
  editing it renumbers them: a pipeline suppressing one by id is
  suppressing a position rather than a rule.
- What a template marks as **open content** is a place it has left to
  you, and nothing here judges it. An element the template identifies
  *as* a marker draws no rule — whatever else it carries beside that,
  which describes the placeholder rather than making it a requirement —
  and neither does one identified by nothing but markers, which would
  leave a rule with nothing to ask for. Either way your own content in
  that place is not faulted for failing to be a placeholder. A marker is
  also never one of the identifiers a rule answers to, so your element
  under a marker cannot stand in for one the template actually asked
  for.
  An element identified as a marker that **also declares children** is
  read the same way: the marker decides it and nothing under it draws a
  rule, so a template that calls a place free content and then describes
  what belongs in it is answered as free content only. If that leaves no
  rule at all the run says so; if it leaves others standing, it does not.
  No vendored template file has that shape.
- Two qualifiers of **one type** on one element — a file the metamodel
  forbids — are read as the later one: `ZeroToOne` written after `One`
  leaves the element optional, the other order requires it, and the one
  that lost is not reported.
- An element a template declares and gives **no semanticId** is not a
  rule. Elements are matched by identifier here and never by idShort, so
  nothing in your file could answer such a row; asked as an obligation
  it was an error no file could clear. The run says which elements those
  were, and giving one a semanticId in the template turns it into a
  rule. A list's item row is the exception and not an instance of this:
  it is matched by its kind, which is how the published templates write
  one.
- An element a template declares **inside itself** — 02011 Hierarchical
  Structures is the published case — is judged at every depth. The table
  stops at the repeat so that it stays finite, the repeat is a row of its
  own at the cardinality the template gives it, and the walk gives each
  nested copy the rows of the element it copies (`docs/divergences.md`
  #48). Only a repeat of its own parent, written with nothing inside it,
  is read that way: a repeat the template writes with content is judged as
  written, and one repeating an ancestor further up is out of scope and
  judged as the table spells it.

The generator reads a row's cardinality from one of three qualifier
spellings -- the current `SMT/Cardinality`, the older `Multiplicity`, or a
bare `Cardinality`, the same vocabulary (`One`, `ZeroToOne`, `OneToMany`,
`ZeroToMany`) in each (`docs/divergences.md` #50) -- and reads an element
carrying none of them as `0..*` (#20). So a template that states its
obligations in any of the three is judgeable once its table is vendored.
IDTA 02002 Contact Information 1.0.1 is the first such template vendored
here: all thirty-six of its elements state their cardinality in
`Multiplicity` and none in `SMT/Cardinality`. IDTA 02007 Software
Nameplate 1.0.1 is the second, all seventy-three of its elements in the
same spelling.

IDTA 02002's pack is generated rows only, and what that leaves unchecked
is worth stating because twenty-one of its thirty-six rows are
`MultiLanguageProperty`: a required multi-language property carrying no
language at all draws nothing structural here (the empty-value check is a
`Property`'s -- `docs/divergences.md` #40), duplicate or malformed
language tags are relayed from the metamodel rather than judged here, and
no email address, telephone number, URL, time zone or language code is
checked for shape. The template states those as strings and this project
does not invent a format for them. Nor is any idShort convention checked:
the template's `IPCommunication__00__` spells a placeholder for a numbered
instance, and because the template carries no `AllowedIdShort` qualifier an
instance may name that element anything at all without comment.

Four of 02002's five mandatory rows sit beneath an *optional* container --
`TelephoneNumber` under `Phone`, `FaxNumber` under `Fax`, `EmailAddress`
under `Email`, `AddressOfAdditionalLink` under `IPCommunication`, each of
those containers `0..1` or `0..*`. So a container whose identifier has
drifted matches no row, violates no count, is never descended, and takes
its mandatory child out of the run: the report names the unasked rules only
where the near-miss lint recognises the drift, and this pack registers no
near-miss lint and no reference-type lint at all. Nothing here promotes an
unasked mandatory row to a finding. That is not specific to one edition of
the template -- it is the shape of 02002, and `docs/divergences.md` #51 and
#23 record it.

IDTA 02011 Hierarchical Structures enabling Bills of Material 1.1.1 is a
tree: a `Node` holds `Node`s of its own identifier, to any depth, and the
pack judges every level of it -- the entry node and its nodes by count
and kind, the three relationships by kind, `BulkCount` and `ArcheType`
by `valueType`. Its pack is generated rows only, and among what is left
unchecked: a node's `entityType` and `globalAssetId` are not read, and a
`RelationshipElement`'s two ends are not either: the
template gives both as `https://admin-shell.io/SMT/General/IntentionallyEmpty`,
which constrains nothing, so whether `HasPart` points at a part -- or at
anything that exists -- is not asked (`docs/divergences.md` #56).
`ArcheType` is not checked against the three words the template's form
offers (`Full`, `OneDown`, `OneUp`), because a form's choices are an
editor's convenience and not a stated constraint. And whether the tree the
relationships draw agrees with the tree the nodes nest is a question this
pack does not ask.

IDTA 02007 Software Nameplate 1.0.1 describes software twice over: one
collection for the software as a type, one for an installed instance.
The template makes both optional, and every one of its fourteen mandatory
elements sits beneath one of them, so a Software Nameplate holding
neither draws nothing. Its pack is generated rows only, and what that
leaves unchecked: twenty-nine of its seventy-three rows are
`MultiLanguageProperty`, with the same limit as 02002's above;
`URIOfTheProduct` is not checked as an absolute URI, which is the Digital
Nameplate's hand rule and not this template's; no version, date,
checksum or path is checked for what it says; and the specification's
instruction that a contact's role be the technical-contact code is not a
rule here. Its `Contact` is 02002's collection copied in, but with 02002
1.0's identifier for `IPCommunication` rather than 1.0.1's, so the same
collection is not judged the same way under the two packs
(`docs/divergences.md` #51).

The rows are the template's, and the specification beside it disagrees
with the template in several places: the two collections' own
identifiers, `ConfigurationURI`'s identifier, `ConfigurationType`'s value
type, whether `InstallationDate` is mandatory, how many `InventoryTag`s
and `Contact`s there may be, two elements the specification makes a
`Blob`, and a second identifier for `SerialNumber`. A file built to the
specification's tables rather than to the template has both of its
collections left unexamined, which `scopeNotExamined` says, and draws no
finding; one that follows the template's collections and the
specification inside them can draw an error the template's own defect
put there. `docs/divergences.md` #57 lists each one and what the
run does with it.
