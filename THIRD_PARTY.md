# Third-party material

## Vendored: IDTA official template and example (CC BY 4.0)

| file | what it is | modified? |
|---|---|---|
| `aas_submodel_validate/data/smt/02004/2.0.1/template.json` | IDTA 02004-2-0-1 *Handover Documentation* template | no |
| `aas_submodel_validate/data/smt/02003/2.0.1/template.json` | IDTA 02003 2.0.1 *Technical Data* template | no |
| `aas_submodel_validate/data/smt/02035-2/1.0/template.json` | IDTA 02035-2 1.0 *Digital Battery Passport, part 2 — Handover Documentation* template | no |
| `tests/corpus/idta/02004/example.json` | official 02004 2.0 example (environment JSON) | no |
| `aas_submodel_validate/data/example/idta-02004-2.0.aasx` | official 02004 2.0 example (AASX) — ships in the wheel, and `smtv --example` judges it | no |
| `tests/corpus/idta/02003/sample-2.0.json` | official 02003 2.0 sample (environment JSON) | no |
| `tests/corpus/idta/02003/sample-2.0.aasx` | official 02003 2.0 sample (AASX) | no |
| `tests/corpus/idta/02003/sample-2.0.1.aasx` | official 02003 2.0.1 sample (AASX) — upstream's own repair of the one above | no |

Source: [admin-shell-io/submodel-templates](https://github.com/admin-shell-io/submodel-templates),
licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), © IDTA
and contributors. Taken from commit `11ef3353124626e2dba4cb50767024df9a39928a` and
hash-verified on every CI run by `tools/vendor_template.py --check`,
which also sweeps those trees for anything this table does not list. The
SHA-256 digest of each file is recorded in a `sha256sums.txt` in its own
directory. The `aas_submodel_validate/` rows are addressed as an
installed package addresses them; this repository keeps those under
`src/`. The `tests/corpus/` rows are in the source distribution only,
and are spelled as that distribution holds them. `--refresh` is the only operation that
touches the network.

The template files are the *generator input* for the structural rule
tables (`rules/hd_tables.py`, `rules/td_tables.py`, `rules/dbp_tables.py`
— one table per template, one generator); the examples are test corpus — including their
defects, which are pinned by name in the suite rather than repaired.

02035-2 shares 02004's submodel identifier, so the two are measured
against each other rather than told apart by it: `--profile` chooses
which answers and `SMT-D2` reports the choice.

## Runtime dependency

[aas-core3.0](https://github.com/aas-core-works/aas-core3.0-python)
(MIT) — metamodel types, JSON/XML de/serialisation, and the verification
this project reports in its `meta` channel.

## Battery-passport requirements indexes

`data/battery-passport/` holds indexes derived from four canonical
sources -- EU Regulation 2023/1542 Annex XIII (EUR-Lex consolidated
text), the Commission's data-point guidance, the Battery Pass
consortium's attribute long list (CC BY 4.0), and IDTA 02035/02099
submodel templates (CC BY 4.0). The sources are not mirrored here; each
is pinned by URL and sha256 in `data/battery-passport/sources.sha256`,
and the bundle's own `README.md` carries the per-source attribution.

Two pins of IDTA 02004 live in this repository and they are different
files on purpose: this tool vendors and validates against **02004
version 2.0.1** (the table above), while the battery bundle indexes
**02004 V2.0** -- the edition the battery-passport template series
references. Same document family, different editions, legitimately
different hashes.

