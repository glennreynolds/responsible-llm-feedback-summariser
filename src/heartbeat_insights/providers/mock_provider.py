"""Deterministic keyword-based stand-in for an LLM.

Used for tests, offline demos and CI. `MockBiasedProvider` deliberately rates comments written
in non-native-English phrasing more negatively, so the bias tests can be shown to catch it.
"""
from __future__ import annotations

import json
import re

from .base import Completion

CATEGORIES: dict[str, dict] = {
    "workload": {
        "title": "Workload and capacity",
        "description": "Volume of work, deadlines, after-hours effort and team capacity.",
        "kw": ["workload", "hours", "overtime", "deadline", "stretched", "capacity", "late night", "too much work", "weekend"],
    },
    "tooling": {
        "title": "Tools and developer environment",
        "description": "Build speed, environments, laptops and access to useful tools including AI assistants.",
        "kw": ["tool", "laptop", "build", "pipeline", "environment", "cursor", "ai ", "vpn", "slow machine"],
    },
    "leadership": {
        "title": "Leadership communication and priorities",
        "description": "Clarity of direction, how priorities are set and how decisions are communicated.",
        "kw": ["leadership", "priorit", "direction", "town hall", "communicat", "decision", "strategy", "manager"],
    },
    "recognition": {
        "title": "Recognition and feeling valued",
        "description": "Whether effort is noticed, thanked and credited.",
        "kw": ["recogni", "thank", "appreciat", "valued", "credit", "shout-out", "shout out"],
    },
    "flexibility": {
        "title": "Flexible and hybrid work",
        "description": "Working from home, office days, commuting and flexibility.",
        "kw": ["remote", "hybrid", "from home", "wfh", "office day", "commute", "flexib"],
    },
    "change_control": {
        "title": "Release and change-control process",
        "description": "Release approvals, change paperwork and process overhead.",
        "kw": ["change record", "release", "approval", "paperwork", "cab", "change window", "process"],
    },
}

POS = ["great", "good", "love", "appreciat", "helpful", "happy", "better", "enjoy", "thank", "supportive", "well done", "valued"]
NEG = ["frustrat", "slow", "stretched", "unclear", "worse", "hard", "tired", "blocked", "never", "too much", "confus",
       "exhaust", "painful", "not enough", "no one", "nobody", "waste", "lacking", "not so much good"]

ESL_MARKERS = re.compile(r"\b(?:we|i) am (?:needing|thinking|having|wanting)\b|\bvery much\b|\bis having\b|\bnot so much\b", re.I)


def _category(text: str) -> str | None:
    t = " " + text.lower() + " "
    best, score = None, 0
    for key, c in CATEGORIES.items():
        s = sum(t.count(k) for k in c["kw"])
        if s > score:
            best, score = key, s
    return best


def _sentiment(text: str) -> str:
    t = text.lower()
    p = sum(t.count(w) for w in POS)
    n = sum(t.count(w) for w in NEG)
    if p and n:
        return "mixed"
    if p:
        return "positive"
    if n:
        return "negative"
    return "mixed"


def _extract(user: str, marker: str) -> list[dict]:
    m = re.search(marker + r":\n(\[.*?\])(?:\n\n|$)", user, re.S)
    return json.loads(m.group(1)) if m else []


class MockProvider:
    name = "mock"
    model = "keyword-rules-v1"
    data_leaves_machine = False

    def sentiment(self, text: str) -> str:
        return _sentiment(text)

    def complete(self, system: str, user: str, max_tokens: int = 4000) -> Completion:
        comments = _extract(user, "COMMENTS_JSON")
        if "TAXONOMY_JSON" in user:
            return Completion(json.dumps(self._classify(comments, _extract(user, "TAXONOMY_JSON"))), self.name, self.model)
        return Completion(json.dumps(self._discover(comments)), self.name, self.model)

    def _discover(self, comments: list[dict]) -> dict:
        groups: dict[str, list[dict]] = {}
        for c in comments:
            cat = _category(c["text"])
            if cat:
                groups.setdefault(cat, []).append(c)
        themes = []
        for cat, cs in groups.items():
            sents = [self.sentiment(c["text"]) for c in cs]
            overall = max(set(sents), key=sents.count)
            themes.append({
                "title": CATEGORIES[cat]["title"],
                "description": CATEGORIES[cat]["description"],
                "sentiment": overall,
                "comment_ids": [c["id"] for c in cs],
                "representative_comment_id": cs[0]["id"],
            })
        return {"themes": themes}

    def _classify(self, comments: list[dict], taxonomy: list[dict]) -> dict:
        def match(cat: str | None) -> str:
            if not cat:
                return "other"
            title = CATEGORIES[cat]["title"].lower()
            for t in taxonomy:  # exact id/title first
                if t["id"] == cat or t["title"].lower() == title:
                    return t["id"]
            best, score = "other", 0  # then the taxonomy entry sharing most keywords (handles edited titles)
            for t in taxonomy:
                blob = (t["title"] + " " + t["description"]).lower()
                s = sum(1 for k in CATEGORIES[cat]["kw"] if k.strip() in blob)
                if s > score:
                    best, score = t["id"], s
            return best

        out = []
        for c in comments:
            cat = _category(c["text"])
            tid = match(cat)
            out.append({
                "comment_id": c["id"],
                "theme_id": tid,
                "sentiment": self.sentiment(c["text"]),
                "rationale": f"Keyword match on {cat or 'no category'}.",
            })
        return {"classifications": out}


class MockBiasedProvider(MockProvider):
    """Intentionally flawed: penalises non-native-English phrasing. For demonstrating the bias harness."""

    name = "mock-biased"
    model = "keyword-rules-v1-biased"

    def sentiment(self, text: str) -> str:
        if ESL_MARKERS.search(text):
            return "negative"
        return _sentiment(text)
