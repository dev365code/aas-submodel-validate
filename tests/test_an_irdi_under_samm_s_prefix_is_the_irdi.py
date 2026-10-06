"""An IRDI written the way SAMM writes one is the IRDI it wraps.

IDTA's templates spell one ECLASS identifier two ways. Most write it bare,
`0173-1#02-AAO134#002`; the battery passport's parts 5 and 7, generated from
SAMM models, write it `urn:irdi:0173-1#02-AAO134#002` -- the synthetic URN
SAMM's modelling guideline uses for an IRDI, which is not a URI, and whose
second `#` that guideline writes `%23`. No URN namespace `irdi` is
registered; the prefix is a convention, around the same identifier.

Matching here is exact unless a reading says otherwise, as IDTA-01001's annex
on matching semantic identifiers makes exact matching the default. The same
annex lists, among the ways a reader may match more widely, treating two
syntaxes of one IRDI as one. This project already reads an ECLASS-CDP address
as its IRDI (docs/divergences.md #4); it reads this prefix and that escape the
same way, and nothing else: no other namespace, no other case, no other
escape.

Before it did, a spare part supplier identified the way 02002 Contact
Information identifies one -- by the bare ECLASS identifiers 02035-7 borrows
under the prefix -- matched no row of 02035-7, and six mandatory fields were
reported missing; a 02002 e-mail address written under the prefix was
missing from 02002; and a 02035-5 value known by the bare identifier the
template prefixes was missing from 02035-5.
"""
from __future__ import annotations

import json

import pytest

from aas_submodel_validate import runner
from aas_submodel_validate.rules import (
    contact_tables,
    dbp1_tables,
    dbp4_tables,
    dbp5_tables,
    dbp7_tables,
    dbp_tables,
    dn_tables,
    hd_tables,
    hs_tables,
    pcf_tables,
    sn_tables,
    td_tables,
)
from aas_submodel_validate.semantics import normalize
from builders import contact_prefixed_env, dbp5_bare_irdi_env, dbp7_supplier_env


def _findings(tmp_path, env):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return sorted(f.id for f in runner.run(path).findings if f.rule.kind != "meta")


def _escaped(irdi):
    head, _, version = irdi.rpartition("#")
    return "urn:irdi:%s%%23%s" % (head, version)


@pytest.mark.parametrize("spell", [
    lambda irdi: irdi,
    lambda irdi: "urn:irdi:" + irdi,
    _escaped,
], ids=["bare, as 02002 writes them", "under the prefix, as 02035-7 writes them",
        "under the prefix with the escape SAMM's guideline writes"])
def test_a_spare_part_supplier_answers_02035_7_however_its_irdis_are_spelt(tmp_path, spell):
    assert _findings(tmp_path, dbp7_supplier_env(spell)) == []


def test_a_02002_e_mail_address_written_under_the_prefix_answers_its_row(tmp_path):
    assert _findings(tmp_path, contact_prefixed_env()) == []


def test_a_02035_5_value_known_by_the_bare_irdi_answers_its_row(tmp_path):
    assert _findings(tmp_path, dbp5_bare_irdi_env()) == []


@pytest.mark.parametrize("written, read", [
    ("urn:irdi:0173-1#02-AAO134#002", "0173-1#02-AAO134#002"),
    ("urn:irdi:0173-1#02-AAC895%23009", "0173-1#02-AAC895#009"),
    (" urn:irdi:0173-1#02-AAO134#002 ", "0173-1#02-AAO134#002"),
    # The prefix is read away and only `%23` is unescaped: what is left is
    # whatever the prefix wrapped, and nothing reads it further.
    ("urn:irdi:0173-1#02-AAO134%2F002", "0173-1#02-AAO134%2F002"),
    ("urn:irdi:urn:irdi:0173-1#02-AAO134#002", "urn:irdi:0173-1#02-AAO134#002"),
    ("urn:irdi:https://api.eclass-cdp.com/0173-1-02-AAO134-002",
     "https://api.eclass-cdp.com/0173-1-02-AAO134-002"),
])
def test_the_prefix_and_its_escape_are_read_and_nothing_further(written, read):
    assert normalize(written) == read


@pytest.mark.parametrize("written", [
    "URN:IRDI:0173-1#02-AAO134#002",
    "urn:iridi:0173-1#02-ABL851#001",  # 02035-5's misspelling, docs/divergences.md #58
    "urn:idi:0173-1#02-ABL854#001",    # 02035-7's specification, #61
    "urn:irdi:",
    "0173-1#02-AAC895%23009",
    "urn:samm:io.admin-shell.idta.batterypass.circularity:1.0.0#Circularity",
])
def test_no_other_spelling_is_read_away(written):
    assert normalize(written) == written


@pytest.mark.parametrize("tables", [
    hd_tables, td_tables, dbp_tables, dn_tables, pcf_tables, contact_tables, hs_tables,
    sn_tables, dbp5_tables, dbp1_tables, dbp4_tables, dbp7_tables,
], ids=lambda tables: tables.__name__.rsplit(".", 1)[-1])
def test_a_vendored_table_holds_what_the_comparison_reads(tables):
    """A generated table carries its rows' identifiers in comparison form,
    because it is generated through the same function a file's identifiers
    go through when it is read. Folding only at reading time would leave
    the two forms facing each other: a file written as the template writes
    it would stop matching."""
    held = [value for row in tables.ROWS for value in row["match"]
            if value.startswith("urn:irdi:")]
    assert held == [], held[:3]
