"""A rule id is a contract: registered once, forever findable."""
import pathlib
import re
import subprocess

import pytest

from aas_submodel_validate import loader, registry, runner
from aas_submodel_validate import rules as _rules  # noqa: F401 - registers
from aas_submodel_validate.model import KINDS, Severity, Violation
from aas_submodel_validate.registry import all_rules
from aas_submodel_validate.rules import container as container_rules
from aas_submodel_validate.rules import (
    dbp_tables,
    engine,
    handover,
    hd_tables,
    profiles,
    td_tables,
)
from aas_submodel_validate.runner import _meta_rule


def test_registration_and_lookup(monkeypatch):
    monkeypatch.setattr(registry, "_registry", {})

    @registry.rule("Z1", kind="container", prio="MUST", title="a test rule",
                   fix="mend it")
    def z1(ctx):
        yield Violation("broken")

    (rule,) = registry.all_rules()
    assert (rule.id, rule.kind, rule.fix) == ("Z1", "container", "mend it")


def test_a_duplicate_id_is_refused(monkeypatch):
    monkeypatch.setattr(registry, "_registry", {})

    @registry.rule("Z1", kind="container", prio="MUST", title="first", fix="f")
    def one(ctx):
        return ()

    with pytest.raises(ValueError, match="Z1"):
        @registry.rule("Z1", kind="container", prio="MUST", title="second", fix="f")
        def two(ctx):
            return ()


def test_every_registered_rule_names_its_remedy(monkeypatch):
    """A validator that names a defect without naming the remedy has told
    you something is wrong and left you the expertise. Refused at the
    registration boundary, not by a later audit."""
    monkeypatch.setattr(registry, "_registry", {})
    with pytest.raises(ValueError, match="fix"):
        @registry.rule("Z2", kind="container", prio="MUST", title="no remedy")
        def bad(ctx):
            return ()


def test_a_kind_the_report_cannot_read_is_refused(monkeypatch):
    """`kind` reaches two table lookups and a published field. The
    reading order's lookup used to fall back, so a rule registered as
    `tempalte` sorted where lints sort -- into the middle of the channels
    a reader is scanning rather than beside the other template findings
    -- and the JSON report carried the typo out to whoever reads `kind`.
    Nothing anywhere said so."""
    monkeypatch.setattr(registry, "_registry", {})
    with pytest.raises(ValueError, match="tempalte"):
        @registry.rule("Z3", kind="tempalte", prio="MUST", title="a typo", fix="f")
        def bad(ctx):
            return ()


def test_a_priority_that_scores_as_nothing_is_refused(monkeypatch):
    """Worse than the kind, because it moves the verdict: severity is
    looked up from `prio`, and the lookup fell back to *warning*. A MUST
    typed `MSUT` stopped counting as an error, so the file it condemned
    came back `ok` and the run exited 0 -- a validator silently agreeing
    with a document it had just found a MUST violation in."""
    monkeypatch.setattr(registry, "_registry", {})
    with pytest.raises(ValueError, match="MSUT"):
        @registry.rule("Z4", kind="template", prio="MSUT", title="a typo", fix="f")
        def bad(ctx):
            return ()


def test_the_gate_admits_every_kind_the_vocabulary_names(monkeypatch):
    """A gate that refused a legitimate kind would be found by whoever
    added the rule, loudly; asserted anyway, because the cost of finding
    it that way is somebody's afternoon."""
    monkeypatch.setattr(registry, "_registry", {})
    for kind in KINDS:
        @registry.rule("Z-%s" % kind, kind=kind, prio="MUST", title=kind, fix="f")
        def fine(ctx):
            return ()
    assert len(registry.all_rules()) == len(KINDS)


#: The one kind no rule registers. The metamodel channel is relayed from
#: aas-core3.0 and built by hand in `runner`, deliberately outside the
#: registry, and this project re-implements no AASd constraint -- so a
#: registered rule wearing `meta` would be that promise breaking.
UNREGISTERED_KINDS = {"meta"}


def test_every_kind_in_the_vocabulary_has_a_user():
    """The other direction, and the one that needed writing.

    The test this replaced emptied the registry, registered one rule per
    kind and then asserted that the kinds it had just registered were the
    kinds in the list. It could not fail. A fifth kind added to `KINDS`
    and used by nothing passed it, which is exactly the case its
    docstring named.

    Asked of the real registry, so the vocabulary cannot grow a word
    nobody says, and `meta` cannot quietly acquire a registered rule."""
    registered = {rule.kind for rule in all_rules()}
    assert registered, "nothing registered at all -- this test proves nothing"
    assert registered <= set(KINDS), "a rule wears a kind the report cannot read"
    assert set(KINDS) - registered == UNREGISTERED_KINDS
    assert _meta_rule(strict=False).kind in UNREGISTERED_KINDS


