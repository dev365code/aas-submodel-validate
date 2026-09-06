"""Everything this reader borrows from `aas_core3`, in one file.

Three modules import the library: `loader.py`, which turns bytes into a
model, `runner.py`, which relays the metamodel channel, and this one.
Those two own the dependency because reading and relaying *are* the
dependency. A rule is a different thing -- it asks questions about a
model this project already has -- and a rule reaching past the reader
into the library is a layer boundary crossed for the convenience of one
call.

It cost nothing until it does. `aas_core3` is pinned `>=1.1.4` and its
own CI stops at Python 3.12; the day a 2.x moves a module or renames a
predicate, every direct import is a separate repair in a separate file,
and the rules are where they are hardest to find. Here they are one
file and one diff.

`tests/test_pack_roster.py` holds the boundary: nothing under `rules/`
may import the library.
"""
from __future__ import annotations

import aas_core3.verification as _verification
from aas_core3.types import MultiLanguageProperty as _MultiLanguageProperty


def is_english_language_tag(tag) -> bool:
    """Whether `tag` names English, by the upstream predicate.

    Borrowed, not copied, and handed the spelling the standard says
    means the same thing -- the caller's case is folded here so the
    lower-casing and the question travel together.

    The predicate is `^(en|EN)(-.*)?$`, which is narrower than BCP 47
    and is upstream's to be: `eng` is well-formed, means English, and
    IANA marks `en` as its preferred value. Refusing it is a different
    argument and it is in `docs/divergences.md` #35. This wrapper does
    not widen it; a reader who wants the boundary moved should move it
    there, once.
    """
    return _verification.is_bcp_47_for_english((tag or "").lower())


def is_multi_language_property(element) -> bool:
    """Whether `element` is a MultiLanguageProperty.

    A type test rather than an import of the type, so a rule never holds
    a class object from the library.
    """
    return isinstance(element, _MultiLanguageProperty)
