"""X rules: every stage of a broken way in has one voice."""
from aas_submodel_validate import runner
from builders import build_aasx, env_json


def _ids(path):
    return {f.id for f in runner.run(path).findings}


def test_a_clean_container_raises_no_x_findings(tmp_path):
    packed = build_aasx(tmp_path / "ok.aasx", payload=env_json())
    assert not {x for x in _ids(packed) if x.startswith("X")}


def test_not_a_zip_is_x1(tmp_path):
    path = tmp_path / "no.aasx"
    path.write_bytes(b"junk")
    assert "X1" in _ids(path)


def test_a_broken_chain_is_x2(tmp_path):
    assert "X2" in _ids(build_aasx(tmp_path / "x.aasx", origin_rel=False))


def test_an_unparsable_payload_is_x3_and_names_the_part(tmp_path):
    packed = build_aasx(tmp_path / "x.aasx", payload=b"<not xml", payload_name="aasx/env.xml")
    findings = {f.id: f for f in runner.run(packed).findings}
    assert findings["X3"].violation.subject == "aasx/env.xml"
