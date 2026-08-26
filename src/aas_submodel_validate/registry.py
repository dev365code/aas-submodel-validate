"""Rule registration: the id is a contract, the remedy is an obligation.

Rules register themselves at import time via the decorator. Two things
are refused at this boundary rather than caught by a later audit: a
duplicate id (a stored report must never become ambiguous) and a rule
without a `fix` sentence (naming a defect without naming the remedy
leaves the reader all of the expertise).
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from .model import KINDS, PRIO_SEVERITY, Rule

_registry: Dict[str, Rule] = {}


def rule(rule_id: str, *, kind: str, prio: str, title: str,
         spec: Optional[str] = None, fix: Optional[str] = None) -> Callable:
    def decorator(fn: Callable) -> Callable:
        if rule_id in _registry:
            raise ValueError("duplicate rule id: %s" % rule_id)
        if not fix:
            raise ValueError("rule %s names no fix; every finding must carry its remedy"
                             % rule_id)
        # Both of these are read by table lookups that used to fall back
        # rather than fail, and a fallback is how a typo becomes a
        # verdict: `MSUT` scored as a warning, so a MUST stopped setting
        # the exit code, and a kind the reading order does not know sorted
        # into the middle of the channels a reader is scanning. Neither
        # left a mark anywhere. They are refused here, beside the other
        # two things this boundary refuses, because a rule that cannot be
        # read correctly must not reach a report at all.
        if kind not in KINDS:
            raise ValueError("rule %s has kind %r; known kinds are %s"
                             % (rule_id, kind, ", ".join(KINDS)))
        if prio not in PRIO_SEVERITY:
            raise ValueError("rule %s has priority %r; known priorities are %s"
                             % (rule_id, prio, ", ".join(sorted(PRIO_SEVERITY))))
        _registry[rule_id] = Rule(id=rule_id, kind=kind, prio=prio, title=title,
                                  spec=spec, fn=fn, fix=fix)
        return fn
    return decorator


def all_rules() -> List[Rule]:
    """Every registered rule, in registration (= id-stable) order."""
    return list(_registry.values())
