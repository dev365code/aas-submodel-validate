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

Each index records identifiers, section references, quotations and the
cardinality or applicability the source itself states, pinned to the sha256 of
the exact file it was read from — see `sources.sha256`, which also gives the
address each file can be fetched from again.

**These are indexes, not copies — but they are not thin, and an earlier version
of this paragraph said they were.** Measured against the pinned bytes: the
guidance table has 71 rows and this carries 71 records, holding about
three-fifths of the characters on its table pages; the longlist has 100 rows
and this carries 100 records, whose longest single quotation runs to about
1,300 characters. What does not travel is the layout, the surrounding prose,
the source's own front matter — and, from the longlist, the column of wording
attributed to a separately published specification, which the extractor does
not read. Where a reading matters, follow the address in `sources.sha256` and
read it there.

**The tools in `tools/` do more than parse, and an earlier version of this
paragraph denied it.** Each one turns wording into a `mandatory` value the
source does not state in those terms: a keyword in a provision, a cardinality
of `ZeroToOne`, an instruction not to fill a field because the same data is
required elsewhere. Those readings are the part of this most likely to be
wrong, so they are not spread around — each extractor keeps them in one
function and one table, named so they can be found and argued with. Where a
source states an obligation but qualifies it, the record says `conditional`
and carries the qualifier; where a source genuinely does not say, it says
`unclear`, and the unclear ones are counted. The annex index carries none:
Annex XIII opens "A battery passport shall include the following
information", so every point under it is required and what a qualifier does
is narrow it.

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
