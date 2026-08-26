"""X rules: the way in, reported one stage at a time.

The loader records what broke as staged data (zip / chain / payload);
each stage has exactly one voice here, so a report never says the same
broken file three ways.
"""
from __future__ import annotations

from ..container import MAX_PART_BYTES, MAX_TOTAL_PART_BYTES
from ..model import Violation
from ..registry import rule

#: What X5 says to an input that is not a container. Absent means the
#: rule's standing advice, which is the container's: it names a part to
#: send and a container to split, and an author who sent neither is being
#: told to do something they cannot.
#:
#: Keyed by the form the loader started with, not the one it decided,
#: because the bound is applied before the branch that decides -- so a
#: form added later cannot arrive without a bound by being added on the
#: wrong side of that question. The consequence is that `.json` here
#: could still be either an environment or a bare Submodel, and the
#: sentence says both rather than guessing about a document this reader
#: has just declined to read.
_ONE_DOCUMENT = "This reader takes in no single document over %d MiB." % (
    MAX_PART_BYTES // 1024 ** 2)
_NOT_YOUR_FAULT = "Nothing is wrong with what you sent; it was refused, not judged."

_BOUNDS_REMEDY = {
    "environment-json": "%s An environment divides along its submodels, so "
                        "fewer of them per file is the way through; one "
                        "Submodel on its own does not divide, and a file that "
                        "large cannot be checked here. %s"
                        % (_ONE_DOCUMENT, _NOT_YOUR_FAULT),
    "environment-xml": "%s An environment divides along its submodels, so "
                       "fewer of them per file is the way through. %s"
                       % (_ONE_DOCUMENT, _NOT_YOUR_FAULT),
}


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
      fix="Open the named document and fix the syntax its parser rejects; "
          "the extension decides the format (.json as AAS JSON, otherwise AAS "
          "XML). Packaged or bare: a part of a container and a file on its "
          "own reach this the same way.")
def x3_payload_parses(ctx):
    for error in ctx.loaded.errors:
        if error.stage == "payload":
            yield Violation(error.message, subject=error.subject, detail=error.detail)


@rule("X5", kind="container", prio="MUST",
      title="the input fits in what an offline reader will take in",
      spec="this project's own bounds -- see container.py",
      fix="This reader takes in no single document over %d MiB, and no "
          "container whose parts come to over %d MiB together. Nothing is "
          "wrong with what you sent; it was refused, not judged. Where the "
          "input is a container, send the part that needs checking on its "
          "own or split the container."
          % (MAX_PART_BYTES // 1024 ** 2, MAX_TOTAL_PART_BYTES // 1024 ** 2))
def x5_within_the_readers_bounds(ctx):
    """Not a defect in the file, which is why it is not X1.

    X1 tells an author to re-create the archive, and there is nothing
    here to re-create. Refusing to read is this tool's decision, and a
    finding that reports somebody else's decision as the author's fault
    is the kind of remedy this project promised not to write.

    Which is also why the remedy is per-input. "Send the part", "split
    the container": a bare document has neither, and a single Submodel
    has no split at all -- telling its author to divide it is the same
    mistake in a smaller place.
    """
    for error in ctx.loaded.errors:
        if error.stage == "bounds":
            yield Violation(error.message, subject=error.subject, detail=error.detail,
                            fix=_BOUNDS_REMEDY.get(ctx.loaded.form))


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
            # A spec part with no relationships declares nothing. A part
            # whose relationships could not be read is a container defect,
            # and the loader has already reported it as one -- X4 has no
            # true remedy for it and must not invent one.
            continue
        for rel_type, target in relationships:
            # `target` came back from the container already normalised;
            # asking through the same entry point as HD-D7 keeps the two
            # rules from ever disagreeing about what a name means.
            if rel_type == SUPPL_REL and container.part(target) is None:
                yield Violation("an aas-suppl relationship names a part the "
                                "archive does not hold", subject=target)
