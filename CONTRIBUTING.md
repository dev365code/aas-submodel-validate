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
the requirement restated in the imperative — and every rule id this
project publishes must fire somewhere in the suite. The ids a
`--template` run makes are the exception and are kept out of that
accounting deliberately: they exist because somebody passed a file, they
are not registered, and `make exercised` asks about this project's own
rules against a baseline listing exactly those. Match by semanticId, never by idShort
(docs/divergences.md explains why, with the template's own words).

## Adding a gate

A rule is born red, and so is a gate. A check under `tools/` or a
property under `tests/` is a claim that something cannot go wrong
unnoticed, and the only evidence for that claim is a state of the tree
where it says so.

So break the thing it watches, deliberately, and watch it fail. Not
reread it — break it. Corrupt the file, drop the record, revert the
repair, and run the gate. Then put it back.

This is written down because four guards here were green and asked
nothing:

- a test asserting `"83" in table` against a whole document, satisfied
  by two characters inside a hash — every mention of what it was
  checking could be deleted and it passed;
- a comparison of two versions across thirty-two inputs, none of which
  could tell the two apart, reporting no differences with confidence;
- a mutation written to prove a guard, comparing an enum against a
  string, so it changed nothing and the guard was never tested;
- an exemption granted by filename to the one member of a distribution
  that becomes an executable on your PATH.

Every one was found by corrupting an input. None would have been found
by reading the code, and all four had been read.

A gate that has never been red is a comment.

## The time budget

`make check` times five layers and compares each against a ratio recorded
in `docs/time-budget.json`. Half again as expensive is said out loud; twice
is a failure.

Five, because each sees something the others cannot:

- **`cold_start`** runs the command in a fresh interpreter, and is the only
  figure that is the time a person actually waits. The others import the
  package before the clock starts and then repeat a warm call, so work done
  at import measures as zero in them -- an index built at import made the
  command more than twice as slow and left every other layer unmoved.
- **`corpus_pass`** judges *and renders* every input the corpus holds.
- **`scale`** is one wide submodel, because the corpus cannot do this job:
  its largest scope holds fifteen elements, so anything superlinear in
  siblings barely moves it. A pairwise comparison added to the walk read
  1.0x on the corpus and 4.4x here.
- **`rules_layer`** is the walk alone, the layer with a cost history.
- **`supplied_template`** is one `--template` run: the only layer that
  times building a table while the caller waits. The four above run
  against tables generated at build time from small vendored files, so
  the build cost is in none of them, and the walk they time asks its
  questions once per pack where a supplied table asks them once per row
  of a file the caller chose.

The seconds are compared as well as the ratios, in one direction: a layer
whose absolute time falls to a fifth of what was recorded has stopped doing
its work, and no ratio can tell that from a fast machine.

Seconds are not the budget. Every figure is a ratio against a yardstick
measured in the same pass, immediately beside the layer it divides, so a
slow machine does not fail. The ratio does not travel between operating
systems either, so each carries its own entry and a platform with no entry
passes quietly, saying so -- there is no way to write a budget for a
machine before a run on it.

What this catches and what it does not, plainly: run-to-run spread on an
idle machine is about 11% on the corpus and 6% on the rules layer, and the
failure line is at twice the budget. So it catches a layer that doubled,
not a layer that got a fifth slower. It is a smoke alarm for the kind of
regression that ships and then has to be apologised for -- the walk here
was quadratic once, correct the whole time, and what noticed was a person
waiting -- and it is not a benchmark. Something genuinely slower but under
the line goes through, and that is the deliberate cost of a gate that does
not fire on runner noise.

If a change makes a layer genuinely more expensive and that is the right
trade, run `python tools/time_budget.py --record` on an idle machine,
about a dozen times, and write in a run close to the middle with a note
giving the peak-to-peak spread and how many runs it came from. A standard
deviation of three samples reads reassuringly and hides what a reader
actually meets; recording one hurried run, or the fastest of several, is
how a budget ends up warning on ordinary work.
