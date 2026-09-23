# What it catches

Eight things this tool says, each one shown as the tool says it. Every
case on this page is a command you can run and a file you can paste; the
sentences quoted are the sentences printed, and a test runs each of them
and fails when they drift.

Nothing here compares this tool to another one. What it does is describe
what this one answers, and where each answer is read from.

| # | The question | The rule | Run it against |
|---|---|---|---|
| 1 | Is it the submodel it claims to be? | `SMT-D1` | a file you paste |
| 2 | Does it carry the elements the template requires? | `DN-E02` | a file you paste |
| 3 | Is a value one the specification names? | `HD-D6` | the published example |
| 4 | Does an identifier match, or only nearly? | `HDL2`, `HDL5` | the published example |
| 5 | Does the document carry what the specification asks for? | `HD-D10` | the published example |
| 6 | Is the package one a reader can open? | `X1` | two shell lines |
| 7 | Does the law expect more than the template does? | `BAT-R8` | a file you paste |
| 8 | Is the file well formed at all? | relayed, never re-implemented | the published example |

---

## 1 · Is it the submodel it claims to be?

A submodel carries a `semanticId` saying which template it follows. When
that identifier is not one this tool holds a table for, nothing here has
judged the file, and the report says so rather than passing it.

```json
{
  "submodels": [
    {
      "modelType": "Submodel",
      "id": "urn:example:mine:1",
      "idShort": "MySubmodel",
      "semanticId": {
        "type": "ExternalReference",
        "keys": [{"type": "GlobalReference", "value": "urn:example:my-own-template"}]
      },
      "submodelElements": []
    }
  ]
}
```

```sh
smtv unknown-claim.json
```

> `error   SMT-D1   no submodel declares a semanticId this tool has a template table for`

The summary line ends `judged 0 of 1 submodel`, and the exit code is 1.
This is not a claim that the file is wrong — it is a claim that nothing
here looked at it. The `fix` lists the identifiers that do have a table,
and says in as many words that a submodel of a template this tool has no
table for should keep the identifier it has.

**Read from**: IDTA 02004-2-0 §2.4, Table 2; IDTA 02003-2-0-1 §2.

---

## 2 · Does it carry the elements the template requires?

Most of what this tool knows is generated from the published template
files: which elements, of which kind, under which identifiers, and how
many of each. A Digital Nameplate that declares the template and carries
one of its mandatory elements is missing the rest.

```json
{
  "submodels": [
    {
      "modelType": "Submodel",
      "id": "urn:example:nameplate:1",
      "idShort": "Nameplate",
      "semanticId": {
        "type": "ExternalReference",
        "keys": [{"type": "GlobalReference",
                  "value": "https://admin-shell.io/idta/nameplate/3/0/Nameplate"}]
      },
      "submodelElements": [
        {"modelType": "Property", "idShort": "URIOfTheProduct",
         "valueType": "xs:anyURI",
         "semanticId": {"type": "ExternalReference",
                        "keys": [{"type": "GlobalReference",
                                  "value": "0112/2///61987#ABN590#002"}]},
         "value": "https://example.com/p/1"}
      ]
    }
  ]
}
```

```sh
smtv nameplate-missing.json
```

> `error   DN-E02   the template expects exactly one 'ManufacturerName' here; found 0`

Four errors, one per mandatory element the file does not carry, each
naming the element and the `semanticId` it must be given. The count is
read from the template's own cardinality qualifier, not from a list
written by hand here.

**Read from**: the IDTA 02006-3-0 template file, `SMT/Cardinality`
qualifier.

---

## 3 · Is a value one the specification names?

IDTA's own published 02004 example ships inside this package,
unmodified. It carries a `StatusValue` of `released`, and the
specification names two values.

```sh
smtv --example
```

> `warning HD-D6    StatusValue is outside the vocabulary`

The finding shows `saw 'released'` and five places it appears. It is a
warning and not an error because the vendored concept description
introduces the two values with *should be used* — the severity follows
the specification's own verb.

**Read from**: IDTA 02004-2-0 §2.8.

---

## 4 · Does an identifier match, or only nearly?

Two ways of being close without being right, both in the same published
example.

```sh
smtv --example
```

> `warning HDL2     semanticId almost matches the template`

> `warning HDL5     ClassificationSystem spells the VDI system non-canonically`