#: What a rule's priority decides is whether a build stops. `MUST` is an
#: error and sets the exit code; `SHOULD` and `MAY` do not. Both
#: directions are one word away and both are observable:
#:
#: - `MUST` -> `SHOULD` finds the violation and exits 0, which is a
#:   conformance tool agreeing with a file it has just failed.
#: - `SHOULD` -> `MUST` fails a file that was conformant.
#:
#: Measured with this list deselected, one rule's word at a time, whole
#: suite each time: **11 of the 16 MUSTs could become warnings and 9 of
#: the 21 others could become errors, all green.**
#:
#: An earlier note here said the promotions were caught and the demotions
#: were not, and said it from a glance rather than a run. Both halves are
#: wrong. Five demotions were caught (HD-D2, HD-D8, SMT-D1, X1, X5) and
#: nine promotions were not (DBP2-D10, DBP2L2, DBP2L3, DBP2L4, DBP2L5,
#: HDL4, TD-D3, TDL1, TDL2). Neither direction was guarded; promotions
#: were guarded better, not caught. And "no fixture asserts a severity"
#: was false when it was written -- twelve did (two in
#: `test_dbp_hand_rules`, seven in `test_hand_rules`, and one each in
#: `test_detect`, `test_profiles` and `test_spec_accuracy`), and two of
#: them are what caught HD-D5 and HD-D9. Counted from the tree this time,
#: which is the only reason this number is different from the last one. The lesson is not about severities. Counting
#: what a suite covers by reading it, rather than by breaking the thing
#: and watching, is how all three sentences came out wrong at once.
#:
#: The pattern in what survived is worth keeping: **nine of the twenty
#: holes are the DBP2 pack**, which is a third of the rules. Its fixtures
#: were built to prove the pack answers at all, and a rule that fires
#: proves nothing about the column it fires in.
#:
#: Read down the columns rather than the rows, and note that the two
#: kinds of rule are graded on different questions:
#:
#: - **Template MUST** is what the template obliges: the mandatory
#:   classification, its English name, its class from the published
#:   twelve, files that exist, dates that are dates.
#: - **Container MUST** is what leaves nothing judged at all -- X1-X3 and
#:   X5 stop the read, SMT-D1 leaves no table able to answer. X4 sits at
#:   SHOULD under that same question and not by oversight: a dangling
#:   aas-suppl relationship is a broken promise about packaging, and
#:   every template verdict still stands. It reads as an asymmetry
#:   against HD-D7/TD-D2, which are MUST for a file the archive does not
#:   hold; the difference is which question goes unanswered, not which
#:   byte-stream is missing.
#: - **SHOULD** is interoperability and the readings this project prefers
#:   without insisting: a PDF/A rendition, a primary identifier, the
#:   status vocabulary, references that resolve, near-misses, duplicates,
#:   the canonical spelling, declared supplementary parts.
#: - **MAY** is idShort patterns and reference types -- tidiness -- plus
#:   SMT-D2, which is not tidiness and is not a defect finding either.
#:   It names which of two templates answered, and that sentence moves
#:   21 rule ids and flips 19 verdicts (docs/divergences.md #30). It is
#:   provenance wearing a finding's shape because every rule must carry a
#:   remedy, and it is at `info` so the exit code stays the answering
#:   template's business (#28).
MUST_RULES = {
    "DBP2-D2", "DBP2-D3", "DBP2-D4", "DBP2-D7",
    "HD-D2", "HD-D3", "HD-D4", "HD-D7", "HD-D8",
    "SMT-D1", "TD-D1", "TD-D2", "X1", "X2", "X3", "X5",
}
SHOULD_RULES = {
    "BAT-R2", "BAT-R8",
    "DBP2-D5", "DBP2-D10", "DBP2L2", "DBP2L4", "DBP2L5",
    "HD-D5", "HD-D6", "HD-D9", "HD-D10", "HDL2", "HDL4", "HDL5",
    "TD-D3", "TDL1", "X4",
}
MAY_RULES = {"DBP2L1", "DBP2L3", "HDL1", "HDL3", "SMT-D2", "TDL2"}

#: The generated rules are not listed one by one: a row's rule reports
#: what the vendored template states about that element -- how many, what
#: kind, and which valueType -- so all of them are `MUST` and the
#: byte-compare gate holds the table they come from. What is asserted is
#: that none of them has drifted off it.
#:
#: Two things that blanket word is quiet about, kept here because the
#: place to argue a severity is beside the list of them:
#:
#: - Four 02003 rows (TD-E08, TD-E12, TD-E21, TD-E26) come from elements
#:   the template gives no `SMT/Cardinality` at all. Their `0..*` is read
#:   from the PDF's element tables (#20), so their rules can report a
#:   kind and never a count, and the generated remedy asks for "any
#:   number" of something at MUST severity. `rules/td.py` says so in the
#:   spec string; this says so beside the severity.
#: - 24 of the 86 rows are `0..1`, where the rule can only ever fire on
#:   the *upper* bound -- two of something the template allows one of.
#:   That is where divergence #32 lives: a wider match set makes a capped
#:   row stricter, and one profile's error is the other's clean file. At
#:   MUST it exits 1.
#:
#: `\d+`, not `\d\d`: the generator formats ids with `%02d`, a *minimum*
#: width, so a 100th row in a pack is `HD-E100` and `\d\d` would not
#: match it. That is the semantic half. The failure-message half needs
#: the assertion below to compare sets before it compares counts -- under
#: `\d\d` an `HD-E100` fell through to the hand census, which named it;
#: under `\d+` it lands here, and a bare `assert 87 == 86` above a
#: truncated repr of 87 Rule objects names nothing. Widening the pattern
#: without moving that assertion would have made the case it was widened
#: for worse.
GENERATED_ID = re.compile(r"^(HD|TD|DBP2)-E\d+$")


