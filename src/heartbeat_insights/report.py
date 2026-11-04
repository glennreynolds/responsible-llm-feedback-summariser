"""Leadership report built from per-comment classifications.

Privacy rules applied at output:
- groups under K never appear (they were removed before analysis)
- any count below CELL_MIN (including zero) is shown as "≤2", so small cells can't be
  recovered by subtracting the other cells from the total
- no verbatim comments by default (writing style can identify people in small teams)
"""
from __future__ import annotations

from collections import Counter, defaultdict

from .audit import AuditLog

CELL_MIN = 3


def _cell(n: int) -> str:
    return f"≤{CELL_MIN - 1}" if n < CELL_MIN else str(n)


def build_report(classified: dict, audit: AuditLog, released_by: str, include_quotes: bool = False) -> str:
    tax = classified["taxonomy"]
    titles = {t["id"]: t["title"] for t in tax["themes"]} | {"other": "Other / not covered"}
    rows = classified["classifications"]
    teams = sorted({r["team"] for r in rows})
    by_theme: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_theme[r["theme_id"]].append(r)
    order = sorted(by_theme, key=lambda t: (t == "other", -len(by_theme[t])))

    out = ["# Heartbeat check-in: themes summary", ""]
    out.append(f"**{len(rows)} responses analysed** across {len(teams)} team(s). "
               f"Teams with fewer than {classified['k']} responses are not reported.")
    if classified["suppressed_groups"]:
        out.append(f"Suppressed for privacy: {', '.join(classified['suppressed_groups'])} (fewer than {classified['k']} responses).")
    out += ["", "## Themes", "", "| Theme | Responses | Positive | Mixed | Negative |", "|---|---:|---:|---:|---:|"]
    for tid in order:
        s = Counter(r["sentiment"] for r in by_theme[tid])
        out.append(f"| {titles.get(tid, tid)} | {len(by_theme[tid])} | {_cell(s['positive'])} | {_cell(s['mixed'])} | {_cell(s['negative'])} |")

    out += ["", "## By team", "", "| Theme | " + " | ".join(teams) + " |", "|---|" + "---:|" * len(teams)]
    for tid in order:
        c = Counter(r["team"] for r in by_theme[tid])
        out.append(f"| {titles.get(tid, tid)} | " + " | ".join(_cell(c[t]) for t in teams) + " |")

    out += ["", "## Theme definitions (approved by reviewer)", ""]
    for t in tax["themes"]:
        out.append(f"- **{t['title']}** — {t['description']} _({t.get('origin', '')})_")

    if include_quotes:
        out += ["", "## Example comments (redacted)", ""]
        for tid in order:
            if tid == "other" or len(by_theme[tid]) < CELL_MIN:
                continue
            cid = by_theme[tid][0]["comment_id"]
            out.append(f"- {titles[tid]}: “{classified['comments'][cid]}”")

    ok, msg = audit.verify()
    last = audit._last_hash()
    rec = audit.record("report.release", {
        "run_id": classified["run_id"], "n": len(rows), "themes": {t: len(v) for t, v in by_theme.items()},
        "include_quotes": include_quotes, "audit_intact": ok,
    }, actor=released_by)
    out += ["", "---", "",
            "**How this was produced.** Comments were de-identified, then a language model proposed themes. "
            f"A human reviewer ({tax['reviewer']}) approved or edited every theme before use. Each response was then "
            "assigned to one approved theme with a recorded rationale; the numbers above are counts of those assignments. "
            "This summary supports, and does not replace, leaders' own reading and conversations with staff.",
            "",
            f"Run `{classified['run_id']}` · model `{classified['provider']}/{classified['model']}` · "
            f"prompt `{classified['prompt_version']}` · released by {released_by} · "
            f"audit {('intact' if ok else 'NOT INTACT: ' + msg)} · audit hash `{rec['hash'][:16]}` (prev `{last[:16]}`)"]
    return "\n".join(out) + "\n"


def evidence_appendix(classified: dict) -> str:
    """For authorised reviewers only: every assignment with its rationale, for spot-checking."""
    titles = {t["id"]: t["title"] for t in classified["taxonomy"]["themes"]} | {"other": "Other"}
    out = ["# Evidence appendix (restricted)", "", "| Comment | Theme | Sentiment | Rationale |", "|---|---|---|---|"]
    for r in sorted(classified["classifications"], key=lambda r: (r["theme_id"], r["comment_id"])):
        out.append(f"| {r['comment_id']} | {titles.get(r['theme_id'], r['theme_id'])} | {r['sentiment']} | {r['rationale']} |")
    return "\n".join(out) + "\n"
