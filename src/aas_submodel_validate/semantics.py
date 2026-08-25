"""semanticId comparison: values, normalised, from any key.

Two decisions live here and nowhere else (docs/divergences.md #4, and
the matching policy behind #1--#3):

Values are collected from *every* key of a Reference, not keys[0] alone —
real instances differ in how they stack keys, and a comparison that only
looks at the first one silently unmatches files other tools accept.

ECLASS-CDP URLs normalise to their IRDI. The official 02004 template
itself spells exactly one property's semanticId as
`https://api.eclass-cdp.com/0173-1-02-ABI002-003` where every sibling
property uses `0173-1#02-ABI002#003` — the PDF does the same — so an
instance carrying either spelling must match either authority.
"""
from __future__ import annotations

import re
from typing import List, Optional

_CDP_URL = re.compile(r"^https?://api\.eclass-cdp\.com/([0-9A-Za-z.-]+)/?$", re.IGNORECASE)
_CDP_TAIL = re.compile(r"^(\d{4}-\d)-(\d{2}-[A-Z]{3}\d{3})-(\d{3})$")


def normalize(value: str) -> str:
    """The comparison form of one semanticId key value."""
    value = value.strip()
    url = _CDP_URL.match(value)
    if url:
        tail = _CDP_TAIL.match(url.group(1))
        if tail:
            return "%s#%s#%s" % tail.groups()
    return value


def key_values(reference) -> List[str]:
    """Every key's value in `reference`, normalised. None-safe, because
    semanticId is optional on every element."""
    if reference is None:
        return []
    return [normalize(key.value) for key in (reference.keys or [])]


def version_stem(irdi: str) -> Optional[str]:
    """`0173-1#01-AHF578#003` -> `0173-1#01-AHF578`; None when the value
    does not end in an ECLASS version suffix."""
    irdi = re.sub(r"~\d+", "", irdi)
    head, sep, tail = irdi.rpartition("#")
    if sep and tail.isdigit() and "#" in head:
        return head
    return None


def candidate_values(reference) -> frozenset:
    """Every spelling under which a reference may match a template row.

    Each key's value, and the "/"-join when a reference stacks several
    keys. IRDI composites are NOT split into their components: the review
    that justified splitting ("the PDF cites the item id alone") was
    checked against the published PDF and found false -- the tables carry
    the composite -- and the splitting cross-contaminated matching (a
    Document collection's id decomposed to its parent Documents-list id
    and matched the list row too). See docs/divergences.md #8.
    """
    values = key_values(reference)
    out = set(values)
    if len(values) > 1:
        out.add("/".join(values))
    return frozenset(out)


def submodel_declares(submodel, anchor: str) -> bool:
    """Does this submodel say it is the template `anchor` identifies?

    A submodel's identity is its *main* semanticId and nothing else. Its
    supplementals are not folded in, although element matching folds
    theirs one level down (docs/divergences.md #14), and the reason is a
    published file: IDTA 02035-4 is a template of its own and carries this
    project's Technical Data anchor in a supplemental. Fold them here and
    that file becomes Technical Data, every way it differs becomes a
    defect it is reported for, and the report contradicts itself -- the
    presence rule, reading the main identifier, says it knows no submodel
    while findings from a template it knows print underneath.

    Three places asked this question with the same line of code, which
    agreed by being one line each. They ask it here now, because the next
    slice makes the answer depend on more than the identifier and three
    copies of that would be three chances to disagree.
    """
    return anchor in candidate_values(submodel.semantic_id)


def candidate_values_from_dict(reference: Optional[dict]) -> frozenset:
    """candidate_values for a JSON-shaped reference (test builders and
    tools work on plain dicts before jsonization)."""
    if not reference:
        return frozenset()
    values = [normalize(key.get("value", "")) for key in reference.get("keys", [])]
    out = set(values)
    if len(values) > 1:
        out.add("/".join(values))
    return frozenset(out)


def element_candidate_values(element) -> frozenset:
    """Match spellings for an element: its semanticId and every
    supplementalSemanticId. The template's own supplementals are in the
    row match set, so an instance that declares its identity only through
    a supplemental should match too."""
    out = set(candidate_values(getattr(element, "semantic_id", None)))
    for supplemental in getattr(element, "supplemental_semantic_ids", None) or []:
        out |= candidate_values(supplemental)
    return frozenset(out)


def edit_distance(a: str, b: str, cap: int = 6) -> int:
    """Levenshtein distance between two short strings, capped: once it is
    clearly large the exact value does not matter. Used to tell a genuine
    near-miss (a singular/plural typo) from an unrelated neighbour that
    merely shares a namespace directory."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (ca != cb)))
        previous = current
        if min(previous) > cap:
            return cap + 1
    return previous[-1]
