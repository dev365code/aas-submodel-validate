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
import zipfile

import pytest

from aas_submodel_validate import runner
from builders import build_aasx, env_json

RECOMMENDED = b"http://admin-shell.io/aasx/relationships/"
DEPRECATED = b"http://www.admin-shell.io/aasx/relationships/"


def _moved(path, tmp_path, names):
    """The package again, with the relationship types whose last word is in
    `names` declared under the deprecated path."""
    out = io.BytesIO()
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(out, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.endswith(".rels"):
                for name in names:
                    data = data.replace(RECOMMENDED + name, DEPRECATED + name)
            zout.writestr(info, data)
    moved = tmp_path / ("moved-%s.aasx" % "-".join(name.decode() for name in names))
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
