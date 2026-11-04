"""Core data types. Kept as plain dataclasses so every artefact can be written to JSON and audited."""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from pathlib import Path

SENTIMENTS = ("positive", "mixed", "negative")


@dataclass
class Response:
    id: str
    team: str
    question: str
    text: str


@dataclass
class Theme:
    id: str
    title: str
    description: str
    sentiment: str = "mixed"
    comment_ids: list[str] = field(default_factory=list)
    representative_comment_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Classification:
    comment_id: str
    theme_id: str  # a taxonomy theme id, or "other"
    sentiment: str
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


def load_responses(path: str | Path) -> list[Response]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    required = {"id", "team", "question", "text"}
    if rows and not required.issubset(rows[0].keys()):
        raise ValueError(f"CSV must have columns {sorted(required)}")
    return [Response(r["id"].strip(), r["team"].strip(), r["question"].strip(), r["text"].strip()) for r in rows]