def test_every_generated_rule_stops_a_build():
    """A generated row says what the template obliges, so a row's rule
    failing is a file failing. One of them at `SHOULD` would report a
    cardinality the template states and let the build through."""
    generated = [rule for rule in all_rules() if GENERATED_ID.match(rule.id)]
    # The ids first, against the tables they are generated from, so a row
    # that appears or disappears is named rather than counted. Then the
    # count, which is the number this project quotes in its README.
    assert {rule.id for rule in generated} == {
        row["id"] for tables in (hd_tables, td_tables, dbp_tables)
        for row in tables.ROWS}
    assert len(generated) == 86
    assert {rule.prio for rule in generated} == {"MUST"}


def test_the_hand_rules_have_the_severities_that_were_decided():
    """Every hand-written rule, in the column somebody put it in.

    Both directions matter and neither was held: promotions only by
    accident, demotions not at all."""
    hand = [rule for rule in all_rules() if not GENERATED_ID.match(rule.id)]
    # The set comparisons first, because they name the rule: a new id
    # prints as `{'HDZ9'}` against an empty diff. The count last, where
    # it can only report a duplicate -- when it ran first it printed
    # `assert 38 == 37` above a truncated repr of every Rule object, and
    # a reader had to go and find which one was new.
    assert {r.id for r in hand if r.severity is Severity.ERROR} == MUST_RULES
    assert {r.id for r in hand if r.severity is Severity.WARNING} == SHOULD_RULES
    assert {r.id for r in hand if r.severity is Severity.INFO} == MAY_RULES
    # No count here. `Severity` has exactly these three members and the
    # registry refuses any other priority, so the three subsets partition
    # `hand`; if all three match, the ids agree and so does the arity.
    # The count that was here read as a fourth check and was none -- it
    # could not fail, and an assertion that cannot fail reads as a gate.


#: Every rule-id namespace this tool registers, as the whole shape of an
#: id rather than a prefix, and what asks the question. A pack that starts
#: registering adds a line; a pack that stops empties one. Both are diffs
#: somebody has to justify.
#:
#: Whole shapes because a prefix is a wildcard: `"X"` admitted `XT-E01`
#: and `XYZ99`, so an entire pack installed under the letter X passed the
#: census as container rules.
NAMESPACES = {
    r"BAT-R\d+": "IDTA 02035 battery passport, read against the regulation",
    r"X\d+": "the AASX/OPC container the submodel arrived in",
    r"SMT-D\d+": "the tool's own questions, belonging to no template",
    r"HD-E\d+": "IDTA 02004, generated from the template's rows",
    r"HD-D\d+": "IDTA 02004, what the template file cannot say",
    r"HDL\d+": "IDTA 02004, informational lints",
    r"TD-E\d+": "IDTA 02003, generated from the template's rows",
    r"TD-D\d+": "IDTA 02003, what the template file cannot say",
    r"TDL\d+": "IDTA 02003, informational lints",
    r"DBP2-E\d+": "IDTA 02035-2, generated from the template's rows",
    r"DBP2-D\d+": "IDTA 02035-2, 02004's hand rules over 02035-2's table",
    r"DBP2L\d+": "IDTA 02035-2, informational lints",
}


def _namespace(rule_id):
    for pattern in NAMESPACES:
        if re.fullmatch(pattern, rule_id):
            return pattern
    return None


def test_every_registered_id_belongs_to_a_declared_namespace():
    """This replaced a guard that said "no rule id starts with DBP-",
    written to hold the boundary of the slice that vendored IDTA 02035-2's
    table without judging by it. That guard could not see the prefix being
    renamed -- it stayed green when `DBP-E` became `DBP2-E` -- and it could
    not see any other pack arriving either. A census can see both."""
    for rule in all_rules():
        assert _namespace(rule.id), \
            "%s belongs to no declared namespace; declare it or rename it" % rule.id


def test_every_declared_namespace_has_at_least_one_rule():
    """The other direction, which the guard it replaced did not have: a
    pack that quietly stops registering leaves its line here, and the
    line is what says the loss was deliberate."""
    registered = [rule.id for rule in all_rules()]
    assert registered, "nothing registered at all -- this test proves nothing"
    for namespace in NAMESPACES:
        assert [rule_id for rule_id in registered
                if _namespace(rule_id) == namespace], \
            "%s is declared and empty" % namespace

