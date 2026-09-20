"""A table generated at run time is the table the build generated.

The mode being built reads a template a caller supplies and judges
against it. The owner's condition is that every entrance gives the same
verdict, and the strongest form of that is this: given the same template
file, the table built now and the table checked in must be the same
table. If they can differ, the free engine and the vendored packs are
two readers wearing one name.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

from aas_submodel_validate import tablegen

# The emitter, for its pack list only. The settings are read from where
# the build declares them rather than copied here: a second copy is a
# second thing to keep in step, and what this file is for is that the
# two paths do not drift.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import extract_smt_rules as tool  # noqa: E402 - the path is set above

#: Every pack the build renders, taken from the build's own list rather
#: than chosen here. Three were picked by hand first and all three had at
#: most one supplemental identifier, so an injected drift in how those are
#: ordered was invisible -- measured. 02035-2 declares two and is the one
#: that shows it. Picking which templates to compare is the kind of
#: judgement that turns a gate into a sample.
PACKS = tuple(
    (pack["output"].name.replace("_tables.py", ""), pack) for pack in tool.PACKS)


def _module_for(pack):
    import importlib

    return importlib.import_module(
        "aas_submodel_validate.rules." + pack["output"].name[:-len(".py")])


@pytest.mark.parametrize("where,pack", PACKS, ids=[p[0] for p in PACKS])
def test_a_table_built_now_matches_the_one_the_build_wrote(where, pack):
    module = _module_for(pack)
    document = json.loads(pack["template"].read_text("utf-8-sig"))
    built = tablegen.table_from(document, pack)

    assert built.ROWS == module.ROWS, (
        "%s: the run-time table has %d rows and the checked-in one has %d"
        % (where, len(built.ROWS), len(module.ROWS)))
    assert built.TREE == module.TREE
    assert built.BY_ID == module.BY_ID
    assert built.BY_LABEL == module.BY_LABEL
    assert built.TEMPLATE_SEMANTIC_ID == module.TEMPLATE_SEMANTIC_ID
    assert built.TEMPLATE_SUBMODEL_SID_TYPE == module.TEMPLATE_SUBMODEL_SID_TYPE
    assert (built.TEMPLATE_SUPPLEMENTAL_SEMANTIC_IDS
            == module.TEMPLATE_SUPPLEMENTAL_SEMANTIC_IDS)


def test_a_run_time_table_wears_every_name_a_generated_one_does():
    """Derived from a generated module rather than listed here, so a
    name added to the generator is a name this has to grow."""
    _where, pack = PACKS[0]
    module = _module_for(pack)
    expected = {name for name in vars(module)
                if name.isupper() and not name.startswith("_")}
    assert expected, "the generated module exposes nothing"

    built = tablegen.table_from(
        json.loads(pack["template"].read_text("utf-8-sig")), pack)
    missing = sorted(name for name in expected if not hasattr(built, name))
    assert not missing, "a run-time table is missing %s" % missing
    assert isinstance(getattr(built, "__name__", None), str), \
        "the walk reads `tables.__name__` to key its cache"


def test_the_walk_accepts_a_table_that_is_not_a_module(tmp_path):
    """And the engine takes it, which is the only thing that makes the
    two paths one engine rather than two readers."""
    from aas_submodel_validate import runner
    from aas_submodel_validate.rules import engine, profiles

    pack = next(p for _w, p in PACKS if p["output"].name == "td_tables.py")
    built = tablegen.table_from(
        json.loads(pack["template"].read_text("utf-8-sig")), pack)

    from builders import env_json
    path = tmp_path / "env.json"
    path.write_bytes(env_json("0173-1#01-AHX837#002"))
    loaded = __import__("aas_submodel_validate.loader", fromlist=["load"]).load(path)
    ctx = runner.Context(loaded, profiles.Selection(None))
    analysed = engine.analyze(ctx, built)
    assert analysed is not None
    assert engine.analyze(ctx, built) is analysed, \
        "the walk re-analysed; its cache keys on a name this table does not keep"
