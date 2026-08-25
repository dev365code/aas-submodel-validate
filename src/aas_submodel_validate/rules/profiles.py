"""Which of two templates answered, when both wear one identifier.

IDTA 02035-2 declares IDTA 02004's submodel semanticId exactly --
`0173-1#01-AHF578#003`, a ModelReference with one Submodel key, under the
same idShort -- and asks for less (docs/divergences.md #26). A file that
says AHF578 might mean either, and the identifier cannot say which.

This is not the question `detect.py` asks. That one asks whether the
input brought a submodel this tool knows at all, and it is answered from
the submodel's *main* semanticId alone -- deliberately, because a
published template wears one of our anchors in a supplemental
(tests/test_detect.py). The profile question is asked here, outside that
path, and `engine.py` and `detect.py` do not import this module.

**The answer only ever adds a sentence.** No rule is selected by it, no
element is walked differently, and the severity is `info`, which
`Report.ok` does not count -- so nothing here can move an exit code.
That restraint is the measurement, not modesty: there is no published
02035-2 *instance* anywhere to measure recall against (both published
files are `kind: Template`), so the mark's precision is known and its
recall is not. A signal like that may say something. It may not take a
check away -- and taking checks away is exactly what choosing the other
table would do, 52 rules' worth.
"""
from __future__ import annotations

from ..model import Violation
from ..registry import rule
from ..semantics import candidate_values, submodel_declares
from . import dbp_tables, hd_tables

RULE_ID = "SMT-D2"


class Profile:
    """A second published template answering to the first one's submodel
    identifier, and what an instance carries to say it means that one."""

    def __init__(self, default, default_name, alternative, name):
        self.default = default
        self.default_name = default_name
        self.alternative = alternative
        self.name = name

    @property
    def marks(self) -> frozenset:
        """What the alternative says about itself that the default does not.

        Derived from the two generated tables rather than written down: the
        value is upstream's, it is hash-verified where it lives, and a copy
        here would be a second place for it to be right. Today it is one
        SAMM URN. If upstream drops it the set empties, this rule stops
        firing, and `make exercised` says so -- the gate is already wired.
        """
        return (frozenset(self.alternative.TEMPLATE_SUPPLEMENTAL_SEMANTIC_IDS)
                - frozenset(self.default.TEMPLATE_SUPPLEMENTAL_SEMANTIC_IDS))

    @property
    def relieved(self) -> tuple:
        """Rows the default requires and the alternative does not -- either
        because it dropped the element or because it made it optional.

        All of them, not only the ones a file is asked for unconditionally.
        Six of the eleven sit under containers the template always requires,
        so a file that has any Document at all is asked for those six; the
        other five are required children
        of an optional container (`RefersToEntities`, `BasedOnReferences`,
        `TranslationOfEntities`, `DocumentedEntities`, `Entities`, each
        `0..1`). It is tempting to drop those five, because a file that
        does not use those branches will not see them above -- but a file
        that *does* use one is faulted for it, and that fault is exactly
        as much a 02004-only demand as the other six. Leaving it unnamed
        would be the under-informing half of the same mistake.
        """
        return tuple(row for row in self.default.ROWS
                     if row["card"][0] >= 1 and _relieved_by(self.alternative, row))


def _relieved_by(tables, row) -> bool:
    other = tables.BY_LABEL.get(row["label"])
    return other is None or other["card"][0] < 1


#: One pair today. IDTA 02023 and IDTA 02035-3 publish the same collision
#: (one CarbonFootprint identifier, two templates) and would be the second;
#: neither is supported yet, so neither is here.
PROFILES = (
    Profile(hd_tables, "Handover Documentation (IDTA 02004)",
            dbp_tables, "Digital Battery Passport part 2 (IDTA 02035-2)"),
)


def declared(submodel):
    """Every profile this submodel positively declares."""
    said = set()
    for supplemental in getattr(submodel, "supplemental_semantic_ids", None) or []:
        said |= candidate_values(supplemental)
    return [profile for profile in PROFILES
            if submodel_declares(submodel, profile.default.TEMPLATE_SEMANTIC_ID)
            and said & profile.marks]


@rule(RULE_ID, kind="template", prio="MAY",
      title="a submodel declaring a second template's profile is told which one answered",
      spec="IDTA 02035-2 1.0 template, submodel supplementalSemanticIds; "
           "docs/divergences.md #26, #28",
      fix="The finding names which template's requirements were applied and "
          "which requirements the two templates disagree about. If this "
          "submodel does not mean the profile it declares, remove the "
          "supplementalSemanticId that declares it.")
def smt_d2_the_report_names_the_profile(ctx):
    """Silent on the default profile, and that silence is load-bearing:
    the golden fixture and the official example must keep drawing nothing
    at all, and they carry no mark. A note on every Handover file would
    also be a note nobody reads by the third one."""
    for submodel in ctx.loaded.submodels:
        for profile in declared(submodel):
            yield Violation(
                "this submodel also declares the %s profile" % profile.name,
                subject=submodel.id_short or "submodel",
                detail="judged as %s; %s does not require %s"
                       % (profile.default_name, profile.name,
                          ", ".join("%s %s" % (row["id"], row["label"])
                                    for row in profile.relieved)))
