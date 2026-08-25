"""X rules: the way in, reported one stage at a time.

The loader records what broke as staged data (zip / chain / payload);
each stage has exactly one voice here, so a report never says the same
broken file three ways.
"""
from __future__ import annotations

from ..model import Violation
from ..registry import rule


@rule("X1", kind="container", prio="MUST",
      title="the file must be a ZIP (OPC) container this reader can open",
      spec="ECMA-376 Part 2",
      fix="Re-create the .aasx with an AAS packaging tool: either what is on "
          "disk is not a ZIP archive at all, or the archive describes one of "
          "its parts in a way that makes the part unreadable.")
def x1_is_a_zip(ctx):
    for error in ctx.loaded.errors:
        if error.stage == "zip":
            yield Violation(error.message, subject=error.subject, detail=error.detail)


@rule("X2", kind="container", prio="MUST",
      title="the OPC relationship chain must reach an aas-spec payload",
      spec="IDTA 01005 (AASX); ISO/IEC 29500-2 (OPC)",
      fix="Repair the chain: _rels/.rels names an aasx-origin part, whose own "
          ".rels names the aas-spec payload. AAS packaging tools write this "
          "automatically; hand-built ZIPs almost never do.")
def x2_chain_resolves(ctx):
    for error in ctx.loaded.errors:
        if error.stage == "chain":
            yield Violation(error.message, subject=error.subject, detail=error.detail)


@rule("X3", kind="container", prio="MUST",
      title="the payload must parse as an AAS environment",
      spec="IDTA 01001 (metamodel) and its published JSON/XML schemas",
      fix="Open the named part and fix the syntax its parser rejects; the "
          "extension decides the format (.json as AAS JSON, otherwise AAS XML).")
def x3_payload_parses(ctx):
    for error in ctx.loaded.errors:
        if error.stage == "payload":
            yield Violation(error.message, subject=error.subject, detail=error.detail)


@rule("X5", kind="container", prio="MUST",
      title="the container fits in what an offline reader will take in",
      spec="this project's own bounds -- see container.py",
      fix="Send the part that needs checking, or split the container: this "
          "reader refuses a single part over 64 MiB, and a container whose "
          "parts come to over 256 MiB together, so that a machine with no "
          "network cannot be exhausted by a file it was asked to check. "
          "Nothing is wrong with the archive; it is larger than this tool "
          "will read.")
def x5_within_the_readers_bounds(ctx):
    """Not a defect in the file, which is why it is not X1.

    X1 tells an author to re-create the archive, and there is nothing
    here to re-create. Refusing to read is this tool's decision, and a
    finding that reports somebody else's decision as the author's fault
    is the kind of remedy this project promised not to write.
    """
    for error in ctx.loaded.errors:
        if error.stage == "bounds":
            yield Violation(error.message, subject=error.subject, detail=error.detail)


@rule("X4", kind="container", prio="SHOULD",
      title="declared supplementary parts exist",
      spec="IDTA 01005 (AASX, aas-suppl relationships)",
      fix="Add the missing part to the archive or delete the aas-suppl "
          "relationship that names it; a declared file a consumer cannot "
          "extract is a broken promise either way.")
def x4_supplementary_parts_exist(ctx):
    from ..container import SUPPL_REL, ContainerError
    container = ctx.loaded.container
    if container is None:
        return
    try:
        parts = container.spec_parts
    except ContainerError:
        return  # X2's finding; nothing to walk from
    for part in parts:
        try:
            relationships = container.relationships(part)
        except ContainerError:
            continue  # a spec part without its own .rels declares nothing
        for rel_type, target in relationships:
            if rel_type == SUPPL_REL and not container.has(target):
                yield Violation("an aas-suppl relationship names a part the "
                                "archive does not hold", subject=target)
