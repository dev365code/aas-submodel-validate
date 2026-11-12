"""The IDTA 02003 table, and what the generator had to learn to make it.

02004 was a template where every element carried a cardinality qualifier
and nothing was open-ended. 02003 is not: four list items declare no
cardinality at all, and thirty-six elements are placeholders for content
the standard deliberately leaves unconstrained. Both of those are
decisions the generator now makes, so both are pinned here rather than
left to be noticed later in a rule that never fires.
"""
from __future__ import annotations

from aas_submodel_validate.rules import hd_tables, td_tables

#: The template's own anchor, whose one key is the ECLASS IRDI: a
#: ModelReference through 2.0.2 and an ExternalReference from 2.0.4
#: (upstream #224), the same shape 02004 uses (divergences #12).
ANCHOR = "0173-1#01-AHX837#002"

#: Elements whose semanticId is this are the standard's open-content
#: placeholders (§3.5: "the set of suitable semanticIds is not
#: restricted"). They describe what a manufacturer may add, not what a
#: conformant file must hold.
ARBITRARY = "https://admin-shell.io/SMT/General/Arbitrary"


def test_the_anchor_and_its_reference_type():
    assert td_tables.TEMPLATE_SEMANTIC_ID == ANCHOR
    assert td_tables.TEMPLATE_SUBMODEL_SID_TYPE == "ExternalReference"


def test_the_concrete_rows_are_twenty_six():
    assert len(td_tables.ROWS) == 26
    assert [row["id"] for row in td_tables.ROWS] == \
        ["TD-E%02d" % n for n in range(1, 27)]


def test_no_open_content_placeholder_became_a_rule():
    """The 36 Arbitrary elements must leave no row behind -- and no row may
    match on their identifier either. A rule generated from a placeholder
    would demand the very thing §3.5 says is unconstrained, and six sibling
    placeholders sharing one identifier would make the first of them claim
    every arbitrary element the walk met.
    """
    for row in td_tables.ROWS:
        assert row["sid"] != ARBITRARY
        assert ARBITRARY not in row["match"]


def test_every_row_is_reachable_by_a_unique_label():
    """The hand rules navigate by label, so two rows sharing one would make
    one of them unreachable -- silently, because the lookup is a dict."""
    assert len(td_tables.BY_LABEL) == len(td_tables.ROWS)


def test_the_unnamed_list_items_default_to_any_number():
    """Four list items carry no SMT/Cardinality. The PDF's element tables
    give each of them 0..*, so that is what the generator assumes when the
    qualifier is absent -- rather than failing, which would refuse the
    template outright, or assuming One, which would invent an obligation.
    """
    for label in ("ProductImage", "ProductClassification",
                  "TechnicalPropertyArea", "SpecificDescription"):
        assert td_tables.BY_LABEL[label]["card"] == (0, None)


def test_a_declared_cardinality_still_wins():
    assert td_tables.BY_LABEL["GeneralInformation"]["card"] == (1, 1)
    assert td_tables.BY_LABEL["CompanyLogo"]["card"] == (0, 1)
    assert td_tables.BY_LABEL["TextStatement"]["card"] == (0, None)
    assert td_tables.BY_LABEL["ValidDate"]["value_type"] == "xs:date"


def test_the_four_example_systems_all_reach_the_remedy():
    """02003 offers one element four example values, one per
    classification system -- four qualifiers through 2.0.2 and one, the
    four separated by "|", from 2.0.3 -- where 02004 had a single bare
    `ExampleValue`. Keeping only one of them would tell a reader ECLASS is
    the answer when the template offers four.
    """
    row = td_tables.BY_LABEL["ClassificationSystem"]
    assert row["example"] == "ECLASS | IEC CDD | UNSPSC | customer specific"
    assert "customer specific" in row["fix"]


def test_example_values_a_bar_separates_are_several_values():
    """02003's Annex B (Issue #190): "Example values are now separated by
    '|' characters". 2.0.3 merged ClassificationSystem's four
    `SMT/ExampleValue/<system>` qualifiers into one `SMT/ExampleValue`
    written that way. The remedy names each value once and joins them as
    it joins several qualifiers', so a reader is told the same four
    systems whichever spelling the template used."""
    from aas_submodel_validate import tablegen

    def template(qualifiers):
        return {"submodels": [{
            "modelType": "Submodel", "id": "urn:test:tpl", "idShort": "T",
            "kind": "Template",
            "semanticId": {"type": "ExternalReference", "keys": [
                {"type": "GlobalReference", "value": "urn:test:t"}]},
            "submodelElements": [{
                "modelType": "Property", "idShort": "System",
                "valueType": "xs:string",
                "semanticId": {"type": "ExternalReference", "keys": [
                    {"type": "GlobalReference", "value": "urn:test:s"}]},
                "qualifiers": [{"type": kind, "valueType": "xs:string",
                                "value": value}
                               for kind, value in qualifiers]}]}]}

    def example(qualifiers, types):
        (row,) = tablegen.build(template(qualifiers), {
            "prefix": "X-E", "citation": "c", "skip_sids": frozenset(),
            "item_names": {}, "example_types": types})["tree"]
        return row["example"]

    merged = example([("SMT/ExampleValue", "ECLASS|IEC CDD|UNSPSC|customer specific")],
                     ("SMT/ExampleValue",))
    several = example([("SMT/ExampleValue/ECLASS", "ECLASS"),
                       ("SMT/ExampleValue/CDD", "IEC CDD"),
                       ("SMT/ExampleValue/UNSPSC", "UNSPSC"),
                       ("SMT/ExampleValue/CustomerSpecific", "customer specific")],
                      ("SMT/ExampleValue/ECLASS", "SMT/ExampleValue/CDD",
                       "SMT/ExampleValue/UNSPSC", "SMT/ExampleValue/CustomerSpecific"))
    assert merged == several == "ECLASS | IEC CDD | UNSPSC | customer specific", \
        (merged, several)


def test_the_handover_table_is_untouched():
    """Both tables come out of one generator now. 02004's rows are the
    regression surface for that change: they are what the whole suite,
    the corpus verdict and the README's numbers rest on.
    """
    assert len(hd_tables.ROWS) == 38
    assert hd_tables.TEMPLATE_SEMANTIC_ID == "0173-1#01-AHF578#003"
