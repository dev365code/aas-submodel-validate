"""The OPC chain, verified link by link.

An .aasx is not "a ZIP with files in it": the payload is found by
following relationships, and a container whose chain is broken has no
payload however plausible its entry names look. Every test that breaks a
link expects a refusal that names the missing link.
"""
from __future__ import annotations

import pytest

from aas_submodel_validate.container import AasxPackage, ContainerError, PartTooLarge
from builders import build_aasx, env_json


def test_a_wellformed_container_resolves_its_chain(tmp_path):
    packed = build_aasx(tmp_path / "ok.aasx", payload=b'{"submodels": []}')
    with AasxPackage(packed) as package:
        assert package.origin == "aasx/aasx-origin"
        assert package.spec_parts == ["aasx/env.json"]
        assert package.read("aasx/env.json") == b'{"submodels": []}'


def test_real_world_rels_carry_a_byte_order_mark(tmp_path):
    """The official IDTA example writes its .rels files with a UTF-8 BOM;
    a reader that chokes on it rejects the reference material."""
    packed = build_aasx(tmp_path / "bom.aasx", bom=True)
    with AasxPackage(packed) as package:
        assert package.spec_parts == ["aasx/env.json"]


def test_not_a_zip_is_refused(tmp_path):
    path = tmp_path / "no.aasx"
    path.write_bytes(b"PK is just how it starts, this is not one")
    with pytest.raises(ContainerError, match="ZIP"):
        AasxPackage(path)


def test_a_missing_package_rels_names_the_missing_link(tmp_path):
    packed = build_aasx(tmp_path / "x.aasx", root_rels=False)
    with AasxPackage(packed) as package, pytest.raises(ContainerError, match="_rels/.rels"):
        _ = package.origin


def test_missing_relationships_of_a_part_name_that_part(tmp_path):
    """The package's own relationships were the only set any test
    removed, so the refusal was only ever read saying "the chain from
    the package root goes nowhere" -- which it would also have said,
    wrongly, for every part. A reader sent to the package root looks at
    `_rels/.rels`, which is fine, instead of the part whose set is
    missing."""
    packed = build_aasx(tmp_path / "x.aasx", origin_rels=False)
    with AasxPackage(packed) as package, pytest.raises(
            ContainerError, match="the chain from 'aasx/aasx-origin' goes nowhere"):
        _ = package.spec_parts


def test_the_origin_is_found_wherever_it_sits_among_the_package_relationships(tmp_path):
    """`_rels/.rels` carries more than the origin -- tools write the
    thumbnail and the core properties there -- and OPC gives
    relationships no order. The origin is the one of its type. Every
    archive the builder wrote declared it alone, so answering with the
    first relationship, whatever its type, passed the whole suite."""
    thumbnail = ("http://schemas.openxmlformats.org/package/2006/"
                 "relationships/metadata/thumbnail", "/thumbnail.png")
    packed = build_aasx(tmp_path / "t.aasx", root_first=[thumbnail])
    with AasxPackage(packed) as package:
        assert package.origin == "aasx/aasx-origin"
        assert package.spec_parts == ["aasx/env.json"]


def test_a_missing_origin_relationship_names_the_relationship(tmp_path):
    packed = build_aasx(tmp_path / "x.aasx", origin_rel=False)
    with AasxPackage(packed) as package, pytest.raises(ContainerError, match="aasx-origin"):
        _ = package.origin


def test_a_missing_spec_relationship_names_the_relationship(tmp_path):
    packed = build_aasx(tmp_path / "x.aasx", spec_rel=False)
    with AasxPackage(packed) as package, pytest.raises(ContainerError, match="aas-spec"):
        _ = package.spec_parts


def test_a_spec_target_that_does_not_exist_is_reported(tmp_path):
    packed = build_aasx(tmp_path / "x.aasx", payload_name="aasx/env.json")
    import zipfile

    rewritten = tmp_path / "gone.aasx"
    with zipfile.ZipFile(packed) as src, zipfile.ZipFile(rewritten, "w") as dst:
        for name in src.namelist():
            if name != "aasx/env.json":
                dst.writestr(name, src.read(name))
    with AasxPackage(rewritten) as package, pytest.raises(ContainerError, match="env.json"):
        package.read(package.spec_parts[0])


def test_a_relationship_target_without_a_slash_resolves_against_its_part(tmp_path):
    """OPC resolves a target that begins with "/" against the package
    root and any other target against the directory of the part whose
    relationships it is (docs/divergences.md #13). That reading is why
    this reader accepts conformant packages other tools reject -- and
    until now no test had ever exercised the branch that does it.

    Written before touching that code, not after: a branch nothing
    watches is a branch a refactor may quietly change.
    """
    path = build_aasx(tmp_path / "rel.aasx", payload=env_json(),
                      files=[("aasx/files/manual.pdf", b"%PDF-1.4 ")],
                      relative_targets=True)
    with AasxPackage(path) as package:
        assert package.origin == "aasx/aasx-origin"
        assert package.spec_parts == ["aasx/env.json"]
        suppl = [target for _type, target, _external in package.relationships("aasx/env.json")]
        assert suppl == ["aasx/files/manual.pdf"]


