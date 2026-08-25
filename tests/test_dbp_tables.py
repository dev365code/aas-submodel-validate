"""The IDTA 02035-2 table, and the one thing it has that 02003 did not.

02003 was a different template with a different identifier: whatever the
generator got wrong there, the walk could still tell the two apart from
outside. 02035-2 cannot be told apart from outside. Its submodel
semanticId is 02004's, to the character, under the same idShort, so a
mistake in this table is a mistake reported against a file that declares
itself to be something this project already validates -- and the finding
would look exactly like a real one.

So the facts pinned here are mostly *comparisons* with 02004's table,
not statements about this one alone. What the second table is for is the
difference; if that difference ever came out empty, or came out
somewhere nobody expected, these are the tests that would say so.
"""
from __future__ import annotations

import json
from pathlib import Path

from aas_submodel_validate.rules import dbp_tables, hd_tables, td_tables

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src/aas_submodel_validate/data/smt/02035-2/1.0/template.json"

#: 02004 rows that 02035-2 does not have. Named rather than counted: a
#: count would survive the template swapping one for another.
ABSENT = {
    "BasedOn", "BasedOnReferences", "DocumentedEntities", "DocumentedEntity",
    "Entities", "EntityForDocumentation", "KeyWords",
    "OrganizationOfficialName", "OrganizationShortName", "PreviewFile",
    "RefersTo", "RefersToEntities", "StatusSetDate", "StatusValue",
    "TranslationOf", "TranslationOfEntities",
}


def _hd(label):
    return hd_tables.BY_LABEL[label]


def test_the_anchor_is_02004s_and_that_is_the_whole_problem():
    """Not "the anchor is AHF578" -- that would pass just as well if the
    two tables had drifted apart. The load-bearing fact is that they are
    the same string, because everything downstream has to choose between
    two tables that answer to one identifier."""
    assert dbp_tables.TEMPLATE_SEMANTIC_ID == hd_tables.TEMPLATE_SEMANTIC_ID
    assert dbp_tables.TEMPLATE_SEMANTIC_ID == "0173-1#01-AHF578#003"
    assert dbp_tables.TEMPLATE_SUBMODEL_SID_TYPE == "ModelReference"
    assert dbp_tables.TEMPLATE_SEMANTIC_ID != td_tables.TEMPLATE_SEMANTIC_ID


def test_the_concrete_rows_are_twenty_two():
    assert len(dbp_tables.ROWS) == 22
    assert [row["id"] for row in dbp_tables.ROWS] == \
        ["DBP2-E%02d" % n for n in range(1, 23)]


def test_every_row_is_reachable_by_a_unique_label():
    assert len(dbp_tables.BY_LABEL) == len(dbp_tables.ROWS)


def test_every_label_is_one_of_02004s_and_sixteen_are_not_here():
    """The profile relationship, as a measurement rather than a claim:
    02035-2 adds no element of its own, and drops sixteen."""
    assert set(dbp_tables.BY_LABEL) <= set(hd_tables.BY_LABEL)
    assert set(hd_tables.BY_LABEL) - set(dbp_tables.BY_LABEL) == ABSENT


def test_exactly_two_rows_relax_a_cardinality_02004_requires():
    """The entire behavioural content of the second table. If this set
    were ever empty the table would be dead weight, and if it grew,
    something changed upstream that nobody read."""
    relaxed = {label: (_hd(label)["card"], row["card"])
               for label, row in dbp_tables.BY_LABEL.items()
               if row["card"] != _hd(label)["card"]}
    assert relaxed == {"Version": ((1, 1), (0, 1)),
                       "Description": ((1, 1), (0, 1))}


def test_no_row_disagrees_with_02004_about_what_it_matches():
    """A mask over the existing table would have been invisible here:
    nothing is narrowed, so matching alone cannot tell the two apart.
    What a mask cannot do is give one rule id a second remedy sentence --
    which is why there are two tables and not one with exceptions."""
    for label, row in dbp_tables.BY_LABEL.items():
        other = _hd(label)
        assert row["sid"] == other["sid"]
        assert row["kind"] == other["kind"]
        assert row["value_type"] == other["value_type"]
        assert set(other["match"]) < set(row["match"])
        added = set(row["match"]) - set(other["match"])
        assert all(value.startswith("urn:samm:") for value in added), added


