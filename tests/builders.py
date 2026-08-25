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


SUPPL_REL = "http://admin-shell.io/aasx/relationships/aas-suppl"


def build_aasx(path, payload: bytes = b"{}", payload_name: str = "aasx/env.json", *,
               content_types: bool = True, root_rels: bool = True,
               origin_rel: bool = True, origin_rels: bool = True,
               spec_rel: bool = True, bom: bool = False,
               files=(), suppl_targets=None):
    """Write an .aasx; every keyword exists so a test can break one link.

    `files` are (name, data) parts to store; `suppl_targets` declares the
    aas-suppl relationships on the spec part (defaults to every name in
    `files`, the honest container; pass a list to declare something the
    archive does not hold).
    """
    marker = b"\xef\xbb\xbf" if bom else b""
    suppl = [name for name, _ in files] if suppl_targets is None else suppl_targets
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
        for name, data in files:
            archive.writestr(name, data)
        if suppl:
            directory, _, base = payload_name.rpartition("/")
            archive.writestr("%s/_rels/%s.rels" % (directory, base),
                             marker + rels([(SUPPL_REL, "/" + name) for name in suppl]))
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


# --- a fully conformant Handover Documentation instance ---------------------

def _sid(value):
    return {"type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": value}]}


def _prop(id_short, sid, value, value_type="xs:string"):
    out = {"modelType": "Property", "valueType": value_type, "value": value,
           "semanticId": _sid(sid)}
    if id_short:
        out["idShort"] = id_short
    return out


def _mlp(id_short, sid, text, language="en"):
    return {"idShort": id_short, "modelType": "MultiLanguageProperty",
            "semanticId": _sid(sid),
            "value": [{"language": language, "text": text}]}


def _sml(id_short, sid, list_type, children, value_type=None):
    out = {"idShort": id_short, "modelType": "SubmodelElementList",
           "semanticId": _sid(sid), "typeValueListElement": list_type,
           "value": children}
    if value_type:  # AASd-109: a Property list must declare its value type
        out["valueTypeListElement"] = value_type
    return out


def _smc(sid, children):
    # list children carry no idShort -- the metamodel forbids it (AASd-120)
    return {"modelType": "SubmodelElementCollection", "semanticId": _sid(sid),
            "value": children}


def hd_env() -> dict:
    """The golden fixture: one Handover Documentation submodel satisfying
    every required row of the 02004 2.0.1 template, written by hand so it
    is evidence about the template rather than an echo of it. Composite
    identifiers use the template's slash spelling; OrganizationShortName
    deliberately uses the IRDI spelling where the template writes the
    CDP URL, pinning the normalisation both ways."""
    document_id = _smc("0173-1#02-ABI501#003/0173-1#01-AHF580#003", [
        _prop("DocumentDomainId", "0173-1#02-ABH994#003", "example.com/ids"),
        _prop("DocumentIdentifier", "0173-1#02-AAO099#004", "XF90-884"),
        _prop("DocumentIsPrimary", "0173-1#02-ABH995#003", "true", "xs:boolean"),
    ])
    classification = _smc("0173-1#02-ABI502#003/0173-1#01-AHF581#003", [
        _prop("ClassId", "0173-1#02-ABH996#003", "03-02"),
        _mlp("ClassName", "0173-1#02-ABJ219#002", "Operation"),
        _prop("ClassificationSystem", "0173-1#02-ABH997#003", "VDI 2770 Blatt 1:2020"),
    ])
    version = _smc("0173-1#02-ABI503#003/0173-1#01-AHF582#003", [
        _sml("Language", "0173-1#02-AAN468#008", "Property",
             [_prop(None, "0173-1#02-AAN468#008", "en")], value_type="xs:string"),
        _prop("Version", "0173-1#02-AAP003#005", "V1.2"),
        _mlp("Title", "0173-1#02-ABG940#003", "Operating manual"),
        _mlp("Description", "0173-1#02-AAN466#004", "How to operate the machine."),
        _prop("StatusSetDate", "0173-1#02-ABI000#003", "2020-02-06", "xs:date"),
        _prop("StatusValue", "0173-1#02-ABI001#003", "Released"),
        _prop("OrganizationShortName", "0173-1#02-ABI002#003", "Example company"),
        _prop("OrganizationOfficialName", "0173-1#02-ABI004#003", "Example company Ltd."),
        _sml("DigitalFiles", "0173-1#02-ABK126#002", "File",
             [{"modelType": "File", "semanticId": _sid("0173-1#02-ABK126#002"),
               "contentType": "application/pdf", "value": "/aasx/files/manual.pdf"}]),
    ])
    document = _smc("0173-1#02-ABI500#003/0173-1#01-AHF579#003", [
        _sml("DocumentIds", "0173-1#02-ABI501#003", "SubmodelElementCollection",
             [document_id]),
        _sml("DocumentClassifications", "0173-1#02-ABI502#003",
             "SubmodelElementCollection", [classification]),
        _sml("DocumentVersions", "0173-1#02-ABI503#003",
             "SubmodelElementCollection", [version]),
    ])
    return {"submodels": [{
        "id": "urn:example:handover", "idShort": "HandoverDocumentation",
        "modelType": "Submodel",
        # the template declares its own semanticId as a ModelReference with a
        # Submodel key -- a faithful instance mirrors that (see divergences #12)
        "semanticId": {"type": "ModelReference",
                       "keys": [{"type": "Submodel", "value": "0173-1#01-AHF578#003"}]},
        "submodelElements": [
            _sml("Documents", "0173-1#02-ABI500#003",
                 "SubmodelElementCollection", [document]),
        ],
    }]}


