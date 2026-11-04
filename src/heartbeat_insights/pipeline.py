"""The governed pipeline:

  load -> group-size gate -> redact -> model call -> validate (retry once) -> audit
  discover: model PROPOSES themes          (draft, not shown to anyone yet)
  review:   human approves/edits/rejects   (see review.py)
  classify: model assigns each comment to an APPROVED theme, with a rationale
  report:   counts come from per-comment assignments, not from the model's own summary
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from .audit import AuditLog, sha256_text
from .models import Response
from .privacy import DEFAULT_K, gate_groups
from .prompts import PROMPT_VERSION, build_classify, build_discover, prompt_hash
from .providers import LLMProvider
from .redact import DEFAULT_ROSTER, Redactor
from .validate import ValidationError, parse_json, validate_classify, validate_discover

BATCH_SIZE = 25


class PolicyError(RuntimeError):
    pass


@dataclass
class Prepared:
    comments: list[dict]          # [{"id", "text"}] redacted
    teams: dict[str, str]         # comment id -> team
    suppressed_groups: list[str]
    redaction_counts: dict[str, int]


def prepare(responses: list[Response], k: int = DEFAULT_K, redactor: Redactor | None = None,
            redact: bool = True) -> Prepared:
    redactor = redactor or Redactor(DEFAULT_ROSTER)
    kept, suppressed = gate_groups(responses, k)
    comments, counts = [], {}
    for r in kept:
        text = r.text
        if redact:
            res = redactor.redact(text)
            text = res.text
            for key, n in res.counts.items():
                counts[key] = counts.get(key, 0) + n
        comments.append({"id": r.id, "text": text})
    return Prepared(comments, {r.id: r.team for r in kept}, suppressed, counts)


def _check_policy(provider: LLMProvider, redact: bool) -> None:
    if provider.data_leaves_machine and not redact:
        raise PolicyError(f"Refusing to send unredacted text to '{provider.name}', which is an external service.")


def call_with_retry(provider: LLMProvider, system: str, user: str, validator, audit: AuditLog, event: str,
                    run_id: str, actor: str | None = None, retries: int = 1):
    attempt, last_errors = 0, []
    while attempt <= retries:
        prompt = user if not last_errors else (
            user + "\n\nYour previous answer failed validation. Fix these problems and answer again:\n- "
            + "\n- ".join(last_errors))
        comp = provider.complete(system, prompt)
        base = {
            "run_id": run_id, "attempt": attempt + 1, "provider": comp.provider, "model": comp.model,
            "prompt_version": PROMPT_VERSION, "prompt_sha256": prompt_hash(system, prompt),
            "input_tokens": comp.input_tokens, "output_tokens": comp.output_tokens,
            "response_sha256": sha256_text(comp.text),
        }
        try:
            result = validator(parse_json(comp.text))
            audit.record(event, {**base, "status": "valid"}, actor)
            return result
        except ValidationError as e:
            last_errors = e.errors
            audit.record(event, {**base, "status": "invalid", "errors": e.errors[:20]}, actor)
        attempt += 1
    raise ValidationError(["Model output failed validation after retry; nothing was produced (fail closed)."]
                          + last_errors)


def _slug(title: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:40] or "theme"
    slug, n = base, 2
    while slug in used:
        slug, n = f"{base}_{n}", n + 1
    used.add(slug)
    return slug


def discover(responses: list[Response], provider: LLMProvider, audit: AuditLog, k: int = DEFAULT_K,
             redact: bool = True, actor: str | None = None) -> dict:
    _check_policy(provider, redact)
    run_id = "run-" + uuid.uuid4().hex[:8]
    prep = prepare(responses, k, redact=redact)
    audit.record("discover.start", {
        "run_id": run_id, "n_input": len(responses), "n_after_gate": len(prep.comments),
        "suppressed_groups": prep.suppressed_groups, "k": k, "redaction_counts": prep.redaction_counts,
        "provider": provider.name, "data_leaves_machine": provider.data_leaves_machine,
    }, actor)
    if not prep.comments:
        raise PolicyError("No groups meet the minimum size; nothing to analyse.")
    redactor = Redactor(DEFAULT_ROSTER)
    ids = {c["id"] for c in prep.comments}
    system, user = build_discover(prep.comments)
    themes = call_with_retry(provider, system, user, lambda d: validate_discover(d, ids, redactor),
                             audit, "discover.model_call", run_id, actor)
    used: set[str] = set()
    for t in themes:
        t["id"] = _slug(t["title"], used)
    return {
        "run_id": run_id, "status": "draft", "provider": provider.name, "model": provider.model,
        "prompt_version": PROMPT_VERSION, "k": k, "suppressed_groups": prep.suppressed_groups,
        "themes": themes,
    }


def classify(responses: list[Response], taxonomy: dict, provider: LLMProvider, audit: AuditLog,
             k: int = DEFAULT_K, redact: bool = True, actor: str | None = None, run_id: str | None = None) -> dict:
    if taxonomy.get("status") != "approved":
        raise PolicyError("Taxonomy has not been approved by a human reviewer.")
    _check_policy(provider, redact)
    run_id = run_id or taxonomy.get("run_id") or "run-" + uuid.uuid4().hex[:8]
    prep = prepare(responses, k, redact=redact)
    themes = taxonomy["themes"]
    theme_ids = {t["id"] for t in themes}
    redactor = Redactor(DEFAULT_ROSTER)
    audit.record("classify.start", {
        "run_id": run_id, "n_after_gate": len(prep.comments), "suppressed_groups": prep.suppressed_groups,
        "taxonomy_sha256": sha256_text(str(sorted(theme_ids))), "provider": provider.name,
    }, actor)
    rows: list[dict] = []
    for i in range(0, len(prep.comments), BATCH_SIZE):
        batch = prep.comments[i:i + BATCH_SIZE]
        ids = {c["id"] for c in batch}
        system, user = build_classify(batch, themes)
        rows += call_with_retry(provider, system, user,
                                lambda d, ids=ids: validate_classify(d, ids, theme_ids, redactor),
                                audit, "classify.model_call", run_id, actor)
    for r in rows:
        r["team"] = prep.teams[r["comment_id"]]
    return {
        "run_id": run_id, "provider": provider.name, "model": provider.model, "prompt_version": PROMPT_VERSION,
        "k": k, "suppressed_groups": prep.suppressed_groups, "taxonomy": taxonomy,
        "comments": {c["id"]: c["text"] for c in prep.comments},  # redacted text only
        "classifications": rows,
    }
