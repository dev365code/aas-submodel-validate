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
counts once however many relationships name it. What the bound does not
cover: the memory a parse then costs, which is a multiple of the bytes
read, and a ZIP's own directory. What it refuses to read, it does not
judge, and the report says so. Validation performs no network access.
