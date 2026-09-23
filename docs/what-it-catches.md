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
version 2.0.1, vendored from the commit `THIRD_PARTY.md` names. Reproduce:
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
- IDTA 02011 Hierarchical Structures — not yet
- IDTA 02007 Software Nameplate — not yet

Before 1.0: the two templates named last, by name rather than by count. A
count can be met by whichever templates are easiest; a name says which
documents a reader can bring. After those two, which templates come next
is decided by what people bring (the README's roadmap).

## Explanation

**One finding, whole.** From the bundled example:

```
warning HD-D10   no DigitalFile is a PDF; VDI 2770 requires a PDF/A rendition
        at   HandoverDocumentation/Documents/CADmodel/DocumentVersions/DocumentVersion_URL
        at   HandoverDocumentation/Documents/CADmodel/DocumentVersions/DocumentVersion_file
        saw  content types present: application/step
        per  IDTA 02004-2-0 §2.1 ("PDF/A files are required")
        fix: Add a DigitalFile with contentType application/pdf (a PDF/A file, per VDI 2770) to this DocumentVersion. A content type cannot prove PDF/A conformance, so this is a warning, not an error.
```

What is wrong, in one sentence; where, as a path of `idShort`s; what was
read (`saw`); where the requirement lives (`per` -- a template's clause for
most rules, this project's own documented bounds or matching policy for the
few that are its own); and what to change (`fix`). Reproduce:
`smtv --example`.

- what is wrong, in one sentence — done
- the evidence as read from the file — not yet
- a remedy, for every rule — done
- where each rule's requirement lives — done
- the line in the file — not yet

The evidence is not yet on every finding: on the bundled example all 87
findings carry a place and a remedy, and 10 carry a `saw` line; the other
77 are relayed metamodel findings, which name a path and no value (see the
README). A finding names a path of `idShort`s, not a line of the file --
except a syntax error (`X3`), which carries the parser's line and column.

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
- a golden report held by a test — not yet
- exit codes 0, 1, 2 and 64 under test — done
- a field-by-field schema page — done

Before 1.0: a golden report — a full JSON report of a fixed input, values
included, committed and compared by a test. The keys are held already, in
both directions; what is not held is what they say.

## Entrances

**One judgement, two ways in today.** The command line (`smtv FILE`, or
`aas-submodel-validate FILE`) and a single file that needs nothing but a
Python: `python3 tools/build_zipapp.py` in a clone, then
`python3 dist/smtv.pyz --example` prints the same verdict line as
`smtv --example`. The README's three doors -- a terminal, a single file, a
build -- are two of the five here: a build runs the command line.

- command line — done
- Python library — not yet
- single file, nothing to install — done
- GitHub Action — not yet
- browser, nothing installed — not yet

There is no importable Python API yet; the supported way to call this from
another program is the command and its JSON (see the README).

Before 1.0: all five ways in, each reaching the same verdict on the same
input — the library, a GitHub Action, and a browser page that checks a file
where it is, with nothing installed and nothing uploaded.

## Input safety

**What it reads is bounded, and a refusal is not a verdict.** One document
at 64 MiB, a container's parts at 64 MiB each and 256 MiB together; past a
bound the input is refused, the report says so, and the run leaves by the
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
- tests verified against their own mutations — not yet
- declared encodings read without loss — not yet

From 0.3.0 on, a security fix that ships has an advisory; `SECURITY.md`
names the two earlier repairs that have a changelog entry only. Each gate
names the mistake it stops, and `make mutants` makes each mistake and checks
a test fails (`tools/mutation_table.py` lists them) -- but not yet every
one: two rows about a release that predates `--template` survive, because
their tests can fail only against such a release and the last release has
the option. XML in UTF-8, UTF-16
and the single-byte encodings it declares is read and judged, but UTF-32 is
refused, and a JSON document -- which declares no encoding -- is read as
UTF-8.

Before 1.0: every row of the mutation table killed on the tree it ships with, and every encoding a document may declare, read without loss.

## Upstream

**The vendored templates are pinned and hash-checked.**

```
vendored material matches its recorded hashes, and the trees hold nothing else (11 files, pin 11ef33531246)
```

Reproduce: `python3 tools/vendor_template.py --check` in a clone; CI runs it
on every change.

- upstream templates pinned by commit — done
- checked for upstream change — not yet
- one pin move shipped — not yet

Before 1.0: a scheduled check that notices when the upstream templates move,
and one release that moved the pin and said what the move changed.

The same six facts as a table: [`docs/capabilities.md`](capabilities.md).
