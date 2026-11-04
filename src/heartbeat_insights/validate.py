"""Output guardrails. Model output is treated as untrusted until it passes these checks.
On failure the pipeline retries once with the errors, then fails closed (no output)."""
from __future__ import annotations

import json
import re

from .models import SENTIMENTS
from .redact import Redactor


class ValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def parse_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValidationError(["Response did not contain a JSON object."])
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise ValidationError([f"Invalid JSON: {e}"]) from e


def _pii_errors(obj, redactor: Redactor, where: str) -> list[str]:
    errs = []
    blob = json.dumps(obj, ensure_ascii=False)
    # Placeholders like [NAME] are fine; anything the redactor would still catch is not.
    if redactor.contains_pii(re.sub(r"\[(NAME|EMAIL|PHONE|URL|STAFF_ID)\]", "", blob)):
        errs.append(f"{where} contains possible personal information.")
    return errs


def validate_discover(data: dict, valid_ids: set[str], redactor: Redactor) -> list[dict]:
    errs: list[str] = []
    themes = data.get("themes")
    if not isinstance(themes, list) or not themes:
        raise ValidationError(["'themes' must be a non-empty list."])
    for i, t in enumerate(themes):
        p = f"themes[{i}]"
        for key in ("title", "description", "sentiment", "comment_ids", "representative_comment_id"):
            if key not in t:
                errs.append(f"{p} missing '{key}'.")
        if errs:
            continue
        if t["sentiment"] not in SENTIMENTS:
            errs.append(f"{p} sentiment '{t['sentiment']}' not in {SENTIMENTS}.")
        bad = [c for c in t["comment_ids"] if c not in valid_ids]
        if bad:
            errs.append(f"{p} cites unknown comment ids {bad} (possible fabrication).")
        if not t["comment_ids"]:
            errs.append(f"{p} cites no comments.")
        if t["representative_comment_id"] not in t["comment_ids"]:
            errs.append(f"{p} representative_comment_id is not one of its comment_ids.")
        if len(t["title"].split()) > 12 or len(t["description"].split()) > 60:
            errs.append(f"{p} title/description too long.")
    errs += _pii_errors(themes, redactor, "Theme output")
    if errs:
        raise ValidationError(errs)
    return themes


def validate_classify(data: dict, valid_ids: set[str], theme_ids: set[str], redactor: Redactor) -> list[dict]:
    errs: list[str] = []
    rows = data.get("classifications")
    if not isinstance(rows, list):
        raise ValidationError(["'classifications' must be a list."])
    seen: dict[str, int] = {}
    allowed = theme_ids | {"other"}
    for i, r in enumerate(rows):
        p = f"classifications[{i}]"
        cid = r.get("comment_id")
        if cid not in valid_ids:
            errs.append(f"{p} unknown comment_id '{cid}'.")
            continue
        seen[cid] = seen.get(cid, 0) + 1
        if r.get("theme_id") not in allowed:
            errs.append(f"{p} theme_id '{r.get('theme_id')}' is not in the approved taxonomy.")
        if r.get("sentiment") not in SENTIMENTS:
            errs.append(f"{p} invalid sentiment '{r.get('sentiment')}'.")
        if not isinstance(r.get("rationale"), str) or not r["rationale"].strip():
            errs.append(f"{p} missing rationale.")
        elif len(r["rationale"].split()) > 30:
            errs.append(f"{p} rationale too long.")
    missing = sorted(valid_ids - seen.keys())
    dupes = sorted(k for k, v in seen.items() if v > 1)
    if missing:
        errs.append(f"Comments not classified: {missing}.")
    if dupes:
        errs.append(f"Comments classified more than once: {dupes}.")
    errs += _pii_errors([r.get("rationale", "") for r in rows], redactor, "Rationales")
    if errs:
        raise ValidationError(errs)
    return rows
