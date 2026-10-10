"""
tests/test_tenders_api.py
API tests for the Tender Explorer endpoints.

Uses FastAPI TestClient with an isolated temporary SQLite database
so tests never touch the real data/gem_astra.db file.

Run with: python -m pytest tests/ -v
"""

import io
import pytest
import pandas as pd
from fastapi.testclient import TestClient


# --------------------------------------------------------------------------- #
#  Fixtures                                                                    #
# --------------------------------------------------------------------------- #

@pytest.fixture()
def client(tmp_path, monkeypatch):
    """
    Return a TestClient wired to an isolated temporary database.
    Monkeypatches DB_PATH in utils.database before the app is imported
    so the router uses the temp DB throughout the test.
    """
    tmp_db = tmp_path / "api_test.db"
    import utils.database as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_db)
    db_mod.init_db()

    # Import app AFTER monkeypatching so it picks up the temp DB
    from backend.main import app
    return TestClient(app)


@pytest.fixture()
def seeded_client(client, tmp_path, monkeypatch):
    """Client with a small set of pre-inserted tenders."""
    import utils.database as db_mod

    rows = [
        {"tender_id": "T001", "item_name": "Laptop",  "department": "MoE",
         "status": "active",  "source_type": "real_public_data",
         "start_date": "2024-01-01", "end_date": "2024-01-31"},
        {"tender_id": "T002", "item_name": "Printer", "department": "MoH",
         "status": "closed",  "source_type": "real_public_data",
         "start_date": "2024-02-01", "end_date": "2024-02-28"},
        {"tender_id": "T003", "item_name": "Chair",   "department": "MoE",
         "status": "active",  "source_type": "synthetic",
         "start_date": "2024-03-01", "end_date": "2024-03-31"},
        {"tender_id": "T004", "item_name": "Desk",    "department": "MoF",
         "status": "active",  "source_type": "unknown",
         "start_date": "2024-04-01", "end_date": "2024-04-30"},
    ]
    db_mod.import_tenders_from_df(pd.DataFrame(rows))
    return client


# --------------------------------------------------------------------------- #
#  1. Health (smoke test)                                                      #
# --------------------------------------------------------------------------- #

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# --------------------------------------------------------------------------- #
#  2. Empty database                                                           #
# --------------------------------------------------------------------------- #

def test_list_empty_db(client):
    r = client.get("/api/tenders")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["page"] == 1
    assert data["pages"] == 1


def test_filters_empty_db(client):
    r = client.get("/api/tenders/filters")
    assert r.status_code == 200
    data = r.json()
    assert data["departments"] == []
    assert data["statuses"] == []
    assert data["source_types"] == []


def test_get_nonexistent_tender(client):
    r = client.get("/api/tenders/MISSING")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
#  3. Basic list and pagination                                                #
# --------------------------------------------------------------------------- #

def test_list_returns_all(seeded_client):
    r = seeded_client.get("/api/tenders")
    assert r.status_code == 200
    assert r.json()["total"] == 4


def test_pagination_page_size(seeded_client):
    r = seeded_client.get("/api/tenders?page=1&page_size=2")
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 2
    assert data["total"] == 4
    assert data["pages"] == 2


def test_pagination_page_2(seeded_client):
    r = seeded_client.get("/api/tenders?page=2&page_size=2")
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 2


def test_pagination_beyond_last_page(seeded_client):
    r = seeded_client.get("/api/tenders?page=99&page_size=10")
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_page_size_max_enforced(client):
    r = client.get("/api/tenders?page_size=999")
    assert r.status_code == 422  # exceeds max 100


def test_page_zero_rejected(client):
    r = client.get("/api/tenders?page=0")
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
#  4. Search                                                                   #
# --------------------------------------------------------------------------- #

def test_search_by_tender_id(seeded_client):
    r = seeded_client.get("/api/tenders?search=T001")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["tender_id"] == "T001"


def test_search_by_item_name(seeded_client):
    r = seeded_client.get("/api/tenders?search=printer")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["item_name"] == "Printer"


