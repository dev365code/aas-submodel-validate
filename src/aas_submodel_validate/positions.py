"""Where in the file each object the reader built from it begins.

A finding names what it is about by a path of `idShort`s, and a person who
has to open the file needs a line. aas-core3.0 builds the model from the
parsed document and keeps no positions, so the line of each object is
found afterwards -- once, and only for a document a finding is about. The
document is read again for its shape alone, JSON's objects in the order
they open or XML's elements, and walked beside the model, each object
paired with the source it was built from. An object's line is the line
its `{` is on in JSON, and in XML the line of its start tag.

Walked, never recursed: a document reaches this already within the
nesting bound, but the walk is the same either way.
"""
from __future__ import annotations

import contextlib
import functools
import json
import re
from typing import Dict, Optional, Tuple
from xml.parsers import expat

from . import upstream
from .evidence import spelt

#: A JSON string, which the brace count leaves out: a `{` in one is text.
#: A string holds no raw line break in JSON, so leaving strings out keeps
#: every line where it was.
_STRING = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"', re.S)
_BRACE = re.compile(r"\{")
_CAPITAL = re.compile(r"([A-Z])")


@functools.cache
def _attribute(key: str) -> str:
    """`isCaseOf` -> `is_case_of`: a JSON member as aas-core3.0 names it."""
    return _CAPITAL.sub(r"_\1", key).lower()


class Source:
    """What one model was built from: its root, the document's form, the
    text as it was parsed, and the part of a package it came from."""

    __slots__ = ("root", "form", "text", "part")

    def __init__(self, root, form: str, text: str, part: Optional[str]):
        self.root, self.form, self.text, self.part = root, form, text, part


class _Members(list):
    """A JSON object's members in the order they are written, a repeated
    key kept as often as it is written -- so every `{` in the text has an
    object here, which is what lets the two be counted against each other."""


def _json_shape(text: str):
    """The document's objects with every member kept, and the line each
    object's `{` is on, in the order they open."""
    objects = [0]

    def members(pairs):
        objects[0] += 1
        return _Members(pairs)

    tree = json.loads(text, object_pairs_hook=members)
    # Each object opens with a `{` outside any string. Where the text holds
    # exactly as many as there are objects, none is inside a string, and
    # the strings need not be taken out to find them.
    shape = text if text.count("{") == objects[0] else _STRING.sub("", text)
    lines, line, at = [], 1, 0
    for match in _BRACE.finditer(shape):
        line += shape.count("\n", at, match.start())
        at = match.start()
        lines.append(line)
    return tree, lines


def _json_lines(text: str, root) -> Dict[int, int]:
    tree, lines = _json_shape(text)
    found, order = {}, 0
    walk = [(root, tree)]
    while walk:
        model, node = walk.pop()
        if isinstance(node, _Members):
            if upstream.is_model_object(model):
                found[id(model)] = lines[order]
            order += 1
            # A repeated key is walked in the order it is written, so the
            # last -- the one json.loads keeps, and the model was built
            # from -- is paired last, and its lines are the ones that stand.
            walk.extend(reversed([
                (getattr(model, _attribute(key), None)
                 if upstream.is_model_object(model) else None, value)
                for key, value in node if isinstance(value, list)]))
        elif isinstance(node, list):
            items = model if isinstance(model, list) else ()
            walk.extend(reversed([
                (items[index] if index < len(items) else None, value)
                for index, value in enumerate(node) if isinstance(value, list)]))
    return found


def json_line_along(text: str, steps) -> Optional[int]:
    """The line the innermost object on a path of keys and indexes opens
    on: where a document this reader could not build stopped being one."""
    tree, lines = _json_shape(text)
    order, ranks, walk = 0, {}, [tree]
    while walk:
        node = walk.pop()
        if isinstance(node, _Members):
            ranks[id(node)] = order
            order += 1
            walk.extend(reversed([value for _key, value in node if isinstance(value, list)]))
        elif isinstance(node, list):
            walk.extend(reversed([value for value in node if isinstance(value, list)]))
    node, innermost = tree, tree if isinstance(tree, _Members) else None
    for step in steps:
        if isinstance(node, _Members) and isinstance(step, str):
            node = dict(node).get(step)
        elif isinstance(node, list) and isinstance(step, int) and 0 <= step < len(node):
            node = node[step]
        else:
            break
        if isinstance(node, _Members):
            innermost = node
    return lines[ranks[id(innermost)]] if innermost is not None else None


class _Element:
    __slots__ = ("tag", "line", "children")

    def __init__(self, tag: str, line: int):
        self.tag, self.line, self.children = tag, line, []


def _xml_skeleton(text: str) -> _Element:
    parser = expat.ParserCreate(encoding="utf-8", namespace_separator=" ")
    top = _Element("", 0)
    open_ = [top]

    def opened(name, _attributes):
        element = _Element(name.rpartition(" ")[2], parser.CurrentLineNumber)
        open_[-1].children.append(element)
        open_.append(element)

    def closed(_name):
        open_.pop()

    parser.StartElementHandler, parser.EndElementHandler = opened, closed
    # As far as it goes: a document that broke past the element a failure
    # names still has that element, and its line.
    with contextlib.suppress(expat.ExpatError):
        parser.Parse(text.encode("utf-8"), True)
    return top.children[0] if top.children else None


def _xml_lines(text: str, root) -> Dict[int, int]:
    found = {}
    top = _xml_skeleton(text)
    if top is None:
        return found
    walk = [(root, top)]
    while walk:
        model, element = walk.pop()
        found[id(model)] = element.line
        children = {}
        for child in element.children:
            children.setdefault(child.tag, child)
        for name, value in vars(model).items():
            if value is None:
                continue
            held = children.get(spelt(name))
            if held is None:
                continue
            if upstream.is_model_object(value):
                # A property whose type is abstract wraps its value in an
                # element named for the value's class: the one child, and
                # not one of the value's own attributes.
                if (len(held.children) == 1
                        and held.children[0].tag not in {spelt(a) for a in vars(value)}):
                    held = held.children[0]
                walk.append((value, held))
            elif isinstance(value, list):
                walk.extend((item, child) for item, child in zip(value, held.children)
                            if upstream.is_model_object(item))
    return found


def xml_line_along(text: str, steps) -> Optional[int]:
    """The line of the innermost element on a path of names and indexes."""
    element = top = _xml_skeleton(text)
    if top is None:
        return None
    innermost = top
    for step in steps:
        if isinstance(step, str):
            if element is top and step == top.tag:
                continue
            element = next((child for child in element.children if child.tag == step), None)
        elif isinstance(step, int) and 0 <= step < len(element.children):
            element = element.children[step]
        else:
            element = None
        if element is None:
            break
        innermost = element
    return innermost.line


class Places:
    """The line each object begins on, for every document a run read --
    the documents asked for, and walked, the first time a finding asks."""

    def __init__(self, documents):
        self._documents = documents
        self._found: Optional[Dict[int, Tuple[int, Optional[str]]]] = None

    def of(self, model) -> Tuple[Optional[int], Optional[str]]:
        if self._found is None:
            self._found = {}
            for source in self._documents():
                # A line is something a finding gains, never something a run
                # can fail on: a walk that goes wrong gives that document's
                # findings no line, and the report goes out as it would have.
                try:
                    lines = (_json_lines if source.form == "json" else _xml_lines)(
                        source.text, source.root)
                except Exception:  # noqa: BLE001 - a line not found is a line not given
                    continue
                for key, line in lines.items():
                    self._found[key] = (line, source.part)
        return self._found.get(id(model), (None, None))
