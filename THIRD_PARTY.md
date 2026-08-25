# Third-party material

## Vendored: IDTA official template and example (CC BY 4.0)

| file | what it is | modified? |
|---|---|---|
| `src/aas_submodel_validate/data/smt/02004/2.0.1/template.json` | IDTA 02004-2-0-1 *Handover Documentation* template | no |
| `src/aas_submodel_validate/data/smt/02003/2.0.1/template.json` | IDTA 02003 2.0.1 *Technical Data* template | no |
| `src/aas_submodel_validate/data/smt/02035-2/1.0/template.json` | IDTA 02035-2 1.0 *Digital Battery Passport, part 2 — Handover Documentation* template | no |
| `tests/corpus/idta/02004/example.json` | official 02004 2.0 example (environment JSON) | no |
| `tests/corpus/idta/02004/example.aasx` | official 02004 2.0 example (AASX) | no |
| `tests/corpus/idta/02003/sample-2.0.json` | official 02003 2.0 sample (environment JSON) | no |
| `tests/corpus/idta/02003/sample-2.0.aasx` | official 02003 2.0 sample (AASX) | no |
| `tests/corpus/idta/02003/sample-2.0.1.aasx` | official 02003 2.0.1 sample (AASX) — upstream's own repair of the one above | no |

Source: [admin-shell-io/submodel-templates](https://github.com/admin-shell-io/submodel-templates),
licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), © IDTA
and contributors. Pinned to one commit and hash-verified on every CI run
by `tools/vendor_template.py --check`, which also sweeps those trees for
anything this table does not list; the pin and the recorded SHA-256
digests live beside the files. `--refresh` is the only operation that
touches the network.

The template files are the *generator input* for the structural rule
tables (`rules/hd_tables.py`, `rules/td_tables.py`, `rules/dbp_tables.py`
— one table per template, one generator); the examples are test corpus — including their
defects, which are pinned by name in the suite rather than repaired.

02035-2 is vendored and tabulated ahead of the rules that will judge by
it: it is here to be measured against 02004, whose submodel identifier it
shares. No rule is generated from its rows; one rule reads the table to
compare the two (`SMT-D2`, which names 02035-2 when a submodel declares
its profile), and 02004 is still what answers for such a file.

## Runtime dependency

[aas-core3.0](https://github.com/aas-core-works/aas-core3.0-python)
(MIT) — metamodel types, JSON/XML de/serialisation, and the verification
this project reports in its `meta` channel.
