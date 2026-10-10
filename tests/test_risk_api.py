"""
tests/test_risk_api.py
Tests for the /api/risk FastAPI endpoint.

Run with: python -m pytest tests/ -v
"""

import pytest
import pandas as pd
from fastapi.testclient import TestClient


# --------------------------------------------------------------------------- #
#  Fixture                                                                     #
# --------------------------------------------------------------------------- #

@pytest.fixture()
def client():
    from backend.main import app
    return TestClient(app)


# --------------------------------------------------------------------------- #
#  1. Endpoint availability and schema                                         #
# --------------------------------------------------------------------------- #

def test_risk_endpoint_exists(client):
    r = client.get("/api/risk")
    assert r.status_code == 200


def test_risk_response_has_required_fields(client):
    data = client.get("/api/risk").json()
    assert "summary" in data
    assert "findings" in data
    assert "source_label" in data
    assert "disclaimer" in data


def test_summary_has_required_fields(client):
    summary = client.get("/api/risk").json()["summary"]
    for field in [
        "score", "score_band", "score_explanation",
        "total_bids_analysed", "actionable_findings_count",
        "rules_fired", "source_type", "real_data_available", "warnings",
    ]:
        assert field in summary, f"Missing field: {field}"


def test_finding_has_required_fields(client):
    findings = client.get("/api/risk").json()["findings"]
    assert len(findings) > 0
    for f in findings:
        for field in [
            "rule", "rule_name", "tender_ids", "bidder_ids",
            "evidence", "threshold_or_criterion", "explanation",
            "source_type", "data_limitations", "insufficient_data",
        ]:
            assert field in f, f"Finding missing field: {field}"


# --------------------------------------------------------------------------- #
#  2. Correct engine output from demo_bids.csv                                #
# --------------------------------------------------------------------------- #

def test_score_is_in_valid_range(client):
    summary = client.get("/api/risk").json()["summary"]
    assert 0 <= summary["score"] <= 100


def test_score_band_is_valid(client):
    band = client.get("/api/risk").json()["summary"]["score_band"]
    assert band in {"Low", "Moderate", "Elevated", "High"}


def test_actionable_findings_count_matches_list(client):
    data = client.get("/api/risk").json()
    actionable_in_list = sum(1 for f in data["findings"] if not f["insufficient_data"])
    assert data["summary"]["actionable_findings_count"] == actionable_in_list


def test_total_bids_analysed_is_positive(client):
    summary = client.get("/api/risk").json()["summary"]
    assert summary["total_bids_analysed"] > 0


def test_rules_fired_contains_a_and_b(client):
    """demo_bids.csv triggers Rule A and Rule B."""
    rules = client.get("/api/risk").json()["summary"]["rules_fired"]
    assert "A" in rules
    assert "B" in rules


# --------------------------------------------------------------------------- #
#  3. Synthetic source labelling                                               #
# --------------------------------------------------------------------------- #

def test_source_label_mentions_synthetic(client):
    label = client.get("/api/risk").json()["source_label"]
    assert "synthetic" in label.lower()


def test_all_findings_have_source_type(client):
    findings = client.get("/api/risk").json()["findings"]
    for f in findings:
        if not f["insufficient_data"]:
            assert f["source_type"], f"Finding {f['rule']} has empty source_type"


def test_real_data_available_is_false_for_synthetic(client):
    """demo_bids.csv is synthetic — real_data_available must be False."""
    summary = client.get("/api/risk").json()["summary"]
    assert summary["real_data_available"] is False


def test_disclaimer_is_present(client):
    disclaimer = client.get("/api/risk").json()["disclaimer"]
    assert len(disclaimer) > 20


# --------------------------------------------------------------------------- #
#  4. Rule D always present as insufficient data                              #
# --------------------------------------------------------------------------- #

def test_rule_d_present_and_insufficient(client):
    findings = client.get("/api/risk").json()["findings"]
    d_findings = [f for f in findings if f["rule"] == "D"]
    assert len(d_findings) >= 1
    assert all(f["insufficient_data"] for f in d_findings)


# --------------------------------------------------------------------------- #
#  5. Filtered findings endpoint                                               #
# --------------------------------------------------------------------------- #

def test_findings_endpoint_exists(client):
    r = client.get("/api/risk/findings")
    assert r.status_code == 200


def test_findings_endpoint_excludes_insufficient_by_default(client):
    findings = client.get("/api/risk/findings").json()
    assert not any(f["insufficient_data"] for f in findings)


def test_findings_endpoint_includes_insufficient_when_requested(client):
    findings = client.get("/api/risk/findings?include_insufficient=true").json()
    assert any(f["insufficient_data"] for f in findings)


def test_findings_endpoint_filter_by_rule_a(client):
    findings = client.get("/api/risk/findings?rule=A").json()
    assert all(f["rule"] == "A" for f in findings)
    assert len(findings) > 0


def test_findings_endpoint_filter_by_rule_b(client):
    findings = client.get("/api/risk/findings?rule=B").json()
    assert all(f["rule"] == "B" for f in findings)


def test_findings_endpoint_unknown_rule_returns_empty(client):
    findings = client.get("/api/risk/findings?rule=Z").json()
    assert findings == []


# --------------------------------------------------------------------------- #
#  6. Empty data handling                                                      #
# --------------------------------------------------------------------------- #

def test_empty_bids_returns_safe_response(monkeypatch):
    import backend.routers.risk as rm
    empty_df = pd.DataFrame(
        columns=["tender_id", "bidder_id", "bid_amount",
                 "bid_timestamp", "outcome", "product_category", "source_type"]
    )
    monkeypatch.setattr(rm, "_RISK", rm._build_risk_response.__wrapped__(empty_df)
                        if hasattr(rm._build_risk_response, "__wrapped__")
                        else rm._build_risk_response())
    # Even with no bids, the endpoint must return 200
    from backend.main import app
    c = TestClient(app)
    r = c.get("/api/risk")
    assert r.status_code == 200


def test_risk_precomputed_score_is_nonzero(client):
    """With demo_bids.csv loaded, score must be > 0."""
    score = client.get("/api/risk").json()["summary"]["score"]
    assert score > 0


# --------------------------------------------------------------------------- #
#  7. Evidence fields for Rule A                                               #
# --------------------------------------------------------------------------- #

def test_rule_a_evidence_has_pairs(client):
    findings = client.get("/api/risk/findings?rule=A").json()
    for f in findings:
        assert "pairs" in f["evidence"], "Rule A finding missing 'pairs' evidence"
        assert isinstance(f["evidence"]["pairs"], list)
        assert len(f["evidence"]["pairs"]) > 0


def test_rule_a_evidence_pairs_have_correct_fields(client):
    findings = client.get("/api/risk/findings?rule=A").json()
    for f in findings:
        for pair in f["evidence"]["pairs"]:
            for key in ["bidder_a", "bidder_b", "bid_a", "bid_b", "diff_pct"]:
                assert key in pair, f"Pair missing '{key}'"


# --------------------------------------------------------------------------- #
#  8. Score determinism                                                        #
# --------------------------------------------------------------------------- #

def test_score_is_deterministic(client):
    r1 = client.get("/api/risk").json()["summary"]["score"]
    r2 = client.get("/api/risk").json()["summary"]["score"]
    assert r1 == r2