# --- mutations, for firing every generated rule -----------------------------

def _element_matches(element: dict, match_values) -> bool:
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src"))
    from aas_submodel_validate.semantics import candidate_values_from_dict
    return bool(candidate_values_from_dict(element.get("semanticId")) & set(match_values))


def _scopes(env: dict):
    """(container list, element) pairs over the whole environment."""
    def walk(container):
        for element in container:
            yield container, element
            child = element.get("value")
            if isinstance(child, list) and element.get("modelType") in (
                    "SubmodelElementCollection", "SubmodelElementList"):
                yield from walk(child)
    for submodel in env["submodels"]:
        yield from walk(submodel.get("submodelElements", []))


def strip_row(env: dict, row) -> dict:
    """Remove the row's elements *from the row's own scope*.

    Global removal would overshoot: component decomposition means a list
    child's match set contains its parent list's identifier, so matching
    "anywhere" deletes the parent too and the child rule loses the very
    scope it should have fired in.
    """
    from aas_submodel_validate.rules import hd_tables
    parent = hd_tables.BY_ID.get(row["parent"])
    if parent is None:
        containers = [env["submodels"][0]["submodelElements"]]
    else:
        containers = [element["value"]
                      for _container, element in _scopes(env)
                      if _element_matches(element, parent["match"])
                      and isinstance(element.get("value"), list)]
    for container in containers:
        for element in list(container):
            if _element_matches(element, row["match"]):
                container.remove(element)
    return env


def stub_of(row) -> dict:
    out = {"modelType": row["kind"]}
    if row["sid"]:
        out["semanticId"] = _sid(row["sid"])
    if row["kind"] == "SubmodelElementList":
        out["typeValueListElement"] = row["list_type"] or "SubmodelElement"
        out["value"] = []
    elif row["kind"] == "Property":
        out["valueType"] = row["value_type"] or "xs:string"
        out["value"] = row["example"] or "x"
    elif row["kind"] == "MultiLanguageProperty":
        out["value"] = [{"language": "en", "text": "x"}]
    elif row["kind"] == "File":
        out["contentType"] = "application/pdf"
    elif row["kind"] == "Entity":
        out["entityType"] = "SelfManagedEntity"
    return out


def inject(env: dict, parent_row, stubs) -> dict:
    """Append stubs into every scope the parent row matches (or the
    submodel root when the row has no parent)."""
    if parent_row is None:
        env["submodels"][0]["submodelElements"].extend(stubs)
        return env
    for _container, element in list(_scopes(env)):
        if _element_matches(element, parent_row["match"]):
            element.setdefault("value", []).extend(stubs)
    return env
