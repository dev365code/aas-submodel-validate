"""X rules: the way in, reported one stage at a time.

The loader records what broke as staged data (zip / chain / payload);
each stage has exactly one voice here, so a report never says the same
broken file three ways.
"""
from __future__ import annotations

from ..model import Violation
from ..registry import rule


@rule("X1", kind="container", prio="MUST",
      title="the file must be a ZIP (OPC) container",
      spec="ECMA-376 Part 2",
      fix="Re-create the .aasx with an AAS packaging tool; what is on disk is not a ZIP archive at all.")
def x1_is_a_zip(ctx):
    for error in ctx.loaded.errors:
        if error.stage == "zip":
            yield Violation(error.message, subject=error.subject, detail=error.detail)


@rule("X2", kind="container", prio="MUST",
      title="the OPC relationship chain must reach an aas-spec payload",
      spec="IDTA 01005 (AASX); ECMA-376 Part 2 §9.3",
      fix="Repair the chain: _rels/.rels names an aasx-origin part, whose own "
          ".rels names the aas-spec payload. AAS packaging tools write this "
          "automatically; hand-built ZIPs almost never do.")
def x2_chain_resolves(ctx):
    for error in ctx.loaded.errors:
        if error.stage == "chain":
            yield Violation(error.message, subject=error.subject, detail=error.detail)


@rule("X3", kind="container", prio="MUST",
      title="the payload must parse as an AAS environment",
      spec="IDTA 01001 (metamodel); 01003 (serialisation)",
      fix="Open the named part and fix the syntax its parser rejects; the "
          "extension decides the format (.json as AAS JSON, otherwise AAS XML).")
def x3_payload_parses(ctx):
    for error in ctx.loaded.errors:
        if error.stage == "payload":
            yield Violation(error.message, subject=error.subject, detail=error.detail)
