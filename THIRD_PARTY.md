# Third-party material

## Vendored: IDTA official template and example (CC BY 4.0)

| file | what it is | modified? |
|---|---|---|
| `src/aas_submodel_validate/data/smt/02004/2.0.1/template.json` | IDTA 02004-2-0-1 *Handover Documentation* template | no |
| `tests/corpus/idta/example.json` | official 02004 2.0 example (environment JSON) | no |
| `tests/corpus/idta/example.aasx` | official 02004 2.0 example (AASX) | no |

Source: [admin-shell-io/submodel-templates](https://github.com/admin-shell-io/submodel-templates),
licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), © IDTA
and contributors. Pinned to one commit and hash-verified on every CI run
by `tools/vendor_template.py --check`; the pin and the recorded SHA-256
digests live beside the files. `--refresh` is the only operation that
touches the network.

The template file is the *generator input* for the structural rule table
(`rules/hd_tables.py`); the examples are test corpus — including their
defects, which are pinned by name in the suite rather than repaired.

## Runtime dependency

[aas-core3.0](https://github.com/aas-core-works/aas-core3.0-python)
(MIT) — metamodel types, JSON/XML de/serialisation, and the verification
this project reports in its `meta` channel.
