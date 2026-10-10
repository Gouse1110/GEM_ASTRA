"""
tests/test_network_api.py
Tests for the /api/network bidder co-participation endpoint.

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


@pytest.fixture()
def empty_network_client(monkeypatch):
    """Client where load_bids returns an empty DataFrame."""
    import backend.routers.network as nm
    monkeypatch.setattr(nm, "_NETWORK", nm._build_network(
        pd.DataFrame(columns=["tender_id", "bidder_id", "bid_amount",
                               "bid_timestamp", "outcome", "product_category", "source_type"])
    ))
    from backend.main import app
    return TestClient(app)


# --------------------------------------------------------------------------- #
#  1. Endpoint availability and schema                                         #
# --------------------------------------------------------------------------- #

def test_network_endpoint_exists(client):
    r = client.get("/api/network")
    assert r.status_code == 200


def test_network_has_required_fields(client):
    data = client.get("/api/network").json()
    for field in ["nodes", "edges", "source_label", "disclaimer",
                  "total_bidders", "total_edges"]:
        assert field in data, f"Missing field: {field}"


def test_node_has_required_fields(client):
    data = client.get("/api/network").json()
    for node in data["nodes"]:
        assert "bidder_id" in node
        assert "tender_count" in node
        assert "source_type" in node


def test_edge_has_required_fields(client):
    data = client.get("/api/network").json()
    for edge in data["edges"]:
        assert "bidder_a" in edge
        assert "bidder_b" in edge
        assert "shared_tender_count" in edge
        assert "shared_tender_ids" in edge
        assert "source_type" in edge


# --------------------------------------------------------------------------- #
#  2. Correct counts from demo_bids.csv                                        #
# --------------------------------------------------------------------------- #

def test_bidder_count_matches_demo_data(client):
    """12 distinct bidders in demo_bids.csv."""
    data = client.get("/api/network").json()
    assert data["total_bidders"] == 12


def test_edge_count_matches_demo_data(client):
    """12 co-participation edges in demo_bids.csv."""
    data = client.get("/api/network").json()
    assert data["total_edges"] == 12


def test_total_fields_match_list_lengths(client):
    data = client.get("/api/network").json()
    assert data["total_bidders"] == len(data["nodes"])
    assert data["total_edges"] == len(data["edges"])


# --------------------------------------------------------------------------- #
#  3. Correct shared-tender counts                                             #
# --------------------------------------------------------------------------- #

def test_b001_b002_share_four_tenders(client):
    """B001 and B002 appear together in T001, T002, T003, T007."""
    data = client.get("/api/network").json()
    edge = next(
        (e for e in data["edges"]
         if set([e["bidder_a"], e["bidder_b"]]) == {"B001", "B002"}),
        None,
    )
    assert edge is not None, "Edge B001-B002 not found"
    assert edge["shared_tender_count"] == 4
    assert sorted(edge["shared_tender_ids"]) == ["T001", "T002", "T003", "T007"]


def test_b007_b008_share_one_tender(client):
    """B007 and B008 only appear together in T005."""
    data = client.get("/api/network").json()
    edge = next(
        (e for e in data["edges"]
         if set([e["bidder_a"], e["bidder_b"]]) == {"B007", "B008"}),
        None,
    )
    assert edge is not None, "Edge B007-B008 not found"
    assert edge["shared_tender_count"] == 1
    assert edge["shared_tender_ids"] == ["T005"]


def test_shared_tender_count_matches_ids_length(client):
    """shared_tender_count must equal len(shared_tender_ids) for every edge."""
    data = client.get("/api/network").json()
    for e in data["edges"]:
        assert e["shared_tender_count"] == len(e["shared_tender_ids"]), (
            f"Count mismatch on edge {e['bidder_a']}-{e['bidder_b']}"
        )


# --------------------------------------------------------------------------- #
#  4. No self-edges, no duplicate edges                                        #
# --------------------------------------------------------------------------- #

def test_no_self_edges(client):
    data = client.get("/api/network").json()
    for e in data["edges"]:
        assert e["bidder_a"] != e["bidder_b"], (
            f"Self-edge found: {e['bidder_a']}"
        )


def test_no_duplicate_edges(client):
    data = client.get("/api/network").json()
    seen = set()
    for e in data["edges"]:
        key = frozenset([e["bidder_a"], e["bidder_b"]])
        assert key not in seen, (
            f"Duplicate edge: {e['bidder_a']}-{e['bidder_b']}"
        )
        seen.add(key)


def test_edges_are_sorted_alphabetically(client):
    """bidder_a must be alphabetically before bidder_b in every edge."""
    data = client.get("/api/network").json()
    for e in data["edges"]:
        assert e["bidder_a"] < e["bidder_b"], (
            f"Edge not sorted: {e['bidder_a']}-{e['bidder_b']}"
        )


# --------------------------------------------------------------------------- #
#  5. Source labelling — must be synthetic                                     #
# --------------------------------------------------------------------------- #

def test_source_label_is_synthetic(client):
    data = client.get("/api/network").json()
    assert "synthetic" in data["source_label"].lower()


def test_all_node_source_types_are_synthetic(client):
    data = client.get("/api/network").json()
    for node in data["nodes"]:
        assert "synthetic" in node["source_type"].lower(), (
            f"Node {node['bidder_id']} has non-synthetic source_type: {node['source_type']}"
        )


def test_all_edge_source_types_are_synthetic(client):
    data = client.get("/api/network").json()
    for e in data["edges"]:
        assert "synthetic" in e["source_type"].lower(), (
            f"Edge {e['bidder_a']}-{e['bidder_b']} has non-synthetic source"
        )


def test_disclaimer_is_present(client):
    data = client.get("/api/network").json()
    assert len(data["disclaimer"]) > 20  # must be a real disclaimer, not empty


# --------------------------------------------------------------------------- #
#  6. Empty dataset                                                            #
# --------------------------------------------------------------------------- #

def test_empty_dataset_returns_zero_counts(empty_network_client):
    data = empty_network_client.get("/api/network").json()
    assert data["total_bidders"] == 0
    assert data["total_edges"] == 0
    assert data["nodes"] == []
    assert data["edges"] == []


# --------------------------------------------------------------------------- #
#  7. Missing bidder/tender identifiers                                        #
# --------------------------------------------------------------------------- #

def test_missing_bidder_ids_excluded(monkeypatch):
    """Rows with null/empty bidder_id must not create nodes or edges."""
    import backend.routers.network as nm
    df = pd.DataFrame([
        {"tender_id": "T1", "bidder_id": "B001", "bid_amount": 100,
         "bid_timestamp": "2024-01-01", "outcome": "won",
         "product_category": "laptops", "source_type": "synthetic_demo"},
        {"tender_id": "T1", "bidder_id": None, "bid_amount": 200,
         "bid_timestamp": "2024-01-01", "outcome": "lost",
         "product_category": "laptops", "source_type": "synthetic_demo"},
    ])
    result = nm._build_network(df)
    assert result.total_bidders == 1  # only B001
    assert result.total_edges == 0    # can't form a pair with 1 bidder


def test_missing_tender_ids_excluded(monkeypatch):
    """Rows with null tender_id must not create edges."""
    import backend.routers.network as nm
    df = pd.DataFrame([
        {"tender_id": "T1", "bidder_id": "B001", "bid_amount": 100,
         "bid_timestamp": "2024-01-01", "outcome": "won",
         "product_category": "laptops", "source_type": "synthetic_demo"},
        {"tender_id": None, "bidder_id": "B002", "bid_amount": 200,
         "bid_timestamp": "2024-01-01", "outcome": "lost",
         "product_category": "laptops", "source_type": "synthetic_demo"},
    ])
    result = nm._build_network(df)
    # B002's row has no tender_id — no shared tender with B001
    assert result.total_edges == 0


# --------------------------------------------------------------------------- #
#  8. Bidder detail endpoint                                                   #
# --------------------------------------------------------------------------- #

def test_bidder_detail_returns_correct_connections(client):
    r = client.get("/api/network/bidder/B001")
    assert r.status_code == 200
    data = r.json()
    assert data["bidder_id"] == "B001"
    # B001 connects to B002, B003, B004, B005 in demo data
    assert "B002" in data["connected_bidders"]
    assert len(data["edges"]) >= 4


def test_bidder_detail_404_for_unknown(client):
    r = client.get("/api/network/bidder/UNKNOWN_BIDDER")
    assert r.status_code == 404


def test_bidder_detail_no_self_in_connected(client):
    r = client.get("/api/network/bidder/B001")
    data = r.json()
    assert "B001" not in data["connected_bidders"]
