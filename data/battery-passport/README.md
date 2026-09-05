# Battery passport requirement indexes

**Attribution, licences and the disclaimers each source asks to travel with
its material are in [`NOTICE.md`](NOTICE.md) beside this file. Read it before
reusing anything here: three of the four sources are CC BY 4.0, and one of
them is a consolidated text that says of itself that it has no legal effect.**

Machine-readable indexes of what an EU battery passport must contain, derived
from four canonical sources and joined so the same obligation can be followed
across all four: Regulation (EU) 2023/1542 Annex XIII (consolidated text
02023R1542-20250731), the European Commission's guidance table *Digital
Batteries Passport – data points by category* v2.0 (CC BY 4.0), the Battery Pass
data attribute longlist v1.3 (CC BY 4.0), and the IDTA Digital Battery Passport
submodel templates 02035-1 to -7 with 02099-1 (CC BY 4.0).

Nothing here mirrors a source document. Each index records identifiers, section
references, short quotations and the cardinality or applicability the source
itself states, pinned to the sha256 of the exact file it was read from — see
`sources.sha256`, which also gives the address each file can be fetched from
again. The tools in `tools/` parse; they do not judge. Where a source does not
state whether something is required, the record says `unclear` and the unclear
ones are counted.

**Coverage figures in `requirements-join.md` are a floor, not a measurement.**
The submodel templates carry no citation of the law, so a template element can
only be matched to an attribute by name, and name matching misses more than it
finds. `divergences-public.md` lists the places where the four sources do not
agree, as observations rather than verdicts.

**Regenerating:** fetch the files listed in `sources.sha256` into a local
`sources/` directory, verify them with
`cd sources && grep -v '^#' ../sources.sha256 | shasum -a 256 -c`, then run the
five commands in `tools/REGENERATE.txt`. The output is byte-for-byte
reproducible: same source bytes, same index bytes, with no timestamp, path or
machine name in any of them.
