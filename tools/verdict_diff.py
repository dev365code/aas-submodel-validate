#!/usr/bin/env python3
"""Which verdicts moved since a released version, measured.

A release note's most consequential sentence is the one about what a
reader's pipeline will do differently, and it is the sentence hardest to
write by hand: the author knows what they changed, not what moved. Those
are different lists. A repair aimed at one shape moves four; a shape
named as newly-strict turns out to be judged exactly as before; and the
movements that matter most to a pipeline are the ones going the quiet
way -- a finding in the old version and silence in the new -- because
nothing downstream will notice them.

This runs the released version and the working tree over the same inputs
and prints what came out differently. The list it prints is the list the
CHANGELOG has to describe.

Nothing here is a gate: it reports, and a person decides which movements
are intended. It reads the old version out of git (`git archive`) rather
than an install, so it never depends on what happens to be on the
machine, and it runs each version in its own process, because two
versions of one package cannot share an interpreter.

    python tools/verdict_diff.py                 # against the latest tag
    python tools/verdict_diff.py --against v0.1.0
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "src/aas_submodel_validate/data/example/idta-02004-2.0.aasx"
TEMPLATES = sorted((ROOT / "src/aas_submodel_validate/data/smt").rglob("template.json"))


# -- the corpus ------------------------------------------------------------
#
# Every entry is a file on disk, built here rather than committed: an
# input that only exists to be judged twice is a fixture nobody would
# maintain, and one that goes stale reports "nothing moved" forever.
#
# Coverage is the honest limit of this tool and the reason it prints its
# own denominator. It cannot enumerate every shape a File value can
# take; what it can do is put the shapes this project has actually been
# wrong about through both versions, so a claim in the CHANGELOG is
# measured rather than believed.

FILE_VALUES = [
    "aasx/files/manual.pdf",            # the plain case, as a control
    "/aasx/files/manual.pdf",
    " aasx/files/manual.pdf ",
    "aasx/files/manual.pdf\n",
    "urn:iso:std:iso:1234",
    "mailto:docs@example.com",
    "data:application/pdf;base64,AAA=",
    "URN:ISO:STD:ISO:1234",
    "rev2:manual.pdf",
    "C:\\docs\\manual.pdf",
    "files/a://absent.pdf",
    "../outside.pdf",
    " ../outside.pdf ",
    "",
    "   ",
    "aasx/files/absent.pdf",
]

LANGUAGE_FOLDS = [("upper", str.upper), ("title", str.title), ("lower", str.lower)]
DECLARED_ENCODINGS = ["utf-8", "iso-8859-1", "windows-1252", "utf-16", "us-ascii"]


def _members(path):
    with zipfile.ZipFile(path) as archive:
        return [(item.filename, archive.read(item.filename))
                for item in archive.infolist()]


def _payload_of(members):
    candidates = [(name, data) for name, data in members
                  if name.endswith(".xml") and "_rels/" not in name
                  and not name.startswith("[")]
    return max(candidates, key=lambda pair: len(pair[1]))[0]


def _write(dest, members):
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members:
            archive.writestr(name, data)
    return dest


def _rewrite_payload(members, change):
    payload = _payload_of(members)
    return [(name, change(data) if name == payload else data)
            for name, data in members]


def build_corpus(into: Path):
    """(label, path) for everything both versions will be asked about."""
    cases = [("the official example, untouched", EXAMPLE)]

    for template in TEMPLATES:
        rel = template.relative_to(ROOT / "src/aas_submodel_validate/data/smt")
        cases.append(("the vendored template %s" % rel.parent, template))

    base = _members(EXAMPLE)

    for name, fold in LANGUAGE_FOLDS:
        def change(data, fold=fold):
            text = data.decode("utf-8-sig")
            return re.sub(r"<language>([^<]*)</language>",
                          lambda m: "<language>%s</language>" % fold(m.group(1)),
                          text).encode("utf-8")
        cases.append(("language tags in %s case" % name,
                      _write(into / ("lang-%s.aasx" % name),
                             _rewrite_payload(base, change))))

    for encoding in DECLARED_ENCODINGS:
        def change(data, encoding=encoding):
            text = data.decode("utf-8-sig")
            text = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", text)
            text = '<?xml version="1.0" encoding="%s"?>\n' % encoding + text
            return text.encode(encoding, "xmlcharrefreplace")
        cases.append(("the payload declares %s" % encoding,
                      _write(into / ("enc-%s.aasx" % encoding),
                             _rewrite_payload(base, change))))

    # A File value is where the most verdicts moved, so each shape gets
    # its own container rather than sharing one: two shapes in one file
    # produce one verdict and hide each other.
    sys.path.insert(0, str(ROOT / "tests"))
    from builders import build_aasx, hd_env  # noqa: E402
    for index, value in enumerate(FILE_VALUES):
        environment = hd_env()
        version = environment["submodels"][0]["submodelElements"][0]["value"][0]["value"][2]["value"][0]
        files = version["value"][-1]
        assert files["idShort"] == "DigitalFiles", files["idShort"]
        files["value"][0]["value"] = value
        cases.append(("a File value of %r" % value,
                      build_aasx(into / ("file-%02d.aasx" % index),
                                 payload=json.dumps(environment).encode("utf-8"),
                                 files=[("aasx/files/manual.pdf", b"%PDF-1.4 ")])))

    # And the shapes an aas-suppl relationship's target takes. The last
    # is the question the rule exists for and must not move; without it
    # the three above are equally satisfied by a rule switched off.
    payload = json.dumps(hd_env()).encode("utf-8")
    for label, kwargs in [
            ("external, absolute", {"suppl_external": ["http://example.com/m.pdf"]}),
            ("external, relative", {"suppl_external": ["../docs/m.pdf"]}),
            ("an absolute URI, no TargetMode",
             {"suppl_verbatim": ["http://example.com/m.pdf"]}),
            ("a part the archive does not hold",
             {"suppl_targets": ["aasx/files/absent.pdf"]})]:
        cases.append(("an aas-suppl relationship: %s" % label,
                      build_aasx(into / ("suppl-%d.aasx" % len(cases)),
                                 payload=payload, **kwargs)))
    return cases


# -- running both versions --------------------------------------------------

def _judge(src: Path, target: Path):
    """One version's verdict on one input: ids, severities and exit code."""
    run = subprocess.run(
        [sys.executable, "-m", "aas_submodel_validate", str(target), "-f", "json"],
        capture_output=True, text=True,
        env={"PYTHONPATH": str(src), "PATH": "/usr/bin:/bin",
             "PYTHONIOENCODING": "utf-8"})
    try:
        report = json.loads(run.stdout)
    except ValueError:
        return ("did not produce a report", run.returncode)
    findings = sorted(
        (f.get("rule"), f.get("severity")) for f in report.get("findings", []))
    ours = [f for f in findings if f[0] != "META"]
    relayed = len(findings) - len(ours)
    return (tuple(ours), relayed, run.returncode)


