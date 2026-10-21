# What it catches

The cases behind the picture under [Where it stands](https://github.com/dev365code/aas-submodel-validate#where-it-stands)
on the front page. For each of its six axes: what a run shows, where the
requirement comes from, and a command that reproduces it; then where the
axis stands, item by item, and what this project asks of itself before it
calls a release 1.0. Every item marked done names a file in this repository
and quotes what it says. The values are set by hand in
[`docs/capabilities.json`](capabilities.json); the tests keep the picture
drawn from them, this page's sections and item lines in step with them, and
the outputs quoted here in step with the tool.

Commands are written for an installed `smtv`; from a clone, run
`PYTHONPATH=src python3 -m aas_submodel_validate` in its place.

## Coverage

**The official IDTA 02004 example, as published.** It is carried in the
package (`src/aas_submodel_validate/data/example/idta-02004-2.0.aasx`),
unmodified, defects and all:

```
ok -- 0 error(s), 87 warning(s), 0 info -- idta-02004-2.0.aasx; judged 1 of 1 submodel; 1 rule not asked (HD-E38): HandoverDocumentation/Entites is not one the template describes, so this run did not look inside it
```

The rules come from the IDTA 02004 Handover Documentation template,
version 2.0.2, vendored from the commit `THIRD_PARTY.md` names. Reproduce:
`smtv --example` (exit 0).

**The official IDTA 02003 sample.** Committed at
`tests/corpus/idta/02003/sample-2.0.1.aasx`:

```
ok -- 0 error(s), 9 warning(s), 0 info -- tests/corpus/idta/02003/sample-2.0.1.aasx; judged 1 of 1 submodel
```

Reproduce: `smtv tests/corpus/idta/02003/sample-2.0.1.aasx` from a clone.

Where it stands, template by template:

- IDTA 02004 Handover Documentation — done
- IDTA 02003 Technical Data — done
- IDTA 02035-2 Digital Battery Passport, part 2 — done
- IDTA 02006 Digital Nameplate — done
- IDTA 02023 Carbon Footprint — done
- IDTA 02002 Contact Information — done
- IDTA 02011 Hierarchical Structures — done
- IDTA 02007 Software Nameplate — done
- IDTA 02035-5 Digital Battery Passport, part 5 — done
- IDTA 02035-1 Digital Battery Passport, part 1 — done
- IDTA 02035-4 Digital Battery Passport, part 4 — done
- IDTA 02035-7 Digital Battery Passport, part 7 — done

Every template named for 1.0 has a pack. The first eight were named
rather than counted: a count can be met by whichever templates are
easiest, and a name says which documents a reader can bring. Which
templates come next is decided by what people bring (the README's
roadmap); the battery passport's parts 5, 1 and 4 came next, and joined
the list with their packs, because the battery-data layer already reads
them. Part 7, Circularity, followed, and that layer does not read it, as
it does not read part 2.

## Explanation

**One finding, whole.** From the bundled example:

```
warning HD-D10   no DigitalFile is a PDF; VDI 2770 requires a PDF/A rendition
        at   HandoverDocumentation/Documents/CADmodel/DocumentVersions/DocumentVersion_URL, line 4293
        at   HandoverDocumentation/Documents/CADmodel/DocumentVersions/DocumentVersion_file, line 3522
        saw  content types present: application/step
        per  IDTA 02004-2-0 §2.1 ("PDF/A files are required")
        fix: Add a DigitalFile with contentType application/pdf (a PDF/A file, per VDI 2770) to this DocumentVersion. A content type cannot prove PDF/A conformance, so this is a warning, not an error.
```

What is wrong, in one sentence; where, as a path of `idShort`s and the
line in the file that path begins on; what was read (`saw`); where the requirement lives (`per` -- a template's clause for
most rules, this project's own documented bounds or matching policy for the
few that are its own); and what to change (`fix`). Reproduce:
`smtv --example`.

- what is wrong, in one sentence — done
- the evidence as read from the file — done
- a remedy, for every rule — done
- where each rule's requirement lives — done
- the line in the file — done

The evidence is on every finding. On the bundled example all 87 carry a
place, a remedy and a `saw` line -- on the 77 relayed metamodel findings it
is what aas-core3.0's check read, its attributes taken from the check's own
source. A finding that an element is missing shows what the scope it
looked in holds, and a refusal shows the fact it rests on: a size, the
bytes a file begins with, how a part that would not come out is stored,
what a relationships part declares, what the operating system answered.

The line is on every finding a line holds: where the element, the concept
description or the object a relayed check is about begins -- JSON's `{`,
XML's start tag -- and, inside a package, in which part, which the screen
names when the findings come from two parts or more. A document that would not
parse or build names the line its parser stopped on or the object it
stopped in, and one nested past the bound the line it crossed on. No line
holds a finding about a whole file (no subject), about a package's
structure (`X1`, `X2`, `X4`), about a path nothing was opened at (`X6`), or
about a file refused for its size, and none is given in a package read past
the total its parts may come to. The line is found once the run is over, by
reading the document again -- the model keeps no positions, and holding
every document through every rule is the memory this reader does not spend
-- and is used only if its digest is the one the loader took of the bytes
it built the model from, so an input that changed after it was read gives
no line rather than another file's; run it again on the file as it now
stands.

Before 1.0: every finding shows what it read, and where in the file it read
it.

## Report contract

**The report is versioned, and its exit codes are pinned by the page that
explains them.** `smtv --example -f json` writes a document that opens with
`"schemaVersion": 1`, described field by field in
[`docs/report-schema.md`](report-schema.md). The runs a reader is likely to
make, and what exit 0 and `ok` mean for each, are a table in
[`docs/scope.md`](scope.md) — and that table is a test: each row is run and
its exit code and `ok` checked against what the page prints.

- schemaVersion in every report — done
- a golden report held by a test — done
- exit codes 0, 1, 2 and 64 under test — done
- a field-by-field schema page — done

The golden report is [`docs/golden-report.json`](golden-report.json): what
`-f json` says about a package built from this repository's fixtures,
values included, which `make check`, CI and the suite compare with what
the tool says now. The keys were held already, in both directions; this
holds what they say.

Reproduce: `python3 tools/golden_report.py --check` in a clone.

## Entrances

**One judgement, five ways in today.** The command line (`smtv FILE`, or
`aas-submodel-validate FILE`), a single file that needs nothing but a
Python -- `python3 tools/build_zipapp.py` in a clone, then
`python3 dist/smtv.pyz --example` prints the same verdict line as
`smtv --example` -- the library, where `validate` returns the report
`-f json` prints and `exit_code` the code `smtv` leaves by, a step in a
GitHub workflow: `uses: dev365code/aas-submodel-validate@` a release tag,
which installs that release and runs the command line on each file it is
given, and a page that needs nothing installed at all:
`python3 tools/build_browser.py` writes `dist/aas-submodel-validate.html`,
which judges the file you choose inside the browser tab. The README's four
doors -- a terminal, a single file, a build, a browser -- are four of the
five here: a build runs the command line, or the action that runs it.

- command line — done
- Python library — done
- single file, nothing to install — done
- GitHub Action — done
- browser, nothing installed — done

The command line judges through the library, so the two cannot disagree:
every input in the corpus the release notes measure, under every flag that
moves a verdict, is held by a test to one byte and one exit code between
them. Bytes and an open file are judged as the file they were read from.
The action's own script is run by the suite the way a runner runs it, and
held to printing what `smtv` prints and leaving by the code `smtv` leaves
by -- a validator that does not start is reported as that, not as a
verdict, and one that starts and then fails while judging a file leaves
by 1, as a finding does, so the step cannot tell the two apart; CI runs
the action itself on Linux and on Windows, from a carried
single file checked against its digest and from the index. The page runs the
command's own entry point inside the tab, on the Python it carries, and CI
opens it in a browser, served and from a disk: what it prints for every
input the release notes measure is held to what the command prints on that
same Python, at a UTF-8 console, byte for byte, and every request it makes
after loading is counted four ways -- and has to be none.

Before 1.0: all five ways in, each reaching the same verdict on the same
input — the library, a GitHub Action, and a browser page that checks a file
where it is, with nothing installed and nothing uploaded.

## Input safety

**What it reads is bounded, and a refusal is not a verdict.** One document
at 64 MiB, a container's parts at 64 MiB each and 256 MiB together, and no
document nested more than 200 levels deep; past a bound the input is refused, the report says so, and the run leaves by the
could-not-run exit code (`SECURITY.md`). The tests that hold the bounds
are in `tests/test_hostile_input.py`; `-k oversized` runs two of them, for a
part past its bound.

**Names the file wrote are printed escaped.** An `idShort` carrying a
control sequence is shown as its escape on every line of the text report,
the summary line included — which before 0.6.0 it was not
([GHSA-8w4g-mg5q-c4m4](https://github.com/dev365code/aas-submodel-validate/security/advisories/GHSA-8w4g-mg5q-c4m4)).
`python3 -m pytest tests/test_scope_the_run_did_not_examine.py -k escaped`
runs the test that holds the summary line.

- read budgets, per file and per run — done
- a security fix ships with an advisory — done
- tests verified against their own mutations — done
- declared encodings read without loss — done

From 0.3.0 on, a security fix that ships has an advisory; `SECURITY.md`
names the two earlier repairs that have a changelog entry only. Each gate
names the mistake it stops, and `make mutants` makes each mistake and checks
a test fails (`tools/mutation_table.py` lists them). CI runs the whole table
on every commit, and a release is cut only from a commit CI passed, so
every row has died on the tree that ships; `docs/mutation-record.json`
keeps the last full run, with the commit it measured. Availability of `--template` is exercised with local readers with and
without the option, so the comparison tests require no older installation. XML is read in
UTF-8, in UTF-16 and in every charset its declaration names by a name the
IANA charset registry gives it -- the table `_REGISTERED` in
`src/aas_submodel_validate/container.py`, Shift_JIS, EUC-KR, GB18030 and
Big5 among them -- and what the report quotes from it comes back as the
characters the file holds, the same on every Python. A name outside the
table is refused, naming the registered one to declare where one can be
named -- from tables, `tools/python_spellings.py` writing the one of
Python's spellings, so a later Python's aliases change no remedy; a
document in UCS-4 or EBCDIC is refused saying which, as aas-core3's own
XML reader refuses it; bytes that are not the charset declared are
refused at the line they are on; and so is a declaration the first
bytes contradict, a byte order mark or UTF-16's shape against another
name, as the parser refuses it.
`python3 -m pytest tests/test_a_document_is_read_in_the_encoding_it_declares.py`
runs the tests that hold it. A JSON document -- which declares no encoding
-- is read as UTF-8.

Before 1.0: every row of the mutation table killed on the tree it ships with, and every name the IANA charset registry gives a charset this reader decodes read without loss -- a document under a name outside that table, or in UCS-4 or EBCDIC, refused saying so.

## Upstream

**The vendored templates are pinned and hash-checked.**

```
vendored material matches its recorded hashes, and the trees hold nothing else (20 files, pin f3790038b6c9)
```

Reproduce: `python3 tools/vendor_template.py --check` in a clone; CI runs it
on every change.

- upstream templates pinned by commit — done
- checked for upstream change — done
- one pin move shipped — done

The pin has moved once: 0.12.0 moved it from `11ef3353`, where it had
stood since 0.1.0, to `f3790038`, and its CHANGELOG entry names every
verdict the move changed.

Whether upstream has moved since is asked every Monday, and on a push that
changes the pin or the check: `.github/workflows/upstream.yml` runs
`tools/upstream_moved.py`, which asks of each folder a vendored file comes
from -- a template's folder, every edition in it -- whether it is still the
tree it was at the pin. A red run there is not a defect here: exit 1 names
the folders that moved and what changed in them, a decision to make about
the pin, and exit 2 says upstream did not answer.
`python3 -m pytest tests/test_the_templates_upstream_are_watched.py` runs
the tests that hold it, with no network.

Before 1.0: a scheduled check that notices when the upstream templates move,
and one release that moved the pin and said what the move changed.

The same six facts as a table: [`docs/capabilities.md`](capabilities.md).
