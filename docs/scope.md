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
- **Not a Digital Product Passport platform.** IDTA 02035-2 is measured
  against the Handover Documentation template it is a profile of, and a
  submodel declaring that profile is told which template answered
  (`SMT-D2`); judging by 02035-2's own rules is not here yet, and when it
  is it will be that and nothing more. This project is the
  submodel-conformance layer.
- **Not a certifier, and not a fixer.** It reports findings and names
  the remedy for each; deciding what a file was meant to say is the
  author's job. No `--fix`, no conformance certificates.
- **Not an unpacked-AASX checker (yet).** OPC relationship semantics on
  a loose directory are ambiguous; refused until a real need defines
  them.

**Deferred, not rejected**: a `--profile` flag. Which template answers
for a submodel declaring IDTA 02035-2's profile is reported (`SMT-D2`)
and never acted on, because there is one set of rules to act with; a flag
selecting between one thing would be an API promising a second. It
arrives with the rules it selects.

**Deferred, not rejected**: IIFU composition — detecting an iiRDS
Information for Use submodel and handing its iiRDS payload to
iirds-validate, so the two standards' validators compose.