def _describe(verdict):
    if len(verdict) == 2:
        return "%s (exit %d)" % verdict
    ours, relayed, code = verdict
    counts = {}
    for _rule, severity in ours:
        counts[severity] = counts.get(severity, 0) + 1
    parts = ["%d %s" % (counts[k], k) for k in ("error", "warning", "info")
             if k in counts] or ["nothing"]
    return "%s, %d relayed (exit %d)" % (", ".join(parts), relayed, code)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--against", default=None,
                        help="the tag to compare with (default: the latest)")
    args = parser.parse_args(argv)

    tag = args.against
    if tag is None:
        tags = subprocess.run(["git", "-C", str(ROOT), "tag", "--sort=-v:refname"],
                              capture_output=True, text=True, check=True)
        tag = tags.stdout.split("\n", 1)[0].strip()
        if not tag:
            sys.exit("no tag to compare against; pass --against")

    workspace = Path(tempfile.mkdtemp(prefix="verdict-diff-"))
    try:
        old = workspace / "old"
        old.mkdir()
        archive = subprocess.run(["git", "-C", str(ROOT), "archive", tag],
                                 capture_output=True, check=True)
        subprocess.run(["tar", "-x", "-C", str(old)], input=archive.stdout, check=True)

        corpus = build_corpus(workspace)
        print("%s -> working tree, over %d inputs\n" % (tag, len(corpus)))

        moved = 0
        for label, target in corpus:
            before = _judge(old / "src", Path(target))
            after = _judge(ROOT / "src", Path(target))
            if before == after:
                continue
            moved += 1
            print("  %s" % label)
            print("      %-14s %s" % (tag, _describe(before)))
            print("      %-14s %s" % ("working tree", _describe(after)))
            if len(before) == 3 and len(after) == 3:
                gone = sorted(set(before[0]) - set(after[0]))
                new = sorted(set(after[0]) - set(before[0]))
                if gone:
                    print("      no longer drawn: %s" % ", ".join(r for r, _ in gone))
                if new:
                    print("      newly drawn:     %s" % ", ".join(r for r, _ in new))
            print()

        print("%d of %d inputs are judged differently." % (moved, len(corpus)))
        print("Every one of them belongs in the CHANGELOG, and the ones whose "
              "exit code falls belong there twice: a pipeline that is red on "
              "them today goes quiet, and nothing downstream reports that.")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    main()
