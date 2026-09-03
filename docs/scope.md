# Scope

What this project is: an offline conformance validator for AAS submodel
template instances. Files in, findings out, a remedy sentence on every
finding.

## What it is not

- **Not a metamodel validator.** aas-core3.0's verification runs here
  and its findings are reported (the `meta` channel), but no AASd/AASc
  constraint is ever re-implemented as a rule of this project. The
  official test tooling for the metamodel, serialisation and APIs is
  admin-shell-io/aas-test-engines; duplicating it would be waste on our
  side and noise on theirs.
- **Not an AAS server, client or API test bench.** Files in, findings out.
- **Not a template authoring or editing tool.** It reads the official
  templates; it never writes one.
- **Not a converter.** AASX, XML and JSON are read; nothing is
  transformed, migrated or re-serialised as a product feature.
- **Not a Digital Product Passport platform.** IDTA 02035-2 is judged as
  what it is measured to be — a profile of the Handover Documentation
  template, twenty-two of its thirty-eight rows with two relaxed — and
  nothing more. `--profile` says which of the two answers, and the
  report says which answered whenever there was a choice to make. No DPP
  registry, no passport identifier resolution, no certificate of
  compliance with Regulation (EU) 2023/1542. This project is the
  submodel-conformance layer.
- **It does say where a template and the regulation disagree, and only
  that.** `BAT-R8` reports an element the template permits to be absent
  that a published legal reading requires, and says both halves in those
  words. It reports the disagreement, not a verdict on the battery:
  reading a category, deciding which applicability date applies, or
  concluding that a passport is compliant are all outside this. Of nine
  such disagreements it knows, it reports the one that does not depend on
  the battery's category, and its coverage note says so.
- **Not a certifier, and not a fixer.** It reports findings and names
  the remedy for each; deciding what a file was meant to say is the
  author's job. No `--fix`, no conformance certificates.
- **Not an unpacked-AASX checker (yet).** OPC relationship semantics on
  a loose directory are ambiguous; refused until a real need defines
  them.

**Deferred, not rejected**: IIFU composition — detecting an iiRDS
Information for Use submodel and handing its iiRDS payload to
iirds-validate, so the two standards' validators compose.
