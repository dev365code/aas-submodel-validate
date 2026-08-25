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
               files=(), suppl_targets=None, relative_targets: bool = False):
    """Write an .aasx; every keyword exists so a test can break one link.

    `files` are (name, data) parts to store; `suppl_targets` declares the
    aas-suppl relationships on the spec part (defaults to every name in
    `files`, the honest container; pass a list to declare something the
    archive does not hold).

    `relative_targets` writes each Target without a leading slash, which
    OPC resolves against the directory of the part whose relationships
    they are. Conformant, and the shape this builder could not make.
    """
    marker = b"\xef\xbb\xbf" if bom else b""
    suppl = [name for name, _ in files] if suppl_targets is None else suppl_targets

    def target(name, source_dir):
        if not relative_targets:
            return "/" + name
        prefix = source_dir + "/" if source_dir else ""
        return name[len(prefix):] if name.startswith(prefix) else "/" + name

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        if content_types:
            archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        if root_rels:
            pairs = [(ORIGIN_REL, target("aasx/aasx-origin", ""))] if origin_rel else []
            archive.writestr("_rels/.rels", marker + rels(pairs))
        archive.writestr("aasx/aasx-origin", b"")
        if origin_rels:
            pairs = [(SPEC_REL, target(payload_name, "aasx"))] if spec_rel else []
            archive.writestr("aasx/_rels/aasx-origin.rels", marker + rels(pairs))
        archive.writestr(payload_name, payload)
        for name, data in files:
            archive.writestr(name, data)
        if suppl:
            directory, _, base = payload_name.rpartition("/")
            archive.writestr("%s/_rels/%s.rels" % (directory, base),
                             marker + rels([(SUPPL_REL, target(name, directory))
                                            for name in suppl]))
    return path