#: Every remedy this tool ships, word for word.
#:
#: A remedy is the only sentence most users read: the finding says what
#: is wrong and this says what to do about it. It is also the part of a
#: rule that no other gate can see -- the rule's logic has fixtures, its
#: severity has the census above, and its remedy had a `%s in fix` here
#: and there, which is not a gate. `assert "X4" in remedy` passes for a
#: remedy that borrows X4's requirement, which was the defect it was
#: written to catch; `assert "exactly one" not in remedy` passes for the
#: same demand in a synonym. Both were measured against a remedy rewritten
#: to be wrong, and both stayed green.
#:
#: So: the whole sentence, and a diff that has to justify itself. Three
#: things this caught on the day it was written, none of which any test
#: could see:
#:
#:   - TD-D2 demanded an `aas-suppl` relationship it does not check --
#:     the same defect that had just been fixed in HD-D7, still in its
#:     sibling.
#:   - HD-D2 told the author to write one spelling "exactly" while the
#:     rule accepts two (docs/divergences.md #9).
#:   - HD-D5 offered the template's per-DocumentId bound as evidence for
#:     something it does not bear on.
#:
#: Seven remedies here never reach a reader: HD-D9, HDL1, DBP2L1, HDL3,
#: DBP2L3, TDL2 and SMT-D2 set one on every Violation they raise, and
#: `Finding.fix` prefers that one. `SHIPPED_REMEDIES` below is where their
#: real sentences are held. They are pinned here anyway -- standing advice
#: that has stopped shipping is a thing to notice, not a thing to delete
#: quietly, and HDL1's says the opposite of what it now ships.
REMEDIES = {
    "BAT-R2":
        "Run --profile with the document number of the template you "
        "mean. This tool has a table for neither side of this "
        "collision, so the profile settles which template the file "
        "claims to be and no more -- nothing here judges it against "
        "either one.",
    "BAT-R8":
        "Provide the element, or record that this battery is outside "
        "the provision read as requiring it. The template will not ask "
        "for it -- that is the point of the finding.",
    "DBP2-D10":
        "Add a DigitalFile with contentType application/pdf (a PDF/A "
        "file, per VDI 2770) to this DocumentVersion. A content type "
        "cannot prove PDF/A conformance, so this is a warning, not an "
        "error.",
    "DBP2-D2":
        "Add a DocumentClassification whose ClassificationSystem "
        "property names VDI 2770 -- 'VDI 2770 Blatt 1:2020' is the "
        "spelling to prefer, and the template's own 'VDI2770:2020' is "
        "accepted too (docs/divergences.md #9). Pick its ClassId from "
        "the twelve VDI 2770 classes (e.g. 03-02, Operation).",
    "DBP2-D3":
        "Replace the ClassId with one of the twelve VDI 2770 Blatt "
        "1:2020 ids: 01-01, 02-01..02-04, 03-01..03-06 or 04-01.",
    "DBP2-D4":
        "Add an entry to ClassName tagged 'en' or 'EN' (a region "
        "subtag is fine); Table 1 names each class in English (for "
        "03-02 it is 'Operation').",
    "DBP2-D5":
        "Mark one of these DocumentIds with DocumentIsPrimary = true, "
        "so consumers know which identifier to file the document under. "
        "This rule asks only that one is marked. The template states no "
        "cardinality on how many may carry the flag -- its own "
        "definition calls it 'the preferred ID', singular -- so several "
        "primaries are not reported here.",
    "DBP2-D7":
        "Add the file to the .aasx under the name this File value "
        "gives, or correct the value's path. (Declaring an aas-suppl "
        "relationship for it is X4's question, not this one's.)",
    "DBP2L1":
        "Rename to the template's suggested pattern (base name plus an "
        "optional 2-3 digit suffix). Any unique idShort is legal; this "
        "is tidiness, not conformance.",
    "DBP2L2":
        "Correct the semanticId to the template's spelling; a near-miss "
        "matches nothing, and every rule that would have applied to the "
        "element silently stops applying.",
    "DBP2L3":
        "Use the reference type the template declares here; the value "
        "matched, so this is interoperability polish, not a failure.",
    "DBP2L4":
        "Give each document a distinct identifier within its domain, or "
        "merge the entries if they describe one document.",
    "DBP2L5":
        "Write ClassificationSystem exactly as 'VDI 2770 Blatt 1:2020' "
        "-- the value §2.3 says identifies the mandatory system. "
        "'VDI2770:2020' is the template's example artefact and other "
        "tools matching on the specified string will not recognise it.",
    "HD-D10":
        "Add a DigitalFile with contentType application/pdf (a PDF/A "
        "file, per VDI 2770) to this DocumentVersion. A content type "
        "cannot prove PDF/A conformance, so this is a warning, not an "
        "error.",
    "HD-D2":
        "Add a DocumentClassification whose ClassificationSystem "
        "property names VDI 2770 -- 'VDI 2770 Blatt 1:2020' is the "
        "spelling to prefer, and the template's own 'VDI2770:2020' is "
        "accepted too (docs/divergences.md #9). Pick its ClassId from "
        "the twelve VDI 2770 classes (e.g. 03-02, Operation).",
    "HD-D3":
        "Replace the ClassId with one of the twelve VDI 2770 Blatt "
        "1:2020 ids: 01-01, 02-01..02-04, 03-01..03-06 or 04-01.",
    "HD-D4":
        "Add an entry to ClassName tagged 'en' or 'EN' (a region "
        "subtag is fine); Table 1 names each class in English (for "
        "03-02 it is 'Operation').",
    "HD-D5":
        "Mark one of these DocumentIds with DocumentIsPrimary = true, "
        "so consumers know which identifier to file the document under. "
        "This rule asks only that one is marked. The template states no "
        "cardinality on how many may carry the flag -- its own "
        "definition calls it 'the preferred ID', singular -- so several "
        "primaries are not reported here.",
    "HD-D6":
        "Set StatusValue to 'InReview' or 'Released' (exact casing). "
        "The vendored concept description is where those two come "
        "from, and it says they 'should be used' -- which is why this "
        "is a warning.",
    "HD-D7":
        "Add the file to the .aasx under the name this File value "
        "gives, or correct the value's path. (Declaring an aas-suppl "
        "relationship for it is X4's question, not this one's.)",
    "HD-D8":
        "Write StatusSetDate as YYYY-MM-DD (xs:date), e.g. 2020-02-06.",
    "HD-D9":
        "Add the element the reference names to the submodel, or "
        "correct its key path; a reference that resolves to nothing "
        "points the document at nothing.",
    "HDL1":
        "Rename to the template's suggested pattern (base name plus an "
        "optional 2-3 digit suffix). Any unique idShort is legal; this "
        "is tidiness, not conformance.",
    "HDL2":
        "Correct the semanticId to the template's spelling; a near-miss "
        "matches nothing, and every rule that would have applied to the "
        "element silently stops applying.",
    "HDL3":
        "Use the reference type the template declares here; the value "
        "matched, so this is interoperability polish, not a failure.",
    "HDL4":
        "Give each document a distinct identifier within its domain, or "
        "merge the entries if they describe one document.",
    "HDL5":
        "Write ClassificationSystem exactly as 'VDI 2770 Blatt 1:2020' "
        "-- the value §2.3 says identifies the mandatory system. "
        "'VDI2770:2020' is the template's example artefact and other "
        "tools matching on the specified string will not recognise it.",
    "SMT-D1":
        "If the submodel means one of the templates this tool has a "
        "table for, give it that template's semanticId: "
        "0173-1#01-AHF578#003 for Handover Documentation (IDTA "
        "02004); 0173-1#01-AHX837#002 for Technical Data (IDTA "
        "02003). If it means a template this tool has no table for, "
        "leave the identifier alone -- it is doing its job, and this "
        "finding only says nothing here judged the submodel against a "
        "template.",
    "SMT-D2":
        "Check that the template named here is the one this submodel "
        "means. `--profile` chooses the other one without editing the "
        "file; a submodel that does not mean the profile it declares "
        "should drop the supplementalSemanticId that declares it.",
    "TD-D1":
        "Write ValidDate as YYYY-MM-DD (xs:date), e.g. 2025-03-15.",
    "TD-D2":
        "Add the file to the .aasx under the name this File value "
        "gives, or correct the value's path. (Declaring an aas-suppl "
        "relationship for it is X4's question, not this one's.)",
    "TD-D3":
        "Add the element this reference names to the submodel, or "
        "correct its key path; a key into the property-area list may "
        "be a position counted from zero, or an idShort where one "
        "exists.",
    "TDL1":
        "Correct the semanticId to the template's spelling; a near-miss "
        "matches nothing, and every rule that would have applied to the "
        "element silently stops applying.",
    "TDL2":
        "Use the reference type the template declares here; the value "
        "matched, so this is interoperability polish, not a failure.",
    "X1":
        "Re-create the .aasx with an AAS packaging tool: either what is "
        "on disk is not a ZIP archive at all, or the archive describes "
        "one of its parts in a way that makes the part unreadable.",
    "X2":
        "Repair the chain: _rels/.rels names an aasx-origin part, whose "
        "own .rels names the aas-spec payload. AAS packaging tools "
        "write this automatically; hand-built ZIPs almost never do.",
    "X3":
        "Open the named document and fix the syntax its parser rejects; "
        "the extension decides the format (.json as AAS JSON, otherwise "
        "AAS XML).",
    "X4":
        "Add the missing part to the archive or delete the aas-suppl "
        "relationship that names it; a declared file a consumer cannot "
        "extract is a broken promise either way.",
    "X5":
        "This reader takes in no single document over 64 MiB, and no "
        "container whose parts come to over 256 MiB together. Nothing "
        "is wrong with what you sent; it was refused, not judged. Where "
        "the input is a container, send the part that needs checking on "
        "its own or split the container.",
}


