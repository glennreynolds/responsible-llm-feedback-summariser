"""Versioned prompts. Any wording change must bump PROMPT_VERSION so audit records and
evaluation results can be tied to the exact prompt that produced them."""
from __future__ import annotations

import hashlib
import json

PROMPT_VERSION = "2026-11-04.1"

_SHARED_RULES = """You are analysing anonymous staff check-in comments for a leadership summary.
Rules:
- Comments have already been de-identified. Never attempt to infer who wrote a comment.
- Never include names, contact details or other identifying details in your output.
- Refer to comments only by their id. Do not quote or paraphrase comments at length.
- Use only the comments provided. If evidence is thin, say so rather than generalising.
- Respond with a single JSON object and nothing else."""

DISCOVER_SYSTEM = _SHARED_RULES + """
Task: propose between 3 and 8 themes that together cover most comments.
JSON schema:
{"themes": [{"title": str (<= 8 words), "description": str (<= 40 words),
  "sentiment": "positive"|"mixed"|"negative",
  "comment_ids": [str, ...]  (ids that support this theme, at least 1),
  "representative_comment_id": str (one of comment_ids)}]}"""

CLASSIFY_SYSTEM = _SHARED_RULES + """
Task: assign EVERY comment to exactly one theme from the approved taxonomy, or "other" if none fits,
and give the comment's sentiment. Judge sentiment on what is said, not on writing style, grammar,
spelling or fluency in English.
JSON schema:
{"classifications": [{"comment_id": str, "theme_id": str (a taxonomy id or "other"),
  "sentiment": "positive"|"mixed"|"negative",
  "rationale": str (<= 20 words, explains the assignment without quoting the comment)}]}"""


def _comments_block(comments: list[dict]) -> str:
    return "COMMENTS_JSON:\n" + json.dumps(comments, ensure_ascii=False, indent=0)


def build_discover(comments: list[dict]) -> tuple[str, str]:
    return DISCOVER_SYSTEM, _comments_block(comments)


def build_classify(comments: list[dict], taxonomy: list[dict]) -> tuple[str, str]:
    tax = [{"id": t["id"], "title": t["title"], "description": t["description"]} for t in taxonomy]
    user = "TAXONOMY_JSON:\n" + json.dumps(tax, ensure_ascii=False, indent=0) + "\n\n" + _comments_block(comments)
    return CLASSIFY_SYSTEM, user


def prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n---\n" + user).encode()).hexdigest()