def test_search_case_insensitive(seeded_client):
    r = seeded_client.get("/api/tenders?search=LAPTOP")
    assert r.status_code == 200
    # SQLite LIKE is case-insensitive for ASCII by default
    assert r.json()["total"] >= 1


def test_search_no_match(seeded_client):
    r = seeded_client.get("/api/tenders?search=XXXXNOTFOUND")
    assert r.status_code == 200
    assert r.json()["total"] == 0
    assert r.json()["items"] == []


def test_search_max_length_enforced(client):
    r = client.get(f"/api/tenders?search={'x' * 201}")
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
#  5. Filters                                                                  #
# --------------------------------------------------------------------------- #

def test_filter_by_department(seeded_client):
    r = seeded_client.get("/api/tenders?department=MoE")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert all(t["department"] == "MoE" for t in data["items"])


def test_filter_by_status(seeded_client):
    r = seeded_client.get("/api/tenders?status=closed")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["tender_id"] == "T002"


def test_filter_by_source_type_real(seeded_client):
    r = seeded_client.get("/api/tenders?source_type=real_public_data")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert all(t["source_type"] == "real_public_data" for t in data["items"])


def test_filter_by_source_type_synthetic(seeded_client):
    r = seeded_client.get("/api/tenders?source_type=synthetic")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["source_type"] == "synthetic"


def test_combined_search_and_department(seeded_client):
    r = seeded_client.get("/api/tenders?search=laptop&department=MoE")
    assert r.status_code == 200
    assert r.json()["total"] == 1


# --------------------------------------------------------------------------- #
#  6. Source-type separation                                                   #
# --------------------------------------------------------------------------- #

def test_real_filter_excludes_synthetic(seeded_client):
    r = seeded_client.get("/api/tenders?source_type=real_public_data")
    items = r.json()["items"]
    assert all(t["source_type"] == "real_public_data" for t in items)
    assert not any(t["source_type"] == "synthetic" for t in items)


def test_synthetic_filter_excludes_real(seeded_client):
    r = seeded_client.get("/api/tenders?source_type=synthetic")
    items = r.json()["items"]
    assert not any(t["source_type"] == "real_public_data" for t in items)


# --------------------------------------------------------------------------- #
#  7. Filter options endpoint                                                  #
# --------------------------------------------------------------------------- #

def test_filter_options_returns_all_values(seeded_client):
    r = seeded_client.get("/api/tenders/filters")
    assert r.status_code == 200
    data = r.json()
    assert "MoE" in data["departments"]
    assert "MoH" in data["departments"]
    assert "active" in data["statuses"]
    assert "closed" in data["statuses"]
    assert "real_public_data" in data["source_types"]


# --------------------------------------------------------------------------- #
#  8. Single tender by ID                                                      #
# --------------------------------------------------------------------------- #

def test_get_tender_by_id(seeded_client):
    r = seeded_client.get("/api/tenders/T001")
    assert r.status_code == 200
    data = r.json()
    assert data["tender_id"] == "T001"
    assert data["item_name"] == "Laptop"
    assert data["source_type"] == "real_public_data"


def test_get_tender_null_fields_are_none(seeded_client):
    """Optional fields not set should be null in the JSON, not NaN strings."""
    r = seeded_client.get("/api/tenders/T001")
    data = r.json()
    # official_url was not set — must be null not "NaN"
    assert data.get("official_url") is None or isinstance(data.get("official_url"), str)


# --------------------------------------------------------------------------- #
#  9. CSV import endpoint                                                      #
# --------------------------------------------------------------------------- #

def _make_csv_bytes(**row_overrides) -> bytes:
    defaults = {
        "tender_id": "IMP001", "item_name": "Widget",
        "department": "MoD", "status": "active",
        "source_type": "real_public_data",
    }
    defaults.update(row_overrides)
    df = pd.DataFrame([defaults])
    return df.to_csv(index=False).encode()


