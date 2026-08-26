"""semanticId comparison: values, normalised, from any key."""
import pytest

from aas_submodel_validate.semantics import (
    edit_distance,
    key_values,
    normalize,
    version_stem,
)


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


#: Spellings the vendored templates actually carry, and the shapes a
#: supplier may send that mean the same thing. A URL is
#: case-insensitive in its scheme and host and may carry a trailing
#: slash, and this reader compares values a supplier chose -- so the
#: latitude the format allows is latitude this has to allow too.
@pytest.mark.parametrize("spelling", (
    "https://api.eclass-cdp.com/0173-1-02-ABI002-003",
    "http://api.eclass-cdp.com/0173-1-02-ABI002-003",
    "HTTPS://API.ECLASS-CDP.COM/0173-1-02-ABI002-003",
    "https://api.eclass-cdp.com/0173-1-02-ABI002-003/",
    "  https://api.eclass-cdp.com/0173-1-02-ABI002-003  ",
))
def test_every_spelling_of_one_cdp_url_compares_equal(spelling):
    assert normalize(spelling) == "0173-1#02-ABI002#003"


@pytest.mark.parametrize("value", (
    # Two of the three CDP spellings the 02003 template got wrong: a
    # space after the host, and `#` where the URL form uses `-`
    # (divergence #24). Neither is a CDP URL, and inventing an IRDI out
    # of one would be this reader deciding what upstream meant.
    "https://api.eclass-cdp.com/ 0173-1-02-ABK161-002/0173-1-01-AHX838-002",
    "https://api.eclass-cdp.com/0173-1#02-ABL775#001",
    # Not that host at all.
    "https://example.com/0173-1-02-ABI002-003",
    "https://admin-shell.io/vdi/2770/1/0/Documentation",
))
def test_what_is_not_a_cdp_url_is_left_alone(value):
    assert normalize(value) == value.strip()


#: `version_stem` is what tells a near-miss from an unrelated neighbour:
#: `…#003` against `…#004` is one supplier's version drift and gets a
#: diagnosis, where two different identifiers get silence. Nothing
#: exercised it directly, and every guard in it could be removed.
@pytest.mark.parametrize("value,stem", (
    ("0173-1#01-AHF578#003", "0173-1#01-AHF578"),
    ("0173-1#02-ABI500#003~0", "0173-1#02-ABI500"),
    ("0173-1#02-ABI500#003/0173-1#01-AHF579#003", "0173-1#02-ABI500#003/0173-1#01-AHF579"),
    # No version suffix to strip.
    ("0173-1#01-AHF578", None),
    # A suffix that is not a version.
    ("0173-1#01-AHF578#abc", None),
    # One `#` only: the head is not an identifier, so there is no stem.
    ("0173-1#003", None),
    # Not an IRDI at all.
    ("https://admin-shell.io/vdi/2770/1/0/Documentation", None),
    ("urn:x", None),
))
def test_a_version_suffix_is_recognised_only_where_there_is_one(value, stem):
    assert version_stem(value) == stem


#: `edit_distance` decides whether a mismatched identifier is close
#: enough to be worth telling the author about. Costs that do not cost
#: anything make everything look close.
@pytest.mark.parametrize("a,b,distance", (
    ("abc", "abc", 0),
    ("abc", "abd", 1),                     # substitution
    ("abc", "abcd", 1),                     # insertion
    ("abcd", "abc", 1),                     # deletion
    ("abc", "", 3),
    ("", "abc", 3),
    ("Entities", "Entites", 1),             # the official example's typo
    ("Language", "Languages", 1),           # template against example
    ("0173-1#02-AAO677#003", "0173-1#02-AAO677#004", 1),
    ("kitten", "sitting", 3),               # the textbook one
))
def test_the_distance_is_the_distance(a, b, distance):
    assert edit_distance(a, b) == distance


def test_far_apart_is_reported_as_far_apart_without_being_counted():
    """Once it is clearly large the exact value does not matter, and the
    cap is what stops a long pair costing a long walk. Both exits report
    the same thing -- the length check before the walk, and the row
    minimum during it -- so both are asked here."""
    assert edit_distance("a" * 20, "b" * 20) == 7      # lengths equal, walk exits
    assert edit_distance("a", "b" * 20) == 7           # lengths differ, no walk
    assert edit_distance("abcdefghij", "x") == 7


def test_the_cap_is_where_the_default_puts_it():
    """Six is a number the callers rely on: a near-miss diagnosis is worth
    printing for a version drift and not for an unrelated neighbour that
    merely shares a namespace directory. Raise it and unrelated pairs
    start looking like typos; lower it and real drift goes unmentioned."""
    assert edit_distance("a" * 7, "") == 7
    assert edit_distance("a" * 6, "") == 6
    assert edit_distance("aaaaaa", "bbbbbb", cap=2) == 3