def test_every_rule_says_where_its_requirement_lives():
    """`docs/report-schema.md` says `spec` is always there, so it has to
    be. A rule that reports a defect and cannot say what it is reading
    from is asking to be taken on trust, which is the one thing this
    tool is not for -- and a schema that offers `null` teaches every
    consumer to write a branch nothing will ever take."""
    # The relayed channel too. It is deliberately not a registered
    # rule, so `all_rules()` cannot see it -- and it produces 77 of the
    # 87 findings on the official example, which makes it the largest
    # thing this gate was written for and the one it could not reach.
    from aas_submodel_validate import runner
    channels = list(all_rules()) + [runner._meta_rule(False)]
    silent = sorted(rule.id for rule in channels if not (rule.spec or "").strip())
    assert not silent, (
        "these rules name no source for what they require: %s" % silent)


def test_every_remedy_is_the_sentence_that_was_decided():
    """What a user is told to do, held to the word.

    Not `in`: a substring assertion cannot tell a remedy from a remedy
    with an extra demand bolted on, and that is exactly the drift this
    is here for."""
    assert {rule.id: rule.fix for rule in all_rules()
            if not GENERATED_ID.match(rule.id)} == REMEDIES


def test_every_rule_offers_a_remedy():
    """Including the generated ones, whose remedies are the generator's
    and are not pinned here -- it writes one sentence per row from the
    row itself, and the byte-compare gate holds the table."""
    for rule in all_rules():
        assert rule.fix and rule.fix.strip(), rule.id

