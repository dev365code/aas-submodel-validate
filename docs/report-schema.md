# The JSON report

`smtv -f json` writes one JSON object to stdout. This is what is in it,
and what the version number at the top of it promises.

One run writes nothing there: `-q`, which asks for the exit code alone.
Exit 2 sometimes does and sometimes does not — an input this reader
refused comes back with a report saying what was refused and what to do
about it, while a path that could not be read at all has no report to
give and leaves only a line on stderr. Both write that line, so read
stdout when it is not empty. A reader that parses it unconditionally
meets its first `JSONDecodeError` on the case it most needs to handle.

```json
{
  "schemaVersion": 1,
  "toolVersion": "0.1.1",
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
    "rulesChecked": 125,
    "complete": true,
    "judged": true,
    "submodelsSeen": 1,
    "submodelsJudged": 1
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
      "spec": "IDTA 02004-2-0 \u00a72.8 (xs:date)"
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
| `path` | string | The input, as it was given on the command line. |
| `ok` | boolean | No finding at `error` severity. `-W` raises the bar for the exit code without changing `ok`, and so does `summary.judged`: a run that judged nothing exits 2 whatever `ok` says. |
| `options` | object | What was asked of this run; see below. |
| `summary` | object | Counts; see below. |
| `notes` | array of string | Things worth saying once about the run rather than about the file — a `--profile` that named a template nothing here answers to, or an unmatched submodel that `--allow-unmatched` let through. |
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
| `inputSha256` | string or null | SHA-256 of the input file as it arrived — of the bytes on disk, whether or not any of them were judged. A refused input still gets one, and that is the point: the report names the file it refused. `null` only when the file could not be opened at all, or when it is larger than the digest itself will read (256 MiB, the bound on a whole container). |
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
| `complete` | boolean | Whether everything this run was handed got read. `false` means an archive that would not open, a relationship chain that went nowhere, a part that would not parse, or a document over the reader's bound — what was not read was not judged, and a report that only said `ok: false` could not tell you which. |
| `submodelsSeen` | integer | How many submodels the input holds. |
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
| `rule` | string | The rule id — stable, and the thing to filter on. |
| `kind` | string | `container`, `template`, `lint` or `meta`. The prose above calls these *channels*; this field is spelled kind, and a reader who filters on `.channel` gets null for every finding with nothing to say why. |
| `severity` | string | `error`, `warning` or `info` — this project's reading of the priority. |
| `priority` | string | The rule's own priority word, one of `MUST`, `MUST NOT`, `REQUIRED`, `SHALL`, `RECOMMENDED`, `SHOULD`, `MAY` or `OPTIONAL` — the RFC 2119 keywords this project maps to a severity. The set is closed and wider than what today's rules use, so accept all eight. Both fields are published so a consumer that wants to re-derive the severity can. |
| `message` | string | What is wrong. |
| `subject` | string or null | Where: an idShort path, an identifier, or a part name. `null` where the finding is about the document as a whole. |
| `detail` | string or null | Context — usually the value that was seen. |
| `fix` | string | One imperative sentence: what to change so this stops being reported. Every finding carries one. |
| `title` | string | The rule's standing description, the same for every finding it produces. |
| `spec` | string or null | Where the requirement lives: the template and section, or — for a rule that reads a regulation rather than a template — the provision, built from the row being reported rather than fixed per rule. |

`kind` is `meta` for findings relayed from
[aas-core3.0](https://github.com/aas-core-works/aas-core3.0-python)'s
metamodel verification, which this project delegates to and never
re-implements. Those carry the rule id `META`, with the constraint's own
name in the message where aas-core3.0's sentence states one -- not every
sentence does, so match on the rule id, never on the prose.