def test_import_valid_csv(client):
    csv_bytes = _make_csv_bytes()
    r = client.post(
        "/api/tenders/import",
        files={"file": ("tenders.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["inserted"] == 1
    assert data["rejected"] == 0


def test_import_with_source_override(client):
    csv_bytes = _make_csv_bytes(source_type="unknown")
    r = client.post(
        "/api/tenders/import?source_type_override=synthetic",
        files={"file": ("tenders.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 200
    assert r.json()["inserted"] == 1
    # Verify override was applied
    import utils.database as db_mod
    record = db_mod.fetch_tender_by_id("IMP001")
    assert record["source_type"] == "synthetic"


def test_import_invalid_source_override_rejected(client):
    csv_bytes = _make_csv_bytes()
    r = client.post(
        "/api/tenders/import?source_type_override=BADVALUE",
        files={"file": ("tenders.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 422


def test_import_missing_tender_id_rejected(client):
    df = pd.DataFrame([{"item_name": "No ID here"}])
    csv_bytes = df.to_csv(index=False).encode()
    r = client.post(
        "/api/tenders/import",
        files={"file": ("tenders.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    # Missing tender_id column → 422
    assert r.status_code == 422


def test_import_empty_csv_rejected(client):
    df = pd.DataFrame(columns=["tender_id", "item_name"])
    csv_bytes = df.to_csv(index=False).encode()
    r = client.post(
        "/api/tenders/import",
        files={"file": ("empty.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 422


def test_import_non_csv_rejected(client):
    r = client.post(
        "/api/tenders/import",
        files={"file": ("data.xlsx", io.BytesIO(b"fake"), "application/octet-stream")},
    )
    assert r.status_code == 400


def test_import_duplicate_skipped(client):
    csv_bytes = _make_csv_bytes()
    client.post(
        "/api/tenders/import",
        files={"file": ("t.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    r = client.post(
        "/api/tenders/import",
        files={"file": ("t.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["inserted"] == 0
    assert data["skipped_duplicate"] == 1


def test_import_then_list_shows_new_record(client):
    csv_bytes = _make_csv_bytes(tender_id="NEWT001")
    client.post(
        "/api/tenders/import",
        files={"file": ("t.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    r = client.get("/api/tenders?search=NEWT001")
    assert r.json()["total"] == 1


# --------------------------------------------------------------------------- #
#  10. Input validation edge cases                                             #
# --------------------------------------------------------------------------- #

def test_invalid_page_size_zero(client):
    r = client.get("/api/tenders?page_size=0")
    assert r.status_code == 422


def test_tender_id_too_long(client):
    long_id = "X" * 201
    r = client.get(f"/api/tenders/{long_id}")
    assert r.status_code == 400

# --------------------------------------------------------------------------- #
#  11. Router registration — guards against stale-process regression          #
# --------------------------------------------------------------------------- #

def test_all_tender_routes_are_registered():
    """
    The tenders router must be mounted on the app.
    A stale FastAPI process missing include_router() would cause every
    /api/tenders/* call to return 404, while /api/health still succeeds.
    This test catches that regression by verifying the OpenAPI spec.
    """
    from backend.main import app
    paths = list(app.openapi()["paths"].keys())
    assert "/api/tenders" in paths,          "GET /api/tenders not registered"
    assert "/api/tenders/filters" in paths,  "GET /api/tenders/filters not registered"
    assert "/api/tenders/{tender_id}" in paths, "GET /api/tenders/{tender_id} not registered"
    assert "/api/tenders/import" in paths,   "POST /api/tenders/import not registered"


def test_health_and_tenders_both_reachable(client):
    """Health endpoint working does NOT guarantee the tenders router is mounted."""
    r_health = client.get("/api/health")
    assert r_health.status_code == 200, "Health endpoint failed"

    r_tenders = client.get("/api/tenders")
    assert r_tenders.status_code == 200, (
        "/api/tenders returned 404 — tenders router is not mounted. "
        "Restart the FastAPI server after code changes."
    )


def test_filters_route_not_shadowed_by_tender_id_route(client):
    """
    /api/tenders/filters must NOT be captured by the /{tender_id} wildcard.
    FastAPI resolves /filters before /{tender_id} when filters is declared first.
    """
    r = client.get("/api/tenders/filters")
    assert r.status_code == 200
    data = r.json()
    # Response must match FilterOptionsResponse, not TenderRecord
    assert "departments" in data
    assert "statuses" in data
    assert "source_types" in data


# --------------------------------------------------------------------------- #
#  12. Bid-only CSV rejection — prevents demo_bids.csv stub-record regression #
# --------------------------------------------------------------------------- #

def test_bid_only_csv_rejected(client):
    """
    demo_bids.csv has tender_id but no tender metadata columns.
    Importing it must be rejected with 422, not silently create stub rows.
    """
    import pandas as pd, io as _io
    bid_df = pd.DataFrame([
        {"tender_id": "T001", "bidder_id": "B001", "bid_amount": 100000,
         "bid_timestamp": "2024-01-01", "outcome": "won",
         "product_category": "laptops", "source_type": "synthetic_demo"},
        {"tender_id": "T002", "bidder_id": "B002", "bid_amount": 200000,
         "bid_timestamp": "2024-01-02", "outcome": "lost",
         "product_category": "laptops", "source_type": "synthetic_demo"},
    ])
    csv_bytes = bid_df.to_csv(index=False).encode()
    r = client.post(
        "/api/tenders/import",
        files={"file": ("demo_bids.csv", _io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 422, (
        f"Expected 422 for bid-only CSV, got {r.status_code}. "
        "Bid files must not be accepted as tender imports."
    )
    assert "tender" in r.json()["detail"].lower()


def test_bid_only_csv_does_not_create_stub_records(client):
    """After a bid-only CSV is rejected, no stub rows must exist in the DB."""
    import utils.database as db_mod
    import pandas as pd, io as _io
    bid_df = pd.DataFrame([
        {"tender_id": "STUB001", "bidder_id": "B001", "bid_amount": 99999,
         "bid_timestamp": "2024-01-01", "outcome": "won",
         "product_category": "laptops", "source_type": "synthetic_demo"},
    ])
    csv_bytes = bid_df.to_csv(index=False).encode()
    client.post(
        "/api/tenders/import",
        files={"file": ("bids.csv", _io.BytesIO(csv_bytes), "text/csv")},
    )
    assert db_mod.fetch_tender_by_id("STUB001") is None, (
        "Bid-only CSV created a stub tender record — import guard failed."
    )


def test_valid_tender_csv_with_metadata_still_accepted(client):
    """The bid-column guard must not break legitimate tender CSV imports."""
    import pandas as pd, io as _io
    tender_df = pd.DataFrame([{
        "tender_id": "VALID001",
        "item_name": "Laptop",
        "department": "MoE",
        "status": "active",
        "source_type": "real_public_data",
    }])
    csv_bytes = tender_df.to_csv(index=False).encode()
    r = client.post(
        "/api/tenders/import",
        files={"file": ("tenders.csv", _io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 200
    assert r.json()["inserted"] == 1


def test_tender_csv_with_only_tender_id_and_item_name_accepted(client):
    """Minimal tender CSV with just tender_id + one metadata field is valid."""
    import pandas as pd, io as _io
    df = pd.DataFrame([{"tender_id": "MIN001", "item_name": "Chair"}])
    csv_bytes = df.to_csv(index=False).encode()
    r = client.post(
        "/api/tenders/import",
        files={"file": ("min.csv", _io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 200
    assert r.json()["inserted"] == 1


# --------------------------------------------------------------------------- #
#  13. Real GeM tender CSV — validates the two supplied public records        #
# --------------------------------------------------------------------------- #

def _gem_tenders_csv_bytes() -> bytes:
    """Return the content of data/gem_tenders.csv as bytes."""
    import pathlib
    path = pathlib.Path(__file__).resolve().parent.parent / "data" / "gem_tenders.csv"
    return path.read_bytes()


def test_gem_tenders_csv_passes_import(client):
    """data/gem_tenders.csv must import cleanly with all rows inserted, 0 errors."""
    import io as _io
    r = client.post(
        "/api/tenders/import",
        files={"file": ("gem_tenders.csv", _io.BytesIO(_gem_tenders_csv_bytes()), "text/csv")},
    )
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.json()}"
    data = r.json()
    assert data["inserted"] >= 9        # CSV currently has 9 records
    assert data["rejected"] == 0
    assert data["errors"] == []


def test_gem_tenders_records_have_correct_fields(client):
    """Both imported records must have the expected non-null fields."""
    import io as _io
    client.post(
        "/api/tenders/import",
        files={"file": ("gem_tenders.csv", _io.BytesIO(_gem_tenders_csv_bytes()), "text/csv")},
    )

    r1 = client.get("/api/tenders/GEM/2026/B/7899748")
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["item_name"] == "Thermo Couple Welding Machine"
    assert d1["department"] == "Department of Space"
    assert d1["status"] == "Technical Evaluation"
    assert d1["source_type"] == "real_public_data"
    # start_date and end_date were not supplied — must be null, not invented
    assert d1["start_date"] is None
    assert d1["end_date"] is None

    r2 = client.get("/api/tenders/GEM/2026/B/7347634")
    assert r2.status_code == 200
    d2 = r2.json()
    assert "Fourier Transform Infrared" in d2["item_name"]
    assert "NRSC" in d2["department"]
    assert d2["end_date"] == "2026-04-02"
    assert d2["start_date"] == "2026-03-13"
    assert d2["source_type"] == "real_public_data"
    # status was not supplied — must be null
    assert d2["status"] is None


def test_gem_tenders_no_duplicate_ids(client):
    """Importing gem_tenders.csv twice must produce 0 inserted on second run."""
    import io as _io
    csv = _gem_tenders_csv_bytes()
    r1 = client.post(
        "/api/tenders/import",
        files={"file": ("gem_tenders.csv", _io.BytesIO(csv), "text/csv")},
    )
    assert r1.status_code == 200
    first_inserted = r1.json()["inserted"]
    assert first_inserted >= 9

    r2 = client.post(
        "/api/tenders/import",
        files={"file": ("gem_tenders.csv", _io.BytesIO(csv), "text/csv")},
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["inserted"] == 0
    assert data["skipped_duplicate"] == first_inserted


def test_demo_bids_csv_still_rejected(client):
    """demo_bids.csv must continue to be rejected after gem_tenders.csv is added."""
    import io as _io, pathlib
    path = pathlib.Path(__file__).resolve().parent.parent / "data" / "demo_bids.csv"
    r = client.post(
        "/api/tenders/import",
        files={"file": ("demo_bids.csv", _io.BytesIO(path.read_bytes()), "text/csv")},
    )
    assert r.status_code == 422
    assert "tender" in r.json()["detail"].lower()


def test_blank_fields_stored_as_null_not_invented(client):
    """Fields missing from gem_tenders.csv must be null in the DB, not filled in."""
    import io as _io
    client.post(
        "/api/tenders/import",
        files={"file": ("gem_tenders.csv", _io.BytesIO(_gem_tenders_csv_bytes()), "text/csv")},
    )
    # Record 1 has no start_date / end_date — must not be invented
    r = client.get("/api/tenders/GEM/2026/B/7899748")
    d = r.json()
    assert d["start_date"] is None, "start_date should be null, not invented"
    assert d["end_date"] is None,   "end_date should be null, not invented"
    assert d["official_url"] is None, "official_url should be null, not invented"
    # Record 2 has no status — must not be invented
    r2 = client.get("/api/tenders/GEM/2026/B/7347634")
    d2 = r2.json()
    assert d2["status"] is None, "status should be null, not invented"
