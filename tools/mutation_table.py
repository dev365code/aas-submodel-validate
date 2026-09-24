#!/usr/bin/env python3
"""Every claim this project makes about a gate, as a mutation somebody can run.

    python3 tools/mutation_table.py            # list the table
    python3 tools/mutation_table.py --run      # apply each row and check it dies

Each row is one gate: *this* gate says it stops *that* mistake -- does it? A
gate is only worth what it catches, and the ones here that caught nothing
were each found individually, with the evidence living in a commit
message. This is that evidence, kept where it can be re-run.

The harness checks itself as hard as it checks the code:

  * **the mutation has to take effect.** Every row asserts its anchor
    appears exactly once. A drifted anchor is an error, not a pass.
  * **the mutant has to compile.** An anchor that omits the line
    governing what it replaces -- an `if:` left with no body -- leaves a
    file that does not import, and then every test errors for a reason
    that is not the mutation. That is a broken row, not a killed mutant.
  * **the bytecode has to be new bytecode.** Restoring a file to its
    previous *size* leaves a `.pyc` CPython still considers valid --
    source mtime is stored at one-second resolution -- so a mutation can
    look survived when it never loaded. Every apply and restore clears
    `__pycache__` and touches the file.
  * **the checks have to exist.** A selection that collects nothing exits
    5, which is a broken row rather than a killed mutant.
  * **one row must survive.** If every row dies, the likeliest
    explanation is a harness that reports red for everything. The canary
    is a change that really does not matter; it dying voids the results
    above it.
  * **the baseline has to be green in the same environment.** Measured:
    a workflow step lifted out of its YAML calls `python`, which does not
    exist on the machine this runs on -- so the baseline and the mutant
    failed with the same sentence, and a harness reading only "did it go
    red" books a kill on a gate that never ran. The shim below is why,
    and the baseline is proved before every row.
  * **the copy has to carry `.git`.** Measured: a tree taken with `git
    archive` has none, two tests skip there, and a row aimed at either
    would be scored survived. With `.git` the suite reads 1308 passed and
    none skipped; without it, 1306 and two.
  * **a selection that skipped everything is not a pass.** pytest exits 0
    on a run that skipped all of it, which looks exactly like a mutation
    nothing objected to. The summary line is read, not just the code.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: (id, file, anchor, mutation, checks that must go red, why it matters)
#: A check is a pytest selection, or `tools/<script> <args>` for a gate
#: that is a tool. `why` is a reproduced event, never a description: a row
#: whose reason has not happened is a row nobody can weigh.
TABLE = [
    ("gates/the-time-budget-actually-compares",
     "tools/time_budget.py",
     "        self.ok = factor is None or factor < FAIL_AT",
     "        self.ok = True",
     ["tests/test_the_run_stays_inside_its_time_budget.py"],
     "a budget that passes whatever it measures is a clock nobody is "
     "watching, which is the state every other gate here was already in: "
     "they all ask whether the verdict is right and none asked whether it "
     "arrived"),

    ("gates/the-time-budget-reports-what-it-found",
     "tools/time_budget.py",
     "    return 1 if bad else 0",
     "    return 0",
     ["tests/test_the_run_stays_inside_its_time_budget.py"],
     "a judgement that the command throws away is a judgement `make check` "
     "cannot act on; the function being tested is not the thing that runs"),

    ("release/signature-covers-only-what-we-built",
     ".github/workflows/release.yml",
     "            dist/aas_submodel_validate-*.whl",
     "            dist/*.whl",
     ["tests/test_ci_parity.py::"
      "test_the_signature_covers_what_this_project_built_and_nothing_else"],
     "the dependency wheel carried for the offline route sits in the same "
     "directory; signing it would claim this workflow built somebody "
     "else's artifact. Nothing named `subject-path` before this, so "
     "the property held because a person had been careful"),

    ("release/gate-runs-before-publish",
     ".github/workflows/release.yml",
     '          pip install -e ".[battery]"\n          make check',
     '          pip install -e ".[battery]"\n          make check || true',
     ["tests/test_ci_parity.py::"
      "test_a_workflow_that_publishes_runs_the_gate_and_is_stopped_by_it"],
     "five ways of keeping this step looking present while removing what "
     "it does, and the suite stayed green through every one, because "
     "nothing read the release workflow at all"),

    ("release/ci-judged-this-commit",
     ".github/workflows/release.yml",
     '[ "$verdict" = "success" ]',
     '[ "$verdict" != "zzz-no-such-conclusion" ]',
     ["tests/test_ci_parity.py::test_the_verdict_gate_fails_closed"],
     "a cancelled run is completed with a conclusion that is not success; "
     "reading the absence of a verdict as a verdict would publish a "
     "commit nothing judged"),

    ("release/dist-holds-only-what-we-publish",
     ".github/workflows/release.yml",
     '          if [ "$count" != "5" ]; then',
     '          if [ "$count" != "$count" ]; then',
     ["tests/test_ci_parity.py::"
      "test_a_file_nobody_built_does_not_ride_out_with_them"],
     "the checksum file sums `dist/*` and the Release is made from "
     "`dist/*`, so a file arriving there by accident is vouched for and "
     "published; nothing said what belonged"),

    ("release/index-gets-only-our-two",
     ".github/workflows/release.yml",
     "packages-dir: up",
     "packages-dir: dist",
     ["tests/test_ci_parity.py::"
      "test_pypi_gets_the_two_files_that_belong_to_this_project"],
     "the publisher uploads a directory, and `dist/` holds a wheel this "
     "project did not build plus a file that is not a distribution"),

    ("release/offline-route-is-rehearsed",
     ".github/workflows/release.yml",
     "pip download --no-deps --only-binary=:all: --python-version 3.9",
     "pip download --no-deps --only-binary=:all: --python-version 3.13",
     ["tests/test_ci_parity.py::"
      "test_the_release_path_is_rehearsed_on_every_push"],
     "the step this mutates cannot be lifted: it reads installed "
     "distribution metadata and it downloads. Its substance is exercised "
     "on every push by the rehearsal, which really does build the "
     "offline install and use it -- so what the table protects here is "
     "the pairing, because a rehearsal that has drifted from the release "
     "is a rehearsal of something else"),

    ("release/single-file-is-built-twice-and-compared",
     ".github/workflows/release.yml",
     "python tools/build_zipapp.py -o /tmp/again.pyz",
     "python tools/build_zipapp.py -o /tmp/again.pyz --check",
     ["tests/test_ci_parity.py::"
      "test_the_release_path_is_rehearsed_on_every_push"],
     "same pairing. The gate itself resists mutation honestly: two builds "
     "of one tree differ only if the stamp or the file order does, and "
     "both are fixed, so a mutation that made it flaky would be a worse "
     "row than none"),

    ("release/nothing-unpacks-outside-the-directory",
     "tools/check_distributions.py",
     'return settled.startswith("/") or ".." in settled.split("/")',
     'return ".." in settled.split("/")',
     ["tests/test_check_distributions.py"],
     "a member whose name starts at the root writes there when somebody "
     "unpacks it -- `os.path.join(dest, \'/tmp/pwned\')` is `/tmp/pwned`. "
     "The question was asked of the raw name while the `..` question was "
     "asked of a normalised one, so `/abs` escaped and `\\\\abs` did not. "
     "This file has met that shape before"),

    ("release/five-places-say-one-version",
     "src/aas_submodel_validate/__init__.py",
     '__version__ = "',
     '__version__ = "9.9.9"  # ',
     ["step:release.yml:the tag and the version agree"],
     "the package, the build configuration, the tag, the CHANGELOG and "
     "the sample report all say the version, and a release where they "
     "disagree is one nobody can cite later; two of them drifted once and "
     "a tag pushed in that state would have built a wheel named for the "
     "older one"),

    ("suite/a-crash-is-not-a-verdict",
     "tests/conftest.py",
     "        assert _ALLOWS_CRASH or not crashed, (",
     "        assert True or not crashed, (",
     ["tests/test_suite_hygiene.py::"
      "test_a_rule_that_crashes_cannot_be_read_as_a_verdict",
      "tests/test_suite_hygiene.py::"
      "test_the_refusal_survives_a_rule_that_only_breaks_sometimes"],
     "a rule that raises is reported under its own id, at its own "
     "severity, with the subject it was reading, so an assertion that a "
     "rule fired is satisfied by that rule having stopped working. "
     "Eighty-one places in twenty-four files reduce a report to "
     "identities that way. Found because a survivor would not die: a "
     "value folded unconditionally made HDL4 raise on the exact input "
     "one test constructed, and that test passed"),

    ("suite/the-crash-door-is-not-propped-open",
     "tests/conftest.py",
     '    _ALLOWS_CRASH = request.node.get_closest_marker("allow_crash") is not None',
     "    _ALLOWS_CRASH = True",
     ["tests/test_suite_hygiene.py::"
      "test_a_rule_that_crashes_cannot_be_read_as_a_verdict"],
     "the opt-out is a marker one test wears; propping it open for every "
     "test restores the hole in a form that reads as configuration"),

    ("rules/generated-tables-match-their-generator",
     "tools/extract_smt_rules.py",
     "TEMPLATE_CITATION = %r",
     "TEMPLATE_CITATION = %r  # ",
     ["tools/extract_smt_rules.py --check"],
     "the rule tables are generated from the vendored template and are "
     "the file a reader's `per` line quotes; a generator edited without "
     "regenerating leaves the shipped citation saying what the generator "
     "no longer says. This check needs no build and no suite, which is "
     "why it can be a row at all -- measured"),

    ("rules/vendored-bytes-are-the-bytes-we-recorded",
     "src/aas_submodel_validate/data/smt/02004/2.0.1/template.json",
     "Name der spezifischen digitalen Datei@de",
     "Name der spezifischen digitalen Datei@dx",
     ["tools/vendor_template.py --check"],
     "every judgement this project makes rests on the vendored template, "
     "and the whole point of carrying it is that an upstream change "
     "cannot arrive silently. One character in a description is the "
     "smallest edit that must still be noticed"),

    ("rules/every-published-id-is-accounted-for",
     "docs/rule-coverage.json",
     '"HD-D9",',
     "",
     ["tests/", "tools/rule_coverage.py --check"],
     "the committed baseline is what says which rule ids this project "
     "expects to fire; the suite writes what actually fired and the tool "
     "compares the two against the registry. **This row states a "
     "dependency**: the tool reads a file the suite leaves behind, and "
     "run on its own it says so rather than answering, so the suite is "
     "listed first"),

    ("rules/ascii-case-is-not-unicode-case",
     "src/aas_submodel_validate/container.py",
     "return value.translate(_ASCII_LOWER)",
     "return value.lower()",
     ["tests/test_part_names.py::"
      "test_the_case_folding_is_ascii_and_stops_there"],
     "ECMA-376 Part 2 6.2.2.3 folds ASCII and says so in code points; "
     "`str.lower()` also folds \u00c9 to \u00e9, which would answer that a part "
     "is present that the archive does not hold"),

    ("input/a-corrupt-stream-is-a-verdict-not-a-traceback",
     "src/aas_submodel_validate/container.py",
     "              EOFError, OSError, zlib.error, ValueError, lzma.LZMAError)",
     "              EOFError, OSError, zlib.error, ValueError)",
     ["tests/test_hostile_input.py::"
      "test_a_corrupt_stream_is_a_verdict_and_never_a_traceback"],
     "measured on the fourth codec: 17 of 38 damaged archives came out as "
     "a traceback and exit 1 with an empty report, which is a crash "
     "wearing a verdict's clothes. `lzma.LZMAError` is not a child of the "
     "others, so the tuple missing it catches nothing there"),

    ("input/a-rule-that-raises-becomes-a-finding",
     "src/aas_submodel_validate/runner.py",
     "        except Exception as exc:  # noqa: BLE001 - the isolation is the point",
     "        except ValueError as exc:  # noqa: BLE001 - the isolation is the point",
     ["tests/test_runner.py::"
      "test_a_rule_that_could_not_run_fails_the_run_whatever_it_asks_for"],
     "one rule raising must not take the other rules with it -- a reader "
     "who gets a traceback learns nothing about the file, and the rules "
     "that would have answered never ran"),

    ("input/a-part-too-large-is-refused-before-it-is-read",
     "src/aas_submodel_validate/container.py",
     "        if info.file_size > MAX_PART_BYTES:",
     "        if False:",
     ["tests/test_loader.py::"
      "test_every_way_the_chain_refuses_is_caught_and_staged"],
     "a 66 KB archive that unpacked to 402 MB, and a container that went "
     "on paying a part's worth of work for every part still to come "
     "after it had already passed its total"),

    ("input/a-path-this-reader-cannot-open-is-a-finding",
     "src/aas_submodel_validate/rules/container.py",
     '        if error.stage == "access":',
     "        if False:",
     ["tests/test_hostile_input.py::"
      "test_a_refusal_prints_a_report_whatever_the_extension"],
     "the same permission denial used to reach `.aasx` through the "
     "container reader and `.json`/`.xml` through the loader, so a "
     "pipeline parsing stdout broke on two extensions out of three for a "
     "condition none of them caused. Nobody decided that; one code path "
     "quietly disagreed with the contract"),

    ("rules/an-element-belongs-to-a-row-by-its-identifier",
     "src/aas_submodel_validate/rules/engine.py",
     '    return in_list and main_empty and kind_name == row["kind"]',
     '    return in_list and kind_name == row["kind"]',
     ["tests/test_engine_regressions.py::"
      "test_a_list_child_wearing_a_wrong_identifier_is_not_claimed_by_the_row"],
     "IDTA 02004 Annex A says a different idShort might be chosen, so "
     "matching is by semanticId and the one fallback -- a list child "
     "with no main identifier of its own -- is narrow on purpose. Widen "
     "it and a child wearing the wrong identifier is claimed by the row "
     "anyway, which is a verdict about an element nobody matched"),

    ("offline/nothing-shipped-can-open-a-connection",
     "src/aas_submodel_validate/report.py",
     "from __future__ import annotations",
     "from __future__ import annotations\nimport socket  # noqa",
     ["tests/test_offline.py::"
      "test_nothing_the_package_ships_can_open_a_connection"],
     "\"Offline, always. No network call in any code path\" is the sentence "
     "an air-gapped reader chooses this tool on, and nothing checked it "
     "until this row -- the paragraph beside it on the same page had "
     "already been false across releases"),

    ("offline/a-verdict-comes-out-with-no-socket",
     "src/aas_submodel_validate/cli.py",
     "    args = parser.parse_args(argv)",
     '    __import__("soc" + "ket").socket()\n    args = parser.parse_args(argv)',
     ["tests/test_offline.py::"
      "test_a_verdict_still_comes_out_with_the_network_taken_away"],
     "the name is assembled at runtime, so reading the source cannot see "
     "it -- measured: the static half passes this and the run fails it, "
     "which is the division of labour the two tests claim"),

    ("template/the-flag-a-case-carries-reaches-the-reader",
     "tools/verdict_diff.py",
     '        argv += ["--template", str(case.template)]',
     '        pass',
     ["tests/test_verdict_diff.py::"
      "test_a_case_the_old_version_cannot_be_asked_is_not_a_verdict_that_moved"],
     "a case can carry a table and the comparison can drop it on the way to "
     "the reader, and then the corpus looks like it covers the mode while "
     "judging every one of those inputs with the packs instead"),

    ("template/a-question-the-old-version-cannot-be-asked-is-not-a-move",
     "tools/verdict_diff.py",
     '    return case.template is None or _has_the_option(src, "--template")',
     '    return True',
     ["tests/test_verdict_diff.py::"
      "test_the_count_leaves_out_what_the_old_version_was_never_asked"],
     "a release that predates the option answers `unrecognized arguments` and "
     "exits 64; counted as a verdict, every template case joins the moved "
     "list the day the option ships and buries the one that moved"),

    ("template/a-tree-with-no-reader-is-not-a-version",
     "tools/verdict_diff.py",
     '    if not (src / "aas_submodel_validate" / "cli.py").is_file():',
     '    if False:',
     ["tests/test_verdict_diff.py::"
      "test_a_tree_with_no_reader_in_it_does_not_get_answered_by_the_machine"],
     "PYTHONPATH is searched before site-packages, so a tree holding no "
     "package lets an installed copy answer for it -- both sides become one "
     "reader, every input agrees with itself, and the tool prints 0 moved"),

    ("scope/what-sat-there-is-named",
     "src/aas_submodel_validate/rules/engine.py",
     "unclaimed=tuple(names[:UNCLAIMED_NAMED]),",
     "unclaimed=(),",
     ["tests/test_scope_the_run_did_not_examine.py::"
      "test_what_sat_there_is_named_so_opposite_cases_differ"],
     "a row's own container under a drifted identifier and a row the file "
     "omits beside an unrelated container of the same kind write the same "
     "record, byte for byte, unless the record names what sat there"),

    ("screen/a-list-cut-short-says-so",
     "src/aas_submodel_validate/report.py",
     'return ", ".join(shown) + (", and %d more" % rest if rest > 0 else "")',
     'return ", ".join(shown)',
     ["tests/test_scope_the_run_did_not_examine.py::"
      "test_names_are_cut_with_a_count_never_silently",
      "tests/test_scope_the_run_did_not_examine.py::"
      "test_a_list_cut_short_says_how_many_it_left_out"],
     "three names and then silence reads as three names in all, on the one "
     "line a generated-only pack speaks on"),

    ("cost/deciding-which-submodels-a-table-answers-for-is-not-skipped",
     "src/aas_submodel_validate/rules/engine.py",
     "cached = cache[tables.__name__] = _matched_submodels(ctx, tables)",
     "cached = cache[tables.__name__] = []",
     ["tests/test_engine_regressions.py::"
      "test_which_submodels_a_table_answers_for_is_decided_once"],
     "the floor under a ceiling: a memo that skips the deciding walks less, "
     "not more, and a gate that only bounds the count from above passes it "
     "while every generated table judges nothing"),

    ("cost/each-table-gets-its-own-answer",
     "src/aas_submodel_validate/rules/engine.py",
     '    cache = ctx.__dict__.setdefault("_smt_matched", {})\n'
     "    cached = cache.get(tables.__name__)",
     '    cache = ctx.__dict__.setdefault("_smt_matched", {})\n'
     "    cached = next(iter(cache.values()), None)",
     ["tests/test_engine_regressions.py::"
      "test_which_submodels_a_table_answers_for_is_decided_once"],
     "a memo keyed wrongly hands every table the first table's answer; it "
     "walks less, so the ceiling passes it, and the table this input is an "
     "instance of is never decided"),

    ("bound/what-sat-there-is-bounded",
     "src/aas_submodel_validate/model.py",
     "            (_bounded(subject), _bounded(seen)) for subject, seen in self.unclaimed))",
     "            (subject, seen) for subject, seen in self.unclaimed))",
     ["tests/test_scope_the_run_did_not_examine.py::"
      "test_a_long_name_sitting_there_does_not_grow_the_report"],
     "a 200,000-character idShort made the summary line 200,892 characters, "
     "with every test green"),

    ("bound/the-place-is-bounded",
     "src/aas_submodel_validate/model.py",
     '        object.__setattr__(self, "where", _bounded(self.where))',
     '        object.__setattr__(self, "where", self.where)',
     ["tests/test_scope_the_run_did_not_examine.py::"
      "test_a_long_name_sitting_there_does_not_grow_the_report"],
     "the place is built from the document's idShorts and was the one field "
     "of the record outside the bound"),

    ("corpus/the-case-only-the-scope-record-speaks-about-stays-that-case",
     "tools/verdict_diff.py",
     '    elsewhere["submodels"][0]["submodelElements"].append({',
     "    [].append({",
     ["tests/test_verdict_diff.py::"
      "test_the_corpus_holds_a_case_only_the_scope_record_speaks_about"],
     "the case becomes a plain clean document and the corpus stays 68 inputs, "
     "so nothing else notices the instrument lost its case for the feature"),

    ("diff/what-sat-there-is-compared",
     "tools/verdict_diff.py",
     '            (record.get("where"), record.get("rule"), record.get("because"),\n'
     '             tuple((pair.get("subject"), pair.get("seen") or "")\n'
     '                   for pair in record.get("unclaimedHere") or ()))',
     '            (record.get("where"), record.get("rule"), record.get("because"))',
     ["tests/test_verdict_diff.py::"
      "test_two_records_that_differ_only_in_what_sat_there_are_two_answers"],
     "the two opposite cases differ only in what sat there, and a key without "
     "it reports the change between them as nothing moved"),

    ("battery/the-category-reading-reaches-the-report",
     "src/aas_submodel_validate/rules/battery.py",
     "    return tuple(found)",
     "    return ()",
     ["tests/test_battery_rules.py::"
      "test_the_category_is_read_a_bounded_number_of_times"],
     "a reading that finds nothing is called as often as one that works, so a "
     "floor on the count passed a category that was never found"),

    ('screen/an-element-already-named-is-not-named-again',
     'src/aas_submodel_validate/report.py',
     '    accounted = {record.subject for record in report.unmatched}',
     '    accounted = set()',
     ['tests/test_scope_the_run_did_not_examine.py::test_the_line_says_each_place_once',
      'tests/test_scope_the_run_did_not_examine.py::test_an_element_the_line_already_names_is_not_named_again'],
     'the bundled example named its drifted list as not asked and again as not examined'),

    ('screen/a-place-is-not-hidden-behind-another-places-rule-id',
     'src/aas_submodel_validate/report.py',
     '        if record.because != "unclaimed-element-present":',
     '        if record.because != "unclaimed-element-present" or set(record.unasked) & set(report.not_asked):',
     ['tests/test_scope_the_run_did_not_examine.py::test_the_line_says_each_place_once'],
     'subtracting by id what the not-asked clause told about one place hid a second submodel losing the same rule for another reason'),

    ('screen/a-near-miss-elsewhere-does-not-hide-the-place',
     'src/aas_submodel_validate/report.py',
     '        if left > 0:',
     '        if left > 0 and not report.not_asked:',
     ['tests/test_scope_the_run_did_not_examine.py::test_a_near_miss_elsewhere_does_not_hide_the_place'],
     'a drifted leaf elsewhere in the place sends its rows to rulesNotAsked, and that clause names ids, not the section or what sat beside it'),

    ('screen/the-count-of-what-sat-there',
     'src/aas_submodel_validate/report.py',
     '        total = sum(lists.values())',
     '        total = len(sitting)',
     ['tests/test_scope_the_run_did_not_examine.py::test_what_sat_there_is_in_path_order_and_bounded'],
     'each record names a few and says how many; counting the names printed and 9 more as 2 more'),

    ('screen/two-lists-at-one-place-are-two-lists',
     'src/aas_submodel_validate/report.py',
     '        lists = {(record.where, fresh): left for record, fresh, left in shown}',
     '        lists = {record.where: left for record, fresh, left in shown}',
     ['tests/test_scope_the_run_did_not_examine.py::test_two_lists_at_one_place_are_two_lists'],
     'two kinds unplaced at one place are two lists; keyed by place alone the line said one element for two'),

    ('screen/what-sat-there-is-named-in-path-order',
     'src/aas_submodel_validate/report.py',
     '            key=_sitting_order)]',
     '            key=lambda pair: pair[0])]',
     ['tests/test_scope_the_run_did_not_examine.py::test_what_sat_there_is_in_path_order_and_bounded'],
     'by spelling the line names Box10, Box11, Box12 ahead of Box8'),

    ('scope/what-sat-there-is-in-path-order',
     'src/aas_submodel_validate/rules/engine.py',
     '    ordered = {kind: sorted(pairs, key=_sitting_order)',
     '    ordered = {kind: list(pairs)',
     ['tests/test_scope_the_run_did_not_examine.py::test_what_sat_there_is_in_path_order_and_bounded'],
     'unsorted, the few a record names are whichever the file happened to list first'),

    ('scope/path-order-survives-the-merge',
     'src/aas_submodel_validate/rules/engine.py',
     '        names = sorted(names, key=_sitting_order)',
     '        names = sorted(names)',
     ['tests/test_scope_the_run_did_not_examine.py::test_what_sat_there_is_in_path_order_and_bounded'],
     'the records are merged out of sets and sorted again; by spelling Box10 comes before Box8'),

    ('scope/how-many-sat-there-is-said',
     'src/aas_submodel_validate/rules/engine.py',
     '             tuple(sitting[:UNCLAIMED_NAMED]), len(sitting)))',
     '             tuple(sitting[:UNCLAIMED_NAMED]), len(sitting[:UNCLAIMED_NAMED])))',
     ['tests/test_scope_the_run_did_not_examine.py::test_what_sat_there_is_in_path_order_and_bounded'],
     'a record names at most a few; without the count a reader takes the few for all of them'),

    ('scope/an-element-with-no-identifier-is-not-counted',
     'src/aas_submodel_validate/rules/engine.py',
     '        if index in claimed or not any(candidates):\n            continue\n        subject = _subject(path, element, index, shared)\n        unplaced.setdefault(',
     '        if index in claimed:\n            continue\n        subject = _subject(path, element, index, shared)\n        unplaced.setdefault(',
     ['tests/test_scope_the_run_did_not_examine.py::test_an_element_with_no_identifier_is_not_counted_as_sitting_there'],
     "a container with no identifier is the commonest shape of a manufacturer's own, and counting it made conformant files speak"),

    ('scope/seen-is-the-elements-own-identifier',
     'src/aas_submodel_validate/rules/engine.py',
     '    for reference in ([element.semantic_id]',
     '    for reference in ([]',
     ['tests/test_scope_the_run_did_not_examine.py::test_seen_is_the_elements_own_identifier'],
     "a supplemental identifier stood in for the element's own"),

    ('scope/seen-falls-back-in-the-files-order',
     'src/aas_submodel_validate/rules/engine.py',
     '                      + list(getattr(element, "supplemental_semantic_ids", None) or [])):',
     '                      + list(reversed(getattr(element, "supplemental_semantic_ids", None) or []))):',
     ['tests/test_scope_the_run_did_not_examine.py::test_seen_is_the_elements_own_identifier'],
     'failing its own identifier, the first supplemental the file gives, not another'),

    ('scope/seen-joins-stacked-keys',
     'src/aas_submodel_validate/rules/engine.py',
     '            return "/".join(values)',
     '            return values[0]',
     ['tests/test_scope_the_run_did_not_examine.py::test_seen_is_the_elements_own_identifier'],
     'a two-key identifier reported as its first key names something the file does not carry'),

    ('scope/a-drifted-place-beside-a-sibling-is-recorded',
     'src/aas_submodel_validate/rules/engine.py',
     '                         if because != "absent" or rule_id not in asked_here)',
     '                         if rule_id not in asked_here)',
     ['tests/test_scope_the_run_did_not_examine.py::test_a_drifted_place_beside_a_sibling_that_entered_it_is_recorded'],
     'rules a sibling item put were taken off a place with a drifted list in it, and the report was the one without the list'),

    ('bound/the-label-is-bounded',
     'src/aas_submodel_validate/model.py',
     '        object.__setattr__(self, "label", _bounded(',
     '        object.__setattr__(self, "label", (',
     ['tests/test_scope_the_run_did_not_examine.py::test_a_long_name_sitting_there_does_not_grow_the_report'],
     "the label is a template's idShort, text somebody else wrote"),

    ('bound/the-identifier-sitting-there-is-bounded',
     'src/aas_submodel_validate/model.py',
     '            (_bounded(subject), _bounded(seen)) for subject, seen in self.unclaimed))',
     '            (_bounded(subject), seen) for subject, seen in self.unclaimed))',
     ['tests/test_scope_the_run_did_not_examine.py::test_a_long_name_sitting_there_does_not_grow_the_report'],
     "the identifier is the document's own, and a 200,000-character one went into the record whole"),

    ('remedy/deleting-a-right-declaration-is-not-offered-as-an-equal',
     'src/aas_submodel_validate/rules/container.py',
     '"relationship removes only the declaration: if a File value in "',
     '"relationship is the other way out: if a File value in "',
     ['tests/test_a_file_a_model_points_at.py::test_the_relationship_remedy_does_not_undo_a_correct_declaration'],
     'one missing part draws X4 and a File rule, and X4 offered deleting the relationship as an equal way out -- where a File value names the part, deleting the declaration leaves the part missing'),

    ('diff/the-place-sitting-there-is-compared',
     'tools/verdict_diff.py',
     '             tuple((pair.get("subject"), pair.get("seen") or "")',
     '             tuple((pair.get("seen") or "",)',
     ['tests/test_verdict_diff.py::test_two_records_that_differ_only_in_what_sat_there_are_two_answers'],
     'the same identifier in another place is another answer'),

    ('diff/the-identifier-sitting-there-is-compared',
     'tools/verdict_diff.py',
     '             tuple((pair.get("subject"), pair.get("seen") or "")',
     '             tuple((pair.get("subject"),)',
     ['tests/test_verdict_diff.py::test_two_records_that_differ_only_in_what_sat_there_are_two_answers'],
     'the same place under another identifier is another answer'),

    ('screen/element-by-element',
     'src/aas_submodel_validate/report.py',
     '        fresh = tuple(pair for pair in record.unclaimed if pair[0] not in accounted)',
     '        fresh = tuple(record.unclaimed)',
     ['tests/test_scope_the_run_did_not_examine.py::test_a_mixed_place_names_only_what_the_line_has_not'],
     "filtered record by record, a place holding a near-missed container and one of the supplier's own named the first twice"),

    ('screen/sections-are-counted-as-sections',
     'src/aas_submodel_validate/report.py',
     '                    % (len(shown), "" if len(shown) == 1 else "s",',
     '                    % (total, "" if total == 1 else "s",',
     ['tests/test_scope_the_run_did_not_examine.py::test_the_line_counts_sections_and_elements_each_as_what_they_are'],
     'one unopened row beside two containers printed as two sections'),

    ('scope/a-blank-identifier-is-none',
     'src/aas_submodel_validate/rules/engine.py',
     '        if index in claimed or not any(candidates):',
     '        if index in claimed or not candidates:',
     ['tests/test_scope_the_run_did_not_examine.py::test_a_blank_identifier_is_no_identifier'],
     'a key that normalises to nothing was counted as an identifier, and seen came out null'),

    ('bound/a-numbered-label-does-not-crash',
     'src/aas_submodel_validate/model.py',
     '            self.label if self.label is None else str(self.label)))',
     '            self.label))',
     ['tests/test_scope_the_run_did_not_examine.py::test_a_template_row_numbered_rather_than_named_does_not_crash'],
     "a supplied template's idShort given as a number crashed the run on its way through the bound: a traceback and exit 1"),

    ('screen/names-on-the-line-are-escaped',
     'src/aas_submodel_validate/report.py',
     '                        _safe(unasked + examined),\n                        incomplete))',
     '                        unasked + examined,\n                        incomplete))',
     ['tests/test_scope_the_run_did_not_examine.py::test_names_on_the_summary_line_are_escaped'],
     'a raw escape in an idShort cleared the screen and printed a fake ok line over a run with an error in it'),

    ('scope/the-path-key-reads-a-bounded-prefix',
     'src/aas_submodel_validate/rules/engine.py',
     '    parts = _RUN_OF_DIGITS.split(subject[:_PATH_KEY_CHARACTERS])',
     '    parts = _RUN_OF_DIGITS.split(subject)',
     ['tests/test_scope_the_run_did_not_examine.py::test_the_path_order_reads_a_bounded_prefix'],
     'a key is one tuple per run of digits over a whole path; alternating letters and digits cost about 9 MB per element'),

    ("cost/where-the-files-are-is-not-asked-per-part",
     "src/aas_submodel_validate/container.py",
     "        if self._canonical is None:",
     "        if True:",
     ["tests/test_a_file_a_model_points_at.py::"
      "test_asking_where_the_files_are_does_not_cost_elements_times_parts"],
     "the rule that asks whether the files a model names are in the "
     "container joins a document to the parts of a package, and the join "
     "is linear only because the container indexes its names once. "
     "Rebuilding the index per lookup changes no verdict at all -- "
     "measured, ten more elements cost 930 more lookups in a package of "
     "forty parts and 8,130 in one of four hundred, with every finding "
     "identical and the rest of the suite green"),

    ("rules/the-corpus-can-see-a-two-category-verdict",
     "tools/verdict_diff.py",
     'for seat, stated in enumerate(("ev", "lmt"))',
     'for seat, stated in enumerate(("ev", "ev"))',
     ["tests/test_verdict_diff.py::"
      "test_the_corpus_holds_a_passport_that_states_two_categories"],
     "0.1.4 stopped `BAT-R8` answering for a file stating two categories "
     "-- a verdict change -- and the corpus comparison read \"none of the "
     "inputs is judged differently\" because every battery input stated one. A "
     "zero from a corpus that cannot hold the case reads exactly like a "
     "zero from one that can"),

    ("rules/the-profile-that-decides-is-the-one-that-explains",
     "src/aas_submodel_validate/rules/profiles.py",
     "    def __init__(self, forced: str = None):\n        self.forced = forced",
     "    def __init__(self, forced: str = None):\n        self.forced = None",
     ["tests/test_cli_flags.py::test_profile_chooses_which_template_answers"],
     "two templates claim one submodel identifier, so which answers is "
     "chosen rather than read off the file. One object holds the choice "
     "and both the walk and the rule that explains it ask the same "
     "object -- when they read the mark separately, a verdict could "
     "switch without the sentence explaining it moving"),

    ("rules/published-ids-are-not-renamed",
     "src/aas_submodel_validate/rules/container.py",
     '@rule("X6"',
     '@rule("X7"',
     ["tests/test_released_rule_ids.py::"
      "test_every_rule_id_the_last_release_published_still_exists"],
     "the front page says no rule id has been renamed or reused, and a "
     "promise in prose goes false in silence -- the sentence beside it "
     "said a new rule meant a minor version through three releases that "
     "said otherwise"),

    ("rules/the-near-miss-bound-is-counted-to-itself",
     "src/aas_submodel_validate/rules/engine.py",
     "edit_distance(seen_tail, exp_tail, cap=bound) <= bound",
     "edit_distance(seen_tail, exp_tail) <= bound",
     ["tests/test_engine_regressions.py::"
      "test_the_near_miss_bound_holds_at_both_edges"],
     "`edit_distance` stops counting at its cap and answers cap + 1. Left "
     "at its default of 6, a bound of 7 -- any last segment of 28 "
     "characters -- was met by every pair, and a manufacturer's own "
     "identifier that shared a directory with a row was billed as a typo "
     "of it (divergences #43)"),

    ("loader/a-packaged-part-is-answered-like-the-bare-file",
     "src/aas_submodel_validate/loader.py",
     "        answered = _failure(exc, decoding=decoding, packaged=part is not None)\n",
     "        answered = None\n",
     ["tests/test_loader.py::"
      "test_a_packaged_json_part_is_answered_the_way_the_same_bare_file_is"],
     "the same bytes zipped or not get the same answer: a payload this "
     "interpreter could not build, or one that is not UTF-8, was told to "
     "fix the syntax its parser rejects when it arrived in a package"),

    ("loader/the-stop-sentence-says-only-what-it-knows",
     "src/aas_submodel_validate/loader.py",
     '    return ("This reader stopped before the end of the document: %s. The "',
     '    return ("This document is JSON. Nothing is wrong with what you sent: %s. The "',
     ["tests/test_registry.py::"
      "test_every_sentence_a_violation_carries_is_the_one_that_was_decided",
      "tests/test_loader.py::"
      "test_a_document_that_runs_out_of_stack_is_not_told_it_is_json"],
     "a reader that stopped before the end of a document cannot know it is "
     "JSON or that nothing is wrong with it, and malformed input that ran "
     "out of stack before its syntax error was told both"),

    ("loader/a-stop-while-building-is-not-a-stop-while-reading",
     "src/aas_submodel_validate/loader.py",
     '    stopped = _out_of_room(exc, building=not decoding)\n',
     '    stopped = _out_of_room(exc, building=False)\n',
     ["tests/test_loader.py::"
      "test_what_the_reader_did_not_reach_is_not_declared_sound",
      "tests/test_loader.py::"
      "test_a_bare_submodel_too_deep_to_build_is_told_the_reader_stopped"],
     "a document the parser read to the end and the builder ran out of "
     "stack on was told what comes after was not read -- false there, "
     "where it was read and not checked"),

    ("loader/decoding-ends-where-building-begins",
     "src/aas_submodel_validate/loader.py",
     "        decoding = False\n",
     "",
     ["tests/test_loader.py::"
      "test_what_building_raises_is_the_documents_whatever_its_type"],
     "a ValueError or UnicodeError means this interpreter's digit limit or "
     "undecodable bytes only while decoding; raised while building -- a Blob "
     "that is not base64 raises one of each -- they are the document's"),

    ("loader/xml-is-asked-about-this-interpreters-limits",
     "src/aas_submodel_validate/loader.py",
     "    except Exception as exc:\n"
     "        _payload_error(loaded, part, exc, _out_of_room(exc, building=False))\n",
     "    except Exception as exc:\n"
     "        _payload_error(loaded, part, exc, None)\n",
     ["tests/test_loader.py::"
      "test_xml_too_deep_to_follow_is_told_the_reader_stopped",
      "tests/test_loader.py::"
      "test_the_deepest_xml_this_reader_builds_is_read_and_one_more_level_is_not",
      "tests/test_loader.py::"
      "test_xml_that_runs_this_reader_out_of_memory_is_told_the_reader_stopped"],
     "350 collections, one inside the next, is AAS XML this interpreter "
     "runs out of stack on, and it was told to fix the syntax its parser "
     "rejects -- bare or packaged -- because only JSON was asked"),

    ("loader/a-refusal-does-not-vouch-for-what-it-refused",
     "src/aas_submodel_validate/loader.py",
     'REFUSED_NOT_JUDGED = "Nothing here is a verdict on the document -- it was refused, not judged."',
     'REFUSED_NOT_JUDGED = "Nothing is wrong with what you sent; it was refused, not judged."',
     ["tests/test_registry.py::"
      "test_no_sentence_vouches_for_what_this_reader_did_not_read",
      "tests/test_registry.py::"
      "test_every_sentence_a_violation_carries_is_the_one_that_was_decided",
      "tests/test_registry.py::"
      "test_every_remedy_is_the_sentence_that_was_decided"],
     "five refusals said nothing was wrong with what was sent, or with its "
     "syntax, or that the chain was intact, of documents this reader had "
     "not read -- measured false for a relationships part naming nothing "
     "at all behind a DTD, which was told it names the parts it should"),

    ("container/indexing-that-runs-out-of-memory-is-refused",
     "src/aas_submodel_validate/container.py",
     '        except MemoryError as exc:\n'
     '            raise OutOfMemory("%s: this reader ran out of memory indexing the archive"\n'
     '                              % self.path) from exc\n',
     "",
     ["tests/test_hostile_input.py::"
      "test_a_package_that_runs_this_reader_out_of_memory_is_refused",
      "tests/test_hostile_input.py::"
      "test_the_security_note_holds_where_a_package_runs_this_reader_out_of_memory"],
     "MemoryError while the archive was indexed left as a traceback and "
     "exit 1, the code for a verdict with findings, against SECURITY.md's "
     "sentence that what this reader refuses leaves by the could-not-run code"),

    ("container/a-part-that-runs-out-of-memory-is-refused",
     "src/aas_submodel_validate/container.py",
     '        except MemoryError as exc:\n'
     '            raise OutOfMemory("%s: this reader ran out of memory reading %s"\n'
     '                              % (self.path, name)) from exc\n',
     "",
     ["tests/test_hostile_input.py::"
      "test_a_package_that_runs_this_reader_out_of_memory_is_refused",
      "tests/test_hostile_input.py::"
      "test_the_security_note_holds_where_a_package_runs_this_reader_out_of_memory"],
     "MemoryError while a part was decompressed left as a traceback and "
     "exit 1, where the same bytes as a bare file were refused with exit 2"),

    ("container/a-relationships-part-that-runs-out-of-memory-is-refused",
     "src/aas_submodel_validate/container.py",
     '            except MemoryError as exc:\n'
     '                stopped = OutOfMemory(',
     '            except ZeroDivisionError as exc:\n'
     '                stopped = OutOfMemory(',
     ["tests/test_hostile_input.py::"
      "test_a_package_that_runs_this_reader_out_of_memory_is_refused",
      "tests/test_hostile_input.py::"
      "test_the_security_note_holds_where_a_package_runs_this_reader_out_of_memory",
      "tests/test_hostile_input.py::"
      "test_a_payload_whose_relationships_ran_this_reader_out_of_memory_is_still_read"],
     "MemoryError while a relationships part was parsed left as a traceback "
     "and exit 1, whether the part was the package's chain or a payload's own"),

    ("loader/a-payloads-relationships-running-out-is-refused-not-a-chain",
     "src/aas_submodel_validate/loader.py",
     "        except OutOfMemory as exc:\n"
     "            loaded.errors.append(_ran_out(exc, subject=rels))\n"
     "        except UnreadablePart as exc:\n"
     "            loaded.errors.append(LoadError(\"zip\", str(exc), subject=rels))\n"
     "        except NoRelationships:\n",
     "        except UnreadablePart as exc:\n"
     "            loaded.errors.append(LoadError(\"zip\", str(exc), subject=rels))\n"
     "        except NoRelationships:\n",
     ["tests/test_hostile_input.py::"
      "test_a_payload_whose_relationships_ran_this_reader_out_of_memory_is_still_read"],
     "without its own handler the stop falls to the chain stage and is "
     "told to repair a chain nobody has seen broken -- the fourth place a "
     "package is read from, and the one no other test reaches"),

    ("container/a-parts-relationships-are-read-once",
     "src/aas_submodel_validate/container.py",
     "        if source not in self._relationships:\n",
     "        if True:\n",
     ["tests/test_hostile_input.py::"
      "test_a_parts_relationships_are_read_once_whoever_asks"],
     "X4 reread a payload's relationships after the loader had, met a "
     "refusal the first read had survived, and skipped the part as "
     "reported: the X4 finding vanished and the run left by 0 calling "
     "itself complete"),

    ("container/the-parser-saying-it-ran-out-is-a-stop",
     "src/aas_submodel_validate/container.py",
     'and getattr(exc, "code", None) == _EXPAT_NO_MEMORY)',
     "and False)",
     ["tests/test_hostile_input.py::"
      "test_a_package_that_runs_this_reader_out_of_memory_is_refused",
      "tests/test_loader.py::"
      "test_xml_that_runs_this_reader_out_of_memory_is_told_the_reader_stopped"],
     "expat reports running out of memory as a parse error with its own "
     "code, and a relationships part it could not finish was told it does "
     "not parse, a payload to fix its syntax"),

    ("loader/decoding-xml-that-runs-out-is-a-stop",
     "src/aas_submodel_validate/loader.py",
     "    except MemoryError as exc:\n"
     "        _payload_error(loaded, part, exc, _out_of_room(exc, building=False))\n",
     "    except ZeroDivisionError as exc:\n"
     "        _payload_error(loaded, part, exc, _out_of_room(exc, building=False))\n",
     ["tests/test_loader.py::"
      "test_xml_that_runs_this_reader_out_of_memory_is_told_the_reader_stopped"],
     "converting a UTF-16 document to UTF-8 sat before the guarded parse, "
     "and running out of memory there left as a traceback, bare or packaged"),

    ("loader/a-bare-xml-that-runs-out-decoding-is-a-stop",
     "src/aas_submodel_validate/loader.py",
     "    except Exception as exc:\n"
     "        _payload_error(loaded, None, exc, _out_of_room(exc, building=False))\n",
     "    except UnicodeDecodeError as exc:\n"
     "        _payload_error(loaded, None, exc, _out_of_room(exc, building=False))\n",
     ["tests/test_loader.py::"
      "test_xml_that_runs_out_of_memory_being_decoded_is_told_the_reader_stopped"],
     "converting to UTF-8 hands the common case back untouched, so the "
     "decode to text beside it is where a bare .xml near the bound runs out "
     "-- narrow that guard to the encoding error alone and running out of "
     "memory there leaves as a traceback"),

    ("loader/a-packaged-xml-that-runs-out-decoding-is-a-stop",
     "src/aas_submodel_validate/loader.py",
     "        except Exception as exc:\n"
     "            _payload_error(loaded, part, exc, _out_of_room(exc, building=False))\n",
     "        except UnicodeDecodeError as exc:\n"
     "            _payload_error(loaded, part, exc, _out_of_room(exc, building=False))\n",
     ["tests/test_loader.py::"
      "test_xml_that_runs_out_of_memory_being_decoded_is_told_the_reader_stopped"],
     "the same decode guards a packaged XML part -- narrow it to the "
     "encoding error alone and a part near the bound that runs out of memory "
     "being decoded leaves as a traceback, not a recorded stop"),

    ("loader/a-payloads-relationships-are-filed-under-that-part",
     "src/aas_submodel_validate/loader.py",
     "        rels = container.relationships_part_name(part)\n",
     "        rels = part\n",
     ["tests/test_hostile_input.py::"
      "test_a_refusal_of_a_payloads_relationships_is_filed_under_that_part"],
     "a refused relationships part was filed under the payload's name, so "
     "one report said 'judged 1 of 1' and that the same document was "
     "refused and not judged"),

    ("report/the-summary-says-not-judged",
     "src/aas_submodel_validate/report.py",
     'some of it was not judged)"',
     'some of it was not read)"',
     ["tests/test_cli.py::"
      "test_a_screen_does_not_say_what_its_own_remedy_contradicts",
      "tests/test_readme_front.py::"
      "test_the_summary_the_page_quotes_is_the_one_printed"],
     "a document read to the end and stopped while building was told by "
     "its remedy that it was read, and by the summary beside it that it "
     "was not"),

    ("loader/a-part-not-utf8-is-rebuilt-not-resaved",
     "src/aas_submodel_validate/loader.py",
     "NOT_UTF8_IN_A_PACKAGE if packaged else NOT_UTF8",
     "NOT_UTF8",
     ["tests/test_loader.py::"
      "test_whether_the_bytes_were_cut_short_is_read_from_the_last_ones",
      "tests/test_loader.py::"
      "test_a_packaged_json_part_is_answered_the_way_the_same_bare_file_is"],
     "a package's part that is not UTF-8 was told to save the file, the "
     "same shape the cut-short remedy was fixed for"),

    ("loader/cut-short-is-asked-of-the-bytes",
     "src/aas_submodel_validate/loader.py",
     "decode(exc.object[exc.start:], final=False)",
     "decode(exc.object[exc.end:], final=False)",
     ["tests/test_loader.py::"
      "test_whether_the_bytes_were_cut_short_is_read_from_the_last_ones"],
     "the half of the cut-short question asked of the bytes could be "
     "deleted with the suite green: a file ending in a byte no character "
     "starts with was told it looked cut short"),

    ("loader/a-byte-order-mark-keeps-the-bytes-it-was-read-from",
     "src/aas_submodel_validate/loader.py",
     "raise UnicodeDecodeError(exc.encoding, raw, exc.start + 3",
     "raise UnicodeDecodeError(exc.encoding, exc.object, exc.start + 3",
     ["tests/test_loader.py::"
      "test_whether_the_bytes_were_cut_short_is_read_from_the_last_ones"],
     "re-raised over the bytes after the mark, a file with one cut short "
     "mid-character was told it was not UTF-8; the test that held it only "
     "did so because its bad byte sat by the end"),

    ("ci/a-job-line-it-does-not-read-fails",
     "tests/test_ci_parity.py",
     '            named = job_line.match(line.rstrip("\\n"))\n'
     '            assert named, (',
     '            named = job_line.match(line.rstrip("\\n"))\n'
     '            if not named:\n'
     '                continue\n'
     '            assert named, (',
     ["tests/test_ci_parity.py::"
      "test_a_job_line_this_does_not_read_fails_rather_than_joining_the_job_above"],
     "`test :` and `? test` are valid YAML job lines the pattern did not "
     "match; each folded into the job above and borrowed its settings, a "
     "token grant included"),

    ("container/an-oversized-conversion-is-refused-not-handed-on",
     "src/aas_submodel_validate/container.py",
     '    if len(converted) > MAX_PART_BYTES:\n'
     '        raise PartTooLarge(\n'
     '            "a document declaring %s is %d bytes as UTF-8, above the %d byte "\n'
     '            "limit" % (encoding, len(converted), MAX_PART_BYTES))\n'
     '    return converted',
     "    return raw if len(converted) > MAX_PART_BYTES else converted",
     ["tests/test_hostile_input.py::"
      "test_a_relationships_part_whose_utf8_form_is_over_the_cap_is_refused",
      "tests/test_hostile_input.py::"
      "test_an_xml_document_whose_utf8_form_is_over_the_cap_is_refused",
      "tests/test_xml_encoding.py::"
      "test_a_conversion_that_would_break_the_part_bound_is_refused"],
     "a UTF-16 relationships part whose UTF-8 form crossed the 64 MiB bound "
     "was handed on unconverted, past declares_doctype (which reads UTF-8) "
     "to a parser that decodes UTF-16 and expands the DTD -- so a nested "
     "DTD refused at any smaller size was processed; present in 0.1.3, 0.1.4"),

    ("container/a-relationships-part-is-found-by-equivalence",
     "src/aas_submodel_validate/container.py",
     "        held = self.part(rels)\n",
     "        held = rels if rels in self._names else None\n",
     ["tests/test_hostile_input.py::"
      "test_a_relationships_part_under_an_equivalent_name_is_still_read"],
     "a payload's relationships part stored as _rels/Env.json.rels was "
     "looked for by exact spelling, found absent, and X4 passed over the "
     "suppl files it declared -- a broken container complete at exit 0"),

    ("container/a-relationships-root-must-be-relationships",
     "src/aas_submodel_validate/container.py",
     "        if root.tag != _RELATIONSHIPS:\n",
     "        if False:\n",
     ["tests/test_hostile_input.py::"
      "test_a_relationships_part_that_is_not_one_is_a_container_defect"],
     "a part in the relationships slot whose root is not OPC Relationships "
     "parsed and yielded no relationships, read as declaring none, so a "
     "missing suppl file drew nothing and the run was complete at exit 0"),

    ("container/one-part-named-twice-is-refused",
     "src/aas_submodel_validate/container.py",
     "        if len(names) != len(self._names):\n",
     "        if False:\n",
     ["tests/test_hostile_input.py::"
      "test_an_archive_naming_one_part_twice_is_refused"],
     "a ZIP naming one part twice was deduped to the last entry silently, "
     "so a defective member ahead of a clean one went unread and the "
     "container passed complete while a consumer might extract the other"),

    ("container/an-encoding-the-parser-cannot-honour-is-caught",
     "src/aas_submodel_validate/container.py",
     "        except (ElementTree.ParseError, LookupError, ValueError) as exc:",
     "        except ElementTree.ParseError as exc:",
     ["tests/test_hostile_input.py::"
      "test_a_relationships_part_the_reader_cannot_decode_is_a_finding_not_a_crash"],
     "a relationships part declaring a codec the parser cannot honour (a "
     "NUL in the name, an unknown codec) left the process by a traceback "
     "and exit 1, on a file it never read"),

    ("loader/an-encoding-with-a-nul-in-the-name-does-not-crash",
     "src/aas_submodel_validate/container.py",
     "    except (UnicodeError, LookupError, ValueError):",
     "    except (UnicodeError, LookupError):",
     ["tests/test_hostile_input.py::"
      "test_a_document_the_reader_cannot_decode_does_not_crash",
      "tests/test_hostile_input.py::"
      "test_a_relationships_part_the_reader_cannot_decode_is_a_finding_not_a_crash"],
     "an encoding name with a NUL in it raised ValueError from the codec "
     "lookup, uncaught, so a bare document and a payload left by a "
     "traceback and exit 1"),

    ("loader/an-environment-that-reached-the-rules-is-judged",
     "src/aas_submodel_validate/loader.py",
     "        return bool(self.errors) and not self.submodels and not self.environments",
     "        return bool(self.errors) and not self.submodels",
     ["tests/test_hostile_input.py::"
      "test_an_environment_read_beside_a_broken_part_is_still_a_verdict"],
     "an environment with a shell and no template submodel, beside a "
     "relationships part that would not parse, was called nothing-judged "
     "and left by 2, though the walk had seen it and the metamodel channel "
     "had verified it -- a verdict under the code a gate reads as could-not-run"),

    ("ci/every-job-has-a-time-limit",
     ".github/workflows/ci.yml",
     "    runs-on: ${{ matrix.os }}\n    timeout-minutes: 15\n",
     "    runs-on: ${{ matrix.os }}\n",
     ["tests/test_ci_parity.py::test_every_job_has_a_time_limit"],
     "a job with no limit runs to GitHub's six-hour ceiling, so a test "
     "that hangs instead of failing holds a runner that long before "
     "anything goes red -- measured: one wrong offset in the prolog walk "
     "stops an in-process CLI test"),
    ("runner/a-rule-out-of-resources-is-not-a-tool-bug",
     "src/aas_submodel_validate/runner.py",
     "        except (MemoryError, RecursionError) as exc:",
     "        except (KeyboardInterrupt,) as exc:",
     ["tests/test_runner.py::"
      "test_a_rule_that_runs_out_of_memory_or_stack_is_not_called_a_validator_defect"],
     "a rule that ran out of memory or stack walking a document within the "
     "size bound was told it is a defect in this tool to report -- the same "
     "advice a rule with a real bug gets, on a file that is large but legal"),

    ("loader/a-bare-submodel-is-read-from-xml",
     "src/aas_submodel_validate/loader.py",
     '                return isinstance(tag, str) and tag.rsplit("}", 1)[-1] == "submodel"',
     '                return isinstance(tag, str) and tag.rsplit("}", 1)[-1] == "environment"',
     ["tests/test_loader.py::test_a_bare_submodel_xml_file"],
     "the reader tells a bare Submodel from an environment by the XML root "
     "element; misread the root and a bare Submodel given as .xml is built "
     "as an environment, which it is not, and never read as the Submodel it "
     "is"),

    ("runner/a-loss-without-the-element-is-half-an-answer",
     "src/aas_submodel_validate/runner.py",
     "    report.unmatched = rules.engine.unmatched_elements(ctx)",
     "    report.unmatched = []",
     ["tests/test_unmatched_coverage.py::test_a_reported_loss_now_names_the_element_behind_it",
      "tests/test_unmatched_coverage.py::test_the_note_is_machine_readable"],
     "the walk knows which element left rules unasked and the report used to "
     "throw it away, so the reader was told a count and left to find the "
     "element. Drop this line and the count comes back alone -- which is the "
     "state this replaced, and it looks like a working report."),
    ("dn/uri-of-the-product-must-be-absolute-not-just-present",
     "src/aas_submodel_validate/rules/dn.py",
     "        if not _SCHEME.match(value.strip()):",
     "        if not value:",
     ["tests/test_hand_rules.py::"
      "test_a_relative_uri_of_the_product_is_not_a_global_identification"],
     "DN-D1 checks only that URIOfTheProduct is non-empty, not that it is "
     "absolute -- a relative reference like 'Model-1234/Serial' passes the "
     "metamodel and this rule both, and is not the unique global "
     "identification the template's definition asks for"),
    ("cli/a-usage-error-leaves-by-64",
     "src/aas_submodel_validate/cli.py",
     "        raise SystemExit(EXIT_USAGE)",
     "        raise SystemExit(EXIT_ERROR)",
     ["tests/test_a_usage_error_exits_64.py::test_a_wrong_call_exits_64"],
     "0.3.0 announced, one release ahead and in four public places, that a "
     "usage error would leave by 64. Put the old code back and every wrong "
     "call is 2 again -- indistinguishable from a file that could not be "
     "judged, which is the conflation the announcement was about. Measured: "
     "nineteen assertions die, and eight of them are in test_cli_flags.py, "
     "which this release converted to the constant. What nothing catches is "
     "the sentence, which is argparse's and is unchanged -- an earlier "
     "version of this row said nothing else notices at all, and the suite "
     "disproved it in one run."),
    ("cli/could-not-run-did-not-quietly-become-called-wrong",
     "src/aas_submodel_validate/cli.py",
     "              % (refusal or \"nothing in %s was judged\" % path), "
     "file=sys.stderr)\n        return EXIT_ERROR",
     "              % (refusal or \"nothing in %s was judged\" % path), "
     "file=sys.stderr)\n        return EXIT_USAGE",
     ["tests/test_a_usage_error_exits_64.py::test_could_not_run_still_exits_2"],
     "the other half of the same release, and the half a change like this "
     "loses by accident: moving usage errors off 2 buys nothing if a path "
     "that cannot be read drifts onto 64 with them, and a pipeline would "
     "then read a missing file as its own mistake and stop looking for the "
     "file. Aimed here rather than at the `UnreadablePath` clause above, "
     "which the first version of this row picked and where the mutant "
     "survived: `runner.run` catches that exception and returns a report, "
     "so the clause in `cli` is not on the path any unreadable input "
     "takes -- measured with `trace` over five shapes, and again by making the clause raise and running the suite, which stayed green."),
    ("engine/a-subject-under-two-same-named-parents-is-two-subjects",
     "src/aas_submodel_validate/rules/engine.py",
     "    names = Counter(element.id_short for element in elements if element.id_short)\n"
     "    shared = {name for name, count in names.items() if count > 1}",
     "    shared = set()",
     ["tests/test_unmatched_coverage.py::"
      "test_two_scopes_that_each_lost_rules_are_two_records"],
     "two containers in one scope can carry the same idShort -- the "
     "metamodel forbids it and this reader relays that as a warning rather "
     "than refusing the file, so such a file is judged. With this empty, an "
     "element under either container gets the same subject, and the record "
     "keyed on it keeps one: the reader is told a single element left rules "
     "unasked when two did. Measured before the fix on a file with two "
     "ContactInformation containers, each holding a drifted Phone: one "
     "record."),
    ("model/a-rules-own-text-goes-through-the-same-funnel",
     "src/aas_submodel_validate/model.py",
     '        for name in ("title", "spec", "fix"):',
     '        for name in ():',
     ["tests/test_hostile_input.py::"
      "test_a_rules_own_text_is_bounded_the_way_a_violations_is"],
     "the bound's own comment said every finding is built through "
     "`Violation`, \"so this is the one funnel\", and it was not one: a "
     "finding carries its rule's title, and its fix falls back to the "
     "rule's when the violation has none. Measured with this emptied: a "
     "rule whose text is 200,000 characters reaches the JSON at 200,014 "
     "and 200,000, beside a violation cut at 2,000. Every generated pack "
     "interpolates that text from the template's own strings, so the "
     "length is the template's to choose."),
    ("container/a-path-is-opened-only-after-the-descriptor-says-what-it-is",
     "src/aas_submodel_validate/container.py",
     "        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):\n"
     "            raise OSError(errno.EINVAL, \"not a regular file\", str(path))",
     "        pass",
     ["tests/test_hostile_input.py::"
      "test_open_regular_refuses_a_stream_and_opens_a_file"],
     "`O_NONBLOCK` above stops the hang -- a FIFO opens at once instead "
     "of waiting for a writer -- and this is what decides what to do with "
     "what was opened. Without it a pipe is not refused, it is read: "
     "measured against a writer holding one open and feeding it, the "
     "handle's first read is b'{\"submodels\": []}'. The reader would "
     "judge whatever was in a stream's buffer at the instant it looked, "
     "and `inputSha256` would be a hash of bytes with no file behind "
     "them. The first check aimed at this row was the end-to-end one and "
     "this mutant survived it, because the loader refuses a named path "
     "before anything opens it -- a property held by two mechanisms needs "
     "a test per mechanism."),
    ("engine/the-same-input-is-the-same-report-in-any-process",
     "src/aas_submodel_validate/rules/engine.py",
     "    return sorted(set(missed), key=lambda rid: (order.get(rid, len(order)), rid))",
     "    return sorted(set(missed), key=lambda rid: order.get(rid, len(order)))",
     ["tests/test_the_report_is_the_same_twice.py::"
      "test_rules_not_asked_is_ordered_the_same_in_any_process"],
     "everything the tables do not place shares one sort position, and "
     "`sorted` is stable over a set -- whose iteration order is string-"
     "hash order, randomised per process. Measured with the tie removed "
     "and a table that is not an imported module: five interpreters, five "
     "different orders for the same input, so the same file gives two "
     "reports nobody can diff. Nothing reaches that fallback today; the "
     "arriving `--template` mode is what makes a table not a module, and "
     "a fallback that is only correct while nothing takes it is not "
     "correct."),
    ("template/a-run-time-rule-goes-through-the-crash-funnel",
     "src/aas_submodel_validate/runner.py",
     "        rules_to_run = list(rules_to_run) + tablegen.rules_for(\n"
     "            supplied[\"table\"], supplied[\"pack\"])",
     "        tablegen.rules_for(supplied[\"table\"], supplied[\"pack\"])",
     ["tests/test_a_template_a_caller_supplied.py::"
      "test_a_submodel_judged_by_a_supplied_template_counts_as_judged"],
     "`execute` is the only place here where a rule that raises becomes a "
     "finding rather than a traceback, and it is handed `rules_to_run`. "
     "Build the rules and drop them and a template the caller supplied is "
     "read, accepted and then judged by nobody -- the run reports on the "
     "packs alone and says nothing about the flag it was given."),
    ("template/a-supplied-table-takes-the-identifier-over",
     "src/aas_submodel_validate/rules/engine.py",
     "    if taken and tables.TEMPLATE_SEMANTIC_ID in taken \\\n"
     "            and not getattr(tables, \"_supplied\", False):\n"
     "        return []",
     "    if False:\n"
     "        return []",
     ["tests/test_a_template_a_caller_supplied.py::"
      "test_a_supplied_template_answers_instead_of_the_pack_not_as_well"],
     "two tables for one identifier is one defect reported twice. Measured "
     "with this removed: handing `--template` the very file 02003's pack "
     "was generated from gives two errors where the pack alone gives one, "
     "the same missing element under `TD-E01` and under `TPL-E01`. A build "
     "counting errors then gets a number that depends on a flag rather "
     "than on the file."),
    ("template/a-run-time-id-stays-out-of-the-coverage-record",
     "tests/conftest.py",
     "                     and not finding.id.startswith(RUN_TIME_PREFIX))",
     "                     )",
     # The suite first: `--check` reads an observation the suite writes,
     # and the harness cleans the tree before each row, so naming the
     # tool alone gives a baseline that fails before any mutation.
     ["tests/", "tools/rule_coverage.py --check"],
     "`make exercised` asks whether every rule this project publishes "
     "fired, against a baseline listing exactly those. An id that exists "
     "because somebody passed a file is in neither list, so recording it "
     "fails two of that gate's three comparisons at once. Measured: one "
     "`--template` run in the suite turned it red with `TPL-E01` on both "
     "lines."),
    ("template/a-template-is-refused-rather-than-trusted",
     "src/aas_submodel_validate/tablegen.py",
     # The one inside `_rows`, which is the one that stops the walk. The
     # check after it is a second reading of the same number, reached by
     # a different path and kept for that reason -- so the anchor names
     # the line above it rather than the bare condition, which now
     # appears twice.
     "    counter[0] += 1\n"
     "    if counter[0] > MAX_TEMPLATE_ROWS:",
     "    counter[0] += 1\n"
     "    if False:",
     ["tests/test_a_template_a_caller_supplied.py::"
      "test_a_template_above_the_bound_is_refused_without_being_built"],
     "a template is not covered by the bound on the document being judged "
     "-- they are different files, and forty-six megabytes of template "
     "sits inside the sixty-four this reader advertises. What a generator "
     "spends is decided by rows, and with this gone a caller's file "
     "reaches the duplicate-label backstop at any width. Checked here "
     "rather than after the walk because after it the bound stopped only "
     "the second pass: measured, 300,000 rows were built in 2.2s and 282 "
     "MiB before the refusal, and 0.06s and 10 MiB once the walk refuses "
     "as it goes."),

    ("template/an-open-content-marker-is-not-an-identity",
     "src/aas_submodel_validate/tablegen.py",
     "    return tuple(sorted(_declared_values(element) - skip_sids))",
     "    return tuple(sorted(_declared_values(element)))",
     ["tests/test_a_template_a_caller_supplied.py::"
      "test_a_marker_beside_a_real_identity_does_not_become_one"],
     "a marker says a place is open, not what belongs in it. Left among "
     "a row's match values it is an identity like any other, and the "
     "supplier's own element under that marker answers the row. "
     "Measured: a template requiring one `urn:test:real`, a file holding "
     "only the supplier's element -- `ok` true, no findings, the "
     "required element absent. Across the packs 0 of 156 rows carried "
     "one, because all 43 markers in the vendored templates are an "
     "element's own semanticId; this is what a caller's template can do"),

    ("template/a-table-of-no-rows-says-it-compared-nothing",
     "src/aas_submodel_validate/runner.py",
     '        if not supplied["table"].ROWS:',
     "        if False:",
     ["tests/test_a_template_a_caller_supplied.py::"
      "test_a_template_that_states_no_checkable_rule_says_so"],
     "a submodel judged against a table of no rows is judged, so "
     "`--require-all-judged` passes it and the run comes back `ok` at "
     "exit 0 having compared nothing. The only trace was "
     "`provenance.template.rows` at zero -- a field nobody reading the "
     "screen sees, and the one number that would have told them"),

    ("template/a-row-nothing-can-answer-is-not-an-obligation",
     "src/aas_submodel_validate/tablegen.py",
     "    unidentified = not match and not in_list",
     "    unidentified = False",
     ["tests/test_a_template_a_caller_supplied.py::"
      "test_an_element_the_template_identifies_with_nothing_is_not_an_obligation"],
     "matching is by identifier and never by idShort, so an element a "
     "template declares with no semanticId has an empty match set and "
     "nothing outside a list can answer it. As a mandatory row that was "
     "an error no file could clear: measured, a file carrying an element "
     "of exactly the name the template writes was told `found 0`, under "
     "a remedy that ended \"with semanticId \" and stopped because there "
     "was nothing to name"),

    ("template/a-lists-item-row-is-matched-by-its-kind",
     "src/aas_submodel_validate/tablegen.py",
     "    unidentified = not match and not in_list",
     "    unidentified = not match",
     ["tests/test_a_template_a_caller_supplied.py::"
      "test_a_list_item_with_no_identifier_of_its_own_keeps_its_obligation"],
     "the other side of the line above, and the reason it is a line. A "
     "`SubmodelElementList` names its item row by kind rather than by "
     "identifier, which is how the published templates write one, so an "
     "item carrying no semanticId is the ordinary case. Dropping the "
     "obligation from every unidentified row takes those with it and a "
     "list the template requires stops being required"),

    ("template/what-the-template-calls-a-place-arbitrary-draws-no-row",
     "src/aas_submodel_validate/tablegen.py",
     '    return "/".join(keys) in markers',
     "    return False",
     ["tests/test_a_template_a_caller_supplied.py::"
      "test_a_placeholder_that_also_names_something_is_still_a_placeholder"],
     "a template's own placeholder generated a rule, and then the "
     "manufacturer's element sitting under it was faulted for not being "
     "the placeholder -- the outcome `docs/divergences.md` #19 names in "
     "advance. What the element carries *beside* the marker describes "
     "the placeholder and does not make the place a requirement: read as "
     "\"every identifier must be a marker\", a placeholder that named a "
     "unit alongside became a mandatory row and a conformant file "
     "reported `found 0`"),

    ("template/a-marker-elsewhere-does-not-take-a-subtree-with-it",
     "src/aas_submodel_validate/tablegen.py",
     '    return "/".join(keys) in markers',
     '    return "/".join(keys) in markers or (\n'
     "        bool(_declared_values(element))\n"
     "        and not (_declared_values(element) - markers))",
     ["tests/test_a_template_a_caller_supplied.py::"
      "test_a_marker_somewhere_other_than_the_elements_own_id_does_not_hide_a_subtree"],
     "read as \"every identifier this element declares is a marker\", a "
     "container with no semanticId of its own and a marker in a "
     "supplemental was dropped and every row beneath it went with it. "
     "Measured on a template whose `Box` holds a mandatory `Inner`: a "
     "file missing `Inner` went from an error to `ok` at exit 0, and no "
     "sentence anywhere said a subtree had been skipped. A conformance "
     "reader going quiet is the one direction with no second opinion"),

    ("template/a-numbering-suffix-is-run-before-it-is-shipped",
     "src/aas_submodel_validate/tablegen.py",
     "            re.compile(pattern)\n"
     "        except re.error:\n"
     "            return None",
     "            pass\n"
     "        except re.error:\n"
     "            return None",
     ["tests/test_a_template_a_caller_supplied.py::"
      "test_a_numbering_suffix_that_is_not_a_repeat_is_read_as_unreadable",
      "tests/test_a_template_a_caller_supplied.py::"
      "test_an_unreadable_naming_suggestion_does_not_take_the_verdict_with_it"],
     "the bracket branch keeps IDTA's suffix as a program, so a template "
     "can hand this reader a program that does not build: `\\d{3,2}` asks "
     "for at least three and at most two. Of the spellings the pattern "
     "admits, forty-five of a hundred and ten are that shape. Unbuilt "
     "here, each one raised the first time its row ran, inside the funnel "
     "-- so a defect in the caller's template was reported on every row "
     "as \"the rule itself could not run\", under a remedy reading \"This "
     "is a defect in the validator, not in your file\", and the run left "
     "by 1 saying `judged 1 of 1` with no row evaluated. The value is a "
     "naming suggestion, so it costs the row its pattern and a note, not "
     "the verdict"),

    ("engine/a-nested-copy-with-no-name-is-still-one-copy",
     "src/aas_submodel_validate/rules/engine.py",
     "            here = _subject(where, child, index, shared)",
     '            here = "%s/%s" % (where, child.id_short or "?")',
     ["tests/test_a_template_a_caller_supplied.py::"
      "test_nested_copies_with_no_name_of_their_own_are_counted_apart"],
     "the note says how many nested copies of a self-containing row the "
     "run did not enter, and `repeats_not_entered` deduplicates. A "
     "`SubmodelElementList`'s children cannot carry an idShort -- the "
     "metamodel forbids it, and that is where repeats sit -- so named "
     "`?` they all became one string. Measured on three copies in one "
     "list: \"did not look inside 1 nested copy below it (H/Node/Nodes/?)\". "
     "One subtree reported for three, at a place with no name. The "
     "fixture the count was first held against names every copy"),

    ("cli/the-value-taking-flags-are-counted-not-recalled",
     "src/aas_submodel_validate/cli.py",
     "            # listing and left by 0. Four entries on this list take a",
     "            # listing and left by 0. Three entries on this list take a",
     ["tests/test_cli_flags.py::"
      "test_the_list_that_refuses_rules_counts_its_own_value_taking_flags"],
     "which entries of the `--rules` refusal list consume the next word "
     "decides which of them can be read for truth, because an empty "
     "string from an unset shell variable is falsy and the flag was "
     "given. Counted by eye three times and wrong three times -- two, "
     "then three, and `-f/--format` was in none of them. The canary "
     "below is a comment nobody reads; this one is read, by a gate that "
     "takes the entries from the list and asks each `add_argument` "
     "whether it takes a value"),

    ("engine/which-submodels-a-table-answers-for-is-decided-once",
     "src/aas_submodel_validate/rules/engine.py",
     # `analyze` is cached the same way three lines of code apart, so
     # the anchor names the call that is this one.
     "        cached = cache[tables.__name__] = _matched_submodels(ctx, tables)",
     "        return _matched_submodels(ctx, tables)",
     ["tests/test_engine_regressions.py::"
      "test_which_submodels_a_table_answers_for_is_decided_once"],
     "the verdict does not move, which is why this survived being "
     "written: every rule of a table asked the same question and got "
     "the same answer. What moves is what it costs, and both of its "
     "numbers belong to the caller. Measured at the row bound, a "
     "supplied table of 9,900 rows against 500 submodels spent 6.48 of "
     "the run's 9.53 seconds re-deciding it; one input of the suite's "
     "own drew 191 walks over the submodels"),

    ("gates/a-table-built-at-run-time-is-timed",
     "tools/time_budget.py",
     'LAYERS = ("cold_start", "corpus_pass", "scale", "rules_layer",\n'
     '          "supplied_template")',
     'LAYERS = ("cold_start", "corpus_pass", "scale", "rules_layer")',
     ["tests/test_the_run_stays_inside_its_time_budget.py::"
      "test_a_table_built_at_run_time_is_timed"],
     "the four layers before it run against tables generated at build "
     "time, so neither the build nor a walk whose cost goes as rows "
     "times submodels is in any of them. Measured: taking the "
     "memoisation above back out moves this layer to 3.98x, and moved "
     "nothing the other four measure"),

    ("template/who-judged-is-one-question-with-two-answers",
     "src/aas_submodel_validate/runner.py",
     # The `else` losing its `if`, which is how this happened: a third
     # note was written between the two halves and took the branch.
     '        else:\n'
     '            # Said, rather than left to a `provenance.template` a consumer',
     '        if True:\n'
     '            # Said, rather than left to a `provenance.template` a consumer',
     ["tests/test_a_template_a_caller_supplied.py::"
      "test_the_two_notes_about_who_judged_cannot_both_be_said"],
     "one note says the supplied template made this verdict and the "
     "other says nothing was judged against it. Written as one if/else "
     "and then a third note was inserted between the halves, which "
     "handed the else to the new condition -- every single-submodel "
     "template that did answer then drew both sentences, and the whole "
     "suite stayed green because nothing asked whether they could "
     "appear together"),

    ("template/a-profile-the-template-overrode-is-said",
     "src/aas_submodel_validate/runner.py",
     "    elif profile in rules.profiles.KEYS:",
     "    elif False:",
     ["tests/test_a_template_a_caller_supplied.py::"
      "test_a_profile_the_supplied_template_overrode_is_not_left_unsaid"],
     "a supplied table takes an identifier from both sides of a profile "
     "pair, so the flag is decided before it is read. The note for a "
     "flag that chose nothing asks `Selection.chosen`, which knows "
     "about the pair and not about the stand-down, so it was silent on "
     "exactly the run where the flag was overridden"),

    ("template/a-file-of-several-templates-says-so",
     "src/aas_submodel_validate/runner.py",
     '        if supplied["declared"] > 1:',
     '        if False:',
     ["tests/test_a_template_a_caller_supplied.py::"
      "test_a_template_file_holding_more_than_one_template_says_so"],
     "the table comes from the first submodel in the file and the rest "
     "are not read. Without this a caller cannot tell 'your other "
     "templates matched nothing' from 'your other templates were never "
     "opened', and those ask opposite things of them"),

    ("template/a-run-time-tables-rows-are-placed",
     "src/aas_submodel_validate/rules/engine.py",
     '    kept = ctx.__dict__.get("_smt_tables") or {}',
     "    kept = {}",
     ["tests/test_a_template_a_caller_supplied.py::"
      "test_a_run_time_table_places_its_rows_in_the_order_it_declares_them"],
     "`rulesNotAsked` is 'in the order the tables declare them'. The "
     "tables were recovered from `sys.modules`, which answers for the "
     "six vendored packs and cannot answer for a `Table` -- its name is "
     "a digest -- so every run-time id fell to the position kept for "
     "rows nothing places and came back sorted by its own spelling. Ids "
     "are padded to two digits, so past ninety-nine rows that is not "
     "the template's order: `TPL-E100` before `TPL-E99`"),

    ("runner/an-unreadable-path-is-a-report-not-an-exception",
     "src/aas_submodel_validate/runner.py",
     "    except UnreadablePath as exc:\n"
     '        loaded = Loaded(path=str(path), form="unopened")',
     "    except UnreadablePath as exc:\n"
     "        raise exc",
     ["tests/test_a_usage_error_exits_64.py::"
      "test_an_unreadable_path_comes_back_as_a_report_and_is_not_raised"],
     "one contract on exit 2 and not one per extension: the same "
     "permission denial reached `.aasx` through the container reader as "
     "an `X1` finding with a JSON document behind it while `.json` and "
     "`.xml` raised and printed nothing, so a pipeline parsing stdout "
     "broke on two of three extensions for a condition none of them "
     "caused. `cli` carried an `except` clause for the propagating "
     "version that `trace` showed none of five unreadable shapes "
     "reaches, and a mutation sending it to 64 survived the suite; the "
     "clause is gone and this is what its absence rests on"),

    ("gates/the-release-commits-numbers-are-read",
     "tests/test_readme_front.py",
     '    return heading.split(" —")[0].strip() == version',
     "    return False",
     ["tests/test_readme_front.py::"
      "test_which_changelog_headings_are_checked_against_this_tree"],
     "the entry's rule counts and byte bounds were checked while the "
     "heading said `unreleased` and not after. This project dates the "
     "heading and bumps the version in one commit, so the gate was off "
     "for exactly the commit that publishes those numbers. Measured: "
     "dating the heading, bumping the version and changing 219 to 218 "
     "in one edit went green before this and red after"),

    ("template/provenance-says-how-many-the-file-held",
     "src/aas_submodel_validate/runner.py",
     '                           "submodels": supplied["declared"]}',
     '                           "submodels": 1}',
     ["tests/test_a_template_a_caller_supplied.py::"
      "test_provenance_says_how_many_templates_the_file_held"],
     "the table is built from the first submodel in the file and the "
     "rest are not read. `rows` and `semanticId` both describe that one "
     "and read the same whether the file held one or five, so without "
     "this field a program cannot tell a template of the caller's that "
     "matched nothing from one this run never opened"),

    ("fixability/a-grade-is-refused-where-it-is-given",
     "src/aas_submodel_validate/model.py",
     '        _graded(self.fixability, self.fixability_why, "a violation")\n',
     "",
     ["tests/test_severity_and_fixability.py::"
      "test_a_grade_is_a_whole_step_with_its_reason_or_nothing"],
     "every grade this package gives is set on a violation, and the first "
     "version refused a grade without a reason only on the rule: "
     "`Violation('x', fixability=2)` went out with a null reason, and '5' "
     "and 9 went out as given"),

    ("fixability/a-drifted-copy-here-is-a-correction",
     "src/aas_submodel_validate/rules/engine.py",
     "            like = {subject for subject, _seen, _expected, near, _element in near_here\n"
     "                    if near is row}\n",
     "            like = set()\n",
     ["tests/test_severity_and_fixability.py::"
      "test_an_element_missing_beside_one_drifted_copy_is_a_2"],
     "`found 0` was graded 5 -- the content is not in this input -- on a "
     "file whose element sat at that very place one version suffix off, "
     "with the near-miss lint saying so on the next line"),

    ("fixability/a-file-value-is-graded-by-the-package",
     "src/aas_submodel_validate/rules/engine.py",
     "    found = len(carrying)\n",
     "    found = 0\n",
     ["tests/test_severity_and_fixability.py::"
      "test_a_file_value_is_graded_by_what_the_package_holds"],
     "a File value naming /aasx/documents/manual.pdf for a file the package "
     "holds in /aasx/files/ was told its bytes were not in the input, "
     "because the grade was fixed per branch and no branch had looked"),

    ("fixability/one-file-under-two-names-is-nothing-to-choose",
     "src/aas_submodel_validate/rules/engine.py",
     "    if len(carrying) > 1 and container.alike(carrying):\n",
     "    if False:\n",
     ["tests/test_severity_and_fixability.py::"
      "test_one_file_stored_under_two_names_is_nothing_to_choose"],
     "the same bytes stored in two folders were graded a choice a person "
     "has to make, and whichever part is chosen is the same file"),

    ("fixability/two-files-of-one-size-are-still-two",
     "src/aas_submodel_validate/container.py",
     "        return len({(info.file_size, info.CRC) for info in infos}) == 1\n",
     "        return len({info.file_size for info in infos}) == 1\n",
     ["tests/test_severity_and_fixability.py::"
      "test_one_file_stored_under_two_names_is_nothing_to_choose"],
     "two manuals of one length and different bytes would have been called "
     "one file stored twice, and the choice between them graded away"),

    ("fixability/an-item-where-its-list-belongs-is-wrapped",
     "src/aas_submodel_validate/rules/engine.py",
     '        return (2, "this element is of the kind the template gives the list\'s "',
     '        return (4, "this element is of the kind the template gives the list\'s "',
     ["tests/test_severity_and_fixability.py::"
      "test_an_item_standing_where_its_list_belongs_is_a_2"],
     "a Language written as a bare Property was graded 4 -- moving it "
     "needs to know what it means -- beside a remedy that wraps it, and "
     "the walk had already told the two cases apart to write that remedy"),

    ("path/a-count-at-the-top-names-the-submodel",
     "src/aas_submodel_validate/rules/engine.py",
     '    here = ("document", "submodel") if top else None\n',
     "    here = None\n",
     ["tests/test_severity_and_fixability.py::"
      "test_a_missing_section_the_template_fully_gives_is_a_2"],
     "PCF-E01's subject is the submodel's idShort, CarbonFootprint, and the "
     "route fixed per rule said it named an element"),

    ("path/a-container-finding-says-file-or-part",
     "src/aas_submodel_validate/rules/container.py",
     "    if subject is None or subject != ctx.loaded.path:\n",
     "    if True:\n",
     ["tests/test_severity_and_fixability.py::"
      "test_a_container_rule_says_whether_it_named_the_file_or_a_part"],
     "X3 of a bare JSON document names the document's own path and X3 of a "
     "package names a part, and a route fixed per rule said 'part' of both"),

    ("path/no-subject-is-the-whole-input",
     "src/aas_submodel_validate/model.py",
     '            return ("container",) if self.rule.kind == "container" else ("document",)\n',
     "            return self.rule.path\n",
     ["tests/test_severity_and_fixability.py::"
      "test_a_rule_that_could_not_run_claims_no_grade"],
     "the report says a null subject means the document as a whole, and a "
     "finding with none took its rule's route instead: SMT-D1, which never "
     "names a subject, said it named a submodel, and a rule that could not "
     "run said it named an element"),

    ("scope/a-near-miss-claims-only-what-it-resembles",
     "src/aas_submodel_validate/rules/engine.py",
     '                result["unmatched"].append((subject, seen, lost, expected))\n'
     '                result["lost_candidates"].extend(lost)\n',
     '                result["unmatched"].append((subject, seen, lost, expected))\n'
     '                result["lost_candidates"].extend(unentered)\n',
     ["tests/test_scope_the_run_did_not_examine.py::"
      "test_a_near_miss_claims_only_the_rows_it_resembles"],
     "a list one version suffix off reported the rules of an optional "
     "section the file omits beside it as rules the drift had kept from "
     "being asked: one near miss claimed every row its place left "
     "unentered, from 0.1.2 on"),

    ("scope/a-near-miss-is-charged-what-its-element-holds",
     "src/aas_submodel_validate/rules/engine.py",
     "                for rule_id in _asked_inside(row, element):\n",
     "                for rule_id in _descendant_ids(row):\n",
     ["tests/test_unmatched_coverage.py::"
      "test_a_near_miss_is_charged_only_what_its_element_would_have_asked"],
     "a drifted Section holding no Sub was charged the rules beneath Sub, "
     "which matched it would not have asked either: a place not examined, "
     "reported as something the drift kept from being asked"),

    ("scope/a-drifted-leaf-claims-nothing",
     "src/aas_submodel_validate/rules/engine.py",
     '                result["lost_candidates"].extend(lost)\n\n\ndef _near_miss(',
     '                result["lost_candidates"].extend(lost)\n'
     '        result["lost_candidates"].extend(unentered)\n\n\ndef _near_miss(',
     ["tests/test_scope_the_run_did_not_examine.py::"
      "test_a_near_miss_elsewhere_does_not_hide_the_place"],
     "a Nameplate whose serial number drifted reported the three rules of "
     "an asset-specific section it does not carry as rules the drift kept "
     "from being asked -- a leaf resembles no row with anything beneath "
     "it, so the first row's line is never reached on this shape"),

    ("scope/what-only-a-drifted-copy-holds-is-its-loss",
     "src/aas_submodel_validate/rules/engine.py",
     '            if not row["children"]:\n'
     '                continue\n'
     '            grouped.setdefault(',
     '            if claimed_by.get(row["id"]) or not row["children"]:\n'
     '                continue\n'
     '            grouped.setdefault(',
     ["tests/test_scope_the_run_did_not_examine.py::"
      "test_what_only_the_drifted_copy_holds_is_its_loss"],
     "a drifted copy of a list beside the intact one, holding a section the "
     "intact one does not, was charged nothing because its sibling had "
     "entered the row: the section's rules were asked of nothing, and "
     "rulesNotAsked said so of nobody"),

    ("unmatched/one-record-holds-every-tables-rules",
     "src/aas_submodel_validate/rules/engine.py",
     "            for rule in unasked:\n"
     "                if rule not in held:\n"
     "                    held.append(rule)\n",
     "            if len(unasked) > len(held):\n"
     "                held[:] = list(unasked)\n",
     ["tests/test_unmatched_coverage.py::"
      "test_an_element_two_tables_walked_is_charged_with_both",
      "tests/test_unmatched_coverage.py::"
      "test_two_elements_printed_as_one_place_lose_no_rule"],
     "a container two tables walked kept the larger of its two records, and "
     "seven rules stood in rulesNotAsked with no element beside them"),

    ('hs/a-nested-copy-takes-the-rows-it-copies',
     'src/aas_submodel_validate/rules/engine.py',
     '            below = (copied or {}).get(row["recurses"], ()) if row.get("recurses") \\\n',
     '            below = () if row.get("recurses") \\\n',
     ['tests/test_generated_rules_hs.py::test_a_defect_below_the_template_is_judged_where_it_is', 'tests/test_a_template_a_caller_supplied.py::test_a_template_that_contains_itself_is_judged_at_every_depth'],
     'a node four levels down in a bill of material, carrying the wrong valueType, was judged by nobody: the table stops one level down, and until the walk gave a nested copy the rows of the element it copies, the run only said in a note that it had not looked'),

    ('hs/a-copy-the-walk-reached-is-not-reported-missed',
     'src/aas_submodel_validate/rules/engine.py',
     '            if carried and judged and not claimed:\n',
     '            if carried and judged:\n',
     ['tests/test_generated_rules_hs.py::test_a_defect_below_the_template_is_judged_where_it_is'],
     'every nested copy is found by the same walk that names the ones it did not reach; without the reached set the note says the run did not look inside copies it has just judged'),

    ('tablegen/a-copy-is-a-row-at-its-own-cardinality',
     'src/aas_submodel_validate/tablegen.py',
     '                          repeats=my_sid if copies else None)\n',
     '                          repeats=None)\n',
     ['tests/test_hierarchical_scheme_spec.py::test_a_self_containing_entity_gives_its_copy_a_marked_row'],
     "02011's nested Node is 0..* where the Node holding it is 1..*; marked as a copy it is walked at any depth, and unmarked it is an ordinary row that stops the walk one level down"),

    ('hs/a-copy-below-a-missed-copy-is-counted',
     'src/aas_submodel_validate/rules/engine.py',
     '                found.append((here, sorted(carried)[0]))\n',
     '                found.append((here, sorted(carried)[0]))\n                continue\n',
     ['tests/test_a_template_a_caller_supplied.py::test_a_copy_below_a_copy_the_walk_missed_is_counted_too'],
     'a copy the walk did not reach hides the copies inside it from the walk too; counting only the first of a chain reported one copy of two'),

    ('hs/a-bill-says-what-the-walk-missed',
     'src/aas_submodel_validate/rules/engine.py',
     '        if copied:\n            per["not_entered"] = _copies_not_reached(\n',
     '        if copied and False:\n            per["not_entered"] = _copies_not_reached(\n',
     ['tests/test_generated_rules_hs.py::test_what_the_walk_could_not_reach_in_a_bill_is_said'],
     "a node inside a collection wearing Node's identifier three levels down is reached by nothing, and what it carries went unjudged with nothing said"),

    ('hs/a-node-inside-nothing-judged-is-not-counted',
     'src/aas_submodel_validate/rules/engine.py',
     '    stack = [(elements, root, False)]\n',
     '    stack = [(elements, root, True)]\n',
     ['tests/test_generated_rules_hs.py::test_a_node_beside_the_entry_is_not_a_nested_copy',
      'tests/test_generated_rules_hs.py::test_nodes_under_an_entry_the_run_could_not_place_are_said_once'],
     "a Node at the submodel's root, and the first-level Nodes under a drifted entry node, were "
     "called nested copies: the first is an element no row describes, and the second is the place "
     "scopeNotExamined names"),

    ('hs/a-node-in-a-box-in-the-entry-is-counted',
     'src/aas_submodel_validate/rules/engine.py',
     '            stack.append((_sub_elements(child), here, judged or claimed))\n',
     '            stack.append((_sub_elements(child), here, judged or (claimed and bool(carried))))\n',
     ['tests/test_generated_rules_hs.py::test_a_node_in_a_container_the_entry_holds_is_counted',
      'tests/test_generated_rules_hs.py::test_a_node_under_a_node_whose_identifier_drifted_is_counted'],
     "a Node in a collection no row describes was counted inside a judged Node and not directly "
     "inside the judged entry node, which carries another identifier -- the same container, told "
     "apart by where it sat"),

    ('hs/one-sibling-s-reach-is-not-another-s',
     'src/aas_submodel_validate/rules/engine.py',
     '            stack.append((_sub_elements(child), here, judged or claimed))\n',
     '            judged = judged or claimed\n'
     '            stack.append((_sub_elements(child), here, judged))\n',
     ['tests/test_generated_rules_hs.py::test_a_stray_at_the_root_does_not_change_what_the_bill_is_told'],
     "a flag kept for a level rather than a path let the entry node's reach stand for the stray Node "
     "beside it at the root, which was then counted as a copy the run had missed"),

    ('tablegen/a-copy-reads-its-own-cardinality',
     'src/aas_submodel_validate/tablegen.py',
     '    endless = card[0] if repeats and card[0] > 0 else None\n',
     '    card = (0, None) if repeats else card\n    endless = card[0] if repeats and card[0] > 0 else None\n',
     ['tests/test_hierarchical_scheme_spec.py::test_a_self_containing_entity_gives_its_copy_a_marked_row'],
     "the nested copy's bound is the template's -- ZeroToOne in the test -- and a generator assuming 0..* passed the test that claimed it read it"),

]

#: The row that must live. A comment nobody reads, in a file whose prose
#: no test asserts. Measured before it was written down: with this line
#: added the suite reads exactly what it reads without it.
CANARY = ("canary/a-comment-nobody-reads",
          "src/aas_submodel_validate/container.py",
          "    # -- files ---",
          "    # canary: nothing reads this line, so a run that kills it\n"
          "    # is a run that would kill anything\n    # -- files ---",
          ["tests/test_part_names.py"],
          "if this dies, every result above it is void")

TABLE.append(CANARY)


def clear(tree: Path) -> None:
    for cache in tree.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def shim(tree: Path) -> Path:
    """A directory putting `python` on PATH, because lifted workflow steps
    call it and CI's `setup-python` is what usually supplies it."""
    d = tree / ".harness-bin"
    d.mkdir(exist_ok=True)
    p = d / "python"
    p.write_text('#!/bin/sh\nexec "%s" "$@"\n' % sys.executable)
    p.chmod(0o755)
    return d


