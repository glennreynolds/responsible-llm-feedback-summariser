import json
from pathlib import Path

import pytest

from heartbeat_insights.audit import AuditLog
from heartbeat_insights.evaluate import run_all
from heartbeat_insights.models import Response, load_responses
from heartbeat_insights.pipeline import PolicyError, classify, discover, prepare
from heartbeat_insights.privacy import gate_groups
from heartbeat_insights.providers import MockBiasedProvider, MockProvider
from heartbeat_insights.providers.base import Completion
from heartbeat_insights.redact import DEFAULT_ROSTER, Redactor
from heartbeat_insights.report import build_report
from heartbeat_insights.review import apply_decisions
from heartbeat_insights.validate import ValidationError, validate_classify, validate_discover

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def audit(tmp_path):
    return AuditLog(tmp_path / "audit.jsonl")


@pytest.fixture
def responses():
    return load_responses(DATA / "synthetic_responses.csv")


# --- privacy -------------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("call me on 0412 345 678", "call me on [PHONE]"),
    ("ring +61 3 9123 4567 please", "ring [PHONE] please"),
    ("email jess.k@example.com", "email [EMAIL]"),
    ("my manager Dave said", "my manager [NAME] said"),
    ("thanks Mohammed", "thanks [NAME]"),
    ("staff id P123456", "staff id [STAFF_ID]"),
])
def test_redaction(text, expected):
    assert Redactor(DEFAULT_ROSTER).redact(text).text == expected


def test_redaction_leaves_ordinary_text_alone():
    text = "The build pipeline is slow and my manager explained the priorities."
    assert Redactor(DEFAULT_ROSTER).redact(text).text == text


def test_small_groups_are_suppressed_before_analysis(responses):
    kept, suppressed = gate_groups(responses, k=5)
    assert suppressed == ["Release Ops"]
    assert all(r.team != "Release Ops" for r in kept)


def test_no_pii_reaches_the_model(responses):
    prep = prepare(responses)
    blob = json.dumps(prep.comments)
    for needle in ["0412", "jess.k@", "Dave", "Priya", "Mohammed"]:
        assert needle not in blob


def test_cloud_provider_refuses_unredacted_text(responses, audit):
    class FakeCloud(MockProvider):
        name, data_leaves_machine = "fake-cloud", True
    with pytest.raises(PolicyError):
        discover(responses, FakeCloud(), audit, redact=False)


# --- output guardrails ---------------------------------------------------------------------

def test_fabricated_citation_is_rejected():
    data = {"themes": [{"title": "Workload", "description": "d", "sentiment": "negative",
                        "comment_ids": ["HB-001", "HB-999"], "representative_comment_id": "HB-001"}]}
    with pytest.raises(ValidationError, match="unknown comment ids"):
        validate_discover(data, {"HB-001"}, Redactor(DEFAULT_ROSTER))


def test_pii_in_model_output_is_rejected():
    data = {"classifications": [{"comment_id": "A", "theme_id": "t", "sentiment": "negative",
                                 "rationale": "Dave is overloaded"}]}
    with pytest.raises(ValidationError, match="personal information"):
        validate_classify(data, {"A"}, {"t"}, Redactor(DEFAULT_ROSTER))


def test_every_comment_must_be_classified_once():
    data = {"classifications": [{"comment_id": "A", "theme_id": "t", "sentiment": "mixed", "rationale": "x"}]}
    with pytest.raises(ValidationError, match="not classified"):
        validate_classify(data, {"A", "B"}, {"t"}, Redactor(DEFAULT_ROSTER))


def test_invalid_output_retries_then_fails_closed(responses, audit):
    class Broken(MockProvider):
        def complete(self, system, user, max_tokens=4000):
            return Completion("not json at all", "broken", "x")
    with pytest.raises(ValidationError, match="fail closed"):
        discover(responses, Broken(), audit)
    events = [json.loads(line) for line in audit.path.read_text().splitlines()]
    assert [e["data"]["status"] for e in events if e["event"] == "discover.model_call"] == ["invalid", "invalid"]


# --- human oversight -----------------------------------------------------------------------

def test_classify_requires_human_approved_taxonomy(responses, audit):
    draft = discover(responses, MockProvider(), audit)
    with pytest.raises(PolicyError):
        classify(responses, draft, MockProvider(), audit)


def test_unreviewed_themes_are_rejected_by_default(responses, audit):
    draft = discover(responses, MockProvider(), audit)
    first = draft["themes"][0]["id"]
    tax = apply_decisions(draft, {first: {"decision": "approve"}}, "Reviewer", audit)
    assert [t["id"] for t in tax["themes"]] == [first]
    assert len(tax["rejected"]) == len(draft["themes"]) - 1


def test_end_to_end_report(responses, audit):
    draft = discover(responses, MockProvider(), audit)
    tax = apply_decisions(draft, {t["id"]: {"decision": "approve"} for t in draft["themes"]}, "Reviewer", audit)
    out = classify(responses, tax, MockProvider(), audit)
    report = build_report(out, audit, "Reviewer")
    assert "Release Ops" in report and "Suppressed" in report
    assert "Dave" not in report and "0412" not in report
    assert audit.verify()[0]


# --- auditability --------------------------------------------------------------------------

def test_audit_log_detects_tampering(audit):
    for i in range(3):
        audit.record("x", {"i": i}, "tester")
    assert audit.verify()[0]
    lines = audit.path.read_text().splitlines()
    rec = json.loads(lines[1])
    rec["data"]["i"] = 99
    lines[1] = json.dumps(rec)
    audit.path.write_text("\n".join(lines) + "\n")
    ok, msg = audit.verify()
    assert not ok and "line 2" in msg


def test_audit_log_detects_deleted_record(audit):
    for i in range(3):
        audit.record("x", {"i": i}, "tester")
    lines = audit.path.read_text().splitlines()
    audit.path.write_text("\n".join([lines[0], lines[2]]) + "\n")
    assert not audit.verify()[0]


# --- bias testing --------------------------------------------------------------------------

def test_bias_harness_passes_fair_model(audit):
    assert run_all(DATA, MockProvider(), audit)["overall_pass"]


def test_bias_harness_catches_biased_model(audit):
    res = run_all(DATA, MockBiasedProvider(), audit)
    assert not res["overall_pass"]
    assert not res["counterfactual"]["dimensions"]["english_fluency"]["pass"]
    assert res["counterfactual"]["dimensions"]["name"]["pass"]