def test_the_example_values_are_this_templates_own():
    """Two rows carry a different ExampleValue, and the remedy sentence is
    baked from the row at import time. A battery passport told to classify
    its document as 02004's example would be told the wrong thing."""
    assert dbp_tables.BY_LABEL["ClassName"]["example"] == "Certificates, declarations"
    assert dbp_tables.BY_LABEL["ClassId"]["example"] == "02-04"
    assert _hd("ClassName")["example"] == "Operation@en"
    assert _hd("ClassId")["example"] == "03-02"
    assert "Certificates, declarations" in dbp_tables.BY_LABEL["ClassName"]["fix"]


def test_four_labels_come_from_a_defect_in_the_published_template():
    """AASd-120 forbids a direct child of a SubmodelElementList an
    idShort; 02035-2 gives one to four of its six. Those names are the
    artefact's own, so a finding names something a reader can find in the
    file. Read from the vendored bytes, so that an upstream repair turns
    this red rather than passing unnoticed."""
    document = json.loads(TEMPLATE.read_text("utf-8-sig"))
    named, unnamed = [], []
    def walk(element):
        for child in element.get("value") or []:
            if isinstance(child, dict) and "modelType" in child:
                if element.get("modelType") == "SubmodelElementList":
                    (named if child.get("idShort") else unnamed).append(
                        child.get("idShort") or element["idShort"])
                walk(child)
    for element in document["submodels"][0]["submodelElements"]:
        walk(element)
    assert named == ["Document", "DocumentClassification",
                     "DocumentId", "DocumentVersion"]
    assert unnamed == ["Language", "DigitalFiles"]
    for label in named:
        assert label in dbp_tables.BY_LABEL


def test_the_generated_header_names_this_templates_own_file():
    """`make generated` cannot catch a source string copied from the pack
    beside it: the generator and its output would agree on the same lie.
    This is the only thing that would."""
    assert "IDTA 02035-2" in dbp_tables.__doc__
    assert "02004" not in dbp_tables.__doc__


def test_the_vendored_file_is_the_published_one_not_its_twin():
    """Upstream's `_without_examplevalues` copy carries every ExampleValue
    the published one does (divergences #25) and generates a table with
    the same bytes, so `make generated` and `make vendored` are both green
    on the wrong file. These are the two bytes that differ."""
    raw = TEMPLATE.read_bytes()
    assert raw.endswith(b"}\n")
    document = json.loads(raw.decode("utf-8-sig"))
    languages = [element for element in _every(document["submodels"][0])
                 if element.get("idShort") == "Language"]
    (language,) = languages
    assert language["value"][0]["value"] == "en"


def _every(element):
    for child in element.get("value") or element.get("submodelElements") or []:
        if isinstance(child, dict) and "modelType" in child:
            yield child
            yield from _every(child)


def test_the_submodel_says_one_thing_about_itself_that_02004_does_not():
    """The only thing in either published file that could tell an instance
    of one from an instance of the other. Both submodels carry an
    ECLASS-CDP supplemental, which normalises to the IRDI they already
    share and so says nothing; 02035-2 carries a second, and that is the
    whole signal.

    It is generated rather than written into a rule because a string
    copied out of a template by hand is how the sixty-four rows would
    have gone stale, and this one would go stale in the quietest way
    available: `SMT-D2` is the only rule that reads it, it is `info`, and
    a note that stops appearing looks like a file that stopped needing
    one.
    """
    theirs = set(hd_tables.TEMPLATE_SUPPLEMENTAL_SEMANTIC_IDS)
    ours = set(dbp_tables.TEMPLATE_SUPPLEMENTAL_SEMANTIC_IDS)
    assert theirs == {hd_tables.TEMPLATE_SEMANTIC_ID}
    assert theirs < ours
    assert ours - theirs == {
        "urn:samm:io.admin-shell.idta.batterypass.handover_documentation"
        ":1.0.0#HandoverDocumentation"}


def test_the_other_two_tables_are_untouched():
    """Three tables out of one generator now. 02004's rows are what the
    whole suite, the corpus verdict and the README's numbers rest on."""
    assert len(hd_tables.ROWS) == 38
    assert len(td_tables.ROWS) == 26
    assert td_tables.TEMPLATE_SEMANTIC_ID == "0173-1#01-AHX837#002"