#: The sentences a *violation* carries -- which is what a reader gets.
#: `Finding.fix` is `violation.fix or rule.fix`, so wherever a rule sets a
#: remedy per violation, the census above pins a string that never leaves
#: the process. Seven rules do -- HD-D9, HDL1, DBP2L1, HDL3, DBP2L3, TDL2
#: and SMT-D2 -- and three more relay one from the loader (X2, X3, X5).
#: Measured before this existed: changes to these sentences left
#: the whole suite green,
#: including ones that turn "nothing is wrong with what you sent" into
#: blaming the author -- which `x5_within_the_readers_bounds` exists to
#: promise it will not do.
#:
#: Generated by calling the thing that builds them over its whole input,
#: rather than by collecting what fixtures happened to produce: a census
#: taken from the fixtures cannot see a sentence no fixture reaches, and
#: those are the ones nothing else is watching either.
SHIPPED_REMEDIES = {
    "HD-D9/DocumentedEntity":
        "Add the element this DocumentedEntity names to the submodel, "
        "or correct the reference's key path; a reference that "
        "resolves to nothing points the document at nothing.",
    "HD-D9/RefersTo":
        "Add the element this RefersTo names to the submodel, or "
        "correct the reference's key path; a reference that resolves "
        "to nothing points the document at nothing.",
    "HD-D9/BasedOn":
        "Add the element this BasedOn names to the submodel, or "
        "correct the reference's key path; a reference that resolves "
        "to nothing points the document at nothing.",
    "HD-D9/TranslationOf":
        "Add the element this TranslationOf names to the submodel, or "
        "correct the reference's key path; a reference that resolves "
        "to nothing points the document at nothing.",
    "reftype/ExternalReference":
        "Use an ExternalReference here, as the template does; the "
        "value matched, so this is interoperability polish, not a "
        "failure.",
    "reftype/ModelReference":
        "Use a ModelReference here, as the template does; the value "
        "matched, so this is interoperability polish, not a failure.",
    "SMT-D2/judged-as-02004":
        "If this submodel means Digital Battery Passport part 2 (IDTA "
        "02035-2), run --profile 02035-2; nothing in the file has to "
        "change for that.",
    "SMT-D2/judged-as-02035-2":
        "If this submodel means Handover Documentation (IDTA 02004) "
        "instead, run --profile 02004. Removing the "
        "supplementalSemanticId that declares the profile changes no "
        "finding and removes this explanation of them.",
    "HDL1/inside-a-list":
        "Remove this idShort. A submodel element directly inside a "
        "SubmodelElementList must not carry one (AASd-120), so "
        "renaming it to the template's suggestion leaves a metamodel "
        "violation the file already has.",
    "HDL1/anywhere-else":
        "Rename to the template's suggested pattern "
        r"(^DigitalFile(?:\d{2,3})?$). Any unique idShort is legal "
        "here; this is tidiness, not conformance.",
    "X5/environment-json":
        "This reader takes in no single document over 64 MiB. An "
        "environment divides along its submodels, so fewer of them "
        "per file is the way through; one holding a single submodel "
        "does not divide, and a file that large cannot be checked "
        "here. Nothing is wrong with what you sent; it was refused, "
        "not judged.",
    "X5/environment-xml":
        "This reader takes in no single document over 64 MiB. An "
        "environment divides along its submodels, so fewer of them "
        "per file is the way through; one holding a single submodel "
        "does not divide, and a file that large cannot be checked "
        "here. Nothing is wrong with what you sent; it was refused, "
        "not judged.",
    "X5/submodel-json":
        "This reader takes in no single document over 64 MiB. An "
        "environment divides along its submodels, so fewer of them "
        "per file is the way through; one holding a single submodel "
        "does not divide, and a file that large cannot be checked "
        "here. Nothing is wrong with what you sent; it was refused, "
        "not judged.",
    "runner/a-rule-that-crashed":
        "This is a defect in the validator, not in your file; please "
        "report it.",
    "runner/the-metamodel-channel":
        "Fix the constraint aas-core3.0 names; these are IDTA 01001 "
        "metamodel rules, upstream of any template.",
    "loader/payload-doctype":
        "Remove the DTD and write out whatever it declared: a "
        "nested-entity DTD is a decompression-free way to exhaust a "
        "reader, so this one refuses the declaration rather than try "
        "to bound what it expands to. Nothing is wrong with the "
        "syntax; it is the declaration this reader will not take in.",
    "loader/directory-bound":
        "This reader indexes no archive whose directory of names "
        "comes to more than 16 MiB -- a ZIP is indexed whole before "
        "any of it is read, so the cost is paid on the names alone, "
        "however little the entries hold. Remove what the package "
        "does not need to carry. Nothing is wrong with what you sent; "
        "it was refused, not judged.",
    "loader/relationship-doctype":
        "Remove the DTD from the named relationships part and write "
        "out whatever it declared. The chain itself is intact -- it "
        "names the parts it should -- and a nested-entity DTD is a "
        "decompression-free way to exhaust a reader, so this one "
        "refuses the declaration rather than bound what it expands "
        "to.",
    "generated/0..1":
        "Provide at most one 'DocumentIsPrimary' element(s) under "
        "DocumentId with semanticId 0173-1#02-ABH995#003; example "
        "value: 'true'.",
    "generated/0..n":
        "Provide any number of 'ProductImage' element(s) under "
        "ProductImages with semanticId "
        "0173-1#02-ABM220#001/0173-1#01-AHY911#001.",
    "generated/1..1":
        "Provide exactly one 'Documents' element(s) with semanticId "
        "0173-1#02-ABI500#003.",
    "generated/1..n":
        "Provide one or more 'Document' element(s) under Documents "
        "with semanticId 0173-1#02-ABI500#003/0173-1#01-AHF579#003.",
}


