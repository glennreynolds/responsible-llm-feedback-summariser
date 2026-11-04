"""Minimum group size gate (k-anonymity style threshold).

Groups smaller than K are dropped BEFORE any model call (data minimisation), and the report
only says that the group was suppressed — never how many responses it had beyond '< K'.
"""
from __future__ import annotations

from collections import defaultdict

from .models import Response

DEFAULT_K = 5


def gate_groups(responses: list[Response], k: int = DEFAULT_K) -> tuple[list[Response], list[str]]:
    by_team: dict[str, list[Response]] = defaultdict(list)
    for r in responses:
        by_team[r.team].append(r)
    kept: list[Response] = []
    suppressed: list[str] = []
    for team, rs in sorted(by_team.items()):
        if len(rs) >= k:
            kept.extend(rs)
        else:
            suppressed.append(team)
    return kept, suppressed
