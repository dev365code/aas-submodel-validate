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

## Which templates it covers, and which it does not

Six official templates are given rule tables: IDTA 02004 Handover
Documentation, 02003 Technical Data, 02035-2 Digital Battery Passport
part 2, 02006 Digital Nameplate, 02023 Carbon Footprint, and 02002
Contact Information. A submodel of any other template is reported as not
matched (`SMT-D1`), not judged; `--allow-unmatched` turns that from an
error into a note.

`--template FILE` is the other answer. Give it an IDTA-shaped template
of your own and a table is generated from it at run time and the
submodel judged against that. What that buys and what it does not:

- It checks **what a template states** — which elements, of which kind, under which identifiers, how many of each, the `valueType` each declares, a list's item type, and any `AllowedIdShort` pattern. That is what a generator
  can read out of a template file.
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
- Where your template claims an identifier one of the six packs also
  answers for, yours answers and the pack stands down — the report says
  which identifier that was.

The generator reads a row's cardinality from one of three qualifier
spellings -- the current `SMT/Cardinality`, the older `Multiplicity`, or a
bare `Cardinality`, the same vocabulary (`One`, `ZeroToOne`, `OneToMany`,
`ZeroToMany`) in each (`docs/divergences.md` #50) -- and reads an element
carrying none of them as `0..*` (#20). So a template that states its
obligations in any of the three is judgeable once its table is vendored.
IDTA 02002 Contact Information 1.0.1 is the first such template vendored
here: all thirty-six of its elements state their cardinality in
`Multiplicity` and none in `SMT/Cardinality`.

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

One published template written in the `Multiplicity` spelling is still
not vendored: **IDTA 02007 Software Nameplate 1.0.1** (73 elements, 14
mandatory), measured from the published template at the upstream pin.
Until its table is added, a submodel of it draws `SMT-D1` — or can be
judged with `--template` against the published template file, with the
limits above.