def test_a_target_wearing_whitespace_reaches_the_part_it_names(tmp_path):
    """Which side the whitespace falls on used to decide the answer.

    `startswith("/")` is false for `" /aasx/…"`, so a target whose only
    defect was a leading space took the relative branch and was joined
    into `aasx/ /aasx/…` -- a string naming nothing -- and `X4` reported
    the archive as not holding a part sitting in it. The same target with
    the space on the *other* end took the absolute branch and resolved.
    One package, two answers, separated by nothing a reader would think
    mattered.

    Measured before this was written: with that branch removed the whole
    suite still passed, so the repair existed and nothing watched it. And
    the first version of this test passed with the branch removed too --
    it declared its targets through the helper that prepends a slash, so
    the archive never held the shape the branch is for, and `part`'s own
    stripping answered instead. The targets are written verbatim now, and
    the asymmetry is asserted rather than the repair: a trailing space
    resolves by a different route and has to keep doing so.
    """
    holds = "aasx/files/manual.pdf"
    for target in (" files/manual.pdf",          # leading, relative
                   " /aasx/files/manual.pdf",    # leading, absolute
                   "  files/manual.pdf  ",       # both sides
                   "files/manual.pdf "):         # trailing: the mirror
        path = build_aasx(tmp_path / ("w%d.aasx" % len(target)),
                          payload=env_json(), files=[(holds, b"%PDF-1.4 ")],
                          suppl_targets=[], suppl_verbatim=[target])
        with AasxPackage(path) as package:
            reached = [name for _type, name, _external
                       in package.relationships("aasx/env.json")]
        assert reached == [holds], (
            "a target spelled %r reached %s instead of the part it names"
            % (target, reached))


def test_an_entry_whose_name_holds_a_space_stays_reachable(tmp_path):
    """The stripped reading is asked second, and this is what that buys.

    An archive may genuinely hold an entry whose name carries whitespace.
    A target spelling it exactly must reach *that* entry -- if the
    stripped reading were tried first, or tried at all when the literal
    already matched, the target would be answered with a different part
    and the one it names would be unreachable. That is
    `docs/divergences.md` #18 one layer out, which is why the repair for
    the leading-space case is ordered behind the literal attempt rather
    than in front of it.

    Measured: with `name is None` dropped from that condition -- so the
    stripped reading runs even when the literal found something -- this
    goes red and the leading-space test above does not.
    """
    holds = "aasx/files/manual.pdf "          # the archive really holds the space
    other = "aasx/files/manual.pdf"
    path = build_aasx(tmp_path / "held.aasx", payload=env_json(),
                      files=[(holds, b"%PDF-1.4 with space"),
                             (other, b"%PDF-1.4 without")],
                      suppl_targets=[], suppl_verbatim=["/" + holds])
    with AasxPackage(path) as package:
        reached = [name for _type, name, _external
                   in package.relationships("aasx/env.json")]
    assert reached == [holds], (
        "the target spells the entry the archive holds; it reached %s"
        % reached)


@pytest.mark.parametrize("outside", [
    {"suppl_external": ["http://example.com/manual.pdf"]},     # TargetMode="External"
    {"suppl_verbatim": ["http://example.com/manual.pdf"]},     # a scheme, no mode
], ids=["declared", "undeclared"])
def test_a_target_outside_the_package_does_not_hide_the_ones_after_it(tmp_path, outside):
    """A target outside the package is passed back as written, and the
    relationships after it are still read.

    Measured before this was written: with that step turned into the end of
    the loop, the whole suite still passed. Every archive the builder wrote
    put the package's own parts first, so stopping at the first outside
    target lost nothing a test could see. A supplier's file has no such
    order, and then every part declared after that target goes unread --
    X4 asks the archive about none of them, so one that is missing is never
    reported.
    """
    holds = "aasx/files/manual.pdf"
    path = build_aasx(tmp_path / "order.aasx", payload=env_json(),
                      files=[(holds, b"%PDF-1.4 ")], outside_first=True, **outside)
    with AasxPackage(path) as package:
        reached = [name for _type, name, _external
                   in package.relationships("aasx/env.json")]
    assert reached == ["http://example.com/manual.pdf", holds], (
        "the part declared after an outside target was not read: %s" % reached)


def test_both_spellings_of_a_relationship_reach_the_same_parts(tmp_path):
    """Absolute and relative are two ways of writing one package, so they
    have to produce one answer."""
    payload, parts = env_json(), [("aasx/files/manual.pdf", b"%PDF-1.4 ")]
    absolute = build_aasx(tmp_path / "abs.aasx", payload=payload, files=parts)
    relative = build_aasx(tmp_path / "rel.aasx", payload=payload, files=parts,
                          relative_targets=True)
    with AasxPackage(absolute) as a, AasxPackage(relative) as b:
        assert a.spec_parts == b.spec_parts
        assert a.relationships("aasx/env.json") == b.relationships("aasx/env.json")


def test_a_part_read_twice_counts_once(tmp_path, monkeypatch):
    """The total the container refuses on is distinct bytes handed out,
    not reads. X4 re-walks the chain a second rule already walked, and
    counting those bytes twice made the refusal depend on which rule
    happened to cross the line first -- a container passing or failing by
    rule registration order.

    the changelog records that repair; nothing tested it. Removing the
    `_counted` guard left the whole suite green, so the cap is lowered
    here instead of the archive being made enormous: the same part read
    twice must not refuse, and a *different* part of the same size must.
    """
    from aas_submodel_validate import container as container_module

    blob = b"x" * 40_000
    packed = build_aasx(tmp_path / "p.aasx",
                        files=[("aasx/a.bin", blob), ("aasx/b.bin", blob)])
    monkeypatch.setattr(container_module, "MAX_TOTAL_PART_BYTES", 60_000)
    with AasxPackage(packed) as package:
        assert package.read("aasx/a.bin") == blob
        assert package.read("aasx/a.bin") == blob
        with pytest.raises(PartTooLarge, match="together"):
            package.read("aasx/b.bin")