The first shows the pair: the file says
`…/vdi/2770/1/0/EntityForDocumentation` where the template says
`EntitiesForDocumentation`. An element whose identifier has drifted
matches no row, so it is never descended into and its mandatory children
are never asked for — which is why the drift itself is reported, and why
the summary line names the rules the run did not ask.

The second is about a value rather than an identifier: `VDI2770:2020`
names the mandatory classification system in a spelling other tools
matching on the specified string will not recognise.

**Read from**: this project's matching policy (`docs/divergences.md`)
for the first; IDTA 02004-2-0 §2.3 for the second.

---

## 5 · Does the document carry what the specification asks for?

A rule can ask about the documents a submodel points at, not only about
the elements it declares.

```sh
smtv --example
```

> `warning HD-D10   no DigitalFile is a PDF; VDI 2770 requires a PDF/A rendition`

`saw content types present: application/step`. It is a warning because a
content type cannot prove PDF/A conformance — the finding says that in
its own `fix`, rather than leaving the reader to wonder why it was not an
error.

**Read from**: IDTA 02004-2-0 §2.1.

---

## 6 · Is the package one a reader can open?

An `.aasx` is an OPC container. Before any template question can be
asked, the container has to open and its relationship chain has to reach
a payload.

```sh
printf 'this is not a zip' > broken.aasx
smtv broken.aasx
```

> `error   X1       cannot open broken.aasx as a ZIP container: BadZipFile: File is not a zip file`

The exit code is 2 — *could not judge this input* — and not the 1 that
means a verdict was reached. The summary says `not a full verdict: some
of it was not judged`, because a reader that cannot open the package has
not disagreed with it.

**Read from**: ECMA-376 Part 2.

---

## 7 · Does the law expect more than the template does?

For the battery passport, and only there, this tool also reports where a
published reading of Regulation (EU) 2023/1542 expects an element the
IDTA template leaves optional. The file below is conformant to its
template and still draws a finding.

```json
{
  "submodels": [
    {
      "modelType": "Submodel",
      "id": "urn:example:battery:technical-data",
      "idShort": "TechnicalData",
      "semanticId": {
        "type": "ExternalReference",
        "keys": [{"type": "GlobalReference",
                  "value": "https://admin-shell.io/idta/digitalbatterypassport/TechnicalData/1/0"}]
      },
      "submodelElements": [
        {"modelType": "SubmodelElementCollection", "idShort": "GeneralInformation",
         "semanticId": {"type": "ExternalReference",
                        "keys": [{"type": "GlobalReference",
                                  "value": "urn:samm:io.admin-shell.idta.batterypass.technical_data:1.0.0#generalInformation"}]},
         "value": [
           {"modelType": "Property", "idShort": "BatteryCategory",
            "valueType": "xs:string",
            "semanticId": {"type": "ExternalReference",
                           "keys": [{"type": "GlobalReference",
                                     "value": "urn:samm:io.admin-shell.idta.batterypass.technical_data:1.0.0#batteryCategory"}]},
            "value": "lmt"}
         ]}
      ]
    }
  ]
}
```

```sh
smtv battery-lmt.json
```

> `warning BAT-R8   conformant to the template; a published reading of the regulation expects it for LMT batteries: 'CapacityFade' is absent`

The finding names *whose* reading it answers for, and the exit code is 0:
the file passes, and the note stands beside the pass rather than
overturning it. Which elements are asked depends on the category the file
itself declares — a passport declaring `ev` is asked a different set, and
one declaring none is asked none and told so.

**Read from**: Regulation (EU) 2023/1542 Annex XIII 4 (a), Annex IV Part
A (1), Annex IV (2); `docs/divergences.md` #37 records whose reading of
it this answers.

---

## 8 · Is the file well formed at all?

Whether a file satisfies the AAS metamodel is a different question from
whether it is the submodel it claims to be, and this project does not
re-implement the first. It relays it.

```sh
smtv --example
```

> `findings relayed from aas-core3.0 about the metamodel, upstream of any template (--show-meta lists them)`

The count is left out of this page on purpose: it belongs to the
dependency and moves when the dependency does, and a number printed here
would be a claim this project cannot keep. By default they are
summarised in that one line and do not move the exit code,
because a file can be worth judging against a template while its
metamodel channel is noisy. `--strict-meta` promotes them; when it does,
the exit code changed because the policy changed, not because the file
did.

**Read from**: [aas-core3.0](https://github.com/aas-core-works/aas-core3.0-python),
reported in its own channel.
