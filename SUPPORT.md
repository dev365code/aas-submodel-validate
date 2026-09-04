# Support

## Where to ask

Open an issue on this repository. That is the whole channel, and it is
open before there is a release to install — a question about a file this
tool judged wrongly is worth more now than after the reading is frozen
into a version somebody depends on.

If an issue is the wrong shape for what you have — a licensing question,
something you would rather not post, an offer of test material you
cannot make public — write to <zero8004paz@gmail.com> instead.

## What makes a report answerable

The one thing that helps most is **the file**, or a reduced one that
still shows the behaviour. This validator reads only what it is given
and reaches no network, so a file plus a command line is the whole
reproduction:

```
smtv --format json your-file.aasx > report.json
```

The JSON report already carries most of what a report needs: the rule
id, the subject it was about, the remedy that shipped with it, the tool
version, and the flags the run was given. Attach that and the file, and
say what you expected instead.

If the file cannot be shared, the rule id and the subject path are
usually enough to start — several of this project's own corrections
began with somebody describing a shape rather than sending one.

## The two reports worth making

**A finding on a conformant file.** This is the one the project treats
as worst, and every reading it has chosen is written down with its
evidence in [docs/divergences.md](docs/divergences.md) so that
disagreeing with one is a conversation about a document rather than
about taste. If a reading there is wrong, that is a report, and the
ledger row is where the argument goes.

**Silence on a file that is not conformant.** Harder to notice and just
as real. What this project has decided not to check at all is in
[docs/scope.md](docs/scope.md) — if the gap you found is listed there it
is deliberate, and if it is not, it is a bug.

## What is not support

Security issues go through GitHub's private reporting, not an issue:
see [SECURITY.md](SECURITY.md).

Metamodel constraints — the `META` channel — are aas-core3.0's, relayed
here and never re-implemented. A wrong `META` message belongs upstream,
and this project's own bug in that area would be relaying it badly, not
the constraint itself.

The requirements indexes under `data/battery-passport/` are generated
from published sources that this repository pins by hash and does not
mirror; `data/battery-passport/tools/REGENERATE.txt` says how to rebuild
them. A disagreement with an index is a disagreement with its source or
with the extractor, and either is a fine thing to open an issue about.

## What to expect

One maintainer, no service level, and no promise about timing. Issues
are read. A report that includes a file is one somebody can act on
without asking anything first, which in practice is the whole
difference.

Contributions are welcome and need a `Signed-off-by` line; the reasons
are in [CONTRIBUTING.md](CONTRIBUTING.md).
