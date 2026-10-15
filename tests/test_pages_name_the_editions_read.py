"""A page that names a pack with an edition names the edition this build reads.

The template pin moved in 0.12.0, and sentences on four pages went on
naming the editions read before it -- "02011 ... 1.1.1 is a tree", "the
IDTA 02004 Handover Documentation template, version 2.0.1" -- each a
number typed by hand that nothing read. The edition is the directory the
template is vendored in (`data/smt/<number>/<edition>/`), so a sentence
of the shape "IDTA 02011 Hierarchical Structures 1.1.2" or "02004
version 2.0.2" is held to that directory. A sentence about an earlier
edition says so in other words ("first vendored at 1.0.1", "1.0 gave",
"the 1.1.1 edition") and is not this test's business.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "tools" / "vendor_template.py").exists():
    pytest.skip("no tools/ here (installed package, not a checkout)",
                allow_module_level=True)
sys.path.insert(0, str(ROOT / "tools"))

import vendor_template  # noqa: E402

#: The pages a reader is sent to. CHANGELOG.md is history, and names the
#: editions each release read; docs/capabilities.md and
#: docs/official-samples.md are generated from what is vendored.
PAGES = ("README.md", "THIRD_PARTY.md", "SECURITY.md", "SUPPORT.md",
         "CONTRIBUTING.md", "docs/scope.md", "docs/what-it-catches.md",
         "docs/divergences.md", "docs/report-schema.md")

VENDORED = re.compile(r"src/aas_submodel_validate/data/smt/([^/]+)/([^/]+)/template\.json")
EDITION = r"(\d+(?:\.\d+)+)(?!\d|\.\d)"


def _titles(source):
    """Upstream's folder names for a template, as a page may write them.

    `published/Digital Battery Passport/2_Handover Documentation/1/1/...`
    is "Handover Documentation" and "Digital Battery Passport part 2";
    a table cell shortens a title to its first words, so every leading
    run of two or more words counts too."""
    folders = [part for part in source.split("/")[1:-1] if not part.isdigit()]
    names = []
    for folder in folders:
        part = re.fullmatch(r"(\d+)_(.+)", folder)
        if part:
            names.append(part.group(2))
            names += ["%s part %s" % (folders[0], part.group(1)),
                      "%s, part %s" % (folders[0], part.group(1))]
        elif len(folders) == 1:
            names.append(folder.replace("_", " "))
    titles = set()
    for name in names:
        words = name.split()
        titles.update(" ".join(words[:n]) for n in range(2, len(words) + 1))
    return sorted(titles, key=len, reverse=True)


def _packs():
    """{number: (edition, titles)} for every vendored template."""
    packs = {}
    for local, source in vendor_template.FILES.items():
        found = VENDORED.fullmatch(local)
        if found:
            packs[found.group(1)] = (found.group(2), _titles(source))
    return packs


def _named(text, number, titles):
    """(suffix, edition, words) for each place `text` names `number` with
    an edition: after its title, or after the word "version"."""
    lead = r"\b%s((?:-\d+)*)\s+" % re.escape(number)
    title = r"(?:%s)\s+(?:template,?\s+)?(?:version\s+)?" % "|".join(
        re.escape(t) for t in titles)
    for shape in (lead + title + EDITION, lead + r"version\s+" + EDITION):
        for found in re.finditer(shape, text, re.IGNORECASE):
            yield found.group(1), found.group(2), found.group(0)


def _page(name):
    return " ".join((ROOT / name).read_text(encoding="utf-8").replace("*", "").split())


def test_every_vendored_template_is_seen_on_the_front_page():
    """The README's table names all of them with their editions; if this
    reader stops finding them there, the test below is reading nothing."""
    readme = _page("README.md")
    packs = _packs()
    assert len(packs) == len(list((ROOT / "src/aas_submodel_validate/data/smt").glob("*/*/template.json")))
    unseen = [number for number, (_, titles) in packs.items()
              if not any(True for _ in _named(readme, number, titles))]
    assert not unseen, unseen


def test_a_page_naming_a_pack_with_an_edition_names_the_one_vendored():
    wrong = []
    for name in PAGES:
        if not (ROOT / name).exists():
            continue
        text = _page(name)
        for number, (edition, titles) in _packs().items():
            for suffix, said, words in _named(text, number, titles):
                if said != edition:
                    wrong.append("%s: %r names %s, and %s is vendored" % (name, words, said, edition))
                elif suffix and suffix.lstrip("-").split("-") != edition.split("."):
                    wrong.append("%s: %r carries an edition in its number that is not %s"
                                 % (name, words, edition))
    assert not wrong, "\n".join(wrong)


def test_the_divergences_page_names_every_template_it_records_readings_of():
    """Its first sentence lists whose readings it records, and stopped at
    the eight packs it had when the battery parts arrived -- while rows
    #58 to #62 recorded readings of four more."""
    first = _page("docs/divergences.md").split(" Non-empty on day one", 1)[0]
    missing = [number for number in _packs() if "IDTA %s" % number not in first]
    assert not missing, missing
