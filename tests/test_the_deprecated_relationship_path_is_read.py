"""IDTA 01005-3-0-1 reads AASX relationships under two paths.

Its section 5.2 ends "The following relationship path is deprecated:
http://www.admin-shell.io/aasx/relationships.", and its list of changes
from V3.0 says to "support both relationship paths:
http://admin-shell.io/aasx/relationships (as specified and recommended)
and (deprecated) http://www.admin-shell.io/aasx/relationships". A package
declaring any of its three relationship types under the deprecated path
is read as the same package declaring it under the recommended one.
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest

from aas_submodel_validate import runner
from builders import build_aasx, contact_env, dn_env, env_json, rels

RECOMMENDED = b"http://admin-shell.io/aasx/relationships/"
DEPRECATED = b"http://www.admin-shell.io/aasx/relationships/"
#: A path neither IDTA 01005-3-0-1 nor the one it deprecates names.
ELSEWHERE = b"http://example.com/aasx/relationships/"


def _moved(path, tmp_path, names, to=DEPRECATED):
    """The package again, with the relationship types whose last word is in
    `names` declared under the path `to` -- the deprecated one unless said."""
    out = io.BytesIO()
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(out, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.endswith(".rels"):
                for name in names:
                    data = data.replace(RECOMMENDED + name, to + name)
            zout.writestr(info, data)
    moved = tmp_path / ("moved-%s-%s.aasx" % ("-".join(name.decode() for name in names),
                                               "deprecated" if to == DEPRECATED else "elsewhere"))
    moved.write_bytes(out.getvalue())
    return moved


def _seen(report):
    return report.ok, report.submodels_seen, sorted(finding.id for finding in report.findings)


@pytest.mark.parametrize("names", [[b"aasx-origin"], [b"aas-spec"], [b"aas-suppl"],
                                   [b"aasx-origin", b"aas-spec", b"aas-suppl"]],
                         ids=["origin", "spec", "suppl", "all"])
def test_a_relationship_under_the_deprecated_path_is_followed(tmp_path, names):
    """The package declares a supplementary file it does not hold, so X4
    shows the aas-suppl relationship was followed too."""
    base = build_aasx(tmp_path / "base.aasx", env_json(), suppl_targets=["aasx/suppl/absent.pdf"])
    expected = _seen(runner.run(base))
    assert "X4" in expected[2], expected
    moved = _moved(base, tmp_path, names)
    with zipfile.ZipFile(moved) as archive:
        declared = b"".join(archive.read(name) for name in archive.namelist() if name.endswith(".rels"))
    assert all(DEPRECATED + name in declared for name in names)
    assert _seen(runner.run(moved)) == expected


def _with_parts(path, tmp_path, name, edit, parts=()):
    """The package again, its relationships parts passed through `edit`
    and `parts` added."""
    out = io.BytesIO()
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(out, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info, edit(info.filename, zin.read(info.filename)))
        for part, data in parts:
            zout.writestr(part, data)
    edited = tmp_path / name
    edited.write_bytes(out.getvalue())
    return edited


def test_an_aas_spec_relationship_under_another_path_alone_is_refused(tmp_path):
    """Only the two paths are read. An aas-spec relationship under a third
    leaves the origin with none this reader follows, and the package is
    refused as one whose origin declares none, as 1.0.2 refused one under
    the deprecated path -- not read on the strength of its last word. The
    detail lists what the origin declares by that last word alone, so it
    does not say which type it was."""
    base = build_aasx(tmp_path / "base.aasx", env_json())
    moved = _moved(base, tmp_path, [b"aas-spec"], to=ELSEWHERE)
    report = runner.run(moved)
    assert _seen(report)[1:] == (0, ["X2"]), _seen(report)
    [finding] = report.findings
    assert "declares no aas-spec relationship on its origin" in finding.violation.message
    assert finding.violation.detail == "aasx/_rels/aasx-origin.rels declares 1 relationship: aas-spec", \
        finding.violation.detail


def test_an_aas_spec_relationship_under_another_path_beside_a_followed_one_is_passed_over(tmp_path):
    """Beside one this reader follows, an aas-spec relationship under a
    third path is passed over rather than refused: the part it names is not
    read, and the package is judged on the other."""
    base = build_aasx(tmp_path / "base.aasx", json.dumps(contact_env()).encode("utf-8"))
    second = json.dumps(dn_env()).encode("utf-8")

    def edit(name, data, prefix):
        if name != "aasx/_rels/aasx-origin.rels":
            return data
        extra = b'<Relationship Type="' + prefix + b'aas-spec" Target="/aasx/second.json" Id="Rsecond"/>'
        return data.replace(b"</Relationships>", extra + b"</Relationships>")
    elsewhere = _with_parts(base, tmp_path, "elsewhere.aasx", lambda n, d: edit(n, d, ELSEWHERE),
                            [("aasx/second.json", second)])
    both = _with_parts(base, tmp_path, "both.aasx", lambda n, d: edit(n, d, DEPRECATED),
                       [("aasx/second.json", second)])
    assert _seen(runner.run(elsewhere)) == _seen(runner.run(base)), _seen(runner.run(elsewhere))
    report = runner.run(both)
    assert report.submodels_seen == 2 and "DN-D2" in _seen(report)[2], _seen(report)


def test_an_aas_suppl_relationship_under_another_path_is_not_followed(tmp_path):
    """The package declares a supplementary file it does not hold. Under the
    recommended or the deprecated path that is X4; under a third the
    relationship is not followed, and nothing is said of the file."""
    base = build_aasx(tmp_path / "base.aasx", env_json(), suppl_targets=["aasx/suppl/absent.pdf"])
    assert "X4" in _seen(runner.run(base))[2]
    assert "X4" in _seen(runner.run(_moved(base, tmp_path, [b"aas-suppl"])))[2]
    assert "X4" not in _seen(runner.run(_moved(base, tmp_path, [b"aas-suppl"], to=ELSEWHERE)))[2]


@pytest.mark.parametrize("order", ["deprecated-first", "recommended-first"])
def test_an_origin_declared_under_both_paths_is_read_by_the_first(tmp_path, order):
    """IDTA 01005-3-0-1 gives a package one aasx-origin. One that declares
    an origin under each path is read by the first it declares -- 1.0.2,
    which followed the recommended path alone, read that one wherever it
    stood. The origin under the deprecated path is the one the package
    holds; the other names a part it does not."""
    base = build_aasx(tmp_path / "base.aasx", json.dumps(contact_env()).encode("utf-8"))
    pairs = [((DEPRECATED + b"aasx-origin").decode(), "/aasx/aasx-origin"),
             ((RECOMMENDED + b"aasx-origin").decode(), "/aasx/absent-origin")]
    if order == "recommended-first":
        pairs.reverse()
    both = _with_parts(base, tmp_path, "%s.aasx" % order,
                       lambda n, d: rels(pairs) if n == "_rels/.rels" else d)
    seen = _seen(runner.run(both))
    if order == "deprecated-first":
        assert seen == _seen(runner.run(base)), seen
    else:
        assert seen[1:] == (0, ["X2"]), seen

