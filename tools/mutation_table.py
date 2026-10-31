#!/usr/bin/env python3
"""Every claim this project makes about a gate, as a mutation somebody can run.

    python3 tools/mutation_table.py            # list the table
    python3 tools/mutation_table.py --run      # apply each row and check it dies
    python3 tools/mutation_table.py --run --record docs/mutation-record.json
                                               # and keep what the run found

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
import contextlib
import json
import os
import platform
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
    ("loader/relationships-refusal-keeps-the-line",
     "src/aas_submodel_validate/loader.py",
     'LoadError("chain", str(exc), line=exc.line, part=rels, subject=rels, detail=exc.detail, fix=encoding_remedy(exc))',
     'LoadError("chain", str(exc), part=rels, subject=rels, detail=exc.detail, fix=encoding_remedy(exc))',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_relationships_refusal_keeps_its_message_line'],
     "an encoding refusal in the relationships chain named the line in its "
     "message while X2 reported null; carrying the exception line makes "
     "the report point to the same place"),

    ("loader/payload-relationships-refusal-keeps-the-line",
     "src/aas_submodel_validate/loader.py",
     'LoadError("chain", str(exc), line=exc.line, part=rels, detail=exc.detail, subject=rels, fix=encoding_remedy(exc))',
     'LoadError("chain", str(exc), detail=exc.detail, subject=rels, fix=encoding_remedy(exc))',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_payload_relationships_refusal_keeps_its_message_line'],
     "a payload part's own relationships part, refused for its encoding, "
     "named line 3 in its message while X2 reported null for both the line "
     "and the part"),

    ("container/an-encoding-refusal-counts-utf16-lines-in-characters",
     "src/aas_submodel_validate/container.py",
     '        before = raw[:error.start].decode(encoding, "replace")\n        line = _line_at(before, len(before))',
     '        line = raw.count(b"\\n", 0, error.start) + 1',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_utf_16_lines_are_counted_in_characters_and_not_in_bytes_0a'],
     "a lone surrogate on line 3 of a UTF-16 document was refused on line 4, "
     "in its message and in X3 and X2 `line`, when line 2 held U+010A, whose "
     "code unit holds a byte 0A"),

    ("container/a-carriage-return-alone-ends-a-line",
     "src/aas_submodel_validate/container.py",
     '    return text.count("\\n", 0, at) + text.count("\\r", 0, at) - text.count("\\r\\n", 0, at) + 1',
     '    return text.count("\\n", 0, at) + 1',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_line_ended_by_a_carriage_return_alone_is_a_line'],
     "a windows-1252 document whose lines end in a carriage return alone was "
     "refused on line 1 for a byte on line 3, where the parser counts line 3"),

    ("container/a-utf7-half-is-counted-past-the-declaration",
     "src/aas_submodel_validate/container.py",
     '            at += taken.end() - taken.end(1)',
     '            pass',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_half_character_utf_7_decodes_is_refused_on_its_own_line'],
     "half of a character at the start of line 3 of a UTF-7 document was "
     "refused on line 1, counted in the text with the declaration taken out"),

    ("gates/the-time-budget-actually-compares",
     "tools/time_budget.py",
     "        self.ok = factor is None or factor < FAIL_AT",
     "        self.ok = True",
     ["tests/test_the_run_stays_inside_its_time_budget.py::"
      "test_the_judgement_has_three_answers_and_they_are_the_thresholds"],
     "a budget that passes whatever it measures is a clock nobody is "
     "watching, which is the state every other gate here was already in: "
     "they all ask whether the verdict is right and none asked whether it "
     "arrived"),

    ("gates/the-time-budget-reports-what-it-found",
     "tools/time_budget.py",
     "    return 1 if bad else 0",
     "    return 0",
     ["tests/test_the_run_stays_inside_its_time_budget.py::"
      "test_the_check_fails_when_a_layer_is_over_its_budget"],
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
     '          if [ "$count" != "6" ]; then',
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
     "src/aas_submodel_validate/data/smt/02004/2.0.2/template.json",
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
     ["tests/test_coverage_record.py::test_every_published_id_is_accounted_for"],
     "the committed baseline is what says which rule ids this project "
     "expects to fire; the suite writes what actually fired and the tool "
     "compares the two against the registry. The targeted test runs the real gate "
     "with a complete observation, isolating this comparison from the "
     "full suite's independent timing checks"),

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
     "distance = edit_distance(seen_tail, exp_tail, cap=bound)",
     "distance = edit_distance(seen_tail, exp_tail)",
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
     '        _payload_error(loaded, part, exc,\n                       _out_of_room(exc, building=False) or _other_edition(text),\n',
     '        _payload_error(loaded, part, exc,\n                       _other_edition(text),\n',
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
     '        except OutOfMemory as exc:\n            loaded.errors.append(_ran_out(exc, subject=rels))\n        except UnreadablePart as exc:\n            loaded.errors.append(LoadError("zip", str(exc), detail=exc.detail, subject=rels))\n        except NoRelationships:\n',
     '        except UnreadablePart as exc:\n            loaded.errors.append(LoadError("zip", str(exc), detail=exc.detail, subject=rels))\n        except NoRelationships:\n',
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
     '    if len(converted) > MAX_PART_BYTES:\n        raise PartTooLarge(\n            "a document declaring %s is %d bytes as UTF-8, above the %d byte "\n            "limit" % (encoding, len(converted), MAX_PART_BYTES),\n            detail="%d bytes as UTF-8, read as %s" % (len(converted), encoding))\n    return converted',
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
     "src/aas_submodel_validate/loader.py",
     '    except EncodingNotRead as exc:\n        try:\n            source = package.origin\n        except EncodingNotRead:\n            source = ""\n        rels = container.relationships_part_name(source)\n        loaded.errors.append(LoadError("chain", str(exc), line=exc.line, part=rels, subject=rels, detail=exc.detail, fix=encoding_remedy(exc)))\n        return loaded\n',
     "",
     ["tests/test_a_document_is_read_in_the_encoding_it_declares.py::"
      "test_a_relationships_part_in_a_name_this_reader_does_not_read_is_filed_with_its_remedy",
      "tests/test_hostile_input.py::"
      "test_a_relationships_part_the_reader_cannot_decode_is_a_finding_not_a_crash"],
     "a relationships part declaring a codec the parser cannot honour (a "
     "NUL in the name, an unknown codec) left the process by a traceback "
     "and exit 1, on a file it never read; refused by name now, before the "
     "parser, it is filed with the encoding's remedy rather than told to "
     "repair a chain nothing says is broken"),

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
     "    name: py${{ matrix.python }} ${{ matrix.label }} on ${{ matrix.os }}\n"
     "    runs-on: ${{ matrix.os }}\n    timeout-minutes: 15\n",
     "    name: py${{ matrix.python }} ${{ matrix.label }} on ${{ matrix.os }}\n"
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
     '    return tag is not None and tag.rsplit("}", 1)[-1] == "submodel"',
     '    return tag is not None and tag.rsplit("}", 1)[-1] == "environment"',
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
     "        _say(\"smtv: %s\" % (refusal or \"nothing in %s was judged\" % path))\n"
     "        _after(args, path, report, EXIT_ERROR, started)\n"
     "        return EXIT_ERROR",
     "        _say(\"smtv: %s\" % (refusal or \"nothing in %s was judged\" % path))\n"
     "        _after(args, path, report, EXIT_ERROR, started)\n"
     "        return EXIT_USAGE",
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
     "and 200,000, beside a violation cut at the bound. Every generated pack "
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
     # An actual supplied-table finding passes through the suite observer;
     # the resulting coverage record must exclude its run-time id.
     ["tests/test_coverage_record.py::test_a_run_time_id_stays_out_of_the_coverage_record"],
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
     "            # listing and left by 0. Six entries on this list take a",
     "            # listing and left by 0. Five entries on this list take a",
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

    ("readme/the-elision-is-the-lines-the-run-prints",
     "README.md",
     "The `…` is six lines: the one that accounts for the `3 info` — the\n",
     "The `…` is four lines: the one that accounts for the `3 info` — the\n",
     ["tests/test_readme_front.py::test_the_anatomy_block_is_what_the_tool_prints"],
     "the sentence under the battery sample said the elided run was four "
     "lines when the tool printed six, and every gate on the block read "
     "the quoted lines and none read the sentence"),

    ("fixability/a-qualified-label-is-not-an-idshort",
     "src/aas_submodel_validate/rules/engine.py",
     "                        if element.id_short and element.id_short == _id_short_of(row))\n",
     "                        if element.id_short and element.id_short == row[\"label\"])\n",
     ["tests/test_severity_and_fixability.py::"
      "test_the_row_s_idshort_is_recognised_where_its_label_is_qualified"],
     "an element carrying AddressOfAdditionalLink sat beside the missing "
     "one, and the row's label -- qualified with its parent because 02002 "
     "declares that idShort twice -- was compared instead of its idShort: "
     "graded 5, nothing here resembles the missing element"),

    ("fixability/a-file-value-is-graded-by-the-package",
     "src/aas_submodel_validate/rules/engine.py",
     "    found = len(carrying)\n",
     "    found = 0\n",
     ["tests/test_severity_and_fixability.py::"
      "test_a_file_value_is_graded_by_what_the_package_holds"],
     "a File value naming /aasx/documents/manual.pdf for a file the package "
     "holds in /aasx/files/ was told its bytes were not in the input, "
     "because the grade was fixed per branch and no branch had looked"),

    ("golden/a-value-that-changes-is-a-line-in-a-diff",
     "src/aas_submodel_validate/rules/engine.py",
     '        yield Violation("the container holds no part at this File\'s value",\n',
     '        yield Violation("the container holds no part at this value",\n',
     ["tests/test_golden_report.py::test_the_stored_report_is_the_one_this_tree_produces"],
     "a finding's message reworded, every key where it was and every type "
     "the same: the shape gate passes it, and a consumer matching on the "
     "sentence finds out from their own pipeline"),

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

    ("fixability/one-checksum-at-two-sizes-is-two-files",
     "src/aas_submodel_validate/container.py",
     "        return len({(info.file_size, info.CRC) for info in infos}) == 1\n",
     "        return len({info.CRC for info in infos}) == 1\n",
     ["tests/test_severity_and_fixability.py::"
      "test_one_file_stored_under_two_names_is_nothing_to_choose"],
     "two parts forged to one CRC-32 at different lengths were graded one "
     "file stored twice, with a reason saying the archive recorded the same "
     "size for each"),

    ("fixability/every-candidate-is-compared",
     "src/aas_submodel_validate/container.py",
     "        infos = [self._zip.getinfo(name) for name in names]\n",
     "        infos = [self._zip.getinfo(name) for name in names[:2]]\n",
     ["tests/test_severity_and_fixability.py::"
      "test_one_file_stored_under_two_names_is_nothing_to_choose"],
     "two copies of one file and a third file under the same name were "
     "graded one file stored twice, the third never compared"),

    ("golden/a-report-from-another-copy-is-refused",
     "tools/golden_report.py",
     '             "got.startswith(os.path.realpath(sys.argv[1]) + os.sep) or "\n',
     '             "True or "\n',
     ["tests/test_golden_report.py::test_a_report_from_another_copy_of_the_package_is_refused"],
     "the golden check ran whichever copy of the package the child imported "
     "and compared its report, and said nothing of which copy that was"),

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
     "                for rule_id in _asked_inside(row, element, copied):\n",
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

    ("scope/a-nested-copy-is-followed-with-the-rows-it-copies",
     "src/aas_submodel_validate/rules/engine.py",
     '    rows = inside.get(row["recurses"], ()) if row.get("recurses") else row["children"]\n',
     '    rows = () if row.get("recurses") else row["children"]\n',
     ["tests/test_unmatched_coverage.py::"
      "test_what_a_nested_copy_holds_is_charged_at_its_depth"],
     "a drifted Node whose nested copy held a Section was not charged the "
     "Section's Leaf: the copy was asked and not followed, and what it held "
     "was counted nowhere"),

    ("scope/a-wrong-kind-near-miss-is-not-entered",
     "src/aas_submodel_validate/rules/engine.py",
     '    if type(element).__name__ != row["kind"]:\n        return _descendant_ids(row)\n',
     '    if type(element).__name__ != row["kind"]:\n        return []\n',
     ["tests/test_unmatched_coverage.py::"
      "test_a_near_miss_of_the_wrong_kind_is_charged_as_a_wrong_kind_match_is"],
     "a Property wearing a near miss of a collection's identifier was "
     "charged nothing, and in a pack with no near-miss lint the report was "
     "the report of a clean file -- one defect quieter than the same file "
     "with the identifier corrected"),

    ("near-miss/the-shared-lint-reports-what-it-finds",
     "src/aas_submodel_validate/rules/engine.py",
     "        yield from near_miss_violations(ctx, tables)\n    return check\n",
     "        yield from ()\n    return check\n",
     ["tests/test_near_miss_lints.py::test_a_drifted_identifier_is_named_by_the_pack_s_lint"],
     "the five packs that registered no near-miss lint until 0.8.0 register "
     "one that reports nothing, and a drifted identifier is again named "
     "only in summary.unmatchedElements"),

    ("near-miss/a-list-item-is-named-too",
     "src/aas_submodel_validate/rules/engine.py",
     "        yield from near_miss_violations(ctx, tables)\n    return check\n",
     "        yield from (v for v in near_miss_violations(ctx, tables)\n"
     "                    if not v.subject.endswith(']'))\n    return check\n",
     ["tests/test_near_miss_lints.py::test_a_drifted_list_item_is_named_by_its_index"],
     "a Carbon Footprint whose one footprint item carried the next "
     "version's identifier drew nothing naming it: an item has no idShort, "
     "and every case the tests drifted had one"),

    ("near-miss/the-five-lints-are-tdl1",
     "src/aas_submodel_validate/rules/engine.py",
     '    @rule(rule_id, kind="lint", prio="SHOULD",\n',
     '    @rule(rule_id, kind="template", prio="SHOULD",\n',
     ["tests/test_near_miss_lints.py::test_every_pack_s_near_miss_lint_is_tdl1_under_another_name"],
     "the five lints registered as template rules, `kind: template` in "
     "the JSON, and nothing compared them with the TDL1 they are said to "
     "copy"),

    ("near-miss/the-nearest-row-is-named",
     "src/aas_submodel_validate/rules/engine.py",
     "            if nearest is None or rank < nearest[0]:\n",
     "            if nearest is None:\n",
     ["tests/test_near_miss_lints.py::test_the_nearest_row_is_the_one_named"],
     "a Software Nameplate whose InstallationPath drifted to "
     "InstallationPaths was told the template says InstallationDate, the "
     "first sibling within the bound, and the file that followed that "
     "remedy drew two errors"),

    ("budget/the-record-keeps-its-history",
     "docs/time-budget.json",
     '  "_from": "',
     '  "_gone": "',
     ["tests/test_the_run_stays_inside_its_time_budget.py::"
      "test_the_budget_file_records_what_it_was_measured_on"],
     "a re-recording pasted over the recorded block deleted the history of "
     "every earlier one, and nothing noticed"),

    ("semantics/an-irdi-under-samm-s-prefix-is-the-irdi",
     "src/aas_submodel_validate/semantics.py",
     "    if value.startswith(_IRDI_URN):\n",
     "    if False:\n",
     ["tests/test_an_irdi_under_samm_s_prefix_is_the_irdi.py::test_a_02002_e_mail_address_written_under_the_prefix_answers_its_row"],
     "a 02002 e-mail address written under SAMM's urn:irdi: prefix was "
     "reported missing from 02002, whose template writes the same IRDI bare"),

    ("semantics/samm-s-escape-is-read-as-the-hash",
     "src/aas_submodel_validate/semantics.py",
     '        wrapped = value[len(_IRDI_URN):].replace("%23", "#")\n',
     "        wrapped = value[len(_IRDI_URN):]\n",
     ["tests/test_an_irdi_under_samm_s_prefix_is_the_irdi.py::test_the_prefix_and_its_escape_are_read_and_nothing_further"],
     "an IRDI written as SAMM's guideline writes it, its second # as %23, "
     "was not the IRDI"),

    ("semantics/a-prefix-alone-is-no-identifier",
     "src/aas_submodel_validate/semantics.py",
     "        if _IRDI.match(wrapped):\n",
     "        if _IRDI.match(wrapped) or not wrapped:\n",
     ["tests/test_an_irdi_under_samm_s_prefix_is_the_irdi.py::test_no_other_spelling_is_read_away"],
     "a key reading urn:irdi: and nothing after it was read as the empty "
     "identifier"),

    ("semantics/the-prefix-is-read-as-written",
     "src/aas_submodel_validate/semantics.py",
     "    if value.startswith(_IRDI_URN):\n",
     "    if value.lower().startswith(_IRDI_URN):\n",
     ["tests/test_an_irdi_under_samm_s_prefix_is_the_irdi.py::test_no_other_spelling_is_read_away"],
     "URN:IRDI: in capitals was read away too, a case this reader says it "
     "does not read"),

    ("semantics/what-is-not-an-irdi-keeps-the-prefix",
     "src/aas_submodel_validate/semantics.py",
     "            return wrapped\n        return value\n",
     "            return wrapped\n        return wrapped\n",
     ["tests/test_an_irdi_under_samm_s_prefix_is_the_irdi.py::test_no_other_spelling_is_read_away"],
     "an IRI or a URN under the prefix lost it, and matched what it would "
     "not match bare"),

    ("dbp7/the-table-holds-the-irdi-bare",
     "src/aas_submodel_validate/rules/dbp7_tables.py",
     "'match': ('0173-1#02-AAO128#002', 'https://schema.org/streetAddress', ",
     "'match': ('https://schema.org/streetAddress', 'urn:irdi:0173-1#02-AAO128#002', ",
     ["tests/test_an_irdi_under_samm_s_prefix_is_the_irdi.py::test_a_vendored_table_holds_what_the_comparison_reads"],
     "a table generated before the prefix was read away kept it, and a "
     "file written as the template writes it stopped matching"),

    ("semantics/the-prefix-stands-before-an-irdi-only",
     "src/aas_submodel_validate/semantics.py",
     "        if _IRDI.match(wrapped):\n",
     "        if True:\n",
     ["tests/test_an_irdi_under_samm_s_prefix_is_the_irdi.py::test_a_submodel_naming_an_iri_under_the_prefix_is_not_taken_for_its_template"],
     "the prefix came off whatever it stood before, and a submodel saying "
     "urn:irdi: before 02006's own IRI was judged as a Digital Nameplate"),

    ("engine/an-own-identifier-is-compared-key-by-key",
     "src/aas_submodel_validate/rules/engine.py",
     '            mine = row.get("sid_compared") or (\n',
     '            mine = None or (\n',
     ["tests/test_an_irdi_under_samm_s_prefix_is_the_irdi.py::test_an_element_known_by_two_keys_keeps_its_own_row_however_they_are_spelt"],
     "an element known by two keys under the prefix lost the row its own "
     "identifier names, and a file written as its template drew found 2 and "
     "found 0"),

    ("tablegen/a-row-carries-its-identifier-as-compared",
     "src/aas_submodel_validate/tablegen.py",
     "    if my_sid and compared != normalize(my_sid):\n",
     "    if False:\n",
     ["tests/test_an_irdi_under_samm_s_prefix_is_the_irdi.py::test_an_element_known_by_two_keys_keeps_its_own_row_however_they_are_spelt"],
     "a caller's template row known by two keys under the prefix carried "
     "nothing the walk could compare its own identifier by"),

    ("engine/a-copy-is-compared-as-read",
     "src/aas_submodel_validate/rules/engine.py",
     '        copied = {row.get("sid_compared") or normalize(row["recurses"])\n',
     '        copied = {row["recurses"]\n',
     ["tests/test_an_irdi_under_samm_s_prefix_is_the_irdi.py::test_a_copy_the_walk_did_not_reach_is_said_however_its_identifier_is_spelt"],
     "a self-containing element written under the prefix lost the note "
     "naming the copies the walk did not reach"),

    ("near-miss/a-samm-near-miss-stays-in-its-namespace",
     "src/aas_submodel_validate/semantics.py",
     '        return "%s#%s" % (match.group(1), match.group(3))\n',
     '        return "urn:samm:#%s" % match.group(3)\n',
     ["tests/test_dbp_hand_rules.py::"
      "test_a_samm_identifier_of_another_namespace_is_not_a_near_miss"],
     "a Documents list wearing 02004's own handover aspect's `documents` "
     "was called a drift of 02035-2's, whose namespace it does not share"),

    ("near-miss/a-samm-namespace-may-hold-a-colon",
     "src/aas_submodel_validate/semantics.py",
     '_SAMM = re.compile(r"^(urn:samm:[^#]+):(\\d+(?:\\.\\d+)*)#(.+)$")',
     '_SAMM = re.compile(r"^(urn:samm:[^:#]+):(\\d+(?:\\.\\d+)*)#(.+)$")',
     ["tests/test_dbp_hand_rules.py::"
      "test_a_samm_meta_model_identifier_one_version_off_is_a_near_miss"],
     "a language item wearing the SAMM meta-model's Locale at 2.2.0, where "
     "the template has 2.1.0, drew nothing: the meta-model's namespace "
     "holds a colon, and the pattern stopped at it"),

    ("near-miss/a-samm-version-is-a-number",
     "src/aas_submodel_validate/semantics.py",
     '_SAMM = re.compile(r"^(urn:samm:[^#]+):(\\d+(?:\\.\\d+)*)#(.+)$")',
     '_SAMM = re.compile(r"^(urn:samm:[^#]+):([^#]+)#(.+)$")',
     ["tests/test_dbp_hand_rules.py::test_a_samm_version_is_a_number"],
     "`latest` in a SAMM identifier's version place was read as a version, "
     "and a Documents list carrying it was called a drift"),

    ("near-miss/a-version-drift-is-nearest",
     "src/aas_submodel_validate/rules/engine.py",
     "    if seen_stem and seen_stem == version_stem(expected):\n        return 0\n",
     "    if seen_stem and seen_stem == version_stem(expected):\n        return 99\n",
     ["tests/test_engine_regressions.py::test_one_element_draws_one_near_miss"],
     "an element one ECLASS version off a row, with a supplemental one "
     "letter off a sibling's, was named against the sibling"),

    ("near-miss/a-tie-goes-to-the-first-row",
     "src/aas_submodel_validate/rules/engine.py",
     "            if nearest is None or rank < nearest[0]:\n",
     "            if nearest is None or rank <= nearest[0]:\n",
     ["tests/test_near_miss_lints.py::test_a_tie_between_rows_nothing_matched_goes_to_the_first"],
     "an identifier as near two rows nothing matched was named against the "
     "later one, where the CHANGELOG says the first"),

    ("near-miss/a-drift-of-a-matched-row-does-not-end-the-search",
     "src/aas_submodel_validate/rules/engine.py",
     "                if rank == (0, False):\n",
     "                if not rank[0]:\n",
     ["tests/test_near_miss_lints.py::"
      "test_a_version_drift_of_a_matched_row_does_not_end_the_search"],
     "an element one version off a row the file carries and, through a "
     "supplemental, one version off a row it lacks was named against the "
     "row it carries, and the missing one was graded as if nothing here "
     "resembled it"),

    ("near-miss/matched-means-matched-in-that-place",
     "src/aas_submodel_validate/rules/engine.py",
     '            rank = (near[0], row["id"] in claimed_by)\n',
     '            rank = (near[0], bool(result["instances"].get(row["id"])))\n',
     ["tests/test_near_miss_lints.py::test_matched_means_matched_in_that_place"],
     "in a second configuration entry a drifted ConfigurationType was named "
     "against ConfigurationURI's identifier, because the first entry had "
     "matched both rows, and the remedy made the entry's URI a second one"),

    ("near-miss/a-tie-goes-to-the-row-nothing-matched",
     "src/aas_submodel_validate/rules/engine.py",
     '            rank = (near[0], row["id"] in claimed_by)\n',
     "            rank = (near[0], False)\n",
     ["tests/test_near_miss_lints.py::test_a_tie_goes_to_the_row_nothing_here_matched"],
     "InstallationDath, as near InstallationDate as InstallationPath, was "
     "named against the date the file already carried, and a file that "
     "followed the remedy drew two errors"),

    ("near-miss/the-rest-of-the-report-uses-the-nearest-row",
     "src/aas_submodel_validate/rules/engine.py",
     "            near_here.append((subject, seen, expected, row, element))\n",
     "            near_here.append((subject, seen, expected, next(\n"
     "                r for r in rows if _nearness(candidates, r[\"match\"])), element))\n",
     ["tests/test_near_miss_lints.py::"
      "test_the_nearest_row_is_the_one_the_rest_of_the_report_uses"],
     "the lint named the nearest row while the charge and a missing "
     "sibling's grade used the first near one: an InstallationDate missing "
     "beside InstallationPaths was graded 2 beside a lint naming "
     "InstallationPath"),

    ("near-miss/a-samm-version-drift-is-a-near-miss",
     "src/aas_submodel_validate/rules/engine.py",
     "    if seen_samm and seen_samm == samm_stem(expected):\n",
     "    if False and seen_samm == samm_stem(expected):\n",
     ["tests/test_dbp_hand_rules.py::test_a_samm_version_drift_is_diagnosed"],
     "a Documents list carrying the SAMM identifier of 02035-2's next "
     "version matched no row and nothing named it"),

    ("near-miss/a-pack-registers-its-lint",
     "src/aas_submodel_validate/rules/dn.py",
     'install_near_miss_lint("DNL1", dn_tables)\n',
     "\n",
     ["tests/test_near_miss_lints.py::test_a_drifted_identifier_is_named_by_the_pack_s_lint"],
     "a Digital Nameplate whose serial number drifted one version suffix "
     "draws no finding naming it"),

    ("scope/the-first-row-takes-the-element-whatever-it-holds",
     "src/aas_submodel_validate/rules/engine.py",
     '                if child["children"] or child.get("recurses"):\n'
     '                    out.extend(_asked_inside(child, sub, inside))\n'
     '                break\n',
     '                if child["children"] or child.get("recurses"):\n'
     '                    out.extend(_asked_inside(child, sub, inside))\n'
     '                    break\n',
     ["tests/test_unmatched_coverage.py::"
      "test_an_element_goes_to_the_first_row_it_matches_whatever_that_row_holds"],
     "an element handed to a Property row -- the first sharing its "
     "identifier -- was handed on to the collection row after it, and the "
     "drift was blamed for a Leaf the walk never asks of it"),

    ("scope/a-wrong-kind-element-inside-a-near-miss-is-charged",
     "src/aas_submodel_validate/rules/engine.py",
     '                if child["children"] or child.get("recurses"):\n'
     '                    out.extend(_asked_inside(child, sub, inside))\n',
     '                if (child["children"] or child.get("recurses")) '
     'and type(sub).__name__ == child["kind"]:\n'
     '                    out.extend(_asked_inside(child, sub, inside))\n',
     ["tests/test_unmatched_coverage.py::"
      "test_a_wrong_kind_element_inside_a_near_miss_is_charged_as_the_walk_charges_it"],
     "a Property standing where a section belongs inside a drifted node "
     "was charged nothing, and the section's rules left the drift's charge "
     "though the corrected file charges them to that Property"),

    ("scope/a-record-lists-its-rules-in-the-tables-order",
     "src/aas_submodel_validate/rules/engine.py",
     "                             unasked=tuple(sorted(lost[key], key=lambda rid: (\n"
     "                                 order.get(rid, len(order)), rid))),\n",
     "                             unasked=tuple(lost[key]),\n",
     ["tests/test_unmatched_coverage.py::test_a_record_lists_its_rules_in_the_tables_order"],
     "an element's record listed the rules beneath a section after the "
     "section's siblings, in the order a walk meets them, while "
     "rulesNotAsked listed the same rules in the table's"),

    ("ci-parity/a-recipe-is-read-past-its-comments",
     "tests/test_ci_parity.py",
     r'    body = re.search(r"^%s:.*?\n((?:\t.*\n|[ \t]*#.*\n|[ \t]*\n)*)" % re.escape(target),',
     r'    body = re.search(r"^%s:.*?\n((?:\t.*\n|#.*\n|\n)*)" % re.escape(target),',
     ["tests/test_ci_parity.py::test_a_recipe_is_read_past_its_comments_and_blank_lines"],
     "a comment indented with spaces between two lines of a recipe hid "
     "every line after it from the comparison with CI, though make runs "
     "them"),

    ("scope/an-element-goes-to-the-first-row-it-matches",
     "src/aas_submodel_validate/rules/engine.py",
     "                    out.extend(_asked_inside(child, sub, inside))\n                break\n",
     "                    out.extend(_asked_inside(child, sub, inside))\n",
     ["tests/test_unmatched_coverage.py::test_an_element_goes_to_the_first_row_it_matches"],
     "one element carrying an identifier two sibling rows share was entered "
     "under both, and the drift was blamed for the second row's rules, "
     "which the walk would never have asked of it"),

    ("scope/a-near-miss-is-charged-though-nothing-beside-it-is-unentered",
     "src/aas_submodel_validate/rules/engine.py",
     "    if near_here:\n        # Asked whether or not this scope left a row unentered, and of a\n",
     "    if unentered and near_here:\n        # Asked whether or not this scope left a row unentered, and of a\n",
     ["tests/test_scope_the_run_did_not_examine.py::"
      "test_a_near_miss_is_charged_though_no_row_beside_it_is_unentered"],
     "a Document carrying every optional list left no row unentered, and the "
     "section only a drifted copy held went unsaid: the charge waited for an "
     "unentered row that had nothing to do with it"),

    ("scope/an-item-matched-by-kind-is-followed",
     "src/aas_submodel_validate/rules/engine.py",
     "            if _child_matches(sub, child, in_list):\n                if child[\"children\"] or child.get(\"recurses\"):\n",
     "            if _child_matches(sub, child, False):\n                if child[\"children\"] or child.get(\"recurses\"):\n",
     ["tests/test_scope_the_run_did_not_examine.py::"
      "test_an_item_matched_by_its_kind_is_followed_as_the_walk_follows_it"],
     "a drifted list whose item carries no semanticId -- the official "
     "example's shape -- was charged none of what the item held, though the "
     "walk takes such an item by its kind"),

    ("scope/every-copy-in-a-drifted-group-counts",
     "src/aas_submodel_validate/rules/engine.py",
     "            for element in elements:\n                for rule_id in _asked_inside(row, element, copied):\n",
     "            for element in elements[:1]:\n                for rule_id in _asked_inside(row, element, copied):\n",
     ["tests/test_scope_the_run_did_not_examine.py::"
      "test_a_group_of_drifted_copies_is_charged_what_any_of_them_holds"],
     "two copies drifted alike, the second holding a section the first did "
     "not: charging the group with its first copy's content lost the "
     "second's"),

    ("scope/the-last-copy-of-a-group-is-not-the-only-one",
     "src/aas_submodel_validate/rules/engine.py",
     "            for element in elements:\n                for rule_id in _asked_inside(row, element, copied):\n",
     "            for element in elements[-1:]:\n                for rule_id in _asked_inside(row, element, copied):\n",
     ["tests/test_scope_the_run_did_not_examine.py::"
      "test_a_group_of_drifted_copies_is_charged_what_any_of_them_holds"],
     "two copies drifted alike, the first holding a section the second did "
     "not: charging the group with its last copy's content lost the first's"),

    ("scope/a-container-of-the-wrong-kind-is-not-entered",
     "src/aas_submodel_validate/rules/engine.py",
     '    if type(element).__name__ != row["kind"]:\n        return _descendant_ids(row)\n',
     '    if type(element).__name__ != row["kind"] and row["kind"] not in _CONTAINERS:\n        return _descendant_ids(row)\n',
     ["tests/test_scope_the_run_did_not_examine.py::"
      "test_a_drifted_container_of_the_wrong_kind_is_charged_as_a_wrong_kind_match"],
     "a collection wearing a near miss of a list's identifier was entered "
     "as though it were the list, and charged by what it held rather than "
     "as the walk charges a collection where a list belongs"),

    ("scope/what-only-a-drifted-copy-holds-is-its-loss",
     "src/aas_submodel_validate/rules/engine.py",
     '            if not row["children"] and not row.get("recurses"):\n'
     '                continue\n'
     '            grouped.setdefault(',
     '            if claimed_by.get(row["id"]) or not row["children"] and not row.get("recurses"):\n'
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

    ("detect/a-samm-identifier-has-no-eclass-stem",
     "src/aas_submodel_validate/rules/detect.py",
     '        return version_stem(self.semantic_id) or ""\n',
     '        return self.semantic_id.rpartition("#")[0]\n',
     ["tests/test_generated_rules_dbp5.py::"
      "test_another_element_of_the_namespace_is_not_one_version_off"],
     "a submodel naming another element of 02035-5's SAMM namespace was "
     "told it differed from the Product Condition template's identifier "
     "only in the ECLASS version suffix"),

    ("detect/a-submodel-one-samm-version-off-is-told-so",
     "src/aas_submodel_validate/rules/detect.py",
     "                if samm_stem(value) and samm_stem(value) == samm_stem(pack.semantic_id) \\\n",
     "                if False and samm_stem(value) == samm_stem(pack.semantic_id) \\\n",
     ["tests/test_generated_rules_dbp5.py::"
      "test_a_submodel_written_to_an_earlier_edition_is_named_by_its_version"],
     "a Product Condition submodel written to 1.0.1 was not told that it "
     "differs from the template's identifier in its SAMM version alone -- "
     "named ProductCondition, it was told only that matching goes by "
     "semanticId"),

    ("edition/a-packaged-document-of-another-edition-is-told-which",
     "src/aas_submodel_validate/loader.py",
     '                       _out_of_room(exc, building=False) or _other_edition(text),\n',
     '                       _out_of_room(exc, building=False),\n',
     ["tests/test_metamodel_edition.py::"
      "test_a_package_in_the_3_1_namespace_is_told_its_edition"],
     "an IDTA sample written for metamodel 3.1 was told to fix the syntax its "
     "parser rejects, of a document whose syntax may be sound"),

    ("edition/a-bare-submodel-of-another-edition-is-told-which",
     "src/aas_submodel_validate/loader.py",
     "            message, fix = (_out_of_room(exc, building=False) or _other_edition(text)\n",
     "            message, fix = (_out_of_room(exc, building=False)\n",
     ["tests/test_metamodel_edition.py::"
      "test_a_bare_submodel_in_the_3_1_namespace_is_told_its_edition"],
     "a bare submodel in the 3.1 namespace was told only that it could not "
     "be read as a Submodel"),

    ("edition/the-edition-read-is-not-another",
     "src/aas_submodel_validate/loader.py",
     "    if edition == EDITION:\n        return None\n",
     "",
     ["tests/test_metamodel_edition.py::"
      "test_a_3_0_document_its_parser_rejects_keeps_the_standing_remedy"],
     "a 3.0 document its parser rejected was told it is written in metamodel "
     "3.0, which this reader does not read"),

    ("edition/the-report-says-which-edition",
     "src/aas_submodel_validate/model.py",
     '                "metamodel": EDITION,\n',
     "",
     ["tests/test_metamodel_edition.py::"
      "test_every_report_names_the_edition_this_reader_reads"],
     "a report did not name the edition of the metamodel this reader reads, "
     "and a JSON document names none"),

    ("edition/no-edition-is-written-with-a-leading-zero",
     "src/aas_submodel_validate/loader.py",
     '    r"/aas/(0|[1-9][0-9]{0,2})/(0|[1-9][0-9]{0,2})")\n',
     '    r"/aas/(\\d+)/(\\d+)")\n',
     ["tests/test_metamodel_edition.py::"
      "test_a_namespace_that_only_resembles_an_edition_s_names_none"],
     "a namespace typed `.../aas/03/0`, or in fullwidth digits, was told it "
     "is written in metamodel 03.0, which this reader does not read"),

    ("edition/only-the-host-forms-editions-use",
     "src/aas_submodel_validate/loader.py",
     "    if host.startswith(\"https://\") != (int(major) >= 3):\n",
     "    if False:\n",
     ["tests/test_metamodel_edition.py::"
      "test_a_namespace_that_only_resembles_an_edition_s_names_none"],
     "`http://www.admin-shell.io/aas/3/1`, a host form the 3.x editions do "
     "not use, was named as metamodel 3.1"),

    ("container/an-origin-of-another-type-is-named",
     "src/aas_submodel_validate/container.py",
     "            if rel_type.rsplit(\"/\", 1)[-1] == ORIGIN_REL.rsplit(\"/\", 1)[-1]:\n",
     "            if False:\n",
     ["tests/test_official_material_refused.py::"
      "test_the_aas_2_sample_is_refused_at_its_relationships"],
     "an AAS 2.0 package was told it declares no aasx-origin relationship, "
     "and to repair a chain that may be whole in its own vocabulary"),

    ("edition/the-namespace-is-matched-whole",
     "src/aas_submodel_validate/loader.py",
     "    match = _EDITION_NAMESPACE.fullmatch(namespace)\n",
     "    match = _EDITION_NAMESPACE.match(namespace)\n",
     ["tests/test_metamodel_edition.py::"
      "test_a_namespace_that_only_resembles_an_edition_s_names_none"],
     "`https://admin-shell.io/aas/3/1/extra`, and 3.1's namespace with a "
     "newline after it, were named as metamodel 3.1"),

    ("edition/the-edition-is-the-root-element-s",
     "src/aas_submodel_validate/loader.py",
     '    parser = ElementTree.XMLPullParser(events=("start",))\n',
     '    parser = ElementTree.XMLPullParser(events=("end",))\n',
     ["tests/test_metamodel_edition.py::"
      "test_the_edition_is_the_root_element_s_and_nobody_else_s"],
     "a 3.0 document whose first child wore the 3.1 namespace was told it is "
     "written in metamodel 3.1"),

    ("edition/the-remedy-says-which-edition-is-which",
     "src/aas_submodel_validate/loader.py",
     "            OTHER_EDITION_REMEDY % (EDITION, edition, namespace, EDITION,\n",
     "            OTHER_EDITION_REMEDY % (edition, edition, namespace, EDITION,\n",
     ["tests/test_registry.py::"
      "test_every_sentence_a_violation_carries_is_the_one_that_was_decided"],
     "a 3.1 document was told this reader reads metamodel 3.1"),
    ("detect/the-handover-name-an-author-reaches-for",
     "src/aas_submodel_validate/rules/detect.py",
     '"handoverdocumentation")',
     '"handoverdocumentations")',
     ["tests/test_detect.py::test_a_submodel_named_but_not_identified_gets_told_why"],
     "a submodel named HandoverDocumentation that carried another identifier "
     "was listed as an unknown identifier -- and the test that asked about it "
     "looked for a word every SMT-D1 detail carries, so it passed"),

    ("detect/the-technical-data-name-an-author-reaches-for",
     "src/aas_submodel_validate/rules/detect.py",
     '"technicaldata")',
     '"technicaldatas")',
     ["tests/test_detect.py::test_the_name_hint_covers_the_second_template_as_well"],
     "a submodel named TechnicalData that carried another identifier was "
     "listed as an unknown identifier, where the other packs' namesakes are "
     "told the name is not what matches"),

    ("samples/the-page-holds-every-sample",
     "tools/gen_official_samples.py",
     '_SAMPLE_TREES = ("tests/corpus/idta/", "src/aas_submodel_validate/data/example/")\n',
     '_SAMPLE_TREES = ("tests/corpus/idta/",)\n',
     ["tests/test_official_samples_page.py::"
      "test_every_official_sample_here_is_on_the_page_and_no_template_is"],
     "the bundled example, the sample `smtv --example` judges, was left off "
     "the page of official samples"),

    ("samples/the-exit-code-is-the-command-line-s",
     "tools/gen_official_samples.py",
     "    return 0 if report.ok else 1\n",
     "    return 1 if report.ok else 0\n",
     ["tests/test_official_samples_page.py::test_the_committed_page_is_what_a_run_writes",
      "tests/test_official_samples_page.py::"
      "test_every_exit_code_on_the_page_is_the_command_line_s"],
     "the page of official samples said exit 1 of every sample the command "
     "line passes, and a regenerated page said so with every gate green"),

    ("dbp5/the-name-an-author-reaches-for",
     "src/aas_submodel_validate/rules/detect.py",
     '"productcondition")',
     '"productconditions")',
     ["tests/test_generated_rules_dbp5.py::"
      "test_a_submodel_named_as_the_template_is_told_matching_goes_by_identifier"],
     "a submodel named ProductCondition that carried another identifier was "
     "listed as an unknown identifier, where the other packs' namesakes are "
     "told the name is not what matches"),

    ("dbp1/the-name-an-author-reaches-for",
     "src/aas_submodel_validate/rules/detect.py",
     '"batterynameplate")',
     '"batterynameplates")',
     ["tests/test_generated_rules_dbp1.py::"
      "test_a_submodel_named_as_the_template_is_told_matching_goes_by_identifier"],
     "a submodel named BatteryNameplate that carried another identifier was "
     "listed as an unknown identifier, where the other packs' namesakes are "
     "told the name is not what matches"),

    ("bundle/a-member-s-name-rides-in-its-row",
     "src/aas_submodel_validate/bundle.py",
     "_extra_ids(info.extra), bool(info.flag_bits & 0x800)])",
     "_extra_ids(info.extra), bool(info.flag_bits & 0x800), name])",
     ["tests/test_a_bug_report_carries_nothing_from_the_files.py::test_nothing_a_sender_wrote_is_in_the_bundle_of_a_package"],
     "a bundle carried the name of every member of the package it described"),

    ("bundle/the-summary-s-lists-are-kept-whole",
     "src/aas_submodel_validate/bundle.py",
     "            kept[key] = len(value)\n",
     "            kept[key] = value\n",
     ["tests/test_a_bug_report_carries_nothing_from_the_files.py::"
      "test_what_the_run_did_not_examine_is_counted_and_not_named"],
     "a bundle carried the report's lists of unexamined places and unclaimed "
     "elements, each named by the file's own idShorts"),

    ("bundle/a-defect-s-message-not-its-hash",
     "src/aas_submodel_validate/bundle.py",
     '"messageSha256": _sha256(str(exc).encode("utf-8", "replace"))}',
     '"messageSha256": str(exc)}',
     ["tests/test_a_bug_report_carries_nothing_from_the_files.py::test_a_failure_of_this_tool_writes_a_bundle_and_leaves_as_it_did"],
     "a bundle written for a defect carried the exception's message, which "
     "quotes what the file said"),

    ("bundle/the-directory-it-was-told-to-use",
     "src/aas_submodel_validate/cli.py",
     "        made = bundling.build(path=path, options=_options(args),\n",
     "        made = bundling.build(path=path, options=_options(args) + [str(args.bundle_out)],\n",
     ["tests/test_a_bug_report_carries_nothing_from_the_files.py::test_a_path_given_in_one_word_stays_out_too"],
     "a bundle carried the directory it was written to, and the user name in it"),

    ("bundle/a-defect-leaves-as-it-did",
     "src/aas_submodel_validate/cli.py",
     "                _say(SENT)\n        raise\n",
     "                _say(SENT)\n        return EXIT_ERROR\n",
     ["tests/test_a_bug_report_carries_nothing_from_the_files.py::test_a_failure_of_this_tool_writes_a_bundle_and_leaves_as_it_did",
      "tests/test_a_bug_report_carries_nothing_from_the_files.py::test_a_process_that_fails_leaves_by_the_same_code_with_or_without_the_bundle"],
     "writing a bundle for a defect swallowed it: no traceback, and exit 2 "
     "where the process had left by 1"),

    ("bundle/a-refused-input-is-told-how-to-report-it",
     "src/aas_submodel_validate/cli.py",
     "    elif refused and report is not None:\n        _say(REFUSED)\n",
     "    elif refused and report is not None:\n        pass\n",
     ["tests/test_a_bug_report_carries_nothing_from_the_files.py::test_a_refused_file_is_told_how_to_report_it_once[text]"],
     "an input this reader refused was reported with no word on how to report "
     "the refusal"),

    ("bundle/a-mistyped-path-is-not-a-refusal",
     "src/aas_submodel_validate/cli.py",
     'REFUSALS = ("X1", "X2", "X3", "X5")',
     'REFUSALS = ("X1", "X2", "X3", "X5", "X6")',
     ["tests/test_a_bug_report_carries_nothing_from_the_files.py::test_a_path_that_is_not_there_is_not_called_a_defect_or_a_refusal"],
     "a path with nothing behind it was asked to be reported as a bug"),

    ("bundle/an-unpublished-extra-id-is-not-told",
     "src/aas_submodel_validate/bundle.py",
     "        ids.append(header if header in PUBLISHED_EXTRA_IDS else -1)\n",
     "        ids.append(header)\n",
     ["tests/test_a_bug_report_carries_nothing_from_the_files.py::test_an_extra_field_s_ids_cannot_carry_text"],
     "an extra field of empty records carried two bytes of text in each "
     "record's id, and the bundle read them all back out"),

    ("bundle/running-out-of-room-is-not-asked-to-be-reported",
     "src/aas_submodel_validate/cli.py",
     "                   and finding.violation.fix != runner.RESOURCE_REMEDY)\n",
     "                   and True)\n",
     ["tests/test_a_bug_report_carries_nothing_from_the_files.py::test_a_rule_that_ran_out_of_room_is_not_asked_to_be_reported"],
     "a run that ran out of memory or stack, whose remedy says that is not a "
     "defect, was followed by a sentence asking for a bug report"),

    ("bundle/only-a-closed-pipe-is-not-a-defect",
     "src/aas_submodel_validate/cli.py",
     "        if not isinstance(exc, BrokenPipeError) and not args.no_bundle:\n",
     "        if not isinstance(exc, OSError) and not args.no_bundle:\n",
     ["tests/test_a_bug_report_carries_nothing_from_the_files.py::test_which_os_errors_are_this_tool_s_defect[this-tool-s-own-file]"],
     "this tool failing to open one of its own files wrote no bundle, because "
     "every OSError was taken for the caller's path"),

    ("bundle/past-the-size-bound-it-is-not-hashed",
     "src/aas_submodel_validate/bundle.py",
     "                if read > container.MAX_TOTAL_PART_BYTES:\n",
     "                if False:\n",
     ["tests/test_a_bug_report_carries_nothing_from_the_files.py::test_a_file_past_the_reader_s_bounds_is_not_read_again_past_them"],
     "the bundle hashed a file past the bound the run holds an input to"),

    ("bundle/past-the-directory-bound-it-is-counted-not-listed",
     "src/aas_submodel_validate/bundle.py",
     "    if end[zipfile._ECD_SIZE] > container.MAX_DIRECTORY_BYTES:\n",
     "    if False:\n",
     ["tests/test_a_bug_report_carries_nothing_from_the_files.py::test_a_file_past_the_reader_s_bounds_is_not_read_again_past_them"],
     "the bundle listed a central directory past the bound the run holds a "
     "directory to"),

    ('bundle/a-name-as-a-number',
     'src/aas_submodel_validate/bundle.py',
     'info.flag_bits, len(name), same if same != i else None,',
     'info.flag_bits, int.from_bytes(name.encode()[-6:], "big"), same if same != i else None,',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_two_files_that_differ_only_in_what_their_senders_wrote_give_one_bundle'],
     "a member's length column carried the last six bytes of its name as a number"),

    ('bundle/a-hash-of-a-name',
     'src/aas_submodel_validate/bundle.py',
     'info.flag_bits, len(name), same if same != i else None,',
     'info.flag_bits, len(name), int(hashlib.sha256(name.encode()).hexdigest()[:12], 16),',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_two_files_that_differ_only_in_what_their_senders_wrote_give_one_bundle'],
     "a member's row carried a hash of its name, which a guess can be checked against"),

    ('bundle/an-extension-as-a-kind',
     'src/aas_submodel_validate/bundle.py',
     '        kinds[KINDS.get(suffix, "other")] += 1\n',
     '        kinds[KINDS.get(suffix, suffix)] = kinds.get(KINDS.get(suffix, suffix), 0) + 1\n',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_two_files_that_differ_only_in_what_their_senders_wrote_give_one_bundle'],
     "the kinds of file a package holds were counted under each member's own extension"),

    ('bundle/the-environment-s-values',
     'src/aas_submodel_validate/bundle.py',
     '    return {"argv": shown, "env": sorted(name for name in ENVIRONMENT if name in os.environ)}',
     '    return {"argv": shown, "env": sorted("%s=%s" % pair for pair in os.environ.items())}',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_the_environment_the_user_and_the_host_stay_out'],
     'the bundle carried every environment variable with its value'),

    ('bundle/the-host-s-name',
     'src/aas_submodel_validate/bundle.py',
     '"machine": platform.machine()},',
     '"machine": platform.machine(), "node": platform.node()},',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_the_environment_the_user_and_the_host_stay_out'],
     'the bundle carried the name of the machine it ran on'),

    ('bundle/a-frame-outside-the-package',
     'src/aas_submodel_validate/bundle.py',
     '            rel = Path(frame.filename).resolve().relative_to(_PACKAGE)\n',
     '            rel = Path(Path(frame.filename).name)\n',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_a_frame_outside_this_package_is_not_kept'],
     "a defect's bundle kept frames from outside this package, with their names"),

    ('bundle/rows-cut-short',
     'src/aas_submodel_validate/bundle.py',
     '    keep_rows(_largest(len(rows), keep_rows))\n',
     '    keep_rows(_largest(len(rows), keep_rows) // 2)\n',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_member_rows_are_trimmed_to_as_many_as_fit'],
     'past the limit, the bundle kept half the rows that would have fitted'),

    ('bundle/no-limit-at-all',
     'src/aas_submodel_validate/bundle.py',
     '    if fits():\n        return bundle\n    members = ',
     '    if True:\n        return bundle\n    members = ',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_member_rows_are_trimmed_to_as_many_as_fit'],
     'a bundle of a large archive passed 256 KiB'),

    ('bundle/every-rule-kept',
     'src/aas_submodel_validate/bundle.py',
     '    keep_rules(_largest(len(ranked), keep_rules))\n',
     '    keep_rules(len(ranked))\n',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_a_caller_template_whose_every_row_fires_stays_within_the_limit'],
     "a caller's template whose every row fired took the bundle past 256 KiB"),

    ('bundle/the-hash-of-other-bytes',
     'src/aas_submodel_validate/bundle.py',
     '                digest.update(block)\n',
     '                digest.update(block[:-1])\n',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_what_the_bundle_says_of_an_archive_is_what_the_archive_holds'],
     "the input's hash was taken of bytes other than the input's"),

    ('bundle/the-utf8-flag-unread',
     'src/aas_submodel_validate/bundle.py',
     '_extra_ids(info.extra), bool(info.flag_bits & 0x800)])',
     '_extra_ids(info.extra), False])',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_what_the_bundle_says_of_an_archive_is_what_the_archive_holds'],
     "a member's UTF-8 flag was said to be off whatever the archive said"),

    ('bundle/containers-inside-uncounted',
     'src/aas_submodel_validate/bundle.py',
     '        inside += suffix in CONTAINERS\n',
     '        inside += 0\n',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_what_the_bundle_says_of_an_archive_is_what_the_archive_holds'],
     'a package inside the package went uncounted'),

    ('bundle/example-unnamed',
     'src/aas_submodel_validate/bundle.py',
     '    if example:\n        shown.append("--example")\n',
     '    if False:\n        shown.append("--example")\n',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_what_the_bundle_says_of_the_run_is_what_the_run_said'],
     'a bundle of the bundled example did not say that is what was judged'),

    ('bundle/where-a-finding-points-unread',
     'src/aas_submodel_validate/bundle.py',
     '        slot["whereKinds"][_where_kind(f)] += 1\n',
     '        slot["whereKinds"]["none"] += 1\n',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_what_the_bundle_says_of_the_run_is_what_the_run_said'],
     'every finding was said to point nowhere'),

    ('bundle/the-bound-met-unnamed',
     'src/aas_submodel_validate/bundle.py',
     '        "budgets": {"hit": sorted({"X5"} & set(findings))},',
     '        "budgets": {"hit": []},',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_the_bound_the_run_met_is_named'],
     "a run that met the reader's bound did not say so"),

    ('bundle/a-defect-s-code-misstated',
     'src/aas_submodel_validate/cli.py',
     '            where = _bundle(args, path, None, 1, started, trigger="crash", error=exc)',
     '            where = _bundle(args, path, None, 2, started, trigger="crash", error=exc)',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_a_frame_outside_this_package_is_not_kept'],
     "a defect's bundle said the run left by 2 where the process leaves by 1"),

    ('bundle/show-bundle-writes-anyway',
     'src/aas_submodel_validate/cli.py',
     '            _say(SENT)\n            return None\n        return bundling.write(made, args.bundle_out)',
     '            _say(SENT)\n            return bundling.write(made, args.bundle_out)\n        return bundling.write(made, args.bundle_out)',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_show_bundle_writes_nothing_on_a_run_that_did_not_fail'],
     '--show-bundle wrote the bundle it was asked only to show'),

    ('bundle/an-interrupt-taken-for-a-defect',
     'src/aas_submodel_validate/cli.py',
     '    except Exception as exc:\n        if not isinstance(exc, BrokenPipeError)',
     '    except BaseException as exc:\n        if not isinstance(exc, BrokenPipeError)',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_an_interrupt_is_not_a_defect'],
     'Ctrl-C wrote a bundle calling itself a defect in this tool'),

    ('bundle/a-refused-template-taken-for-a-refused-file',
     'src/aas_submodel_validate/cli.py',
     '    elif refused and report is not None:\n',
     '    elif refused:\n',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_a_refused_template_is_not_a_refused_file'],
     'a template this reader refused was followed by the sentence about reporting a file'),

    ('bundle/only-one-kind-of-refusal',
     'src/aas_submodel_validate/cli.py',
     'REFUSALS = ("X1", "X2", "X3", "X5")',
     'REFUSALS = ("X1",)',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_each_kind_of_refusal_is_told_how_to_report_it[X2]'],
     'a part of a package that was refused was not followed by how to report it'),

    ('bundle/rules-ignores-the-bundle-switches',
     'src/aas_submodel_validate/cli.py',
     '            ("--bug-report", args.bug_report), ("--show-bundle", args.show_bundle),\n            ("--no-bundle", args.no_bundle), ("--note", args.note is not None),\n',
     '            ("--note", args.note is not None),\n',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_rules_refuses_every_bundle_switch[--bug-report]'],
     '--rules --bug-report printed the listing and wrote nothing, without a word'),

    ('bundle/a-dead-stderr-raises',
     'src/aas_submodel_validate/cli.py',
     '    except (OSError, ValueError):\n        sys.stderr = _NOWHERE\n',
     '    except (OSError, ValueError):\n        raise\n',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_a_stderr_nobody_reads_moves_no_exit_code'],
     "a stderr whose reader had gone turned a bundle's lines into exit 120"),

    ('bundle/stdout-not-first',
     'src/aas_submodel_validate/cli.py',
     '    with contextlib.suppress(OSError, ValueError, AttributeError):\n        sys.stdout.flush()\n',
     '    with contextlib.suppress(OSError, ValueError, AttributeError):\n        pass\n',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_the_report_comes_before_the_lines_after_it_in_a_merged_log'],
     'in a log merging both streams, the sentence after the report came before it'),

    ('bundle/written-through-a-link',
     'src/aas_submodel_validate/bundle.py',
     '        os.replace(temporary, target)\n',
     '        target.write_text(dumps(bundle), encoding="utf-8")\n',
     ['tests/test_a_bug_report_carries_nothing_from_the_files.py::test_a_link_planted_under_the_bundle_s_name_is_replaced_not_written_through'],
     "a link planted under the bundle's name had the file it pointed at overwritten"),

    ("bundle/written-as-text",
     "src/aas_submodel_validate/bundle.py",
     '        with os.fdopen(handle, "wb") as stream:\n            stream.write(dumps(bundle).encode("utf-8"))\n',
     '        with os.fdopen(handle, "w", encoding="utf-8", newline="\\r\\n") as stream:\n            stream.write(dumps(bundle))\n',
     ["tests/test_a_bug_report_carries_nothing_from_the_files.py::"
      "test_nothing_a_sender_wrote_is_in_the_bundle_of_a_package"],
     "the bundle was written as text, and on Windows every line ending grew "
     "a byte past what the limit had measured"),

    ("cli/a-line-for-a-person-goes-through-say",
     "src/aas_submodel_validate/cli.py",
     '        _say("smtv: %s" % (refusal or "nothing in %s was judged" % path))\n',
     '        print("smtv: %s" % (refusal or "nothing in %s was judged" % path), file=sys.stderr)\n',
     ["tests/test_a_line_for_a_person_stays_off_the_report.py::"
      "test_with_stderr_closed_no_line_reaches_stdout"],
     "with stderr closed, the sentence saying why nothing was judged was "
     "written into the JSON on stdout"),

    ("cli/the-template-refusal-goes-through-say",
     "src/aas_submodel_validate/cli.py",
     '        _say("smtv: %s" % refused)\n',
     '        print("smtv: %s" % refused, file=sys.stderr)\n',
     ["tests/test_a_line_for_a_person_stays_off_the_report.py::"
      "test_with_stderr_closed_no_line_reaches_stdout"],
     "with stderr closed, the sentence saying a template was refused was "
     "written to stdout"),

    ("cli/the-judged-count-goes-through-say",
     "src/aas_submodel_validate/cli.py",
     '        _say("smtv: judged %d of %d submodel%s; --require-all-judged was given"\n'
     '             % (report.submodels_judged, expected, "" if expected == 1 else "s"))\n',
     '        print("smtv: judged %d of %d submodel%s; --require-all-judged was given"\n'
     '              % (report.submodels_judged, expected, "" if expected == 1 else "s"),\n'
     '              file=sys.stderr)\n',
     ["tests/test_a_line_for_a_person_stays_off_the_report.py::"
      "test_with_stderr_closed_no_line_reaches_stdout"],
     "with stderr closed, the count --require-all-judged reports was "
     "written into the JSON on stdout"),

    ("cli/the-missing-example-line-survives-a-dead-stderr",
     "src/aas_submodel_validate/cli.py",
     '            _say("smtv: %s" % exc)\n            return EXIT_ERROR\n',
     '            if sys.stderr is not None:\n'
     '                print("smtv: %s" % exc, file=sys.stderr)\n'
     '            return EXIT_ERROR\n',
     ["tests/test_a_line_for_a_person_stays_off_the_report.py::"
      "test_a_stderr_nobody_reads_leaves_a_package_without_its_example_its_exit_code"],
     "a package without its example, run with a stderr nobody reads, left "
     "by 120 -- safe from a closed stderr, not from a dead one"),

    ("cli/a-writer-with-no-flush-is-still-written-to",
     "src/aas_submodel_validate/cli.py",
     '        flush = getattr(sys.stderr, "flush", None)\n'
     '        if flush is not None:\n'
     '            flush()\n',
     '        sys.stderr.flush()\n',
     ["tests/test_a_line_for_a_person_stays_off_the_report.py::"
      "test_a_stderr_that_only_writes_gets_the_line_and_the_run_keeps_its_code"],
     "a program that handed redirect_stderr a writer with no flush had main "
     "raise AttributeError and leave by 1 instead of the run's code"),

    ("cli/a-stderr-let-go-of-is-handed-back-as-none",
     "src/aas_submodel_validate/cli.py",
     '        sys.stderr = _NOWHERE\n',
     '        sys.stderr = None\n',
     ["tests/test_a_line_for_a_person_stays_off_the_report.py::"
      "test_a_stderr_let_go_of_is_not_handed_back_as_none"],
     "after main returned, the calling program's own lines for stderr went "
     "to its stdout"),

    ("cli/a-closed-stderr-raises",
     "src/aas_submodel_validate/cli.py",
     '    except (OSError, ValueError):\n        sys.stderr = _NOWHERE\n',
     '    except OSError:\n        sys.stderr = _NOWHERE\n',
     ["tests/test_a_line_for_a_person_stays_off_the_report.py::"
      "test_a_stderr_already_closed_is_let_go_of_too"],
     "a stderr closed in-process raised ValueError out of main"),

    ("tablegen/the-clause-names-the-qualifier-as-written",
     "src/aas_submodel_validate/tablegen.py",
     '    return "%s qualifier" % written\n',
     '    return "SMT/Cardinality qualifier"\n',
     ["tests/test_a_rule_names_the_qualifier_its_template_wrote.py::test_each_pack_s_rules_name_the_qualifier_as_its_template_wrote_it",
      "tests/test_a_rule_names_the_qualifier_its_template_wrote.py::test_a_caller_s_template_is_cited_the_same_way"],
     "a rule whose template stated its cardinality with a bare Cardinality, or "
     "with Multiplicity, cited SMT/Cardinality"),

    ("tablegen/the-row-keeps-the-qualifier-it-was-read-from",
     "src/aas_submodel_validate/tablegen.py",
     '    if written != "SMT/Cardinality":\n',
     '    if False:\n',
     ["tests/test_a_rule_names_the_qualifier_its_template_wrote.py::"
      "test_a_caller_s_template_is_cited_the_same_way"],
     "a row built from a template that stated no cardinality qualifier, or "
     "another spelling, cited SMT/Cardinality -- held where the generator "
     "runs, a caller's template, since the vendored tables are its output "
     "and `extract_smt_rules.py --check` holds those"),

    ("tablegen/a-pack-cites-a-fixed-spelling",
     "src/aas_submodel_validate/rules/pcf.py",
     '         spec="%s, %s" % (pcf_tables.TEMPLATE_CITATION, qualifier_said(_row)),\n',
     '         spec="%s, SMT/Cardinality qualifier" % pcf_tables.TEMPLATE_CITATION,\n',
     ["tests/test_a_rule_names_the_qualifier_its_template_wrote.py::"
      "test_each_pack_s_rules_name_the_qualifier_as_its_template_wrote_it"],
     "02023's two unqualified list items cited SMT/Cardinality, and no test "
     "counted that pack"),

    ("dbp7/the-clause-is-read-off-the-row",
     "src/aas_submodel_validate/rules/dbp7.py",
     '         spec="%s, %s" % (dbp7_tables.TEMPLATE_CITATION, qualifier_said(_row)),\n',
     '         spec="%s, SMT/Cardinality qualifier" % dbp7_tables.TEMPLATE_CITATION,\n',
     ["tests/test_a_rule_names_the_qualifier_its_template_wrote.py::"
      "test_a_pack_reads_the_qualifier_off_the_row_where_every_row_agrees_too[dbp7]"],
     "02035-7's rules cited SMT/Cardinality whatever its row carried; every "
     "row there says so, so no count could tell"),

    ("tablegen/the-reason-sits-outside-its-parenthesis",
     "src/aas_submodel_validate/rules/td.py",
     '                          qualifier_said(_row, why="as the PDF\'s element tables give it")),\n',
     '                          qualifier_said(_row)),\n',
     ["tests/test_a_rule_names_the_qualifier_its_template_wrote.py::"
      "test_02003_s_unqualified_items_say_where_their_0_to_many_comes_from"],
     "02003's four list items no longer said the PDF's element tables are "
     "where their 0..* comes from"),

    ("changelog/the-entry-counts-its-packs",
     "tests/test_readme_front.py",
     '    assert ("across %s template packs" % _TEMPLATE_WORDS[vendored]\n',
     '    assert ("across %s template packs" % _TEMPLATE_WORDS[vendored - 1]\n',
     ["tests/test_readme_front.py::"
      "test_the_newest_changelog_entry_is_a_draft_or_a_dated_release"],
     "the newest entry's count of template packs was held to a number one "
     "short of the tree's"),

    ("dbp4/the-name-an-author-reaches-for",
     "src/aas_submodel_validate/rules/detect.py",
     '"batterytechnicaldata")',
     '"batterytechnicaldatas")',
     ["tests/test_generated_rules_dbp4.py::"
      "test_a_submodel_named_as_the_template_is_told_matching_goes_by_identifier"],
     "a submodel named BatteryTechnicalData that carried another identifier "
     "was listed as an unknown identifier, where the other packs' namesakes "
     "are told the name is not what matches"),

    ("dbp4/the-pack-registers-its-lint",
     "src/aas_submodel_validate/rules/dbp4.py",
     'install_near_miss_lint("DBP4L1", dbp4_tables)\n',
     "\n",
     ["tests/test_near_miss_lints.py::"
      "test_a_drifted_identifier_is_named_by_the_pack_s_lint[DBP4L1]"],
     "a Battery Technical Data element one version suffix off its row drew "
     "no finding naming it"),

    ("dbp7/the-name-an-author-reaches-for",
     "src/aas_submodel_validate/rules/detect.py",
     '"circularity")',
     '"circularitys")',
     ["tests/test_generated_rules_dbp7.py::"
      "test_a_submodel_named_as_the_template_is_told_matching_goes_by_identifier"],
     "a submodel named Circularity that carried another identifier was listed "
     "as an unknown identifier, where the other packs' namesakes are told the "
     "name is not what matches"),

    ("dbp7/the-pack-registers-its-lint",
     "src/aas_submodel_validate/rules/dbp7.py",
     'install_near_miss_lint("DBP7L1", dbp7_tables)\n',
     "\n",
     ["tests/test_near_miss_lints.py::"
      "test_a_drifted_identifier_is_named_by_the_pack_s_lint[DBP7L1]"],
     "a Battery Circularity element one SAMM version off its row drew no "
     "finding naming it"),

    ("dbp4/the-passport-states-its-category-in-the-template-s-element",
     "tests/test_battery_rules.py",
     "            value = _declaring(_conformant(dbp4_tables, dbp4_env, value, deep=True), category)\n",
     "            value = _conformant(dbp4_tables, dbp4_env, value, deep=True)\n",
     ["tests/test_battery_rules.py::"
      "test_a_light_transport_passport_is_not_asked_for_what_its_guidance_forbids"],
     "the synthetic passport's Technical Data part stated the golden "
     "fixture's category, `ev`, whatever the test asked for"),

    ("dbp4/the-passport-s-technical-data-is-mandatory-all-the-way-down",
     "tests/test_battery_rules.py",
     "_conformant(dbp4_tables, dbp4_env, value, deep=True)",
     "_conformant(dbp4_tables, dbp4_env, value, deep=False)",
     ["tests/test_battery_rules.py::"
      "test_an_electric_vehicle_passport_is_asked_the_two_its_guidance_requires"],
     "the synthetic passport's Technical Data part carried every optional "
     "element the golden fixture does, so it answered the questions the "
     "battery rules ask of an EV passport before they were asked"),

    ("engine/an-element-s-own-identifier-names-its-row",
     "src/aas_submodel_validate/rules/engine.py",
     "                   and owned.get(index, row[\"id\"]) == row[\"id\"]\n",
     "",
     ["tests/test_generated_rules_dbp4.py::"
      "test_a_file_carrying_the_template_s_own_supplementals_is_judged_as_one_without",
      "tests/test_generated_rules_dn.py::"
      "test_hardware_and_firmware_versions_each_keep_their_own_row"],
     "a Technical Data file carrying the template's own supplementals drew "
     "twenty-eight errors, and a Digital Nameplate carrying them was told it "
     "had two hardware versions: the first row holding a shared identifier "
     "claimed every element carrying it"),

    ("battery/the-category-is-read-under-every-identifier",
     "src/aas_submodel_validate/rules/battery.py",
     "            if CATEGORY_IDENTIFIERS & element_candidate_values(element):\n",
     "            if CATEGORY_ELEMENT in element_candidate_values(element):\n",
     ["tests/test_battery_rules.py::"
      "test_the_category_is_read_under_every_identifier_the_template_gives_it"],
     "a category written with the ECLASS identifier the template gives it "
     "passed the template and was reported as no category"),

    ("dbp4/both-file-rows-are-asked",
     "src/aas_submodel_validate/rules/dbp4.py",
     'install_file_rule("DBP4-D1", dbp4_tables, dbp4_tables.TEMPLATE_CITATION)\n',
     'install_file_rule("DBP4-D1", dbp4_tables, dbp4_tables.TEMPLATE_CITATION,\n'
     '                  only=("CompanyLogo",))\n',
     ["tests/test_generated_rules_dbp4.py::test_each_file_row_is_asked_for_its_part"],
     "a product image naming a part the package does not hold drew nothing"),

    ("dbp1/the-pack-registers-its-lint",
     "src/aas_submodel_validate/rules/dbp1.py",
     'install_near_miss_lint("DBP1L1", dbp1_tables)\n',
     "\n",
     ["tests/test_near_miss_lints.py::"
      "test_a_drifted_identifier_is_named_by_the_pack_s_lint[DBP1L1]"],
     "a Battery Nameplate element one version suffix off its row drew no "
     "finding naming it"),

    ("dbp5/the-pack-registers-its-lint",
     "src/aas_submodel_validate/rules/dbp5.py",
     'install_near_miss_lint("DBP5L1", dbp5_tables)\n',
     "\n",
     ["tests/test_generated_rules_dbp5.py::"
      "test_an_element_one_samm_version_off_is_named_by_the_lint"],
     "an element of 02035-5's release before, inside a 1.0.2 submodel, "
     "drew no finding naming it"),

]

#: The row that must live. A comment nobody reads, in a file whose prose
#: no test asserts. Measured before it was written down: with this line
#: added the suite reads exactly what it reads without it.
TABLE.extend([('engine/a-match-note-names-the-intersecting-identifier',
  'src/aas_submodel_validate/rules/engine.py',
  '                for attribute, value in _matching_spellings(element, row))',
  '                for attribute, value in [("semanticId", _identifier(element))])',
  ['tests/test_matched_identifier_evidence.py::test_only_the_supplemental_identifier_that_opened_the_row_is_named'],
  'A collection opened by its supplemental old IPCommunication identifier reported an '
  'unrelated supplier primary identifier as the spelling matched. The match note has to '
  'intersect the row, as matching itself does.'),
 ('engine/matched-supplementals-keep-the-file-order',
  'src/aas_submodel_validate/rules/engine.py',
  '                for attribute, value in _matching_spellings(element, row))',
  '                for attribute, value in sorted(_matching_spellings(element, row)))',
  ['tests/test_matched_identifier_evidence.py::test_matching_supplementals_are_all_named_in_file_order'],
  'A collection carrying both old and repaired IPCommunication identifiers named neither '
  'supplemental in its finding. Both are evidence, in the order the file supplies; sorting '
  'reverses the old-then-repaired example.')])


TABLE.extend([('engine/the-repaired-ip-identifier-opens-its-child-scope',
  'src/aas_submodel_validate/rules/engine.py',
  '    if candidates & set(row["match"]):',
  '    if candidates & (set(row["match"]) - '
  '{"https://admin-shell.io/zvei/nameplate/1/0/ContactInformations/ContactInformation/IPCommunication"}):',
  ['tests/test_unmatched_coverage.py::test_the_repaired_ip_communication_identifier_enters_its_row_and_asks_for_its_child'],
  'The unknown-path test kept asserting silence after its input became the repaired '
  'identifier and matched its row. It also passed with AddressOfAdditionalLink missing. '
  'The repaired identifier must enter the row and report CI-E22 for that missing child; an '
  'unrelated optional collection remains unjudged.')])


TABLE.extend([
    ("battery/the-index-keeps-lf-under-platform-defaults",
     "data/battery-passport/tools/_common.py",
     '    with open(out_path, "w", encoding="utf-8", newline="\\n") as fh:\n',
     '    with open(out_path, "w", encoding="utf-8") as fh:\n',
     ["tests/test_generators_write_the_same_bytes.py::"
      "test_windows_text_defaults_do_not_change_committed_bytes"
      "[data/battery-passport/tools/extract_idta_smt.py]"],
     "the IDTA index acquired CRLF under Windows text defaults while "
     "UTF-8 was explicit and its LF-normalized content stayed identical"),

    ("battery/the-join-check-sees-byte-drift",
     "data/battery-passport/tools/join_requirements.py",
     '            if not os.path.exists(path) or Path(path).read_bytes() != text.encode("utf-8"):\n',
     '            if not os.path.exists(path) or open(path, encoding="utf-8").read() != text:\n',
     ["tests/test_generators_write_the_same_bytes.py::"
      "test_check_refuses_crlf_even_when_the_text_is_the_same"
      "[data/battery-passport/tools/join_requirements.py]"],
     "a CRLF join and its markdown passed --check although their "
     "committed bytes were LF"),
])

TABLE.extend([
    ("comparison/the-option-probe-keeps-the-bytecode-environment",
     "tools/verdict_diff.py",
     '        asked = subprocess.run(\n'
     '            [sys.executable, "-m", "aas_submodel_validate", "--help"],\n'
     '            capture_output=True, text=True, timeout=_PATIENCE,\n'
     '            env=_reader_environment(src))',
     '        asked = subprocess.run(\n'
     '            [sys.executable, "-m", "aas_submodel_validate", "--help"],\n'
     '            capture_output=True, text=True, timeout=_PATIENCE,\n'
     '            env={"PYTHONPATH": str(src), "PATH": "/usr/bin:/bin",\n'
     '                 "PYTHONIOENCODING": "utf-8"})',
     ["tests/test_regeneration_contracts.py::"
      "test_the_option_probe_keeps_the_parent_bytecode_environment"],
     "the option probe discarded the bytecode environment while the "
     "judgement kept it; checking a supplied-template case for "
     "comparability wrote bytecode in the reader's source tree"),
])

TABLE.extend([
    ("pages/an-edition-a-page-names-is-the-one-vendored",
     "docs/scope.md",
     "IDTA 02011 Hierarchical Structures enabling Bills of Material 1.1.2 is a\n",
     "IDTA 02011 Hierarchical Structures enabling Bills of Material 1.1.1 is a\n",
     ["tests/test_pages_name_the_editions_read.py::"
      "test_a_page_naming_a_pack_with_an_edition_names_the_one_vendored"],
     "the scope page went on calling 02011 1.1.1 after 0.12.0 vendored "
     "1.1.2, and three more pages named an edition the pin had moved past; "
     "each was a number nothing read"),

    ("pages/the-divergences-page-names-every-template",
     "docs/divergences.md",
     "02007, IDTA 02035-5, IDTA 02035-1, IDTA 02035-4, IDTA 02035-7, or of the\n",
     "02007, or of the\n",
     ["tests/test_pages_name_the_editions_read.py::"
      "test_the_divergences_page_names_every_template_it_records_readings_of"],
     "the page's first sentence stopped at the eight templates it had "
     "before the battery parts, while rows 58 to 62 recorded readings of "
     "four more"),

    ("divergences/row-38-counts-references-in-this-tree",
     "docs/divergences.md",
     "**44 of the 2,074 references stack more than one key**",
     "**48 of the 935 references stack more than one key**",
     ["tests/test_divergence_counts_are_this_trees.py::"
      "test_row_38_counts_the_references_of_the_files_it_names"],
     "row 38 kept the reference counts of the editions vendored before the "
     "0.12.0 pin move, counted over three templates where twelve are now "
     "vendored"),

    ("divergences/row-38-measures-the-collector",
     "docs/divergences.md",
     "calls the collector 1,793 times and 56 of those are multi-key",
     "calls the collector 1,200 times and 23 of those are multi-key",
     ["tests/test_divergence_counts_are_this_trees.py::"
      "test_row_38_measures_the_collector_on_the_official_example"],
     "the collector count row 38 printed was measured before the pin moved "
     "and nine packs arrived, and went on being printed"),

    ("divergences/row-40-counts-the-official-properties",
     "docs/divergences.md",
     "all 132 properties carry a value",
     "all 102 properties carry a value",
     ["tests/test_divergence_counts_are_this_trees.py::"
      "test_row_40_counts_the_official_properties_and_the_rows_it_reaches"],
     "row 40 said 102 official properties where the files it names hold "
     "132, and had said so since the day it was written"),

    ("scope/the-ok-true-runs-are-counted",
     "docs/scope.md",
     "Four of these come back `ok: true`, and only one of them judged\n",
     "Three of these come back `ok: true`, and only one of them judged\n",
     ["tests/test_what_a_pass_means.py::"
      "test_the_paragraph_under_the_table_counts_its_rows"],
     "the paragraph under the table said three of its runs come back "
     "ok: true over a table where four do"),

    ("help/a-settle-only-profile-names-the-table-that-judges",
     "src/aas_submodel_validate/cli.py",
     "        others = judged_instead(key)\n",
     "        others = ()\n",
     ["tests/test_cli_flags.py::"
      "test_the_help_names_the_table_that_judges_where_a_profile_only_settles"],
     "--help said 02035-3 settles a collision with a table for neither "
     "side, while 02023's table judged the very submodel and BAT-R2 said so"),

    ("readme/the-integration-example-reads-the-refusal-report",
     "README.md",
     "if not done.stdout:                 # 64 called wrong, or a --template refused:\n",
     "if done.returncode >= 2:            # 64 called wrong, or a --template refused:\n",
     ["tests/test_the_readme_integration_example_runs.py::"
      "test_a_document_this_reader_refuses_is_read_from_its_report"],
     "the front page's integration example left on exit 2 and discarded "
     "the report a refused document comes back with"),

    ("detect/the-presence-rule-cites-every-template",
     "src/aas_submodel_validate/rules/detect.py",
     '      spec="the submodel semanticId of each template docs/scope.md lists "\n',
     '      spec="the submodel semanticId of each template "\n',
     ["tests/test_spec_accuracy.py::"
      "test_the_presence_rule_cites_the_page_that_lists_every_template_it_asks_about"],
     "SMT-D1 asks about twelve templates and cited two of their clauses, "
     "so a Nameplate or battery file was sent elsewhere for its requirement"),

    ("contact/the-submodel-identifier-is-not-an-ip-spelling",
     "src/aas_submodel_validate/rules/contact_tables.py",
     "                'match': ('https://admin-shell.io/zvei/nameplate/1/0/ContactInformations/', ",
     "                'match': ('https://admin-shell.io/zvei/nameplate/1/0/ContactInformations', "
     "'https://admin-shell.io/zvei/nameplate/1/0/ContactInformations/', ",
     ["tests/test_editions_published_since_the_pin.py::"
      "test_the_submodel_s_own_identifier_does_not_open_ip_communication"],
     "the submodel's own identifier was an IPCommunication alias although "
     "no 02002 edition gave IPCommunication that identifier"),

    ("tablegen/a-list-item-remedy-says-to-give-no-idshort",
     "src/aas_submodel_validate/tablegen.py",
     "    if in_list:\n        fix += (\", as an item of that list: give it no idShort%s\"\n",
     "    if False:\n        fix += (\", as an item of that list: give it no idShort%s\"\n",
     ["tools/extract_smt_rules.py --check"],
     "a list item's remedy quoted a label this tool invented, the way an "
     "idShort is quoted, and followed to the letter it put an idShort on a "
     "list item, which the metamodel forbids"),
])


TABLE.extend([
    ("api/a-keyword-reaches-the-engine",
     "src/aas_submodel_validate/api.py",
     "    return runner.run(held, strict_meta=meta, allow_unmatched=allow_unmatched,\n",
     "    return runner.run(held, strict_meta=meta, allow_unmatched=False,\n",
     ["tests/test_python_api.py::"
      "test_each_keyword_reaches_the_engine_and_is_recorded_as_asked"],
     "a keyword the library drops on its way to the engine is dropped by "
     "the command line too, which calls the library: the two stay one byte "
     "in step and the flag does nothing at either"),

    ("api/require-all-judged-is-read",
     "src/aas_submodel_validate/api.py",
     "              or (require_all_judged and short_of_all_judged(report))\n",
     "              or (False and short_of_all_judged(report))\n",
     ["tests/test_python_api.py::"
      "test_require_all_judged_fails_an_input_with_nothing_to_judge"],
     "exit_code is where the command line's code is computed, so a flag it "
     "stops reading passes every file under it at both entrances at once"),

    ("api/bytes-are-read-as-the-format-named",
     "src/aas_submodel_validate/api.py",
     "        return container.InMemory(source, _named(name), _suffix(form))\n",
     "        return container.InMemory(source, _named(name), _suffix(\"json\"))\n",
     ["tests/test_python_api.py::"
      "test_bytes_and_an_open_file_are_judged_as_the_file_they_were_read_from"],
     "bytes carry no extension, and the format they were handed over as is "
     "the one thing that chooses their reader"),

    ("api/what-was-not-judged-leaves-by-2",
     "src/aas_submodel_validate/api.py",
     "    if not report.judged:\n        return EXIT_ERROR\n",
     "    if not report.judged:\n        return EXIT_FINDINGS\n",
     ["tests/test_python_api.py::"
      "test_what_cannot_be_judged_comes_back_as_a_report_that_leaves_by_2"],
     "1 is the code for a verdict and a file nothing was judged in has none; "
     "a pipeline reading 1 goes looking for findings that are not there"),

    ("api/a-keyword-keeps-its-released-name",
     "src/aas_submodel_validate/api.py",
     "             allow_unmatched=False, profile=None, template=None) -> Report:\n",
     "             allow_unmatch=False, profile=None, template=None) -> Report:\n"
     "    allow_unmatched = allow_unmatch\n",
     ["tests/test_python_api.py::"
      "test_the_root_exports_what_released_api_txt_lists_and_nothing_else"],
     "a renamed keyword is a call somebody wrote that stops working, and the "
     "library's names and keywords are a promise the front page makes"),

    ("api/a-profile-there-is-none-of-is-refused",
     "src/aas_submodel_validate/api.py",
     "    if profile is not None and profile not in choices:\n",
     "    if False:\n",
     ["tests/test_python_api.py::"
      "test_a_profile_there_is_none_of_is_refused_where_the_engine_would_ignore_it"],
     "the engine reads a key no pair publishes as no key at all, and only "
     "the parser's choices stood in front of it; a library has no parser"),

    ("api/the-package-imports-without-the-engine",
     "src/aas_submodel_validate/__init__.py",
     "def __getattr__(name):\n",
     "from . import api  # noqa: E402,F401\n\n\ndef __getattr__(name):\n",
     ["tests/test_python_api.py::"
      "test_importing_the_package_does_not_import_the_engine"],
     "the tools import a module beneath the root from a bare source tree, "
     "and with the engine imported by the root the single-file builder died "
     "for want of the one dependency it exists to fetch"),

    ("api/bytes-are-bounded-as-a-path-is",
     "src/aas_submodel_validate/container.py",
     "        return len(path.data)\n",
     "        return 0\n",
     ["tests/test_python_api.py::"
      "test_bytes_over_the_bound_are_refused_as_the_same_file_on_disk_is"],
     "a document over the bound was refused before it was read when it "
     "came from disk, and read to the bound first when it came as bytes"),
])


TABLE.extend([
    ("action/a-file-name-is-not-a-command",
     "action.yml",
     '          "$@" "$file" || rc=$?\n',
     '          eval "\\"\\$@\\" $file" || rc=$?\n',
     ["tests/test_the_action_is_a_way_in.py::"
      "test_a_file_name_is_a_name_and_not_a_command"],
     "a name handed to the shell as text is a command: a supplier's file "
     "called `x; touch y` would run touch on the runner"),

    ("action/the-code-is-published",
     "action.yml",
     '        echo "exit-code=$worst" >> "$GITHUB_OUTPUT"\n',
     '        true\n',
     ["tests/test_the_action_is_a_way_in.py::"
      "test_the_step_says_what_smtv_says_about_one_file[judged]"],
     "with fail-on-finding false the output is the only place the code "
     "goes, and a job reading it would read nothing and carry on"),

    ("action/several-files-leave-by-the-heaviest-code",
     "action.yml",
     '          if [ "$(weight "$rc")" -gt "$(weight "$worst")" ]; then\n',
     '          if true; then\n',
     ["tests/test_the_action_is_a_way_in.py::"
      "test_several_files_leave_by_the_heaviest_code_in_either_order"],
     "the last file's code standing for all of them passes a step whose "
     "first file could not be judged, so long as a clean one follows it"),

    ("action/a-code-smtv-does-not-give-is-not-a-verdict",
     "action.yml",
     '            0|1|2|64) ;;\n',
     '            0|1|2|3|64) ;;\n',
     ["tests/test_the_action_is_a_way_in.py::"
      "test_a_code_smtv_does_not_give_is_not_a_verdict"],
     "a validator that did not run is not a verdict, and read as one under "
     "fail-on-finding false it passes a step nothing looked at"),

    ("action/a-carried-file-is-checked-against-its-hash",
     "action.yml",
     '            if [ "$got" != "$want" ]; then\n',
     '            if false; then\n',
     ["tests/test_the_action_is_a_way_in.py::"
      "test_a_carried_file_with_the_wrong_hash_is_not_run"],
     "the hash is asked for so that a file carried into a closed network "
     "is checked rather than trusted, and an answer nobody compares checks "
     "nothing"),

    ("action/the-release-is-the-one-the-tag-names",
     "action.yml",
     '            v[0-9]*) version="${ACTION_REF#v}" ;;\n',
     '            v[0-9]*) ;;\n',
     ["tests/test_the_action_is_a_way_in.py::"
      "test_the_release_it_installs_is_the_one_it_was_pinned_at[the-ref-pinned]"],
     "a step pinned at one release that installs another runs a validator "
     "nobody asked for, and its verdict is cited against the wrong version"),

    ("action/a-pinned-digest-is-read-from-the-bytes",
     "action.yml",
     '              got=$(sha256sum < "$PYZ" | cut -d" " -f1)\n',
     '              got=$(sha256sum "$PYZ" | cut -d" " -f1)\n',
     ["tests/test_the_action_is_a_way_in.py::"
      "test_a_carried_file_with_the_right_hash_is_run_whatever_it_is_called[lower]"],
     "read off the line sha256sum writes for a name, the digest came back "
     "with a backslash in front wherever the name had one -- as a path "
     "written the Windows way does -- and a pinned file named so never ran"),

    ("action/a-validator-that-does-not-start-is-told-apart",
     "action.yml",
     '        if [ "$started" -ne 0 ]; then\n',
     '        if false; then\n',
     ["tests/test_the_action_is_a_way_in.py::"
      "test_a_validator_that_does_not_start_is_not_a_finding"],
     "a validator that cannot start leaves by 1, the code for a finding, and "
     "read as one the step reports a file judged that nothing looked at"),

    ("action/the-step-writes-what-smtv-writes",
     "action.yml",
     '        said=$("$@" --version 2>&1) || started=$?\n',
     '        "$@" --version >&2 || started=$?\n',
     ["tests/test_the_action_is_a_way_in.py::"
      "test_the_step_says_what_smtv_says_about_one_file[judged]"],
     "a line of the step's own on either stream makes the log of a step a "
     "different document from the log of the command it runs"),
])


TABLE.extend([
    ("browser/a-request-after-load-is-a-problem",
     "tools/browser_gates.py",
     '        if urls:\n            problems.append("%s: %d request(s) after load, seen by the %s counter: %s"\n',
     '        if False:\n            problems.append("%s: %d request(s) after load, seen by the %s counter: %s"\n',
     ["tests/test_the_page_says_what_the_command_says.py::test_a_request_after_load_is_a_problem_named_by_the_counter_that_saw_it"],
     "the page's whole promise is the zero this counts; a gate that counts "
     "and does not object is a gate that passes a page that phones home"),

    ("browser/two-different-commands-are-not-compared",
     "tools/browser_gates.py",
     "    if list(page.argv) != list(cli.argv):\n",
     "    if False:\n",
     ["tests/test_the_page_says_what_the_command_says.py::test_two_runs_of_different_commands_are_not_compared"],
     "outputs of two different commands agree or disagree for reasons that "
     "say nothing about the page"),

    ("browser/every-door-has-to-be-among-the-files",
     "tools/browser_gates.py",
     "    if opened != sorted(DOORS):\n",
     "    if False:\n",
     ["tests/test_the_page_says_what_the_command_says.py::test_the_doors_have_to_be_among_the_files_checked"],
     "a zero counted over files that never asked the reader to reach out "
     "says nothing about a reader that was asked to"),

    ("browser/the-deep-documents-have-to-be-among-the-files",
     "tools/browser_gates.py",
     "    if sorted(path.name for path in todo if path.name in DEEP) != sorted(DEEP):\n",
     "    if False:\n",
     ["tests/test_the_page_says_what_the_command_says.py::"
      "test_the_documents_past_the_bound_have_to_be_among_the_files_checked"],
     "the page crashed on documents nested past its stack; a run without "
     "them says nothing about whether it now refuses them as the command does"),

    ("browser/the-entity-door-uses-its-entity",
     "tools/browser_gates.py",
     '              + xml[:first] + "&pull;" + xml[xml.index("</value>", first):])\n',
     '              + xml[:first] + "pull" + xml[xml.index("</value>", first):])\n',
     ["tests/test_the_page_says_what_the_command_says.py::test_the_doors_are_shut_to_the_command_and_it_is_asked_through_each"],
     "an entity declared and never used is a door painted on a wall: a "
     "reader that resolves entities as it meets them is never asked"),

    ("browser/every-counter-is-shown-the-controls",
     "tools/browser_gates.py",
     'CONTROLS = {"browser": 2, "server": 2, "page timing": 1, "worker timing": 1}\n',
     'CONTROLS = {"browser": 2, "server": 2, "page timing": 1}\n',
     ["tests/test_the_page_says_what_the_command_says.py::test_a_counter_that_missed_the_control_is_blind_not_quiet"],
     "a counter nobody shows a request to can be attached to nothing and "
     "read zero forever"),

    ("browser/a-blind-counter-fails-the-run",
     "tools/browser_gates.py",
     "    for name in blind(CONTROLS, counted):\n",
     "    for name in blind(CONTROLS, CONTROLS):\n",
     ["tests/test_the_page_says_what_the_command_says.py::test_a_blind_counter_fails_the_run_even_when_it_read_zero"],
     "the zero from a counter that missed the control is the zero of a "
     "counter that sees nothing"),

    ("browser/the-python-is-compared-to-the-patch",
     "tools/browser_gates.py",
     '    return [name for name in ("python", "aas_submodel_validate", "aas_core3")\n',
     '    return [name for name in ("aas_submodel_validate", "aas_core3")\n',
     ["tests/test_the_page_says_what_the_command_says.py::test_the_gate_refuses_to_compare_across_interpreters"],
     "two patch releases are two readers; a comparison across them cannot "
     "tell the page's difference from the interpreter's"),

    ("browser/the-page-asks-for-no-bundle",
     "browser/aas_page.py",
     '    return ["--no-bundle", *(["-f", "json"] if as_json else []), path]\n',
     '    return [*(["-f", "json"] if as_json else []), path]\n',
     ["tests/test_the_page_says_what_the_command_says.py::test_a_name_that_reads_as_an_option_is_passed_as_a_file"],
     "a diagnostic bundle written into the tab's memory is a file nobody "
     "could open, and asked for one the page runs another command"),

    ("browser/a-download-is-held-to-its-digest",
     "tools/build_browser.py",
     "    if got != sha256:\n",
     "    if False:\n",
     ["tests/test_the_page_says_what_the_command_says.py::test_a_download_that_is_not_the_pinned_bytes_is_refused"],
     "the page is the bytes it was built from; a download nothing compares "
     "is whatever the network handed over that day"),

    ("browser/the-runtime-package-is-the-one-its-lock-names",
     "tools/build_browser.py",
     '        if (locked.get("file_name"), locked.get("sha256")) != (entry["file"], entry["sha256"]):\n',
     "        if False:\n",
     ["tests/test_the_page_says_what_the_command_says.py::test_the_runtime_package_has_to_be_the_one_its_lock_file_names"],
     "a package pinned here and not the one the runtime's lock names is one "
     "its runtime would not have loaded"),

    ("browser/what-is-compiled-in-has-its-notice",
     "tools/build_browser.py",
     '     "notice": "liblzma", "version": "5.2.2", "revision": "v5.2.2",\n',
     '     "notice": "xz", "version": "5.2.2", "revision": "v5.2.2",\n',
     ["tests/test_the_page_says_what_the_command_says.py::test_the_page_carries_the_notice_of_everything_compiled_into_its_runtime"],
     "a binary built from code under a notice carries the notice, and the "
     "lzma package the engine needs has liblzma built into it"),
])


TABLE.extend([
    ('bound/json-is-asked-how-deep-before-it-is-parsed',
     'src/aas_submodel_validate/loader.py',
     '    if depth > container.MAX_NESTING:\n        raise NestedTooDeep(depth, crossing_line(text, "json", container.MAX_NESTING))\n',
     '    if False:\n        raise NestedTooDeep(depth, crossing_line(text, "json", container.MAX_NESTING))\n',
     ['tests/test_a_document_nested_past_the_bound.py::test_the_scan_neither_recurses_nor_takes_long[json-_json-1000000]'],
     "without the scan a deep document reaches the parser, and how deep it may nest is again the machine's stack: a report at one entrance and a crash at another"),

    ('bound/xml-is-asked-how-deep-before-it-is-parsed',
     'src/aas_submodel_validate/loader.py',
     '    if depth > container.MAX_NESTING:\n        loaded.errors.append(_too_deep(part or loaded.path, depth,\n',
     '    if False:\n        loaded.errors.append(_too_deep(part or loaded.path, depth,\n',
     ['tests/test_a_document_nested_past_the_bound.py::test_a_document_nested_to_the_bound_is_read_and_one_level_more_is_refused[xml-_xml]'],
     "XML is the same class: the browser's runtime ran out of stack on it near 3,000 levels while the command read on"),

    ('bound/the-bound-is-the-measured-one',
     'src/aas_submodel_validate/container.py',
     'MAX_NESTING = 200\n',
     'MAX_NESTING = 201\n',
     ['tests/test_a_document_nested_past_the_bound.py::test_the_bound_is_ten_times_the_deepest_file_judged_here'],
     'the bound is a measurement -- ten times the deepest file judged here, rounded up to the hundred -- and a number nobody derived drifts'),

    ('bound/an-escaped-quote-stays-inside-its-string',
     'src/aas_submodel_validate/loader.py',
     '_JSON_STRING = re.compile(r\'"[^"\\\\]*(?:\\\\.[^"\\\\]*)*(?:"|\\\\?\\Z)\', re.S)\n',
     '_JSON_STRING = re.compile(r\'"[^"]*(?:"|\\Z)\', re.S)\n',
     ['tests/test_a_document_nested_past_the_bound.py::test_the_scan_reads_json_as_a_character_by_character_reader_would'],
     'an escaped quote read as the end of its string turns the text after it into nesting, and a document full of brackets in its notes is refused'),

    ('bound/a-bracket-inside-a-string-is-text',
     'src/aas_submodel_validate/loader.py',
     '    brackets = others.sub(nothing, strings.sub(nothing, data))\n',
     '    brackets = others.sub(nothing, data)\n',
     ['tests/test_a_document_nested_past_the_bound.py::test_brackets_inside_a_string_are_text_and_not_nesting'],
     'a bracket inside a string is text; counted as nesting it refuses a document for what its descriptions say'),
])

TABLE.extend([
    ('saw/a-relayed-finding-shows-what-its-check-read',
     'src/aas_submodel_validate/runner.py',
     '                                              detail=evidence.relayed(error, target),\n',
     '                                              detail=None,\n',
     ['tests/test_every_finding_says_what_it_read.py::test_a_check_on_a_concept_description_shows_the_attribute_it_read'],
     "a relayed finding without what its check read names a path and leaves the reader to open the file to see what was there"),

    ('saw/the-attributes-shown-are-the-ones-the-check-names',
     'src/aas_submodel_validate/evidence.py',
     '    paths = relayed_reads.READS.get((type(value).__name__, error.cause))\n',
     '    paths = None\n',
     ['tests/test_every_finding_says_what_it_read.py::test_a_check_on_a_concept_description_shows_the_attribute_it_read'],
     "without the table a relayed finding names the object it is about, not what its check looked at"),

    ('saw/every-item-of-a-list-is-read',
     'src/aas_submodel_validate/evidence.py',
     '            values = [item for value in values if isinstance(value, (list, tuple))\n                      for item in value]\n',
     '            values = [value[0] for value in values if isinstance(value, (list, tuple)) and value]\n',
     ['tests/test_every_finding_says_what_it_read.py::test_a_long_list_is_shown_in_part_and_says_how_much_is_left'],
     "a check that read every item of a list, shown as if it read the first, hides the items that broke it"),

    ('saw/a-long-list-is-shown-in-part',
     'src/aas_submodel_validate/evidence.py',
     'SHOWN = 5\n',
     'SHOWN = 50\n',
     ['tests/test_every_finding_says_what_it_read.py::test_a_long_list_is_shown_in_part_and_says_how_much_is_left',
      'tests/test_every_finding_says_what_it_read.py::test_a_long_scope_is_shown_in_part'],
     "a list shown whole makes one finding as long as the file it read"),

    ('saw/the-table-reads-into-upstreams-helpers',
     'tools/extract_meta_reads.py',
     'HELPER_DEPTH = 3\n',
     'HELPER_DEPTH = 0\n',
     ['tests/test_every_finding_says_what_it_read.py::test_the_table_is_what_the_installed_checks_read'],
     "a condition that hands a list to one of aas-core3.0's helpers reads what the helper reads; stopped at the call, two strings in one language show as two strings, not as the language they share"),

    ('saw/a-scope-that-found-nothing-shows-what-it-holds',
     'src/aas_submodel_validate/rules/engine.py',
     '                else _held(elements)))\n',
     '                else None))\n',
     ['tests/test_every_finding_says_what_it_read.py::test_a_missing_element_shows_what_its_scope_holds'],
     "a finding that found nothing and shows nothing leaves the reader to open the file to learn what is there instead"),
])

TABLE.extend([
    ('saw/a-refusal-carries-what-the-container-read',
     'src/aas_submodel_validate/container.py',
     '        super().__init__(message)\n        self.detail = detail\n',
     '        super().__init__(message)\n        self.detail = None\n',
     ['tests/test_every_finding_says_what_it_read.py::test_a_file_that_is_not_a_zip_shows_what_it_begins_with',
      'tests/test_every_finding_says_what_it_read.py::test_a_package_with_no_origin_shows_what_its_relationships_declare'],
     "a refusal that drops what the container read says a file is not a package without the bytes that say why"),

    ('saw/a-path-refused-says-what-the-system-answered',
     'src/aas_submodel_validate/runner.py',
     '                                       detail=getattr(exc, "detail", None)))\n',
     '                                       detail=None))\n',
     ['tests/test_every_finding_says_what_it_read.py::test_every_finding_in_the_corpus_says_what_it_read'],
     "a path refused without what the operating system answered leaves nothing but the path to go on"),

    ('saw/a-document-over-the-bound-shows-its-size',
     'src/aas_submodel_validate/loader.py',
     'subject=str(path), detail="%d bytes, as the file system reports it" % size))\n',
     'subject=str(path), detail=None))\n',
     ['tests/test_every_finding_says_what_it_read.py::test_a_document_over_the_size_bound_shows_its_size'],
     "a size refusal that does not say the size it read is a refusal nobody can check"),

    ('saw/a-dtd-is-shown-as-written',
     'src/aas_submodel_validate/loader.py',
     '            detail=container.doctype_written(raw)))\n',
     '            detail=None))\n',
     ['tests/test_every_finding_says_what_it_read.py::test_a_document_declaring_a_dtd_shows_the_declaration'],
     "a document refused for a DTD shows the declaration, so its author can find the line that has to go"),

    ('saw/the-depth-the-scan-read-is-shown',
     'src/aas_submodel_validate/loader.py',
     '                     fix=nesting_remedy(), detail="at least %d levels deep" % depth,\n',
     '                     fix=nesting_remedy(), detail=None,\n',
     ['tests/test_every_finding_says_what_it_read.py::test_every_finding_in_the_corpus_says_what_it_read'],
     "a depth refusal says how deep the scan had read when it stopped"),

    ('saw/ids-none-of-which-is-primary-show-what-each-says',
     'src/aas_submodel_validate/rules/handover.py',
     '                                detail="DocumentIsPrimary: %s" % listed(\n',
     '                                detail=None and listed(\n',
     ['tests/test_every_finding_says_what_it_read.py::test_ids_none_of_which_is_primary_show_what_each_says'],
     "a hand rule that read every flag and shows none of them leaves the reader to open the file to see which was meant"),
])

TABLE.extend([
    ('action/a-file-not-judged-outweighs-a-finding',
     'action.yml',
     '        weight() { case "$1" in 64) echo 3 ;; 2) echo 2 ;; 1) echo 1 ;; *) echo 0 ;; esac; }\n',
     '        weight() { case "$1" in 64) echo 3 ;; 2) echo 1 ;; 1) echo 2 ;; *) echo 0 ;; esac; }\n',
     ['tests/test_the_action_is_a_way_in.py::test_several_files_leave_by_the_heaviest_code_in_either_order'],
     "a file nobody could judge says more than a finding; swapped, a run holding both leaves by 1 and reads as judged"),
])

TABLE.extend([
    ('line/a-finding-is-given-the-line-its-object-begins-on',
     'src/aas_submodel_validate/runner.py',
     '    report.findings = [_placed(finding, places) for finding in report.findings]\n',
     '    report.findings = list(report.findings)\n',
     ['tests/test_every_finding_names_its_line.py::test_every_finding_in_the_corpus_names_a_line_unless_no_line_holds_it'],
     "a finding that knows the object it is about and is not given its line leaves the reader to search the file for a path of idShorts"),

    ('line/a-brace-inside-a-string-opens-nothing',
     'src/aas_submodel_validate/positions.py',
     '    shape = text if text.count("{") == objects[0] else _STRING.sub("", text)\n',
     '    shape = text\n',
     ['tests/test_every_finding_names_its_line.py::test_a_brace_inside_a_string_opens_nothing'],
     "a `{` inside a string counted as an object moves every line after it onto the wrong object"),

    ('line/a-wrapped-value-is-read-inside-its-wrapper',
     'src/aas_submodel_validate/positions.py',
     '                    held = held.children[0]\n',
     '                    pass\n',
     ['tests/test_every_finding_names_its_line.py::test_every_object_of_an_xml_document_is_placed_on_its_start_tag'],
     "an abstract-typed value sits inside an element named for its class; read as its own wrapper, nothing beneath it has a line"),

    ('line/the-screen-names-the-part-when-there-are-two',
     'src/aas_submodel_validate/report.py',
     '    parts = len({f.violation.part for f in visible if f.violation.part}) > 1\n',
     '    parts = False\n',
     ['tests/test_every_finding_names_its_line.py::test_the_screen_gives_the_line_and_names_the_part_only_when_there_are_two'],
     "a line in a package of two documents, with no part named, is a line in one of two files"),

    ('line/a-syntax-error-names-the-line-its-parser-stopped-on',
     'src/aas_submodel_validate/loader.py',
     '    if isinstance(exc, json.JSONDecodeError):\n        return exc.lineno\n',
     '    if isinstance(exc, json.JSONDecodeError):\n        return None\n',
     ['tests/test_every_finding_names_its_line.py::test_a_syntax_error_names_the_line_the_parser_stopped_on'],
     "a document that would not parse is fixed at the line its parser stopped on, and a finding that does not give it sends the reader to look"),

    ('line/a-document-that-will-not-build-names-the-object-it-stopped-in',
     'src/aas_submodel_validate/loader.py',
     '            return positions.json_line_along(\n',
     '            return None and positions.json_line_along(\n',
     ['tests/test_every_finding_names_its_line.py::test_a_document_that_will_not_build_names_the_object_it_stopped_in'],
     "a document that parsed and would not build stopped in one object, and the library says which; without its line the finding names the whole file"),

    ('line/the-bound-names-the-line-it-was-crossed-on',
     'src/aas_submodel_validate/loader.py',
     '            return shape.count("\\n", 0, match.start()) + 1\n',
     '            return 1\n',
     ['tests/test_every_finding_names_its_line.py::test_a_document_nested_past_the_bound_names_the_line_it_crossed_on'],
     "a document refused for its depth is repaired where it goes past the bound"),

    ('line/a-relayed-finding-names-the-object-its-check-read',
     'src/aas_submodel_validate/runner.py',
     '                                              at=upstream.innermost(error, target)))\n',
     '                                              at=target))\n',
     ['tests/test_every_finding_names_its_line.py::test_a_relayed_finding_names_the_line_of_the_object_its_check_read'],
     "a relayed finding placed at the document it verified gives every one of them the document's first line"),

    ('line/an-element-finding-names-its-element',
     'src/aas_submodel_validate/rules/engine.py',
     '                    subject=subject, at=element, detail="found a %s" % actual,\n',
     '                    subject=subject, at=None, detail="found a %s" % actual,\n',
     ['tests/test_every_finding_names_its_line.py::test_every_finding_in_the_corpus_names_a_line_unless_no_line_holds_it'],
     "an element of the wrong kind is fixed where it stands; a finding that drops it has no line to give"),

    ('line/a-count-finding-names-the-scope-it-counted',
     'src/aas_submodel_validate/rules/engine.py',
     '                subject=path, path=here, at=holder,\n',
     '                subject=path, path=here, at=None,\n',
     ['tests/test_every_finding_names_its_line.py::test_every_finding_in_the_corpus_names_a_line_unless_no_line_holds_it'],
     "a missing element is added inside the scope that lacks it, and that scope's line is where to add it"),
])

TABLE.extend([
    ('line/an-input-that-changed-under-the-run-gives-no-line',
     'src/aas_submodel_validate/runner.py',
     '            if document_digest(raw) != loaded.digests.get(part):\n                return []\n',
     '            if False:\n                return []\n',
     ['tests/test_every_finding_names_its_line.py::test_a_file_changed_after_it_was_read_gives_no_line',
      'tests/test_every_finding_names_its_line.py::test_a_package_whose_document_changed_after_it_was_read_gives_no_line'],
     "a second reading of a file that changed after it was read pairs this file's findings with another file's lines"),

    ('line/a-file-is-held-to-the-bytes-the-model-was-built-from',
     'src/aas_submodel_validate/loader.py',
     '    loaded.digests[None] = document_digest(raw)\n',
     '    loaded.digests[None] = document_digest(b"")\n',
     ['tests/test_every_finding_names_its_line.py::test_a_file_changed_after_it_was_read_gives_no_line',
      'tests/test_every_finding_names_its_line.py::test_a_rule_finding_names_the_line_of_the_element_it_judged'],
     "the digest a bare file is held to has to be of the bytes the model was built from, or no finding in one names its line"),

    ('line/a-part-is-held-to-the-bytes-the-model-was-built-from',
     'src/aas_submodel_validate/loader.py',
     '        loaded.digests[part] = document_digest(raw)\n',
     '        loaded.digests[part] = document_digest(b"")\n',
     ['tests/test_every_finding_names_its_line.py::test_a_package_names_the_part_each_line_is_in',
      'tests/test_every_finding_names_its_line.py::test_a_package_whose_document_changed_after_it_was_read_gives_no_line'],
     "the digest a package's part is held to has to be of the bytes the model was built from, or no finding in a package names its line"),

    ('line/a-package-past-its-total-is-not-read-again',
     'src/aas_submodel_validate/runner.py',
     '    if loaded.container is not None and loaded.container.went_past_its_total:\n        return []\n',
     '    if False:\n        return []\n',
     ['tests/test_hostile_input.py::test_a_container_over_the_total_stops_paying_for_the_rest'],
     "a package read past what this reader takes in from one is read no further, and reading it again for lines is reading further"),

    ('line/a-walk-that-goes-wrong-gives-no-line-not-a-failed-run',
     'src/aas_submodel_validate/positions.py',
     '                except Exception:  # noqa: BLE001 - a line not found is a line not given\n                    continue\n',
     '                except ZeroDivisionError:\n                    continue\n',
     ['tests/test_every_finding_names_its_line.py::test_a_walk_that_goes_wrong_gives_no_line_and_the_run_goes_on'],
     "a line is something a finding gains; a run that dies because a walk for lines went wrong has lost every finding it made"),
])

TABLE.extend([
    ('release/the-page-is-built-into-what-the-checksums-cover',
     '.github/workflows/release.yml',
     '          python tools/build_browser.py -o dist/aas-submodel-validate.html\n',
     '          python tools/build_browser.py -o "$RUNNER_TEMP/aas-submodel-validate.html"\n',
     ['tests/test_the_release_carries_the_page.py::test_the_release_builds_the_page_into_what_it_sums_and_compares_it_with_ci'],
     "a page built anywhere but dist is one no checksum vouches for and no release attaches, and the front page points at an asset that is not there"),

    ('ci/the-round-trip-counts-what-the-release-path-sent',
     '.github/workflows/ci.yml',
     '          if [ "$count" != "6" ]; then\n            echo "the round trip returned $count files, not the 6 that went out"\n',
     '          if [ "$count" != "5" ]; then\n            echo "the round trip returned $count files, not the 6 that went out"\n',
     ['tests/test_the_release_carries_the_page.py::test_the_round_trip_expects_every_file_the_release_path_sends'],
     "the job that downloads what the release path sent counts it, and a count left behind when the release grew a file fails the commit that grew it, in CI alone"),

    ('upstream/a-folder-that-moved-is-a-move',
     'tools/upstream_moved.py',
     '        moved = [folder for folder in folders if current.get(folder) != then[folder]]\n',
     '        moved = []\n',
     ['tests/test_the_templates_upstream_are_watched.py::test_a_new_edition_is_a_move_and_says_what_arrived'],
     "a folder upstream changed after the pin is the one answer this check exists to give; read as unmoved, a new edition waits for somebody to notice it by hand"),

    ('upstream/no-answer-is-not-an-answer',
     'tools/upstream_moved.py',
     '        print("upstream did not answer: %s" % error)\n        return 2\n',
     '        print("upstream did not answer: %s" % error)\n        return 0\n',
     ['tests/test_the_templates_upstream_are_watched.py::test_a_question_upstream_does_not_answer_is_neither_answer'],
     "an outage read as nothing moved is a green week that asked nothing"),

    ('upstream/a-folder-is-cut-where-its-edition-begins',
     'tools/upstream_moved.py',
     '        folders.add("/".join(parts[:cut]))\n',
     '        folders.add("/".join(parts[:-1]))\n',
     ['tests/test_the_templates_upstream_are_watched.py::test_every_vendored_file_comes_from_a_folder_that_is_watched'],
     "a folder cut at the edition the pin chose holds that edition alone, and the next one is published beside it, where nothing looks"),

    ('upstream/the-check-runs-every-week',
     '.github/workflows/upstream.yml',
     '  schedule:\n    - cron: "17 6 * * 1"          # 06:17 UTC every Monday\n',
     '',
     ['tests/test_the_templates_upstream_are_watched.py::test_the_workflow_asks_every_week_and_when_the_pin_or_the_check_changes'],
     "without the schedule the check runs when somebody edits the pin, which is the one time nobody needs telling"),

    ('container/a-declared-name-is-read-by-the-registry-not-by-python',
     'src/aas_submodel_validate/container.py',
     '    codec = _CODEC_OF.get(name.lower())\n    if codec is None:\n',
     '    codec = _CODEC_OF.get(name.lower(), name)\n    if codec is None:\n',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_name_the_registry_does_not_give_is_refused_naming_the_one_it_does'],
     "a name Python reads and the registry does not give was read on some Pythons and not others; asked of the running Python, cp1252 is read again and one document reads two ways at two entrances"),

    ('container/unmarked-ucs4-is-known-by-its-nuls',
     'src/aas_submodel_validate/container.py',
     '    if head in _UCS4_MARKS or head.count(0) == 3:\n',
     '    if head in _UCS4_MARKS:\n',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_ucs4_and_ebcdic_are_refused_saying_which'],
     "UCS-4 without its mark, in any of its four byte orders, went on to the parser to be refused as not well-formed -- the reader's limit reported as the document's syntax"),

    ('container/ebcdic-is-known-by-its-first-bytes',
     'src/aas_submodel_validate/container.py',
     '    return "EBCDIC" if head == _EBCDIC_OPENING else None\n',
     '    return None\n',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_ucs4_and_ebcdic_are_refused_saying_which'],
     "a document in EBCDIC, whose declaration cannot be read as ASCII, was refused as not well-formed rather than as an encoding this reader does not read"),

    ('container/bytes-that-are-not-the-declared-charset-are-refused',
     'src/aas_submodel_validate/container.py',
     '        raise EncodingNotRead(\n            "the document declares %s, and the bytes on line %d are not %s: %s"',
     '        return raw\n        raise EncodingNotRead(\n            "the document declares %s, and the bytes on line %d are not %s: %s"',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_bytes_that_are_not_the_declared_charset_are_refused_where_they_are',
      'tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_utf16_bytes_that_are_not_utf16_are_refused_whatever_the_name'],
     "bytes that were not the charset declared went on undecoded to a parser that refused them as syntax; XML 1.0 makes them the fatal error, and the line they are on is where it is"),

    ('container/a-remedy-names-the-registered-charset',
     'src/aas_submodel_validate/container.py',
     '    if codec in _REGISTERED:\n        return registered_name(codec)\n',
     '    if False:\n        return registered_name(codec)\n',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_name_the_registry_does_not_give_is_refused_naming_the_one_it_does'],
     "a refusal that names no charset to declare leaves the author to find the registry's spelling of the one they meant"),

    ('container/a-remedy-reads-the-bytes-where-no-registration-names-the-charset',
     'src/aas_submodel_validate/container.py',
     '            if raw.decode(candidate) == text:\n',
     '            if False:\n',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_name_the_registry_does_not_give_is_refused_naming_the_one_it_does'],
     "cp949 has no registration of its own, and a file in it that holds only EUC-KR's characters reads the same as EUC-KR, which is the name to give it"),

    ('container/a-remedy-reads-the-registry-s-own-names-first',
     'src/aas_submodel_validate/container.py',
     '    codec = _FOLDED.get(key)\n',
     '    codec = None\n',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_name_the_registry_does_not_give_is_refused_naming_the_one_it_does'],
     "windows_31j is the registry's Windows-31J with an underscore, and CPython 3.9 has no spelling for it: without the registry's names, folded, the remedy names nothing there"),

    ('container/a-remedy-reads-the-spellings-cpython-3-9-gives',
     'src/aas_submodel_validate/container.py',
     '    codec = _SPELLED.get(key)\n',
     '    codec = None\n',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_name_the_registry_does_not_give_is_refused_naming_the_one_it_does'],
     "sjis, cp1252, cp932 and ascii are spellings no registration gives, and the remedy names their charsets only from the table CPython 3.9 wrote"),

    ('container/a-remedy-asks-no-python-that-runs-it',
     'src/aas_submodel_validate/container.py',
     '    codec = _SPELLED.get(key)\n',
     '    codec = _SPELLED.get(key) or getattr(__import__("encodings").search_function(name), "name", None)\n',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_spelling_a_later_python_adds_draws_the_remedy_it_draws_on_every_python'],
     "falling back to the running Python's own spellings is the remedy turning on which Python read the document: 3.13.15 named IBM00858 for pc_multilingual_850_euro where 3.13.2 named nothing"),

    ('container/ms-kanji-is-shift-jis',
     'src/aas_submodel_validate/container.py',
     '    "shift_jis": ("Shift_JIS", "MS_Kanji", "csShiftJIS"),\n',
     '    "shift_jis": ("Shift_JIS", "csShiftJIS"),\n',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_ms_kanji_is_shift_jis_and_not_what_python_calls_it'],
     "the registry gives MS_Kanji as Shift_JIS and Python reads it as Windows-31J; without the registry's name it is refused as unregistered, and a reader that asked Python would read NEC's extensions under it"),

    ('container/a-remembered-encoding-refusal-keeps-what-it-named',
     'src/aas_submodel_validate/container.py',
     '        if self.encoding is not None:\n',
     '        if False:\n',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_relationships_part_in_a_name_this_reader_does_not_read_is_filed_with_its_remedy'],
     "a relationships part refused for its encoding is asked again by the rules after the loader; rebuilt from its message alone the refusal raised a TypeError, and the run left by a traceback"),

    ('container/the-parser-is-handed-only-the-names-it-reads',
     'src/aas_submodel_validate/container.py',
     '_PARSER_READS = {"utf-8", "us-ascii"}\n',
     '_PARSER_READS = {"utf-8", "us-ascii", "csutf8"}\n',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_registered_name_the_parser_does_not_know_is_read_before_it_parses'],
     "csUTF8 handed to the parser as it came is a name the parser asks Python about, and no Python knows it: a relationships part declaring it stopped the run with a traceback"),

    ('container/a-utf-16-mark-holds-the-declaration-to-utf-16',
     'src/aas_submodel_validate/container.py',
     '                _held_to(raw, encoding, settled, names.__contains__,\n',
     '                _held_to(raw, encoding, settled, lambda name: True,\n',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_declaration_its_first_bytes_contradict_is_refused_as_the_parser_refuses_it'],
     "a UTF-16 byte order mark followed by a declaration of ISO-8859-1 is refused by expat and aas-core3, and was judged here"),

    ('container/a-utf-8-mark-refuses-a-declaration-of-utf-16',
     'src/aas_submodel_validate/container.py',
     '            _held_to(raw, "utf-8", "UTF-8", lambda name: name not in _UTF16_NAMES,\n',
     '            _held_to(raw, "utf-8", "UTF-8", lambda name: True,\n',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_declaration_its_first_bytes_contradict_is_refused_as_the_parser_refuses_it'],
     "a UTF-8 mark followed by a declaration of UTF-16 is the one declaration after that mark every parser refuses"),

    ('container/unmarked-utf-16-holds-the-declaration-to-its-byte-order',
     'src/aas_submodel_validate/container.py',
     '        _held_to(raw, encoding, settled, names.__contains__,\n                 "is %s by',
     '        _held_to(raw, encoding, settled, lambda name: True,\n                 "is %s by',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_declaration_its_first_bytes_contradict_is_refused_as_the_parser_refuses_it'],
     "UTF-16 with no mark, its shape plain in the first bytes, declaring ISO-8859-1 is refused by expat and was judged here"),

    ('container/ascii-s-shape-cannot-be-utf-16',
     'src/aas_submodel_validate/container.py',
     '    if name.lower() in _UTF16_NAMES:\n',
     '    if False:\n',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_declaration_its_first_bytes_contradict_is_refused_as_the_parser_refuses_it'],
     "a document whose first bytes are ASCII's cannot be in UTF-16 whatever it declares, and expat refuses the declaration as incorrect"),

    ('container/utf-16-declaring-nothing-is-refused-for-bytes-that-are-not-it',
     'src/aas_submodel_validate/container.py',
     '        if declared is None:\n            raise EncodingNotRead(\n                "the document is in %s by its first bytes',
     '        if declared is None:\n            return raw\n            raise EncodingNotRead(\n                "the document is in %s by its first bytes',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_utf16_bytes_that_are_not_utf16_are_refused_whatever_the_name'],
     "UTF-16 by its first bytes, declaring nothing, with bytes that do not decode went to the parser, which reads a surrogate with no partner inside an attribute value: the package holding one was judged"),

    ('rules/a-near-miss-of-an-alias-names-the-template-s-spelling',
     'src/aas_submodel_validate/rules/engine.py',
     '        if current is not None:\n            # Near an alias: a spelling an earlier edition gave the row, still\n',
     '        if False:\n            # Near an alias: a spelling an earlier edition gave the row, still\n',
     ['tests/test_near_miss_lints.py::test_a_near_miss_of_an_earlier_edition_s_spelling_says_so_and_names_the_template_s'],
     "a near miss of an alias said the earlier edition's spelling was what the template says, and its remedy sent the author to write it"),
])


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
    p.write_text('#!/bin/sh\nexec "%s" "$@"\n' % sys.executable, encoding="utf-8")
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


@contextlib.contextmanager
def _released_heading(tree: Path):
    """The CHANGELOG as the release commit would carry it, while a step runs.

    The tag-and-version step refuses a heading still marked `unreleased`,
    by design: a release is cut from the commit that dates it. Between
    releases the version is opened ahead of that date, so on every such
    commit that step was red before any mutation, and the row lifting it
    could be measured on the release commit alone -- CI's run of the table
    failed on it. The heading for the declared version is dated here, in
    the copy, and put back: for the same reason the tag is supplied, so
    the baseline is green by construction and what turns it red is the row.
    """
    changelog = tree / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    draft = "## %s \u2014 unreleased" % _declared_version(tree)
    if draft in text:
        changelog.write_text(text.replace(draft, draft.replace("unreleased", "2000-01-01"), 1),
                             encoding="utf-8")
    try:
        yield
    finally:
        changelog.write_text(text, encoding="utf-8")


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
            script.write_text(lift(tree, spec), encoding="utf-8")
            # The tag the workflow would see, taken from the tree being
            # measured, so the baseline is green by construction and a
            # row that breaks the agreement is what makes it red.
            with _released_heading(tree):
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


def _measured_commit(repo: Path) -> str:
    """The commit a run is about to copy, or an exit if no commit is it.

    Asked before the copy rather than after the run: the copy is what is
    measured, and a commit made while the table runs is not that tree. A
    checkout with uncommitted changes is not any commit's tree either, so
    a run that is to be recorded refuses before it starts, not ten minutes
    later.
    """
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                           cwd=repo, capture_output=True, text=True).stdout.strip()
    if dirty:
        raise SystemExit("not recorded: the checkout has uncommitted changes, so "
                         "no commit names the tree that would be measured")
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                          capture_output=True, text=True, check=True).stdout.strip()


def _record(path: Path, commit: str, killed: list, survivors: list) -> None:
    """What a run found, kept in the repository rather than in a terminal.

    Written only by a run in which every row died, naming the commit it
    copied (`_measured_commit`). `tests/test_mutation_record.py` holds it
    to the table, so a row added or dropped without a run makes the two
    disagree.
    """
    path.write_text(json.dumps({
        "_about": "The last full run of tools/mutation_table.py --run kept by "
                  "the run itself: every row it applied, which died and which "
                  "survived, the commit it measured and the Python it ran "
                  "under. CI runs the table on every commit; this is the run "
                  "a reader can see without CI.",
        "commit": commit,
        "python": platform.python_version(),
        "rows": [row[0] for row in TABLE],
        "killed": killed,
        "survived": survivors,
    }, indent=1) + "\n", encoding="utf-8")
    print("recorded in %s" % path)


TABLE.extend([
    ('release/first-paragraph-names-the-audience',
     '.github/workflows/release.yml',
     '          if not first.startswith("Who should take this release: "):',
     '          if False:',
     ['tests/test_ci_parity.py::test_release_opening_refuses_a_missing_first_paragraph'],
     'without the check, a dated entry whose first paragraph names no audience still opens '
     'the release notes with that paragraph'),

    ('docs/dated-release-opens-with-the-audience',
     'tests/test_readme_front.py',
     '            assert first.startswith("Who should take this release: "), heading',
     '            assert True, heading',
     ['tests/test_readme_front.py::test_dated_release_openings_refuse_a_missing_first_paragraph'],
     'without the assertion, a dated entry after 1.0.0 whose first paragraph names no '
     'audience passes the documentation tests, even while the newest entry is a draft'),

])


TABLE.extend([
    ('loader/declared-byte-refusal-offers-utf8-first',
     'src/aas_submodel_validate/loader.py',
     '    if refusal.kind == "bytes":\n        return ("Save the document as UTF-8 and drop the declaration, or declare the encoding "\n                "the file is in, by the name the IANA charset registry gives it. %s"\n                % REFUSED_NOT_JUDGED)\n',
     '',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_declared_byte_refusal_offers_utf8_first'],
     'a Windows code page 949 file declared as KS_C_5601-1987 and holding a character '
     'KS X 1001 does not have was asked first to declare the encoding it is in, which no '
     'registration names'),
])


TABLE.extend([
    ('loader/chain-encoding-refusal-names-the-relationships-part',
     'src/aas_submodel_validate/loader.py',
     'LoadError("chain", str(exc), line=exc.line, part=rels, subject=rels, detail=exc.detail, fix=encoding_remedy(exc))',
     'LoadError("chain", str(exc), line=exc.line, subject=rels, detail=exc.detail, fix=encoding_remedy(exc))',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_chain_encoding_refusal_names_its_relationships_part'],
     'the package and origin relationships encoding refusals carried a line with no part; naming the refused relationships part points to the same place'),

])


TABLE.extend([
    ('container/a-paired-carriage-return-ends-one-line',
     'src/aas_submodel_validate/container.py',
     '    return text.count("\\n", 0, at) + text.count("\\r", 0, at) - text.count("\\r\\n", 0, at) + 1',
     '    return text.count("\\n", 0, at) + text.count("\\r", 0, at) + 1',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_carriage_return_and_line_feed_end_one_line'],
     'a windows-1252 byte on line 3 was counted on line 5 when a paired carriage return and line feed ended two lines instead of one'),

    ('container/a-utf7-half-before-the-encoding-keeps-its-line',
     'src/aas_submodel_validate/container.py',
     '        if taken is not None and at >= taken.end(1):',
     '        if taken is not None:',
     ['tests/test_a_document_is_read_in_the_encoding_it_declares.py::test_a_utf7_half_before_the_encoding_keeps_its_line'],
     'a UTF-7 half on line 3 before the encoding in a declaration was counted on line 4 when restoring positions moved characters before the removed text too'),

    ('tools/capability-data-directory-is-the-same-folder',
     'tools/capabilities_svg.py',
     '    if not os.path.samefile(os.path.dirname(src), os.path.join(ROOT, "docs")):',
     '    if os.path.dirname(src) != os.path.join(ROOT, "docs"):',
     ['tests/test_capability_data_directory.py::test_capability_data_accepts_two_spellings_of_one_directory'],
     'NFC and NFD names for the same data folder were refused as different folders when the generator compared path text'),

])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--record", metavar="FILE",
                    help="with --run, and only when every row died: write "
                         "what the run found, with the commit it measured")
    args = ap.parse_args()
    if args.record and not args.run:
        ap.error("--record keeps what a run found, so it needs --run")
    repo = ROOT

    if not args.run:
        for row_id, rel, _old, _new, checks, why in TABLE:
            print("%s\n    %s\n    dies in: %s\n    why: %s"
                  % (row_id, rel, ", ".join(checks), why))
        print("\n%d rows, one of them the canary." % len(TABLE))
        return 0

    measured = _measured_commit(repo) if args.record else None
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

        survivors, broken, killed = [], [], []
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
                    py_compile.compile(str(tree / rel),
                                       cfile=str(tree / ".harness-compiled.pyc"),
                                       doraise=True)
                except py_compile.PyCompileError as exc:
                    uncompilable = str(exc).splitlines()[0]
            code, said = (5, None) if uncompilable else run(tree, checks)
            (tree / rel).write_text(pristine, encoding="utf-8")
            (tree / rel).touch()
            clear(tree)

            if uncompilable is not None:
                broken.append("%s: the mutant does not compile (%s) -- the "
                              "anchor omits the line that governs it, so a kill "
                              "would be a syntax error and not the behaviour"
                              % (row_id, uncompilable))
            elif code in (4, 5):
                broken.append("%s: the selection collects nothing" % row_id)
            elif code == 0 and said is not None and not _ran(said):
                broken.append("%s: the mutant asserted nothing here -- it "
                              "skipped, so the row cannot kill anything" % row_id)
            elif code == 0:
                survivors.append(row_id)
                print("  survived  %s" % row_id)
            else:
                killed.append(row_id)
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
        if args.record:
            _record(Path(args.record), measured, killed, survivors)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
