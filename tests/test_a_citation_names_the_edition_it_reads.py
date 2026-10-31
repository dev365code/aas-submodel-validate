"""A rule that cites IDTA 01005 or IDTA 01001 says which edition it reads.

The packaging this reader follows is IDTA 01005-3-0-1's: the edition whose
section 5.2 keeps reading the relationship path it deprecates. The
metamodel is 3.0, the one aas-core3.0 implements -- its types module
opens "Provide an implementation of the Asset Administration Shell (AAS)
V3.0." A citation with no edition read as any edition of either, while a
package or a document of another one is refused against the one this
reader follows.
"""
from __future__ import annotations

import aas_submodel_validate.rules  # noqa: F401  -- every rule registers on import
from aas_submodel_validate import runner
from aas_submodel_validate.registry import all_rules


def _citing(number):
    rules = list(all_rules()) + [runner._meta_rule(False)]
    return {rule.id: rule.spec for rule in rules if number in (rule.spec or "")}


def test_every_citation_of_the_packaging_names_01005_3_0_1():
    cited = _citing("IDTA 01005")
    assert {"X2", "X4", "HD-D7", "TD-D2"} <= set(cited), cited
    assert all("IDTA 01005-3-0-1" in spec for spec in cited.values()), cited


def test_every_citation_of_the_metamodel_names_3_0():
    cited = _citing("IDTA 01001")
    assert {"X3", "META"} <= set(cited), cited
    assert all("metamodel 3.0" in spec for spec in cited.values()), cited
