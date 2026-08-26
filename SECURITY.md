# Security

Report vulnerabilities via GitHub's private reporting on this repository.

The validator's own attack surface is the files it reads: AASX (ZIP/OPC)
containers and AAS JSON/XML from arbitrary suppliers. Inputs are treated
as hostile — parsing failures become findings, not crashes, and the test
suite carries deliberately broken containers and documents. How much of
a file this reader will take in is bounded the same way whether it
arrives packaged or bare; what it refuses to read, it does not judge.
Validation performs no network access.
