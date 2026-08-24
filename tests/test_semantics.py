"""semanticId comparison: values, normalised, from any key."""
from aas_submodel_validate.semantics import key_values, normalize


def test_eclass_cdp_urls_normalise_to_their_irdi():
    """The official 02004 template itself spells exactly one property's
    semanticId as a CDP URL where every sibling uses an IRDI (recorded as
    divergence #4), so both spellings must compare equal."""
    assert normalize("https://api.eclass-cdp.com/0173-1-02-ABI002-003") == "0173-1#02-ABI002#003"
    assert normalize("0173-1#02-ABI002#003") == "0173-1#02-ABI002#003"


def test_anything_else_passes_through_untouched():
    iri = "https://admin-shell.io/vdi/2770/1/0/Documentation"
    assert normalize(iri) == iri
    assert normalize("  spaced  ") == "spaced"


def test_key_values_is_none_safe():
    assert key_values(None) == []
