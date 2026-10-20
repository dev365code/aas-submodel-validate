#!/usr/bin/env python3
"""Generate what each of aas-core3.0's own checks reads, from its source.

The relayed channel passes aas-core3.0's metamodel findings on as they
come: a sentence, and a path to the object it is about. A path names where;
it does not say what was there, and the object at the end of most paths is
a whole element or concept description -- 104 of the 137 on the bundled
example and the 02003 sample -- of which the check read one or two
attributes. Which ones is written in the check itself. aas-core3.0's
verification module is generated code: every constraint on a class is one
`if not (<condition>): yield Error("<sentence>")` in the transformer method
for that class, and the condition names what it reads -- `that.is_case_of`,
or `element.id_short for element in that.value`. This reads those
conditions and writes, per class and sentence, the attribute paths they
name, so that a relayed finding can show what was there without this
project restating a single constraint.

`--check` regenerates and byte-compares, the contract the template tables'
generator keeps.
"""
from __future__ import annotations

import argparse
import ast
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src" / "aas_submodel_validate" / "relayed_reads.py"
#: A step that reads every item of a list.
EACH = "*"


def _sentence(node) -> str:
    """A sentence written as string literals joined by `+`."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _sentence(node.left) + _sentence(node.right)
    raise ValueError("a sentence that is not literals joined by +: %s" % ast.dump(node))


def _index(node):
    value = node.slice
    if isinstance(value, ast.Index):                 # pragma: no cover - Python 3.8
        value = value.value
    if isinstance(value, ast.Constant) and isinstance(value.value, int):
        return value.value
    return None


def _path(node, bound):
    """The attribute path `node` reads, from `that` or from a name a
    comprehension bound to the items of one; None if it is neither."""
    steps = []
    while True:
        if isinstance(node, ast.Attribute):
            steps.append(node.attr)
            node = node.value
        elif isinstance(node, ast.Subscript) and _index(node) is not None:
            steps.append(_index(node))
            node = node.value
        elif isinstance(node, ast.Name) and node.id in bound:
            # A helper's own parameter -- one of them is called `that` too --
            # stands for what it was handed, or for nothing this can follow.
            if bound[node.id] is None:
                return None
            return bound[node.id] + tuple(reversed(steps))
        elif isinstance(node, ast.Name) and node.id == "that":
            return tuple(reversed(steps))
        else:
            return None


def _items(node, bound):
    """What a comprehension's `for` walks, as a path to a list."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "enumerate" and node.args):
        return _path(node.args[0], bound)
    return _path(node, bound)


def _bind(target, source, bound):
    if isinstance(target, ast.Name):
        bound[target.id] = source + (EACH,)
    elif isinstance(target, ast.Tuple) and len(target.elts) == 2:
        # `for i, item in enumerate(...)`: the index reads nothing.
        _bind(target.elts[1], source, bound)


#: How far into aas-core3.0's own helper functions a condition is
#: followed. The deepest chain it has is one helper calling another.
HELPER_DEPTH = 3


def _reads(node, bound, found, helpers, depth=0) -> None:
    """Every attribute path the expression reads, in reading order --
    through any helper function of aas-core3.0's it hands a path to."""
    if isinstance(node, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
        inner = dict(bound)
        for generator in node.generators:
            _reads(generator.iter, inner, found, helpers, depth)
            source = _items(generator.iter, inner)
            if source is not None:
                _bind(generator.target, source, inner)
            for condition in generator.ifs:
                _reads(condition, inner, found, helpers, depth)
        _reads(node.elt, inner, found, helpers, depth)
        return
    path = _path(node, bound)
    if path is not None:
        if path and path not in found:
            found.append(path)
        return
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in helpers and depth < HELPER_DEPTH):
        helper = helpers[node.func.id]
        given = {parameter.arg: None for parameter in helper.args.args}
        for parameter, argument in zip(helper.args.args, node.args):
            given[parameter.arg] = _path(argument, bound)
        if any(source is not None for source in given.values()):
            _statements(helper.body, given, found, helpers, depth + 1)
    for child in ast.iter_child_nodes(node):
        _reads(child, bound, found, helpers, depth)


