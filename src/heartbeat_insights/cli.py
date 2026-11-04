from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit import AuditLog
from .evaluate import run_all, to_markdown
from .models import load_responses
from .pipeline import PolicyError, prepare
from .privacy import DEFAULT_K
from .providers import ProviderError, get_provider
from .report import build_report, evidence_appendix
from .review import apply_decisions, interactive_decisions
from .validate import ValidationError


def _write(path: Path, content) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if isinstance(content, str) else json.dumps(content, indent=2, ensure_ascii=False))
    print(f"wrote {path}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="heartbeat-insights", description="Governed LLM theme summaries for staff check-ins.")
    p.add_argument("--run-dir", default="runs", help="where artefacts and the audit log are written")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, provider=True):
        sp.add_argument("--input", default="data/synthetic_responses.csv")
        sp.add_argument("--k", type=int, default=DEFAULT_K, help="minimum group size")
        if provider:
            sp.add_argument("--provider", default="mock", help="mock | mock-biased | anthropic | ollama")
            sp.add_argument("--model", default=None)
            sp.add_argument("--no-redact", action="store_true", help="local providers only; for bias testing")

    common(sub.add_parser("discover", help="model proposes themes (draft)"))
    r = sub.add_parser("review", help="human approves/edits/rejects proposed themes")
    common(r, provider=False)
    r.add_argument("--reviewer", required=True)
    r.add_argument("--decisions", help="JSON file of decisions (non-interactive)")
    common(sub.add_parser("classify", help="assign each comment to an approved theme"))
    rep = sub.add_parser("report", help="build the leadership report")
    rep.add_argument("--released-by", required=True)
    rep.add_argument("--include-quotes", action="store_true")
    e = sub.add_parser("eval", help="accuracy + counterfactual bias tests")
    e.add_argument("--provider", default="mock")
    e.add_argument("--model", default=None)
    e.add_argument("--no-redact", action="store_true")
    e.add_argument("--data-dir", default="data")
    sub.add_parser("verify-audit", help="check the audit log hash chain")

    a = p.parse_args(argv)
    run = Path(a.run_dir)
    audit = AuditLog(run / "audit.jsonl")
    try:
        if a.cmd == "discover":
            from .pipeline import discover
            draft = discover(load_responses(a.input), get_provider(a.provider, a.model), audit, a.k, not a.no_redact)
            _write(run / "draft_themes.json", draft)
            print(f"{len(draft['themes'])} themes proposed. Next: review --reviewer <name>")
        elif a.cmd == "review":
            draft = json.loads((run / "draft_themes.json").read_text())
            if a.decisions:
                decisions = json.loads(Path(a.decisions).read_text())
            else:
                comments = {c["id"]: c["text"] for c in prepare(load_responses(a.input), a.k).comments}
                decisions = interactive_decisions(draft, comments)
            _write(run / "taxonomy.json", apply_decisions(draft, decisions, a.reviewer, audit))
        elif a.cmd == "classify":
            from .pipeline import classify
            tax = json.loads((run / "taxonomy.json").read_text())
            out = classify(load_responses(a.input), tax, get_provider(a.provider, a.model), audit, a.k, not a.no_redact)
            _write(run / "classified.json", out)
        elif a.cmd == "report":
            classified = json.loads((run / "classified.json").read_text())
            _write(run / "report.md", build_report(classified, audit, a.released_by, a.include_quotes))
            _write(run / "evidence_appendix.md", evidence_appendix(classified))
        elif a.cmd == "eval":
            res = run_all(Path(a.data_dir), get_provider(a.provider, a.model), audit, not a.no_redact)
            tag = f"{res['provider']}{'' if res['redaction'] else '-noredact'}"
            _write(run / f"eval_{tag}.json", res)
            _write(run / f"eval_{tag}.md", to_markdown(res))
            print("OVERALL:", "PASS" if res["overall_pass"] else "FAIL")
            return 0 if res["overall_pass"] else 2
        elif a.cmd == "verify-audit":
            ok, msg = audit.verify()
            print(msg)
            return 0 if ok else 1
    except (PolicyError, ValidationError, ProviderError, ValueError, FileNotFoundError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