def test_every_sentence_a_violation_carries_is_the_one_that_was_decided():
    """The other half of the remedy census, and the half a user reads."""
    built = {}
    for label in D9_LABELS:
        built["HD-D9/%s" % label] = handover.dangling_remedy(label)
    for reference_type in REFERENCE_TYPES:
        built["reftype/%s" % reference_type] = engine.reftype_remedy(reference_type)
    for profile in profiles.PROFILES:
        built["SMT-D2/judged-as-%s" % profile.default_key] = _rules.profiles._remedy(
            profile, profile.default)
        built["SMT-D2/judged-as-%s" % profile.key] = _rules.profiles._remedy(
            profile, profile.alternative)
    for in_list, tag in ((True, "inside-a-list"), (False, "anywhere-else")):
        built["HDL1/%s" % tag] = engine.idshort_remedy(in_list, IDSHORT_PATTERN)
    for form in NON_CONTAINER_FORMS:
        built["X5/%s" % form] = container_rules._bounds_remedy(form)
    built["runner/a-rule-that-crashed"] = runner.CRASH_REMEDY
    built["runner/the-metamodel-channel"] = runner.META_REMEDY
    built["loader/payload-doctype"] = loader.PAYLOAD_DOCTYPE_REMEDY
    built["loader/directory-bound"] = loader.directory_bound_remedy()
    built["loader/relationship-doctype"] = loader.RELATIONSHIP_DOCTYPE_REMEDY
    for card, row in _one_row_per_cardinality().items():
        built["generated/%s..%s" % (card[0], "n" if card[1] is None else card[1])] = row["fix"]
    assert built == SHIPPED_REMEDIES


def test_the_article_is_right_for_a_type_the_walk_cannot_hand_it():
    """`"" in "AEIOU"` is True, so an empty type would read "an ", and a
    lowercase one would read "a externalReference".

    Neither is reachable through the walk, which reports drift only
    against a row that declares a type and only for the two the metamodel
    has. It is reachable through the function, which is half the point of
    there being a function: this arithmetic existed in two copies, one
    was corrected and the other was not, and no fixture could tell them
    apart because the inputs that separate them never arrive."""
    assert engine.reftype_remedy("").startswith("Use a ")
    assert engine.reftype_remedy("externalReference").startswith("Use an ")
    assert engine.reftype_remedy("modelReference").startswith("Use a ")


def test_a_container_is_told_where_to_divide_and_a_document_is_not():
    """`_bounds_remedy` returns nothing for a container, because X5's own
    remedy already says how to split one and a second sentence saying it
    differently is worse than one. The `None` is the decision."""
    assert container_rules._bounds_remedy("aasx") is None


#: The four labels HD-D9 reads -- read out of the roster, not written
#: again here.
#:
#: A copy was written here first, and it made this census measure itself:
#: adding a fifth label to the rule changed what shipped and left the
#: expectations alone, so the sentence for it went out unpinned. The
#: direction that did fail -- editing this tuple by itself -- is the edit
#: nobody makes. The roster is where a rule declares what it navigates,
#: and `test_pack_roster` already holds the rule's own loop against it.
D9_LABELS = next(entry[6] for entry in handover.ROSTER if entry[0] == "-D9")
REFERENCE_TYPES = ("ExternalReference", "ModelReference")

#: Every form the loader can record that is not a container. `X5`'s
#: remedy differs between a container -- which its own rule already tells
#: how to split -- and a bare document, and the first version of this
#: census asked for `"json"`, which is not a form this code produces.
#: Calling a builder with an input it never receives is a census of a
#: sentence nobody gets.
NON_CONTAINER_FORMS = ("environment-json", "environment-xml", "submodel-json")