def _statements(body, bound, found, helpers, depth) -> None:
    """The reads of a helper's body, with its parameters standing for the
    paths it was handed: a `for` over one reads its items, and a name
    assigned from one stands for it after."""
    for statement in body:
        if isinstance(statement, ast.For):
            _reads(statement.iter, bound, found, helpers, depth)
            inner = dict(bound)
            source = _items(statement.iter, bound)
            if source is not None:
                _bind(statement.target, source, inner)
            _statements(statement.body, inner, found, helpers, depth)
            _statements(statement.orelse, bound, found, helpers, depth)
        elif (isinstance(statement, ast.Assign) and len(statement.targets) == 1
              and isinstance(statement.targets[0], ast.Name)):
            _reads(statement.value, bound, found, helpers, depth)
            source = _path(statement.value, bound)
            if source is not None:
                bound[statement.targets[0].id] = source
        elif isinstance(statement, (ast.If, ast.While)):
            _reads(statement.test, bound, found, helpers, depth)
            _statements(statement.body, bound, found, helpers, depth)
            _statements(statement.orelse, bound, found, helpers, depth)
        else:
            for child in ast.iter_child_nodes(statement):
                _reads(child, bound, found, helpers, depth)


def _longest(paths):
    """Drop a path another one extends: reading `value[*].idShort` reads `value`."""
    return tuple(path for path in paths
                 if not any(other != path and other[:len(path)] == path for other in paths))


def extract(source: str) -> dict:
    tree = ast.parse(source)
    helpers = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    transformer = next(node for node in tree.body
                       if isinstance(node, ast.ClassDef) and node.name == "_Transformer")
    reads = {}
    for method in transformer.body:
        if not (isinstance(method, ast.FunctionDef) and method.name.startswith("transform_")):
            continue
        annotation = method.args.args[1].annotation
        checked = annotation.attr if isinstance(annotation, ast.Attribute) else None
        if checked is None:                          # pragma: no cover - upstream shape
            raise ValueError("%s names no class it checks" % method.name)
        for node in ast.walk(method):
            if not (isinstance(node, ast.If) and isinstance(node.test, ast.UnaryOp)
                    and isinstance(node.test.op, ast.Not)):
                continue
            sentences = [_sentence(statement.value.value.args[0]) for statement in node.body
                         if isinstance(statement, ast.Expr)
                         and isinstance(statement.value, ast.Yield)
                         and isinstance(statement.value.value, ast.Call)
                         and getattr(statement.value.value.func, "id", None) == "Error"]
            for sentence in sentences:
                found = list(reads.get((checked, sentence), ()))
                _reads(node.test.operand, {}, found, helpers)
                reads[(checked, sentence)] = _longest(found)
    return reads


def generate() -> str:
    import aas_core3
    from aas_core3 import verification

    reads = extract(inspect.getsource(verification))
    lines = [
        '"""GENERATED by tools/extract_meta_reads.py from aas-core3.0\'s own',
        "verification module -- edit the generator, regenerate, never this file.",
        "",
        "What each of aas-core3.0's checks on a class reads: for the class it",
        "checks and the sentence it reports, the attribute paths its condition",
        "names, from the object a relayed finding's path ends at. %r is every" % EACH,
        'item of a list."""',
        "",
        "#: The aas-core3.0 release these were read from.",
        "SOURCE = %r" % aas_core3.__version__,
        "",
        "READS = {",
    ]
    for key in sorted(reads):
        lines.append("    %r: %r," % (key, reads[key]))
    lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = generate()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_bytes() != text.encode("utf-8"):
            print("%s is stale: run tools/extract_meta_reads.py" % OUTPUT.name, file=sys.stderr)
            return 1
        print("%s matches its generator (%d checks)" % (OUTPUT.name, text.count("): (")))
        return 0
    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    print("wrote %s" % OUTPUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
