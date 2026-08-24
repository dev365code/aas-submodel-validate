"""Rule registration: the id is a contract, the remedy is an obligation.

Rules register themselves at import time via the decorator. Two things
are refused at this boundary rather than caught by a later audit: a
duplicate id (a stored report must never become ambiguous) and a rule
without a `fix` sentence (naming a defect without naming the remedy
leaves the reader all of the expertise).
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from .model import Rule

_registry: Dict[str, Rule] = {}


def rule(rule_id: str, *, kind: str, prio: str, title: str,
         spec: Optional[str] = None, fix: Optional[str] = None) -> Callable:
    def decorator(fn: Callable) -> Callable:
        if rule_id in _registry:
            raise ValueError("duplicate rule id: %s" % rule_id)
        if not fix:
            raise ValueError("rule %s names no fix; every finding must carry its remedy"
                             % rule_id)
        _registry[rule_id] = Rule(id=rule_id, kind=kind, prio=prio, title=title,
                                  spec=spec, fn=fn, fix=fix)
        return fn
    return decorator


def all_rules() -> List[Rule]:
    """Every registered rule, in registration (= id-stable) order."""
    return list(_registry.values())
