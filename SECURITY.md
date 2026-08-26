# Security

Report vulnerabilities via GitHub's private reporting on this repository.

The validator's own attack surface is the files it reads: AASX (ZIP/OPC)
containers and AAS JSON/XML from arbitrary suppliers. Inputs are treated
as hostile — parsing failures become findings, not crashes, and the test
suite carries deliberately broken containers and documents. What this
reader takes in is bounded: one document at 64 MiB, and a container's
parts at 64 MiB each and 256 MiB together — so a container may deliver
four times what a bare document may. The total is asked before each part
is decompressed, so a container already past it stops costing, and a part
counts once however many relationships name it. A container's directory
of names is bounded too, at 16 MiB, and separately: a ZIP is indexed
whole before any of it is read, so the cost falls on how many names the
archive declares rather than on what its entries hold — an archive of
800,000 empty entries weighed 69 MiB on disk and 523 MiB in memory, and
was otherwise perfectly conformant. What the bound does not cover: the
memory a parse then costs, which is a multiple of the bytes read. What it
refuses to read, it does not judge, the report says so, and the run
leaves by the could-not-run exit code rather than reporting a verdict it
does not have. Validation performs no network access.
