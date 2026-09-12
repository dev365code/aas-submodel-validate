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
