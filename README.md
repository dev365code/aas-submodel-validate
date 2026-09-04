# aas-submodel-validate

**Template-conformance checking for AAS submodels — offline.**

An [Asset Administration Shell](https://industrialdigitaltwin.org/) file
can be perfectly valid against the AAS metamodel and still not be the
submodel it claims to be: the wrong cardinalities, the wrong semantic
identifiers, a mandatory VDI 2770 classification missing. This tool
checks a submodel instance against its IDTA template — starting with
[IDTA 02004 *Handover Documentation* 2.0](https://industrialdigitaltwin.org/en/content-hub/submodels)
— from the command line, on a machine with no internet connection, as a
step in a build.

```sh
pip3 install aas-submodel-validate
smtv --example              # IDTA's own published example, carried in the package
smtv your-submodel.aasx
```

The second line needs no file of your own, no clone and no network: the
example IDTA publishes travels in the wheel, under the same CC BY 4.0
licence as the templates beside it (see `NOTICE`). It is unmodified,
defects and all — it raises findings, which is the point of shipping
that one rather than a clean file written to pass.

If `pip3` is not the spelling on your machine, `python3 -m pip install
aas-submodel-validate` always is. If `smtv` is then *command not found*,
pip printed the directory it installed into — put that on your `PATH`,
or run the tool as `python3 -m aas_submodel_validate`.

**For a machine with no package manager**, build the single file once
where there is a network and carry it:

```sh
python tools/build_zipapp.py            # dist/smtv.pyz, about 220 KB
python dist/smtv.pyz your-submodel.aasx
```

Everything is inside it — this package and its one dependency — and
nothing is compiled, so the same file runs on Linux, macOS and Windows,
and it is an ordinary zip anyone who has to approve it can open and
read. Two builds of one tree are byte-identical, so the hash on a
release page is the hash of the file you carried in.

Reads `.aasx` (OPC containers, XML or JSON payload), AAS environment
`.json`/`.xml`, and bare Submodel `.json`. Exit codes: 0 nothing at error
severity, 1 at least one error, 2 could not run — which covers a path
that cannot be read and an input this reader refused, since nothing about
either was judged. Warnings and info do
not fail a build unless you ask with `-W`. `-f json` writes a versioned
machine-readable report, described in
[docs/report-schema.md](docs/report-schema.md).

### Putting it in a build

    smtv -q -W your-submodel.aasx        # 0 pass, 1 findings, 2 could not run

`-W` fails on this tool's warnings. It leaves the relayed metamodel
channel alone; `--strict-meta` is the flag for that one, because no edit
to your submodel can clear a finding about the metamodel.

Two more that decide exit codes, both for the case where the tool cannot
speak to your file:

- `--allow-unmatched` — an input declaring a submodel identifier this
  tool has no table for is an *error* by default, because silence about
  an unknown file is the one answer a validator must never give. When
  that is expected — a repository where most submodels are of other
  kinds — this makes it a note instead.
- `--require-all-judged` — an environment can hold submodels this tool
  has no business judging, so `judged 1 of 3` is a number rather than a
  finding and the run still exits 0. If your pipeline reads only the exit
  code, this makes partial coverage fail rather than pass quietly.

One dependency
([aas-core3.0](https://github.com/aas-core-works/aas-core3.0-python)),
pure Python, no C extensions. Both wheels fit on a USB stick and
install with `--no-index --find-links`; the single file above needs not
even that.

## What it checks

125 rules, 123 of them across three IDTA templates — 86 generated from the vendored
official template files (cardinality, element kinds, value types,
semantic identifiers at every nesting level), the rest hand-written
where a template file cannot speak. The other two read the battery
passport against Regulation (EU) 2023/1542 rather than against a
template, over IDTA 02035-1, 02035-4 and 02035-5: one names a submodel
identifier that two published templates claim, and one reports an
element a template permits to be absent that a published legal reading
requires — a file can be conformant to the template and not to the law,
and those are different answers. It reports the one such disagreement
that does not depend on the battery's category; eight more are known,
counted in the report, and left unsaid because saying them without the
category would tell one manufacturer to add what another's guidance
forbids. X1, X2 and X4 are about the AASX/OPC
package the submodel arrives in; X3 says a document would not parse,
packaged or bare; and X5 is this reader's own bound on how much it will
take in, whichever way it arrives. One, SMT-D1, asks whether
the input brought a submodel this tool knows at all; and one, SMT-D2,
says which template answered wherever two published templates share one
submodel identifier and something had to choose.

| template | generated | hand-written |
|---|---|---|
| IDTA 02004 Handover Documentation 2.0.1 | 38 | the mandatory VDI 2770 classification and its twelve classes, English class names, the status vocabulary, dates that are dates, files that exist in the container, references that resolve |
| IDTA 02003 Technical Data 2.0.1 | 26 | dates that are dates, files that exist in the container, references that resolve |
| IDTA 02035-2 Digital Battery Passport part 2 1.0 | 22 | 02004's, minus the three whose elements this template drops |

02003 declares open content: §3.5 says the set of suitable semanticIds
is not restricted, so its 36 placeholder elements generate no rules and
a manufacturer's own properties pass without complaint. Near-miss
identifiers are diagnosed rather than silently unmatched, in all three.

IDTA 02035-2 (*Digital Battery Passport*, part 2) publishes IDTA 02004's
submodel identifier and asks for less than it does, so which of the two
answers has to be chosen. Today that choice is the caller's:
`--profile 02035-2` judges by the battery passport's table,
`--profile 02004` by the Handover template's, and without the flag 02004
answers as it always has. Whenever a file declares the profile or the
flag is used, the report says which template answered and counts the
checks the two disagree about — what this run asked that the other would
not, or what it did not ask that the other would (SMT-D2). A plain
02004 file judged as 02004 draws nothing, because there was no choice
to report.

Beside the validator, `data/battery-passport/` publishes machine-readable
indexes of what a battery passport is required to carry -- Annex XIII of
Regulation (EU) 2023/1542, the Commission's data-point guidance, the
Battery Pass long list, and the IDTA 02035/02099 templates -- with a
join across all four whose coverage is stated as a floor. The sources
are pinned by hash, not mirrored; `data/battery-passport/README.md` says
how to rebuild every index from them.

The AAS metamodel itself is relayed from aas-core3.0's verification in
a separate `meta` channel (the JSON field is `kind`) — warnings by
default, folded into one line unless `--show-meta`, `--strict-meta` to
promote — and never re-implemented here.

```text
error   SMT-D1   no submodel declares a semanticId this tool has a template table for
        saw  semanticId value(s): urn:somecompany:docs
        fix: If the submodel means one of the templates this tool has a table for, give it that template's semanticId: 0173-1#01-AHF578#003 for Handover Documentation (IDTA 02004); 0173-1#01-AHX837#002 for Technical Data (IDTA 02003). If it means a template this tool has no table for, leave the identifier alone -- it is doing its job, and this finding only says nothing here judged the submodel against a template.
1 error(s), 0 warning(s), 0 info — machine-docs.json · judged 0 of 1 submodel
```

The sample above is generated by a test and fails the build when it goes
stale; the rule counts (125, 86) are pinned the same way.

## Where this sits

[aas-test-engines](https://github.com/admin-shell-io/aas-test-engines)
is the official conformance tooling for the AAS metamodel,
serialisation, AASX packaging and APIs; as of v1.0.3 its
submodel-template layer covers two templates (Contact Information,
Digital Nameplate). This project is the complementary layer for the
templates it supports, starting with IDTA 02004: does a given submodel
instance conform to the template — cardinality, semantic identifiers,
the VDI 2770 classification rules — with a remedy sentence for every
finding, offline. Metamodel checking is deliberately delegated to
aas-core3.0's verification and reported in a separate channel, never
re-invented here.

What it refuses to do is written down in [docs/scope.md](docs/scope.md);
every chosen reading of the template, with evidence, in
[docs/divergences.md](docs/divergences.md); the shape of the JSON report,
and what its version number promises, in
[docs/report-schema.md](docs/report-schema.md). Where to send a question,
and what makes a report answerable, in [SUPPORT.md](SUPPORT.md).

## Licence

Apache-2.0, © 2026 Wooyong Lee. Contributions need a `Signed-off-by`
line (DCO); see [CONTRIBUTING.md](CONTRIBUTING.md).

This is an unofficial project, not affiliated with or endorsed by IDTA
or the Eclipse BaSyx project. "AAS", "Asset Administration Shell" and
template identifiers are used descriptively.
