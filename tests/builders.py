"""Build AASX containers for tests, one deliberate defect at a time.

The chain a real AASX carries (verified against the official IDTA 02004
example): package-level `_rels/.rels` holds an `aasx-origin` relationship
to `/aasx/aasx-origin`, whose own `aasx/_rels/aasx-origin.rels` holds an
`aas-spec` relationship to the payload. Real files write their rels with
a UTF-8 BOM, so the builder can too.
"""
from __future__ import annotations

import zipfile

RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
ORIGIN_REL = "http://admin-shell.io/aasx/relationships/aasx-origin"
SPEC_REL = "http://admin-shell.io/aasx/relationships/aas-spec"

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />'
    '<Default Extension="json" ContentType="application/json" />'
    '<Default Extension="xml" ContentType="text/xml" />'
    "</Types>"
)


def rels(pairs) -> bytes:
    body = "".join('<Relationship Type="%s" Target="%s" Id="R%d" />' % (t, target, i)
                   for i, (t, target) in enumerate(pairs))
    return ('<?xml version="1.0" encoding="utf-8"?><Relationships xmlns="%s">%s</Relationships>'
            % (RELS_NS, body)).encode("utf-8")


def build_aasx(path, payload: bytes = b"{}", payload_name: str = "aasx/env.json", *,
               content_types: bool = True, root_rels: bool = True,
               origin_rel: bool = True, origin_rels: bool = True,
               spec_rel: bool = True, bom: bool = False):
    """Write an .aasx; every keyword exists so a test can break one link."""
    marker = b"\xef\xbb\xbf" if bom else b""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        if content_types:
            archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        if root_rels:
            pairs = [(ORIGIN_REL, "/aasx/aasx-origin")] if origin_rel else []
            archive.writestr("_rels/.rels", marker + rels(pairs))
        archive.writestr("aasx/aasx-origin", b"")
        if origin_rels:
            pairs = [(SPEC_REL, "/" + payload_name)] if spec_rel else []
            archive.writestr("aasx/_rels/aasx-origin.rels", marker + rels(pairs))
        archive.writestr(payload_name, payload)
    return path


def env_json(semantic_value: str = "0173-1#01-AHF578#003") -> bytes:
    """A minimal, metamodel-valid AAS environment with one submodel."""
    import json
    return json.dumps({"submodels": [{
        "id": "urn:test:submodel",
        "modelType": "Submodel",
        "semanticId": {"type": "ExternalReference",
                       "keys": [{"type": "GlobalReference", "value": semantic_value}]},
    }]}).encode("utf-8")
