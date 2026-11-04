"""PII redaction applied BEFORE any text is sent to a model.

Deliberately simple and transparent: regex rules plus an optional roster of staff names.
Known limits (documented in docs/use-case-register.md): it will miss names not on the roster
that don't follow a title/role pattern, and nicknames. Output is re-scanned after the model
call, so anything that slips through is at least caught on the way out.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# (label, pattern, replacement)
_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(\.[\w-]+)+\b"), "[EMAIL]"),
    ("URL", re.compile(r"\bhttps?://\S+", re.I), "[URL]"),
    # Australian mobiles/landlines, with or without +61 and spaces
    ("PHONE", re.compile(r"(?<!\w)(\+?61[\s-]?|0)[2-478](?:[\s-]?\d){8}(?!\w)"), "[PHONE]"),
    ("STAFF_ID", re.compile(r"\b[PpEe]\d{5,7}\b"), "[STAFF_ID]"),
    # "my manager Dave", "team lead Priya", "Mr Smith" etc. - names not on the roster
    ("NAME", re.compile(r"\b(manager|lead|boss|director|colleague|Mr|Mrs|Ms|Dr)\s+[A-Z][a-z]+(?:\s[A-Z][a-z]+)?"),
     r"\1 [NAME]"),
]


@dataclass
class RedactionResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


class Redactor:
    def __init__(self, roster: list[str] | None = None):
        names = sorted({n.strip() for n in (roster or []) if n.strip()}, key=len, reverse=True)
        self._roster = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b", re.I) if names else None

    def redact(self, text: str) -> RedactionResult:
        counts: dict[str, int] = {}
        out = text

        def apply(label: str, pat: re.Pattern, repl: str) -> None:
            nonlocal out
            out, n = pat.subn(repl, out)
            if n:
                counts[label] = counts.get(label, 0) + n

        # Structured identifiers first (so "jess.k@example.com" is caught as one email, not a name)
        for label, pat, repl in _PATTERNS:
            if label != "NAME":
                apply(label, pat, repl)
        if self._roster:
            apply("NAME", self._roster, "[NAME]")
        for label, pat, repl in _PATTERNS:
            if label == "NAME":
                apply(label, pat, repl)
        return RedactionResult(out, counts)

    def contains_pii(self, text: str) -> bool:
        """Used as an output guardrail: does model output contain anything we would have redacted?"""
        return self.redact(text).total > 0


DEFAULT_ROSTER = [
    # Synthetic roster for the demo dataset. In real use this would be loaded from the HR system
    # at run time and never written to disk.
    "Sarah", "Mohammed", "Wei", "Priya", "Dave", "Jess", "Tom", "Aroha", "Nguyen", "Fatima", "Liam",
]
