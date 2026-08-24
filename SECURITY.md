# Security

Report vulnerabilities via GitHub's private reporting on this repository.

The validator's own attack surface is the files it reads: AASX (ZIP/OPC)
containers and AAS JSON/XML from arbitrary suppliers. Inputs are treated
as hostile — parsing failures become findings, not crashes, and the test
suite carries deliberately broken containers. Validation performs no
network access.
