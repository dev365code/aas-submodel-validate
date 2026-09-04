"""What may travel inside the single file, and what may not.

The `.pyz` is the artifact that goes onto a USB stick and through a
site's inbound review. Its whole trust story is that a reviewer can open
it -- it is an ordinary zip of ordinary Python -- so what a reviewer
finds inside it is the product.

Asked of the builder's own selection rule rather than of a built file:
the archive takes minutes to produce and needs a network to resolve the
dependency, and a gate nobody can run in the suite is a gate that rots.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

BUILDER = ROOT / "tools" / "build_zipapp.py"


def _rule():
    """The builder's `belongs`, imported without running the builder."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_zipapp_builder", BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.belongs


@pytest.mark.parametrize("path", [
    "dev_scripts/precommit.py",
    "dev_scripts/continuous_integration_of_dev_scripts/precommit.py",
    "aas_core3/dev_scripts/anything.py",
])
def test_a_dependencys_own_build_scripts_do_not_travel(path):
    """aas-core3.0's wheel carries the scripts its maintainers use to
    build it, and they arrived in the artifact.

    Dead code -- nothing the entry point reaches imports them -- and
    also the only `subprocess` import in the whole archive, which is the
    one line a scanner stops on and a reviewer must then ask about.
    They land as a top-level `dev_scripts` package on `sys.path` besides,
    which is a name this artifact has no business claiming.
    """
    assert not _rule()(path), "%s should not travel in the .pyz" % path


@pytest.mark.parametrize("path", [
    "aas_submodel_validate/cli.py",
    "aas_submodel_validate/data/smt/02004/2.0.1/template.json",
    "aas_submodel_validate/data/example/idta-02004-2.0.aasx",
    "aas_core3/verification.py",
    "aas_core3-1.1.4.dist-info/RECORD",
    "__main__.py",
])
def test_what_the_tool_needs_still_travels(path):
    """The exclusion is a rule, and a rule that also excludes the
    payload is worse than none. `dist-info` stays: a reviewer checks the
    archive's `aas_core3` files against the hashes upstream signed into
    its own RECORD, and removing it removes that check."""
    assert _rule()(path), "%s must travel in the .pyz" % path


def test_the_builder_names_no_import_it_does_not_reach():
    """A second reading of the same fact, from the other side.

    The rule above is a path filter; this asks what the sources it lets
    through actually import. `subprocess` in the shipped tree means the
    artifact can start a process, and nothing this tool does needs to.
    """
    tree = ast.parse(BUILDER.read_text(encoding="utf-8"))
    excluded = {node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "dev_scripts" in excluded, \
        "the builder no longer names the directory it excludes"


def _entry_point() -> str:
    import importlib.util
    spec = importlib.util.spec_from_file_location("_zipapp_builder", BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MAIN


def test_the_entry_point_says_which_python_it_needs():
    """An old interpreter has to be told, not to fail at a syntax error.

    The wheel declares `Requires-Python` in metadata the single file does
    not carry, so a reader who took the `.pyz` through a site's inbound
    review and ran it on a plant machine with Python 3.6 got a traceback
    from a file they had no way to inspect first -- and the trip back out
    to a networked machine to find out why is measured in half-days, not
    minutes.
    """
    main = _entry_point()
    assert "version_info" in main, "the entry point checks no version"
    assert "3.9" in main or "(3, 9)" in main, \
        "the entry point does not say which version it wants"


def test_the_version_check_parses_on_the_pythons_it_is_meant_to_warn():
    """The check is useless if reading it is what fails.

    It has to be the first thing that runs and use nothing newer than
    what it refuses -- no f-string, no walrus, no annotation. Compiled
    here as plain Python 2-era-safe syntax would be overkill; what is
    asserted is that the guard precedes every import of this package,
    since an import is what raises on the old interpreter."""
    main = _entry_point()
    guard = main.index("version_info")
    package = main.index("aas_submodel_validate")
    assert guard < package, \
        "the version guard runs after the import whose failure it explains"
    assert "f\"" not in main[:package] and "f'" not in main[:package], \
        "the guard uses syntax the interpreters it warns cannot parse"