def _one_row_per_cardinality():
    """One generated row per cardinality the tables use.

    The 86 generated remedies are written by `tools/extract_smt_rules.py`
    from four sentence shapes, and none of them was held by anything: the
    byte-compare gate holds table-against-generator, not
    sentence-against-decision, so editing the generator's wording and
    regenerating passed every gate. Four rows pin the four shapes; the
    generator cannot change one without changing all of its kind."""
    seen = {}
    for tables in (hd_tables, td_tables, dbp_tables):
        for row in tables.ROWS:
            seen.setdefault(row["card"], row)
    return seen


#: The pattern the sentence quotes. Read from the table rather than
#: written out, because the census is about the sentence and the table
#: has its own byte-compare gate.
IDSHORT_PATTERN = next(row["allowed_idshort"] for row in hd_tables.ROWS
                       if row["label"] == "DigitalFile")


def test_the_refusal_lists_the_priorities_in_reading_order():
    """The ValueError for an unknown priority names the known ones,
    sorted -- a stable sentence, so two people hitting it file one bug."""
    with pytest.raises(ValueError) as caught:
        registry.rule("ZZ-TEST", kind="template", prio="MSUT",
                      title="t", fix="f")(lambda ctx: ())
    assert "MAY, MUST" in str(caught.value)


def test_the_decorator_hands_the_function_back():
    """`@rule` returns what it was given, so the module-level name stays
    callable. Returning None poisons the name silently: every use through
    the registry still works -- the function was stored before the
    return -- and the first direct call is a TypeError."""
    from aas_submodel_validate.rules import container as _c
    assert callable(_c.x1_is_a_zip)



ROOT = pathlib.Path(__file__).resolve().parents[1]

def test_every_divergence_this_project_cites_exists():
    """A pointer to a chosen reading is only worth the reading it
    reaches.

    Three files said a decision was recorded at `docs/divergences.md`
    #4 and #4 records something else -- the decision they meant was not
    in the document at all. That was found by reading, which does not
    scale to the twenty-odd citations scattered through the code and
    the suite. It scales to a gate.

    The number existing is what can be checked here; whether the row
    says what the citing line thinks it says cannot be, and is why the
    rows are written as observation and reading rather than as a
    label."""
    rows = {int(line.split("|")[1].strip())
            for line in (ROOT / "docs" / "divergences.md").read_text("utf-8").splitlines()
            if re.match(r"^\|\s*\d+\s*\|", line)}
    assert len(rows) > 30, "the divergences table did not parse"
    # Numbered 1..N with nothing missing. Without this, a dangling
    # citation could be answered by appending a row with that number and
    # nothing in it -- the gate would go green and the reader following
    # the pointer would arrive at an empty cell.
    assert rows == set(range(1, max(rows) + 1)), (
        "the divergences table skips %s"
        % sorted(set(range(1, max(rows) + 1)) - rows))
    # Every file this repository tracks, not a list of directories.
    # The list was `src/`, `tests/`, `tools/` and two markdown files,
    # and it missed the one in `docs/assets/verdict.svg` -- the picture
    # the front page shows. A list of places to look is a list somebody
    # has to keep; the tracked files are the tree.
    #
    # Spelling is the same problem one level down, so the number is
    # taken from anything within a few words of the document's name,
    # in either order, and adjacent string literals are joined first
    # because a citation written across two of them is one sentence to
    # a reader and two to a scanner.
    cited: dict = {}
    tracked = subprocess.run(["git", "ls-files"], cwd=str(ROOT),
                             capture_output=True, text=True)
    paths = [ROOT / name for name in tracked.stdout.split("\n") if name]
    assert len(paths) > 50, "git ls-files found nothing; is this a checkout?"
    # One direction, and then every number in the list that follows.
    # The reverse alternative was written for citations that name the
    # number first, and what it actually found was a CSS colour: on
    # `docs/assets/verdict.svg` -- the file the comment above says this
    # rewrite was for -- it matched the `7` of `#7d8a99` and never
    # reached the `#37` a few hundred bytes later. And this repository
    # writes runs of them, `#1--#5, #8` and `#26, #28`, of which only
    # the first was ever read.
    opener = re.compile(r"divergences?(?:\.md)?[`\s\\\"',(]{0,12}#")
    number = re.compile(r"(\d{1,3})\b")
    run = re.compile(r"(?:#\s*\d{1,3}\b[\s,;]*(?:--|-|and|or|to)?[\s]*)+")
    for path in paths:
        if path.suffix in (".aasx", ".pdf", ".xlsx") or not path.is_file():
            continue
        try:
            text = path.read_text("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        text = re.sub(r"[\"\']\s*\n?\s*[\"\']", "", text)
        for opening in opener.finditer(text):
            tail = run.match(text, opening.end() - 1)
            if not tail:
                continue
            for found in number.findall(tail.group(0)):
                cited.setdefault(int(found), set()).add(path.name)
    assert cited, "nothing in this tree cites a divergence at all"
    dangling = sorted((number, sorted(where)) for number, where in cited.items()
                      if number not in rows)
    assert not dangling, (
        "these divergence numbers are cited and the document has no such "
        "row: %s" % dangling)
