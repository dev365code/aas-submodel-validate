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

    def __init__(self, default, default_key, default_name, alternative, key, name):
        self.default = default
        #: What `--profile` is spelled with: the IDTA document number of
        #: the template that answers, not a word for the profile. The
        #: same collision is published a second time (IDTA 02023 and
        #: IDTA 02035-3 share one CarbonFootprint identifier), and
        #: document numbers extend to it without inventing a vocabulary.
        self.default_key = default_key
        self.default_name = default_name
        self.alternative = alternative
        self.key = key
        self.name = name

    def side(self, key):
        """(tables, name) for one of this profile's two document numbers."""
        if key == self.key:
            return self.alternative, self.name
        return self.default, self.default_name

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
    Profile(hd_tables, "02004", "Handover Documentation (IDTA 02004)",
            dbp_tables, "02035-2", "Digital Battery Passport part 2 (IDTA 02035-2)"),
)

#: Every document number `--profile` accepts, derived rather than typed
#: into the parser, so `--help` cannot name a template this tool does not
#: have a table for.
KEYS = tuple(key for profile in PROFILES
             for key in (profile.default_key, profile.key))


class Selection:
    """Which of two templates answers, for every submodel in one run.

    One object, two readers: the walk asks it which table answers, and
    `SMT-D2` asks it what to say. That is deliberate. When the walk read
    the mark for itself and the rule read it again, a change to one of
    the two readings could switch the verdict without moving the sentence
    that explains it -- and a switch nobody reports is the failure this
    whole pack has been arranged around.
    """

    def __init__(self, forced: str = None):
        self.forced = forced

    def chosen(self, submodel):
        """(profile, tables, name, why) for a submodel in a profile pair,
        or None for a submodel that is not in one. `why` is None when
        nothing overrode the default."""
        for profile in PROFILES:
            if not submodel_declares(submodel, profile.default.TEMPLATE_SEMANTIC_ID):
                continue
            if self.forced in (profile.default_key, profile.key):
                tables, name = profile.side(self.forced)
                return profile, tables, name, "--profile %s" % self.forced
            return profile, profile.default, profile.default_name, None
        return None

    def answers(self, submodel, tables) -> bool:
        picked = self.chosen(submodel)
        return True if picked is None else picked[1] is tables


def _marks_of(submodel) -> frozenset:
    """Everything this submodel says about itself besides its identifier."""
    said = set()
    for supplemental in getattr(submodel, "supplemental_semantic_ids", None) or []:
        said |= candidate_values(supplemental)
    return frozenset(said)


def declared(submodel):
    """Every profile this submodel positively declares."""
    said = _marks_of(submodel)
    return [profile for profile in PROFILES
            if submodel_declares(submodel, profile.default.TEMPLATE_SEMANTIC_ID)
            and said & profile.marks]


@rule(RULE_ID, kind="template", prio="MAY",
      title="the report names which of two templates sharing one identifier answered",
      spec="IDTA 02035-2 1.0 template, submodel supplementalSemanticIds; "
           "docs/divergences.md #26, #28",
      fix="Check that the template named here is the one this submodel "
          "means. `--profile` chooses the other one without editing the "
          "file; a submodel that does not mean the profile it declares "
          "should drop the supplementalSemanticId that declares it.")
def smt_d2_the_report_names_the_profile(ctx):
    """Silent when the default answered and nothing said otherwise, which
    is load-bearing: the golden fixtures and the official example must
    keep drawing nothing at all.

    It reads the same `Selection` the walk reads. Two readings of one
    question is how a verdict changes without the sentence that explains
    it changing with it -- and a switch nobody reports is the failure
    this whole pack has been arranged around.
    """
    for submodel in ctx.loaded.submodels:
        picked = ctx.selection.chosen(submodel)
        if picked is None:
            continue
        profile, tables, name, why = picked
        declared = bool(_marks_of(submodel) & profile.marks)
        if tables is profile.default and not declared:
            continue
        said = ("; this submodel declares %s" % profile.name) if declared else ""
        yield Violation(
            "judged as %s%s" % (name, " (%s)" % why if why else ""),
            subject=submodel.id_short or "submodel",
            detail="%s and %s disagree about %s%s"
                   % (profile.default_name, profile.name,
                      ", ".join("%s %s" % (row["id"], row["label"])
                                for row in profile.relieved), said))
