"""Evaluation and bias testing for the classification step.

1. Accuracy on a labelled synthetic set (theme and sentiment), per-theme precision/recall.
2. Counterfactual bias tests: each case has a base comment and variants that change ONLY
   something that should not matter (a name, gendered wording, non-native-English phrasing).
   A fair classifier gives every variant the same theme and sentiment as the base.

Pass thresholds are explicit so results can go into a use-case register / go-live decision.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from .audit import AuditLog
from .models import Response
from .pipeline import classify
from .providers import LLMProvider

THRESHOLDS = {"theme_accuracy": 0.80, "sentiment_accuracy": 0.75, "cf_consistency": 0.95, "cf_accuracy_gap": 0.05}


def _approved(taxonomy: list[dict]) -> dict:
    return {"run_id": "eval", "status": "approved", "reviewer": "eval-fixture", "themes": taxonomy}


def _run(items: list[dict], taxonomy: list[dict], provider: LLMProvider, audit: AuditLog, redact: bool) -> dict[str, dict]:
    responses = [Response(i["id"], "eval", "eval", i["text"]) for i in items]
    out = classify(responses, _approved(taxonomy), provider, audit, k=1, redact=redact, actor="evaluator", run_id="eval")
    return {r["comment_id"]: r for r in out["classifications"]}


def accuracy_eval(eval_set: dict, provider: LLMProvider, audit: AuditLog, redact: bool = True) -> dict:
    items = eval_set["items"]
    pred = _run(items, eval_set["taxonomy"], provider, audit, redact)
    theme_ok = sum(pred[i["id"]]["theme_id"] == i["theme"] for i in items)
    sent_ok = sum(pred[i["id"]]["sentiment"] == i["sentiment"] for i in items)
    per_theme = {}
    for t in [t["id"] for t in eval_set["taxonomy"]] + ["other"]:
        tp = sum(1 for i in items if i["theme"] == t and pred[i["id"]]["theme_id"] == t)
        fp = sum(1 for i in items if i["theme"] != t and pred[i["id"]]["theme_id"] == t)
        fn = sum(1 for i in items if i["theme"] == t and pred[i["id"]]["theme_id"] != t)
        if tp + fp + fn:
            per_theme[t] = {"precision": round(tp / (tp + fp), 2) if tp + fp else None,
                            "recall": round(tp / (tp + fn), 2) if tp + fn else None, "support": tp + fn}
    errors = [{"id": i["id"], "expected": [i["theme"], i["sentiment"]],
               "got": [pred[i["id"]]["theme_id"], pred[i["id"]]["sentiment"]], "rationale": pred[i["id"]]["rationale"]}
              for i in items if (pred[i["id"]]["theme_id"], pred[i["id"]]["sentiment"]) != (i["theme"], i["sentiment"])]
    return {"n": len(items), "theme_accuracy": round(theme_ok / len(items), 3),
            "sentiment_accuracy": round(sent_ok / len(items), 3), "per_theme": per_theme, "errors": errors}


def counterfactual_eval(cases: list[dict], taxonomy: list[dict], provider: LLMProvider, audit: AuditLog,
                        redact: bool = True) -> dict:
    items = []
    for c in cases:
        for v in c["variants"]:
            items.append({"id": f"{c['case']}:{v['variant']}", "text": v["text"]})
    pred = _run(items, taxonomy, provider, audit, redact)
    by_dim: dict[str, dict] = defaultdict(lambda: Counter())
    flips = []
    for c in cases:
        base = pred[f"{c['case']}:base"]
        base_correct = (base["theme_id"], base["sentiment"]) == (c["label"]["theme"], c["label"]["sentiment"])
        for v in c["variants"]:
            if v["variant"] == "base":
                continue
            p = pred[f"{c['case']}:{v['variant']}"]
            d = by_dim[c["dimension"]]
            d["n"] += 1
            same = (p["theme_id"], p["sentiment"]) == (base["theme_id"], base["sentiment"])
            d["consistent"] += same
            d["base_correct"] += base_correct
            d["variant_correct"] += (p["theme_id"], p["sentiment"]) == (c["label"]["theme"], c["label"]["sentiment"])
            if not same:
                flips.append({"case": c["case"], "dimension": c["dimension"], "variant": v["variant"],
                              "base": [base["theme_id"], base["sentiment"]], "variant_got": [p["theme_id"], p["sentiment"]]})
    dims = {}
    for dim, d in by_dim.items():
        cons = d["consistent"] / d["n"]
        gap = (d["base_correct"] - d["variant_correct"]) / d["n"]
        dims[dim] = {"n": d["n"], "consistency": round(cons, 3), "accuracy_gap": round(gap, 3),
                     "pass": cons >= THRESHOLDS["cf_consistency"] and gap <= THRESHOLDS["cf_accuracy_gap"]}
    return {"dimensions": dims, "flips": flips}


def run_all(data_dir: Path, provider: LLMProvider, audit: AuditLog, redact: bool = True) -> dict:
    eval_set = json.loads((data_dir / "eval_set.json").read_text())
    cases = json.loads((data_dir / "counterfactuals.json").read_text())
    acc = accuracy_eval(eval_set, provider, audit, redact)
    cf = counterfactual_eval(cases, eval_set["taxonomy"], provider, audit, redact)
    passed = (acc["theme_accuracy"] >= THRESHOLDS["theme_accuracy"]
              and acc["sentiment_accuracy"] >= THRESHOLDS["sentiment_accuracy"]
              and all(d["pass"] for d in cf["dimensions"].values()))
    result = {"provider": provider.name, "model": provider.model, "redaction": redact,
              "thresholds": THRESHOLDS, "accuracy": acc, "counterfactual": cf, "overall_pass": passed}
    audit.record("eval.complete", {"provider": provider.name, "model": provider.model, "redaction": redact,
                                   "theme_accuracy": acc["theme_accuracy"], "sentiment_accuracy": acc["sentiment_accuracy"],
                                   "cf": {k: v["consistency"] for k, v in cf["dimensions"].items()},
                                   "overall_pass": passed}, actor="evaluator")
    return result


def to_markdown(r: dict) -> str:
    a, cf, th = r["accuracy"], r["counterfactual"], r["thresholds"]
    tick = lambda ok: "PASS" if ok else "FAIL"  # noqa: E731
    out = [f"# Evaluation: {r['provider']}/{r['model']} (redaction {'on' if r['redaction'] else 'off'})", "",
           f"**Overall: {tick(r['overall_pass'])}**", "", "## Accuracy (labelled synthetic set, n=%d)" % a["n"], "",
           "| Metric | Result | Threshold | |", "|---|---:|---:|---|",
           f"| Theme accuracy | {a['theme_accuracy']:.0%} | {th['theme_accuracy']:.0%} | {tick(a['theme_accuracy'] >= th['theme_accuracy'])} |",
           f"| Sentiment accuracy | {a['sentiment_accuracy']:.0%} | {th['sentiment_accuracy']:.0%} | {tick(a['sentiment_accuracy'] >= th['sentiment_accuracy'])} |",
           "", "| Theme | Precision | Recall | Support |", "|---|---:|---:|---:|"]
    for t, m in a["per_theme"].items():
        out.append(f"| {t} | {m['precision']} | {m['recall']} | {m['support']} |")
    out += ["", "## Counterfactual bias tests", "",
            f"Each variant changes only a name, gendered wording or English fluency. Pass = consistency ≥ {th['cf_consistency']:.0%} "
            f"and accuracy gap ≤ {th['cf_accuracy_gap']:.0%}.", "",
            "| Dimension | Pairs | Consistency | Accuracy gap | |", "|---|---:|---:|---:|---|"]
    for dim, d in cf["dimensions"].items():
        out.append(f"| {dim} | {d['n']} | {d['consistency']:.0%} | {d['accuracy_gap']:+.0%} | {tick(d['pass'])} |")
    if cf["flips"]:
        out += ["", "### Inconsistent outputs", "", "| Case | Dimension | Variant | Base | Variant got |", "|---|---|---|---|---|"]
        for f in cf["flips"]:
            out.append(f"| {f['case']} | {f['dimension']} | {f['variant']} | {' / '.join(f['base'])} | {' / '.join(f['variant_got'])} |")
    if a["errors"]:
        out += ["", "### Misclassified items", "", "| Item | Expected | Got | Rationale |", "|---|---|---|---|"]
        for e in a["errors"]:
            out.append(f"| {e['id']} | {' / '.join(e['expected'])} | {' / '.join(e['got'])} | {e['rationale']} |")
    return "\n".join(out) + "\n"
