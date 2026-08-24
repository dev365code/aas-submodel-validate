# Contributing

## Certify your commits (DCO)

Every commit needs a sign-off line:

```
Signed-off-by: Your Name <you@example.com>
```

`git commit -s` writes it for you; `git commit --amend -s` repairs a
forgotten one. The line certifies the [Developer Certificate of
Origin 1.1](https://developercertificate.org/) — that you wrote the change
or otherwise have the right to submit it under this project's licence. That
is the whole deal: you keep your copyright, your contribution arrives under
Apache-2.0 like everything here (inbound = outbound), and the project keeps
a provenance trail it can show anyone who asks — which, for a tool courting
a standards body, someone eventually will. There is no CLA and no paperwork;
a certificate of origin is a statement of fact, not a transfer of rights.

Pull requests are checked for the line automatically.

The certificate, verbatim:

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

## Adding a rule

A rule is born red: commit a fixture that violates it and one that does
not, watch the violation test fail, then implement. Every rule carries a
`fix` sentence — what to change so the finding stops being reported, not
the requirement restated in the imperative — and every rule id must fire
somewhere in the suite. Match by semanticId, never by idShort
(docs/divergences.md explains why, with the template's own words).
