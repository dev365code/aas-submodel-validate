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

**The mark reports; `--profile` chooses.** That split is the
measurement, not modesty: no published 02035-2 *instance* exists
anywhere (both published files are `kind: Template`), so the mark's
precision is known and its recall is not, and a signal like that may say
something without taking a check away. Judging by the other table takes
21 checks away and turns 19 of them from a failed build into a passing
one, so an operator asks for it in as many words. docs/divergences.md
#30 has the numbers.

What this module does move is the walk: `Selection` is carried on the
context and `engine.matched_submodels` asks it which table answers. The
same object answers `SMT-D2`, so a verdict cannot change without the
sentence that explains it -- but only within one profile pair. A pair
says nothing about a third pack's table, and the first version of
`answers` said False to those too, silently.
"""
from __future__ import annotations

from ..model import Violation
from ..registry import rule
from ..semantics import candidate_values, submodel_declares
from . import dbp_tables, hd_tables
from .detect import instances

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
        SAMM URN. If upstream drops it the set empties and the
        marked-submodel fixtures in `test_profiles` go red -- coverage
        alone would not notice, because the rule still fires under
        `--profile`. (This sentence first named `make exercised` as the
        gate, which was the wrong one: measured, emptying the set leaves
        that gate green.)
        """
        return (frozenset(self.alternative.TEMPLATE_SUPPLEMENTAL_SEMANTIC_IDS)
                - frozenset(self.default.TEMPLATE_SUPPLEMENTAL_SEMANTIC_IDS))

    @property
    def not_asked(self) -> tuple:
        """Every check the default makes that the alternative does not.

        Three kinds, and the report names all three because each one is a
        question that stops being asked: rows the alternative has no
        entry for at all, rows it keeps but no longer requires, and hand
        rules whose elements it dropped entirely. The last kind leaves no
        other trace -- a missing StatusSetDate rule is not a row anybody
        can look up -- so naming it is the only way a reader learns it
        went. Measured rather than listed: 16 + 2 + 3.
        """
        from . import handover
        absent = tuple(row for row in self.default.ROWS
                       if row["label"] not in self.alternative.BY_LABEL)
        relaxed = tuple(row for row in self.default.ROWS
                        if row["label"] in self.alternative.BY_LABEL
                        and row["card"][0] >= 1
                        and self.alternative.BY_LABEL[row["label"]]["card"][0] == 0)
        hand = tuple(sorted(handover.answerable(self.default)
                            - handover.answerable(self.alternative)))
        return absent, relaxed, hand

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
        """Does `tables` answer for this submodel?

        A profile pair decides between *its own two* tables and says
        nothing about anybody else's. A submodel can declare more than one
        identifier -- `candidate_values` collects every key of the
        reference on purpose (docs/divergences.md #38) -- and the first
        version of this returned False for every table but the chosen one,
        so a Technical Data submodel that also named 02004's anchor lost
        the whole 02003 pack, silently.
        """
        picked = self.chosen(submodel)
        if picked is None:
            return True
        profile, chosen, _name, _why = picked
        if tables not in (profile.default, profile.alternative):
            return True
        return chosen is tables


def _marks_of(submodel) -> frozenset:
    """Everything this submodel says about itself besides its identifier."""
    said = set()
    for supplemental in getattr(submodel, "supplemental_semantic_ids", None) or []:
        said |= candidate_values(supplemental)
    return frozenset(said)

@rule(RULE_ID, kind="template", prio="MAY",
      title="the report names which of two templates sharing one identifier answered",
      spec="IDTA 02035-2 1.0 template, submodel supplementalSemanticIds; "
           "docs/divergences.md #26, #28",
      # Unreachable: the rule sets `_remedy(...)` on its one violation.
      # Kept and pinned, and worth reading beside what does ship -- this
      # sentence still ends with the advice `_remedy` was rewritten to
      # stop giving, which is what an unread copy does.
      fix="Check that the template named here is the one this submodel "
          "means. `--profile` chooses the other one without editing the "
          "file; a submodel that does not mean the profile it declares "
          "should drop the supplementalSemanticId that declares it.")
def smt_d2_the_report_names_the_profile(ctx):
    """Silent only when nothing was chosen and nothing was declared: no
    flag, no mark, the default answering as it always would. That silence
    is load-bearing -- the golden fixtures and the official example must
    keep drawing nothing at all -- and it is the only silence there is.
    An explicit `--profile`, even one that picks the template that would
    have answered anyway, is a choice a stored report has to carry.

    It reads the same `Selection` the walk reads. Two readings of one
    question is how a verdict changes without the sentence that explains
    it changing with it.
    """
    for submodel in instances(ctx.loaded):
        picked = ctx.selection.chosen(submodel)
        if picked is None:
            continue
        profile, tables, name, why = picked
        declared = bool(_marks_of(submodel) & profile.marks)
        if tables is profile.default and not declared and why is None:
            continue
        yield Violation(
            "judged as %s%s" % (name, " (%s)" % why if why else ""),
            subject=submodel.id_short or "submodel",
            detail=_what_the_choice_cost(profile, tables)
                   + ("; this submodel declares %s" % profile.name
                      if declared and tables is profile.default else ""),
            fix=_remedy(profile, tables))


def _what_the_choice_cost(profile, tables) -> str:
    absent, relaxed, hand = profile.not_asked
    total = len(absent) + len(relaxed) + len(hand)
    if tables is profile.default:
        # Named, not counted, in this direction. This is the run where the
        # reader has findings in front of them and needs to know which of
        # them the other template would not have asked for -- the count
        # alone leaves them to work that out from two specifications.
        return ("%s also answers to this identifier and asks %d fewer things; "
                "this run asked all of them, including %s"
                % (profile.name, total,
                   ", ".join(row["label"] for row in profile.relieved)))
    return ("%d checks %s makes are not made here: %d elements this template "
            "does not have (%s), %d it no longer requires (%s), and %d rules "
            "whose elements it dropped (%s)"
            % (total, profile.default_name,
               len(absent), ", ".join(row["label"] for row in absent),
               len(relaxed), ", ".join(row["label"] for row in relaxed),
               len(hand), ", ".join(suffix.lstrip("-") for suffix in hand)))


def _remedy(profile, tables) -> str:
    """What to do about it, and what each choice costs.

    The first version of this sentence offered dropping the
    supplementalSemanticId as a remedy, which a reader under six errors
    would reasonably reach for -- and which removes the only line in the
    report that explains them while changing no finding. So the flag
    comes first and the deletion is described with its price.
    """
    if tables is profile.default:
        return ("If this submodel means %s, run --profile %s; nothing in the "
                "file has to change for that." % (profile.name, profile.key))
    return ("If this submodel means %s instead, run --profile %s. Removing "
            "the supplementalSemanticId that declares the profile changes no "
            "finding and removes this explanation of them."
            % (profile.default_name, profile.default_key))
