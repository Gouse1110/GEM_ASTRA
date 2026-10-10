"""
tests/test_summary_api.py
Tests for the /api/summary Overview dashboard endpoint.

Run with: python -m pytest tests/ -v
"""

import pytest
import pandas as pd
from fastapi.testclient import TestClient
from unittest.mock import patch


# --------------------------------------------------------------------------- #
#  Fixture                                                                     #
# --------------------------------------------------------------------------- #

@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Isolated DB for every test."""
    tmp_db = tmp_path / "test.db"
    import utils.database as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_db)
    db_mod.init_db()
    from backend.main import app
    return TestClient(app)


@pytest.fixture()
def seeded_client(client, monkeypatch):
    """Client with 2 tenders already in DB."""
    import utils.database as db_mod
    db_mod.import_tenders_from_df(pd.DataFrame([
        {"tender_id": "GEM/2026/B/1001", "item_name": "Laptop",
         "department": "MoE", "status": "active", "source_type": "real_public_data"},
        {"tender_id": "GEM/2026/B/1002", "item_name": "Printer",
         "department": "MoH", "status": "closed", "source_type": "real_public_data"},
    ]))
    return client


# --------------------------------------------------------------------------- #
#  1. Response schema                                                          #
# --------------------------------------------------------------------------- #

def test_summary_endpoint_exists(client):
    r = client.get("/api/summary")
    assert r.status_code == 200


def test_summary_has_required_fields(client):
    data = client.get("/api/summary").json()
    required = {
        "tender_count", "tender_source",
        "bid_record_count", "unique_bidder_count",
        "bid_source", "bid_source_label",
        "active_findings_count", "findings_source", "findings_source_label",
    }
    assert required <= set(data.keys()), f"Missing fields: {required - set(data.keys())}"


# --------------------------------------------------------------------------- #
#  2. Tender count                                                             #
# --------------------------------------------------------------------------- #

def test_tender_count_empty_db(client):
    data = client.get("/api/summary").json()
    assert data["tender_count"] == 0
    assert data["tender_source"] == "sqlite_db"


def test_tender_count_reflects_actual_rows(seeded_client):
    data = seeded_client.get("/api/summary").json()
    assert data["tender_count"] == 2


def test_tender_count_does_not_include_bid_rows(client):
    """Bid records must never be counted as tenders."""
    data = client.get("/api/summary").json()
    # The demo_bids.csv has 22 rows, none should appear in tender_count
    assert data["tender_count"] == 0


# --------------------------------------------------------------------------- #
#  3. Bid record count                                                        #
# --------------------------------------------------------------------------- #

def test_bid_record_count_is_int(client):
    data = client.get("/api/summary").json()
    assert isinstance(data["bid_record_count"], int)


def test_bid_record_count_matches_demo_bids_csv(client):
    """Count must equal the number of rows in demo_bids.csv."""
    from utils.data_loader import load_bids
    expected = len(load_bids())
    data = client.get("/api/summary").json()
    assert data["bid_record_count"] == expected


def test_bid_record_count_when_file_empty(client, monkeypatch):
    """When _BID_STATS is pre-computed with empty bids, bid_record_count is 0."""
    import backend.routers.summary as sm
    # Patch the pre-computed cache directly — _compute_bid_stats is tested separately
    monkeypatch.setattr(sm, "_BID_STATS", {
        "bid_record_count": 0,
        "unique_bidder_count": 0,
        "bid_source": "unknown",
        "bid_source_label": "unknown",
        "active_findings_count": 0,
        "findings_source": "unknown",
        "findings_source_label": "No bids",
    })
    data = client.get("/api/summary").json()
    assert data["bid_record_count"] == 0


# --------------------------------------------------------------------------- #
#  4. Unique bidder count                                                      #
# --------------------------------------------------------------------------- #

def test_unique_bidder_count_is_int(client):
    data = client.get("/api/summary").json()
    assert isinstance(data["unique_bidder_count"], int)


def test_unique_bidder_count_matches_demo_data(client):
    """Must match distinct non-empty bidder_ids in demo_bids.csv."""
    from utils.data_loader import load_bids
    bids = load_bids()
    expected = int(
        bids["bidder_id"].dropna().astype(str).str.strip()
        .replace("", None).dropna().nunique()
    )
    data = client.get("/api/summary").json()
    assert data["unique_bidder_count"] == expected


def test_unique_bidder_count_not_equal_to_bid_record_count(client):
    """Unique bidders must be fewer than total bid rows (multiple bids per bidder)."""
    data = client.get("/api/summary").json()
    assert data["unique_bidder_count"] < data["bid_record_count"]


def test_unique_bidder_count_ignores_missing_bidder_ids(client, monkeypatch):
    """_compute_bid_stats must not count null/empty bidder_ids."""
    from backend.routers.summary import _compute_bid_stats
    df = pd.DataFrame([
        {"tender_id": "T1", "bidder_id": "B001", "bid_amount": 100,
         "bid_timestamp": "2024-01-01", "outcome": "won",
         "product_category": "laptops", "source_type": "synthetic_demo"},
        {"tender_id": "T1", "bidder_id": None, "bid_amount": 200,
         "bid_timestamp": "2024-01-01", "outcome": "lost",
         "product_category": "laptops", "source_type": "synthetic_demo"},
        {"tender_id": "T1", "bidder_id": "", "bid_amount": 300,
         "bid_timestamp": "2024-01-01", "outcome": "lost",
         "product_category": "laptops", "source_type": "synthetic_demo"},
    ])
    monkeypatch.setattr("backend.routers.summary.load_bids", lambda: df)
    stats = _compute_bid_stats.__wrapped__(df) if hasattr(_compute_bid_stats, '__wrapped__') else None
    # Test via direct cache injection
    import backend.routers.summary as sm
    original = sm._BID_STATS
    try:
        # Recompute with patched load_bids
        sm._BID_STATS = sm._compute_bid_stats()
        data = client.get("/api/summary").json()
        assert data["unique_bidder_count"] == 1  # only B001 counts
    finally:
        sm._BID_STATS = original


# --------------------------------------------------------------------------- #
#  5. Source labels — synthetic data must be clearly identified               #
# --------------------------------------------------------------------------- #

def test_bid_source_is_synthetic(client):
    data = client.get("/api/summary").json()
    assert "synthetic" in data["bid_source"].lower()


def test_bid_source_label_mentions_synthetic(client):
    data = client.get("/api/summary").json()
    assert "synthetic" in data["bid_source_label"].lower()


def test_findings_source_label_mentions_synthetic(client):
    data = client.get("/api/summary").json()
    assert "synthetic" in data["findings_source_label"].lower()


# --------------------------------------------------------------------------- #
#  6. Active findings count                                                    #
# --------------------------------------------------------------------------- #

def test_active_findings_count_is_int(client):
    data = client.get("/api/summary").json()
    assert isinstance(data["active_findings_count"], int)


def test_active_findings_count_nonnegative(client):
    data = client.get("/api/summary").json()
    assert data["active_findings_count"] >= 0


def test_active_findings_count_matches_engine(client):
    """Count must equal actionable (non-insufficient_data) findings from the engine."""
    from utils.data_loader import load_bids
    from utils.risk_analysis_helpers import run_analysis_safe
    bids = load_bids()
    result, _ = run_analysis_safe(bids)
    expected = len([f for f in result.findings if not f.insufficient_data])
    data = client.get("/api/summary").json()
    assert data["active_findings_count"] == expected


def test_active_findings_zero_when_no_bids(client, monkeypatch):
    """When _BID_STATS is pre-computed with empty bids, active_findings_count is 0."""
    import backend.routers.summary as sm
    monkeypatch.setattr(sm, "_BID_STATS", {
        "bid_record_count": 0,
        "unique_bidder_count": 0,
        "bid_source": "unknown",
        "bid_source_label": "No bids",
        "active_findings_count": 0,
        "findings_source": "unknown",
        "findings_source_label": "No bids",
    })
    data = client.get("/api/summary").json()
    assert data["active_findings_count"] == 0


def test_compute_bid_stats_with_empty_df():
    """_compute_bid_stats must return 0 counts when given an empty bids file."""
    import backend.routers.summary as sm
    original_load = sm.load_bids
    try:
        sm.load_bids = lambda: pd.DataFrame(
            columns=["tender_id", "bidder_id", "bid_amount",
                     "bid_timestamp", "outcome", "product_category", "source_type"]
        )
        stats = sm._compute_bid_stats()
        assert stats["bid_record_count"] == 0
        assert stats["unique_bidder_count"] == 0
        assert stats["active_findings_count"] == 0
    finally:
        sm.load_bids = original_load


# --------------------------------------------------------------------------- #
#  7. Source separation — tender count must not bleed into bid count          #
# --------------------------------------------------------------------------- #

def test_tender_source_is_sqlite(client):
    data = client.get("/api/summary").json()
    assert data["tender_source"] == "sqlite_db"


def test_tenders_and_bids_are_independent(seeded_client):
    """Adding real tenders must not change the bid or findings counts."""
    data = seeded_client.get("/api/summary").json()
    from utils.data_loader import load_bids
    from utils.risk_analysis_helpers import run_analysis_safe
    bids = load_bids()
    result, _ = run_analysis_safe(bids)
    expected_findings = len([f for f in result.findings if not f.insufficient_data])

    assert data["tender_count"] == 2
    assert data["bid_record_count"] == len(bids)
    assert data["active_findings_count"] == expected_findings
