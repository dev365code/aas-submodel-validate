# Security

Report vulnerabilities via GitHub's private reporting on this repository.

The validator's own attack surface is the files it reads: AASX (ZIP/OPC)
containers and AAS JSON/XML from arbitrary suppliers. Inputs are treated
as hostile — parsing failures become findings, not crashes, and the test
suite carries deliberately broken containers and documents. What this
reader takes in is bounded: one document at 64 MiB, and a container's
parts at 64 MiB each and 256 MiB together — so a container may deliver
four times what a bare document may. The total is asked of what has been
read so far, before each next part is decompressed -- so a container
stops costing once it is past the bound, having read the part that
crossed it: the ceiling in practice is the bound plus one part, and what
it buys is that the cost cannot keep growing. A part counts once however
many relationships name it.

`--template` reads a **second** file, and it is bounded separately
because it is a separate file: the same 64 MiB, and additionally a limit
of ten thousand rows on what the template may declare. The row limit is
not decoration. Bytes do not bound the work a template costs — rows do,
and a template of 46 MiB sits comfortably inside the byte bound while
declaring far more rows than anything published. A template above the byte
limit is refused before it is read; one above the row limit is refused
at the row that crosses it, so what a template can cost is bounded by
ten thousand rows rather than by its size. Both leave at the exit code
that means the input could not be judged. A container's directory
of names is bounded too, at 16 MiB, and separately: a ZIP is indexed
whole before any of it is read, so the cost falls on how many names the
archive declares rather than on what its entries hold — an archive of
800,000 empty entries weighed 69 MiB on disk and 523 MiB in memory, and
was otherwise perfectly conformant. What the bound does not cover: the
memory a parse then costs, which is a multiple of the bytes read. What it
refuses to read, it does not judge, and the report says so; where
nothing could be judged, the run leaves by the could-not-run exit code
rather than reporting a verdict it does not have. Validation performs no network access.

A security fix that shipped in a release has a GitHub security advisory on
this repository, naming the versions it reaches and the release that fixes it:

- [GHSA-m8g8-xjhr-x529](https://github.com/dev365code/aas-submodel-validate/security/advisories/GHSA-m8g8-xjhr-x529):
  a DTD refused at any smaller size could be processed in an oversized UTF-16
  relationships part. 0.1.3 and 0.1.4; fixed in 0.1.5.