def corrupt_part(path, entry: str, how: str):
    """Rewrite an archive so one entry cannot be decompressed.

    `build_aasx` can cut any structural link, but every archive it writes
    describes itself truthfully -- `writestr` computes the sizes and the
    checksum from the data. A supplier's file need not, and what the
    reader does when the description is wrong is exactly the question
    this repository says it answers. So the fields are edited afterwards,
    in both the local header and the central directory (a reader may
    consult either):

    - "declared_size": the entry claims to be far smaller than it is, so
      the read stops early and the checksum no longer matches.
    - "method": a compression method no reader implements.
    - "encrypted": the encryption flag, with no password to be had.
    - "stream": the compressed bytes themselves, which fail inside the
      decompressor rather than in any check zipfile makes first.

    Nothing is written to the repository -- callers pass a tmp_path.
    """
    import struct
    raw = bytearray(path.read_bytes())
    name = entry.encode("utf-8")
    central = raw.find(b"PK\x01\x02")
    while central != -1:
        length = struct.unpack_from("<H", raw, central + 28)[0]
        if raw[central + 46:central + 46 + length] == name:
            break
        central = raw.find(b"PK\x01\x02", central + 4)
    if central == -1:
        raise LookupError("no central directory entry for %s" % entry)
    local = struct.unpack_from("<I", raw, central + 42)[0]
    assert raw[local:local + 4] == b"PK\x03\x04", "not a local header at %d" % local

    if how == "declared_size":
        struct.pack_into("<I", raw, central + 24, 100)   # uncompressed size
        struct.pack_into("<I", raw, local + 22, 100)
    elif how == "method":
        struct.pack_into("<H", raw, central + 10, 99)    # compression method
        struct.pack_into("<H", raw, local + 8, 99)
    elif how == "encrypted":
        flags = struct.unpack_from("<H", raw, central + 8)[0]
        struct.pack_into("<H", raw, central + 8, flags | 0x1)
        struct.pack_into("<H", raw, local + 6, flags | 0x1)
    elif how == "stream":
        name_length = struct.unpack_from("<H", raw, local + 26)[0]
        extra_length = struct.unpack_from("<H", raw, local + 28)[0]
        start = local + 30 + name_length + extra_length
        compressed = struct.unpack_from("<I", raw, central + 20)[0]
        for i in range(start, start + max(1, compressed // 2)):
            raw[i] ^= 0xFF
    else:
        raise ValueError("unknown corruption: %s" % how)
    path.write_bytes(bytes(raw))
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


def declaring_profile(env: dict, mark: str, template_id: str = None) -> dict:
    """A copy of `env` whose first submodel says it means a second
    template's profile, the way IDTA 02035-2 says it: a supplemental
    semanticId beside the main one, which is left alone.

    `template_id` writes `administration.templateId` as well, because the
    two published 02035-2 serialisations disagree about that field and a
    test needs to build both shapes.
    """
    import copy
    env = copy.deepcopy(env)
    submodel = env["submodels"][0]
    submodel.setdefault("supplementalSemanticIds", []).append(
        {"type": "ExternalReference",
         "keys": [{"type": "GlobalReference", "value": mark}]})
    if template_id is not None:
        submodel["administration"] = {"version": "1", "revision": "0",
                                      "templateId": template_id}
    return env


def wearing_our_anchor_as_a_supplemental(anchor: str, id_short: str,
                                         also: str = None) -> bytes:
    """An environment shaped like IDTA 02035-4: it declares an identity of
    its own and carries one of ours in a *supplemental*.

    Copied from the published file (pin 11ef3353,
    `published/Digital Battery Passport/4_Technical Data/1/0/1/`), whose
    submodel names `https://admin-shell.io/idta/digitalbatterypassport/
    TechnicalData/1/0` and lists `0173-1#01-AHX837#002` -- this project's
    Technical Data anchor -- beside a SAMM URN.

    Synthesised rather than vendored on purpose: the only fact this
    fixture holds is that shape, and the other several thousand rows of
    the real file would be read by nothing. The anchor is passed in so
    it comes from the generated table rather than from a second copy of
    the string.
    """
    import json
    return json.dumps({"submodels": [{
        "id": "urn:test:a-template-of-its-own",
        "idShort": id_short,
        "modelType": "Submodel",
        "semanticId": {"type": "ExternalReference", "keys": [
            {"type": "GlobalReference",
             "value": "https://admin-shell.io/idta/digitalbatterypassport"
                      "/TechnicalData/1/0"}]},
        "supplementalSemanticIds": [
            {"type": "ExternalReference",
             "keys": [{"type": "GlobalReference", "value": anchor}]},
            {"type": "ExternalReference",
             "keys": [{"type": "GlobalReference",
                       "value": "urn:samm:io.admin-shell.idta.batterypass"
                                ".technical_data:1.0.0#TechnicalData"}]},
        ] + ([{"type": "ExternalReference",
               "keys": [{"type": "GlobalReference", "value": also}]}]
             if also else []),
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


def _smc(sid, children, id_short=None):
    # A list child carries no idShort -- the metamodel forbids it
    # (AASd-120) -- but anything that is not a list child must have one
    # (AASd-117), so the caller says which case this is.
    out = {"modelType": "SubmodelElementCollection", "semanticId": _sid(sid)}
    if children:
        # AASd-...: a collection's value is either unset or non-empty. An
        # empty list is not "no children", it is a declared emptiness the
        # metamodel refuses.
        out["value"] = children
    if id_short:
        out["idShort"] = id_short
    return out


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


# --- a fully conformant Technical Data instance ------------------------------

def _ref(keys):
    return {"type": "ModelReference",
            "keys": [{"type": kind, "value": value} for kind, value in keys]}


TD_SUBMODEL_ID = "urn:example:technicaldata"


def td_env() -> dict:
    """The golden fixture for IDTA 02003, written by hand for the same
    reason hd_env is: a fixture generated from the table would agree with
    the table however wrong the table was.

    It carries every optional container as well as every required
    element, so each row has a scope it can be stripped from. The
    submodel's own id is deliberately *not* the template's -- the
    official sample reuses the template's identifier, and a fixture that
    copied that would stop being evidence about instances.
    """
    product_image = _smc("0173-1#02-ABM220#001/0173-1#01-AHY911#001", [
        {"idShort": "ImageFile", "modelType": "File",
         "semanticId": _sid("0173-1#02-ABK291#002"),
         "contentType": "image/png", "value": "/aasx/files/front.png"},
        _mlp("ImageNote", "0173-1#02-ABL423#001", "Front view"),
    ])
    classification = _smc("0173-1#02-ABK162#002/0173-1#01-AHX839#002", [
        _prop("ClassificationSystem", "0173-1#02-ABL424#001", "ECLASS"),
        _prop("ClassificationSystemVersion", "0173-1#02-AAR710#003", "15.0"),
        # The template spells this identifier "ProduktClassification" -- a
        # German/English mix that is nonetheless the published identifier,
        # so a faithful instance carries it verbatim (divergences).
        _prop("ClassificationSystemUrl",
              "https://admin-shell.io/IDTA/TechnicalData/ProductClassifications"
              "/ProduktClassification/ClassificationSystemUrl/2/0",
              "https://eclass.eu/"),
        _prop("ProductClassId", "0173-1#02-ABG776#003", "27-01-01-01"),
        _prop("ProductClassCodedName", "0173-1#02-ABK128#002", "27-01-01-01"),
        _mlp("ProductClassName", "0173-1#02-ABK273#002", "Low voltage switchgear"),
        {"idShort": "ReferenceToTechnicalPropertyArea",
         "modelType": "ReferenceElement",
         "semanticId": _sid("0173-1#02-ABL358#002"),
         # Resolves: the list is addressed by idShort, its child by index.
         "value": _ref((("Submodel", TD_SUBMODEL_ID),
                        ("SubmodelElementList", "TechnicalPropertyAreas"),
                        ("SubmodelElementCollection", "0")))},
    ])
    general = _smc("0173-1#02-ABK161#002/0173-1#01-AHX838#002", [
        _prop("ManufacturerName", "0173-1#02-AAO677#004", "Example company Ltd."),
        {"idShort": "CompanyLogo", "modelType": "File",
         "semanticId": _sid("0173-1#02-ABI776#002"),
         "contentType": "image/png", "value": "/aasx/files/logo.png"},
        _mlp("ManufacturerProductDesignation", "0173-1#02-AAW338#003",
             "Switchgear type A"),
        _prop("ManufacturerArticleNumber", "0173-1#02-AAO676#005", "A-1000"),
        _prop("ManufacturerOrderCode", "0173-1#02-AAO227#004", "A-1000-24V"),
        _sml("ProductImages", "0173-1#02-ABM220#001",
             "SubmodelElementCollection", [product_image]),
    ], id_short="GeneralInformation")
    return {"submodels": [{
        "id": TD_SUBMODEL_ID, "idShort": "TechnicalData",
        "modelType": "Submodel",
        "semanticId": {"type": "ModelReference",
                       "keys": [{"type": "Submodel",
                                 "value": "0173-1#01-AHX837#002"}]},
        "submodelElements": [
            general,
            _sml("ProductClassifications", "0173-1#02-ABK162#002",
                 "SubmodelElementCollection", [classification]),
            _sml("TechnicalPropertyAreas", "0173-1#02-ABK163#002",
                 "SubmodelElementCollection",
                 [_smc("0173-1#02-ABL358#002/0173-1#01-AHX773#002", [])]),
            _smc("0173-1#02-ABK164#002", [
                _mlp("TextStatement", "0173-1#02-ABK134#002", "Indoor use only."),
                _prop("ValidDate", "0173-1#02-ABL775#001", "2025-03-15", "xs:date"),
            ], id_short="FurtherInformation"),
            _sml("SpecificDescriptions", "0173-1#02-ABM221#001",
                 "SubmodelElementCollection",
                 [_smc("0173-1#02-ABM221#001/0173-1#01-AHY912#001", [])]),
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


def strip_row(env: dict, row, tables) -> dict:
    """Remove the row's elements *from the row's own scope*.

    Global removal would overshoot: component decomposition means a list
    child's match set contains its parent list's identifier, so matching
    "anywhere" deletes the parent too and the child rule loses the very
    scope it should have fired in.
    """
    parent = tables.BY_ID.get(row["parent"])
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


def break_row(env: dict, row, tables) -> dict:
    """A copy of `env` that violates exactly `row`.

    The mutation is chosen by what the row demands, and the choice is the
    reason this lives here rather than in one test: a required element
    the environment holds is removed; a required element whose container
    the environment does *not* hold gets that container injected empty
    (removing it would remove nothing); an optional one is injected past
    its maximum. Two suites need the same three-way choice -- the one
    that proves every generated rule fires, and the one that proves a
    profile mark takes no rule away -- and the second was written without
    it and silently reached only six of the eleven rows it named.
    """
    import copy
    env = copy.deepcopy(env)
    low, _high = row["card"]
    if low < 1:
        inject(env, tables.BY_ID.get(row["parent"]), [stub_of(row), stub_of(row)], tables)
    elif any(_element_matches(element, row["match"]) for _c, element in _scopes(env)):
        strip_row(env, row, tables)
    else:
        parent = tables.BY_ID[row["parent"]]
        inject(env, tables.BY_ID.get(parent["parent"]), [stub_of(parent)], tables)
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


def inject(env: dict, parent_row, stubs, tables) -> dict:
    """Append stubs into every scope the parent row matches (or the
    submodel root when the row has no parent). `tables` is required for
    symmetry with strip_row rather than used: the scopes are found by
    match value, which is table-independent. A caller that has to name
    the table cannot pass rows from one and mean another."""
    if parent_row is None:
        env["submodels"][0]["submodelElements"].extend(stubs)
        return env
    for _container, element in list(_scopes(env)):
        if _element_matches(element, parent_row["match"]):
            element.setdefault("value", []).extend(stubs)
    return env