def lift(tree: Path, spec: str):
    """A workflow step's own script, pulled out of its YAML so it can run
    here.

    Some gates are not tests and not tools -- they are shell inside a
    `run:` block that only ever executes when a tag is pushed, which is
    the worst place to learn one of them is broken. Spelled
    `step:<workflow>:<step name>`.

    The `pip install` lines are dropped: the harness already puts this
    tree's `src` on `PYTHONPATH`, and letting a row reach the network
    would make the result depend on an index. Everything else
    runs as written.
    """
    _, workflow, name = spec.split(":", 2)
    text = (tree / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    found = re.search(r"      - name: %s\n(?:\s+#[^\n]*\n)*"
                      r"        run: \|\n((?:[ ]{10}[^\n]*\n|\n)+)"
                      % re.escape(name), text)
    if found is None:
        raise SystemExit("no step named %r in %s" % (name, workflow))
    body = "".join(line[10:] if line.startswith(" " * 10) else line
                   for line in found.group(1).splitlines(keepends=True))
    kept = [line for line in body.splitlines()
            if not line.strip().startswith("pip install")]
    #: `_ran` reads a pytest summary and a lifted step has none, so a
    #: script that turned out to be empty -- a regex that matched a step
    #: whose body is nothing but the installs above, say -- would exit 0
    #: before and after, and the row would report `survived` forever
    #: while asserting nothing. Cheap to rule out at the point of
    #: lifting, so it is ruled out here rather than left as a limitation.
    if not [line for line in kept if line.strip() and not line.strip().startswith("#")]:
        raise SystemExit(
            "%s: lifting left nothing to run, so this row could only ever "
            "report survived" % spec)
    return "\n".join(kept)


def _declared_version(tree: Path) -> str:
    found = re.search(r'(?m)^version = "([^"]+)"',
                      (tree / "pyproject.toml").read_text(encoding="utf-8"))
    return found.group(1) if found else "0.0.0"


def run(tree: Path, checks: list) -> tuple:
    """Whatever the row names. Returns (worst exit code, what pytest said).

    `said` is None when the row names no pytest selection, which is
    different from a selection that printed nothing.
    """
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env["PATH"] = "%s%s%s" % (shim(tree), os.pathsep, env.get("PATH", ""))
    env["PYTHONPATH"] = os.pathsep.join(
        [str(tree / "src"), str(tree / "tests"), env.get("PYTHONPATH", "")])
    #: In the order the row lists them, because some gates read what an
    #: earlier one wrote. `tools/rule_coverage.py --check` compares the
    #: file the suite leaves behind against the committed baseline, and
    #: run on its own it says `no .rule-coverage.json -- run the suite
    #: first` -- a red baseline for a reason that is not the row's, which
    #: the harness would report as "already fails before the mutation".
    #: A row states the dependency by listing the suite before the tool.
    worst, said = 0, None
    for spec in checks:
        if spec.startswith("step:"):
            script = tree / ".harness-step.sh"
            script.write_text(lift(tree, spec))
            # The tag the workflow would see, taken from the tree being
            # measured, so the baseline is green by construction and a
            # row that breaks the agreement is what makes it red.
            code = subprocess.run(
                ["sh", str(script)], cwd=tree, capture_output=True, text=True,
                env=dict(env, GITHUB_REF_NAME="v" + _declared_version(tree))
            ).returncode
        elif spec.startswith("tools/"):
            code = subprocess.run([sys.executable, *spec.split()], cwd=tree,
                                  capture_output=True, text=True,
                                  env=env).returncode
        else:
            done = subprocess.run(
                [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", spec],
                cwd=tree, capture_output=True, text=True, env=env)
            code = done.returncode
            said = (said or "") + done.stdout + done.stderr
        worst = worst or code
    return worst, said


def _ran(said: str) -> bool:
    """Whether pytest actually asserted anything, rather than skipping."""
    return re.search(r"\b\d+ passed", said) is not None


def apply(tree: Path, row) -> None:
    row_id, rel, old, new, _checks, _why = row
    f = tree / rel
    text = f.read_text(encoding="utf-8")
    found = text.count(old)
    if found != 1:
        raise SystemExit(
            "%s: the anchor appears %d times in %s; the table has drifted "
            "from the code and the row proves nothing" % (row_id, found, rel))
    f.write_text(text.replace(old, new), encoding="utf-8")
    f.touch()
    clear(tree)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args()
    repo = ROOT

    if not args.run:
        for row_id, rel, _old, _new, checks, why in TABLE:
            print("%s\n    %s\n    dies in: %s\n    why: %s"
                  % (row_id, rel, ", ".join(checks), why))
        print("\n%d rows, one of them the canary." % len(TABLE))
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "tree"
        # `.git` is carried on purpose: two tests read it, and a tree
        # without it skips them silently.
        shutil.copytree(repo, tree, ignore=shutil.ignore_patterns(
            "__pycache__", "build", "dist", "*.egg-info", ".pytest_cache",
            ".ruff_cache", ".harness-bin"))
        if not (tree / ".git").exists():
            print("the copy has no .git; rows would be scored against a "
                  "tree where two tests skip", file=sys.stderr)
            return 1
        # Whatever the repository itself calls an artifact, drop. Measured:
        # `.rule-coverage.json` is gitignored, lives in the working tree
        # after any `make check`, and `copytree` carried it in -- so the
        # gate that reads it was green in the copy for a reason that was
        # not in the copy's source, and a row stating that dependency
        # could not show it. Untracked files the repository does *not*
        # ignore are left alone: they are somebody's work in progress,
        # and measuring the tree as it is is why this copies rather than
        # exports.
        subprocess.run(["git", "clean", "-Xdfq"], cwd=tree,
                       capture_output=True)

        survivors, broken = [], []
        for row in TABLE:
            row_id, rel, _old, _new, checks, _why = row
            pristine = (tree / rel).read_text(encoding="utf-8")

            clear(tree)
            code, said = run(tree, checks)
            if code != 0:
                broken.append("%s: what it names already fails before the "
                              "mutation" % row_id)
                continue
            if said is not None and not _ran(said):
                broken.append("%s: what it names asserted nothing here -- it "
                              "skipped, so the row cannot kill anything" % row_id)
                continue

            apply(tree, row)
            # The mutant has to be code the interpreter would run. An anchor
            # that omits the line governing what it replaces -- an `if:` left
            # with no body, a `try:` with no block -- leaves a file that does
            # not compile, and then every test errors at import for a reason
            # that is not the mutation. `run` reads that as red and books a
            # kill on a gate that proved nothing (measured: the oversized-
            # conversion row killed by IndentationError, not by the reverted
            # behaviour). A row that does not compile is broken, not killed.
            uncompilable = None
            if rel.endswith(".py"):
                import py_compile
                try:
                    py_compile.compile(str(tree / rel), doraise=True)
                except py_compile.PyCompileError as exc:
                    uncompilable = str(exc).splitlines()[0]
            code, _ = (5, None) if uncompilable else run(tree, checks)
            (tree / rel).write_text(pristine, encoding="utf-8")
            (tree / rel).touch()
            clear(tree)

            if uncompilable is not None:
                broken.append("%s: the mutant does not compile (%s) -- the "
                              "anchor omits the line that governs it, so a kill "
                              "would be a syntax error and not the behaviour"
                              % (row_id, uncompilable))
            elif code == 5:
                broken.append("%s: the selection collects nothing" % row_id)
            elif code == 0:
                survivors.append(row_id)
                print("  survived  %s" % row_id)
            else:
                print("  killed    %s" % row_id)

        problems = list(broken)
        if CANARY[0] not in survivors:
            problems.append(
                "the canary %s died. Everything above it is unreliable: a "
                "harness that reports red for a change that does not matter "
                "is reporting red for everything." % CANARY[0])
        real = [s for s in survivors if s != CANARY[0]]
        if real:
            problems.append("mutations nothing caught: %s" % real)

        for p in problems:
            print(p, file=sys.stderr)
        if problems:
            return 1
        print("\n%d mutations, all caught; the canary survived."
              % (len(TABLE) - 1))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
