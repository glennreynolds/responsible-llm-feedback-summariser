"""Human review gate. Nothing the model proposes reaches a report until a named reviewer
approves it. Themes without an explicit decision are rejected (fail closed)."""
from __future__ import annotations

from datetime import datetime, timezone

from .audit import AuditLog

DECISIONS = ("approve", "edit", "reject")


def apply_decisions(draft: dict, decisions: dict, reviewer: str, audit: AuditLog) -> dict:
    if not reviewer.strip():
        raise ValueError("A named reviewer is required.")
    approved, rejected = [], []
    for t in draft["themes"]:
        d = decisions.get(t["id"], {"decision": "reject", "note": "no decision recorded"})
        kind = d.get("decision")
        if kind not in DECISIONS:
            raise ValueError(f"Invalid decision '{kind}' for theme {t['id']}")
        rec = {"run_id": draft["run_id"], "theme_id": t["id"], "decision": kind, "note": d.get("note", "")}
        if kind == "reject":
            rejected.append(t["id"])
        else:
            new = dict(t)
            if kind == "edit":
                rec["before"] = {"title": t["title"], "description": t["description"]}
                new["title"] = d.get("title", t["title"])
                new["description"] = d.get("description", t["description"])
                rec["after"] = {"title": new["title"], "description": new["description"]}
            new["origin"] = "model-proposed, human-edited" if kind == "edit" else "model-proposed, human-approved"
            approved.append(new)
        audit.record("review.decision", rec, actor=reviewer)
    if not approved:
        raise ValueError("No themes approved; nothing can be released.")
    taxonomy = {
        "run_id": draft["run_id"], "status": "approved", "reviewer": reviewer,
        "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_provider": draft["provider"], "source_model": draft["model"],
        "prompt_version": draft["prompt_version"],
        "themes": [{k: v for k, v in t.items() if k in ("id", "title", "description", "origin")} for t in approved],
        "rejected": rejected,
    }
    audit.record("review.complete", {"run_id": draft["run_id"], "approved": [t["id"] for t in approved],
                                     "rejected": rejected}, actor=reviewer)
    return taxonomy


def interactive_decisions(draft: dict, comments: dict[str, str]) -> dict:
    """Terminal review. Shows each proposed theme with the actual (redacted) evidence it cites."""
    decisions = {}
    for i, t in enumerate(draft["themes"], 1):
        print("\n" + "=" * 72)
        print(f"Theme {i}/{len(draft['themes'])}: {t['title']}   [{t['sentiment']}]")
        print(f"  {t['description']}")
        print(f"  Cites {len(t['comment_ids'])} comment(s). Evidence:")
        for cid in t["comment_ids"][:5]:
            print(f"   - {cid}: {comments.get(cid, '(not found)')[:160]}")
        if len(t["comment_ids"]) > 5:
            print(f"   … and {len(t['comment_ids']) - 5} more")
        while True:
            ans = input("  [a]pprove / [e]dit / [r]eject? ").strip().lower()
            if ans in ("a", "e", "r"):
                break
        if ans == "a":
            decisions[t["id"]] = {"decision": "approve"}
        elif ans == "r":
            decisions[t["id"]] = {"decision": "reject", "note": input("  Reason (optional): ").strip()}
        else:
            title = input(f"  New title [{t['title']}]: ").strip() or t["title"]
            desc = input("  New description [enter to keep]: ").strip() or t["description"]
            decisions[t["id"]] = {"decision": "edit", "title": title, "description": desc,
                                  "note": input("  Reason (optional): ").strip()}
    return decisions
