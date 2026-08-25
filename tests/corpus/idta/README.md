# Official IDTA material as test corpus

One directory per template, holding the published examples unmodified,
vendored under CC BY 4.0 (© IDTA and contributors — see THIRD_PARTY.md
for the pin and hashes).

- `02004/` — the 2.0 Handover Documentation example, as JSON and as AASX.
- `02003/` — the Technical Data sample, published twice: beside the 2.0
  template and again beside 2.0.1. The second is upstream's own repair of
  the first, and keeping both is what makes it evidence rather than a
  version bump.

They are here *with their defects*: the suite pins what this validator
reports against them by name, because the published reference material
is exactly the input a real-world tool meets first, and because upstream
repairs on its own schedule — a corpus that quietly tracked those
repairs would stop being a witness to them. Repaired variants used as
passing fixtures are built in the tests, with each repair named.
