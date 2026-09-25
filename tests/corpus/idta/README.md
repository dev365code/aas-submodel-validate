# Official IDTA material as test corpus

One directory per template, holding the published examples unmodified,
vendored under CC BY 4.0 (© IDTA and contributors — see THIRD_PARTY.md
for the upstream revision; each
directory's `sha256sums.txt` has the digests).

- `02004/` — the 2.0 Handover Documentation example as JSON. The AASX
  form of it ships in the package, under `data/example/`, because
  `smtv --example` judges it.
- `02003/` — the Technical Data sample, published twice: beside the 2.0
  template and again beside 2.0.1. The second is upstream's own repair of
  the first, and keeping both is what makes it evidence rather than a
  version bump.
- `02006/` — the 2.0 Digital Nameplate sample, an AAS 2.0 package that
  upstream has since moved under `deprecated/`.
- In `02004/` and `02003/`, the files upstream publishes beside 2.0.1 a
  second time, "for AAS metamodel V3.1", in the
  `https://admin-shell.io/aas/3/1` namespace. The 02004 one is a template
  (`kind: Template`), whatever its name says.

Those last three are refused rather than judged -- this reader follows
the 3.0 package relationships and parses metamodel 3.0 -- and they are
kept for the refusal: they are what someone downloading IDTA's current
material meets first, and the suite pins each beside a mutation of
itself that isolates why, so a change that moved one for another reason
fails.

They are here *with their defects*: the suite pins what this validator
reports against them by name, because the published reference material
is exactly the input a real-world tool meets first, and because upstream
repairs on its own schedule — a corpus that quietly tracked those
repairs would stop being a witness to them. Repaired variants used as
passing fixtures are built in the tests, with each repair named.
