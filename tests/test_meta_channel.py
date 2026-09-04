"""The metamodel layer is relayed, never re-implemented.

aas-core3.0's verification runs inside every validation and reports
through the `meta` channel: warnings by default (the official published
example itself carries 77), errors under --strict-meta. This project's
own rules never restate an AASd constraint -- one defect, one voice.
"""
from __future__ import annotations

import copy
import json

from aas_submodel_validate import runner
from aas_submodel_validate.model import Severity
from builders import hd_env


def _run(tmp_path, env, **kwargs):
    path = tmp_path / "env.json"
    path.write_bytes(json.dumps(env).encode("utf-8"))
    return runner.run(path, **kwargs)


def _broken(env):
    """An AASd-120 violation: an idShort on a list child."""
    env["submodels"][0]["submodelElements"][0]["value"][0]["idShort"] = "Datasheet"
    return env


def test_the_golden_fixture_is_metamodel_clean_too(tmp_path):
    assert _run(tmp_path, hd_env()).findings == []


def test_metamodel_defects_arrive_as_warnings(tmp_path):
    report = _run(tmp_path, _broken(copy.deepcopy(hd_env())))
    meta = [f for f in report.findings if f.id == "META"]
    assert meta and all(f.severity is Severity.WARNING for f in meta)
    assert "AASd-120" in meta[0].violation.message
    assert report.ok  # warnings alone do not fail a run


def test_strict_meta_promotes_them_to_errors(tmp_path):
    report = _run(tmp_path, _broken(copy.deepcopy(hd_env())), strict_meta=True)
    meta = [f for f in report.findings if f.id == "META"]
    assert meta and all(f.severity is Severity.ERROR for f in meta)
    assert not report.ok


def test_every_environment_in_a_container_is_verified_not_only_the_last(tmp_path):
    """An AASX may declare more than one aas-spec part, and the relayed
    channel saw one of them.

    `loaded.environment` was assigned per part and read once, so the
    metamodel findings of every part but the last vanished -- with
    `complete: true` and `submodelsSeen` counting them all, because the
    template rules did walk them. Nothing in the report said anything
    had been skipped, which is the one failure this project refuses:
    silence about a file that is not conformant.

    Measured with the same violation planted on each side in turn: last
    part, one finding; first part, none.
    """
    import copy
    import json
    import zipfile

    from builders import CONTENT_TYPES, ORIGIN_REL, SPEC_REL, hd_env, rels

    def container(path, bad_first):
        first, second = copy.deepcopy(hd_env()), copy.deepcopy(hd_env())
        first["submodels"][0]["id"] = "urn:one"
        second["submodels"][0]["id"] = "urn:two"
        (first if bad_first else second)["submodels"][0]["displayName"] = [
            {"language": "en", "text": "x"}, {"language": "en", "text": "y"}]
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", CONTENT_TYPES)
            archive.writestr("_rels/.rels", rels([(ORIGIN_REL, "/aasx/aasx-origin")]))
            archive.writestr("aasx/aasx-origin", b"")
            archive.writestr("aasx/_rels/aasx-origin.rels",
                             rels([(SPEC_REL, "/aasx/a.json"),
                                   (SPEC_REL, "/aasx/b.json")]))
            archive.writestr("aasx/a.json", json.dumps(first))
            archive.writestr("aasx/b.json", json.dumps(second))
        return path

    seen = []
    for bad_first in (True, False):
        report = runner.run(container(tmp_path / "multi.aasx", bad_first))
        assert report.submodels_seen == 2
        relayed = [f for f in report.findings if f.rule.kind == "meta"]
        seen.append(len(relayed))
    assert seen == [1, 1], \
        "the same violation reported %s findings depending on which part " \
        "of the container it was in" % (seen,)
