"""
tests/test_schema_migration.py
Tests for Step 1 schema additions and tenders migration.

Verifies:
- All new tables are created
- All new columns on tenders are added safely
- Existing 9 real tender records are preserved
- Foreign-key enforcement works
- Migration is idempotent
- New table constraints are enforced

Run with: python -m pytest tests/test_schema_migration.py -v
"""

import pytest
import sqlite3
import pandas as pd
from pathlib import Path


# --------------------------------------------------------------------------- #
#  Fixtures                                                                    #
# --------------------------------------------------------------------------- #

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Each test gets a fresh isolated database."""
    tmp_db = tmp_path / "test_schema.db"
    import utils.database as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_db)
    db_mod.init_db()
    yield tmp_db


def get_tables(conn):
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}


def get_columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def get_indexes(conn, table=None):
    if table:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?",
            (table,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    return {r[0] for r in rows}


# --------------------------------------------------------------------------- #
#  1. All tables exist                                                         #
# --------------------------------------------------------------------------- #

EXPECTED_TABLES = {
    "tenders", "organisations", "users", "bids",
    "analysis_runs", "risk_findings", "audit_log",
}

def test_all_tables_created(isolated_db):
    conn = sqlite3.connect(str(isolated_db))
    tables = get_tables(conn)
    conn.close()
    for t in EXPECTED_TABLES:
        assert t in tables, f"Table '{t}' missing"


def test_init_is_idempotent(isolated_db):
    """Calling init_db() twice must not raise or corrupt data."""
    import utils.database as db_mod
    db_mod.init_db()  # second call
    conn = sqlite3.connect(str(isolated_db))
    tables = get_tables(conn)
    conn.close()
    for t in EXPECTED_TABLES:
        assert t in tables


# --------------------------------------------------------------------------- #
#  2. Tenders table migration — new columns added safely                      #
# --------------------------------------------------------------------------- #

def test_tenders_has_new_columns(isolated_db):
    conn = sqlite3.connect(str(isolated_db))
    cols = get_columns(conn, "tenders")
    conn.close()
    assert "published_by"  in cols, "published_by column missing from tenders"
    assert "deadline"      in cols, "deadline column missing from tenders"
    assert "budget_amount" in cols, "budget_amount column missing from tenders"


def test_tenders_original_columns_preserved(isolated_db):
    conn = sqlite3.connect(str(isolated_db))
    cols = get_columns(conn, "tenders")
    conn.close()
    original = {
        "tender_id", "item_name", "department", "start_date", "end_date",
        "status", "quantity", "official_url", "source_type", "source_document",
        "created_at",
    }
    for col in original:
        assert col in cols, f"Original column '{col}' was removed"


def test_new_tender_columns_are_nullable(isolated_db):
    """New columns must be NULL by default — existing rows must not break."""
    import utils.database as db_mod
    # Insert a row without the new columns
    df = pd.DataFrame([{
        "tender_id": "T_MIGRATE",
        "item_name": "Test Item",
        "department": "MoT",
        "status": "active",
        "source_type": "real_public_data",
    }])
    result = db_mod.import_tenders_from_df(df)
    assert result["inserted"] == 1

    conn = sqlite3.connect(str(isolated_db))
    row = conn.execute(
        "SELECT published_by, deadline, budget_amount FROM tenders WHERE tender_id=?",
        ("T_MIGRATE",)
    ).fetchone()
    conn.close()
    assert row[0] is None  # published_by
    assert row[1] is None  # deadline
    assert row[2] is None  # budget_amount


def test_migration_runs_on_existing_db_with_data(tmp_path, monkeypatch):
    """
    Simulate upgrading an existing DB that already has tenders but lacks new columns.
    After init_db(), the new columns must exist and old rows must be intact.
    """
    import utils.database as db_mod
    old_db = tmp_path / "old.db"
    monkeypatch.setattr(db_mod, "DB_PATH", old_db)

    # Bootstrap with just the old schema (no new columns)
    conn = sqlite3.connect(str(old_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("""
        CREATE TABLE tenders (
            tender_id TEXT PRIMARY KEY,
            item_name TEXT,
            department TEXT,
            start_date TEXT,
            end_date TEXT,
            status TEXT,
            quantity REAL,
            official_url TEXT,
            source_type TEXT NOT NULL DEFAULT 'unknown',
            source_document TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO tenders (tender_id, item_name, source_type, created_at) "
        "VALUES (?, ?, ?, ?)",
        ("OLD001", "Old Item", "real_public_data", "2024-01-01T00:00:00+00:00")
    )
    conn.commit()
    conn.close()

    # Run migration
    db_mod.init_db()

    conn2 = sqlite3.connect(str(old_db))
    cols = get_columns(conn2, "tenders")
    row = conn2.execute(
        "SELECT tender_id, item_name, published_by, deadline, budget_amount "
        "FROM tenders WHERE tender_id='OLD001'"
    ).fetchone()
    conn2.close()

    assert "published_by"  in cols
    assert "deadline"      in cols
    assert "budget_amount" in cols
    assert row[0] == "OLD001"
    assert row[1] == "Old Item"
    assert row[2] is None  # published_by — null on old row
    assert row[3] is None  # deadline — null on old row
    assert row[4] is None  # budget_amount — null on old row


# --------------------------------------------------------------------------- #
#  3. Existing 9 real tender records preserved                                #
# --------------------------------------------------------------------------- #

def test_real_tenders_preserved_after_migration():
    """
    Import the real gem_tenders.csv, then run init_db() again.
    All 9 records must survive with their original values.
    """
    import utils.database as db_mod
    import io

    csv_path = Path(__file__).resolve().parent.parent / "data" / "gem_tenders.csv"
    df = pd.read_csv(csv_path)
    db_mod.import_tenders_from_df(df)
    assert db_mod.count_tenders() == 9

    # Second init — must be idempotent, no rows lost
    db_mod.init_db()
    assert db_mod.count_tenders() == 9

    record = db_mod.fetch_tender_by_id("GEM/2026/B/7899748")
    assert record is not None
    assert record["item_name"] == "Thermo Couple Welding Machine"
    assert record["source_type"] == "real_public_data"


# --------------------------------------------------------------------------- #
#  4. New table column schemas                                                 #
# --------------------------------------------------------------------------- #

def test_organisations_columns(isolated_db):
    conn = sqlite3.connect(str(isolated_db))
    cols = get_columns(conn, "organisations")
    conn.close()
    for col in ["org_id", "name", "org_type", "gstin", "is_active", "created_at"]:
        assert col in cols, f"organisations missing column '{col}'"


def test_users_columns(isolated_db):
    conn = sqlite3.connect(str(isolated_db))
    cols = get_columns(conn, "users")
    conn.close()
    for col in ["user_id", "email", "password_hash", "role", "org_id",
                "is_active", "created_at"]:
        assert col in cols


def test_bids_columns(isolated_db):
    conn = sqlite3.connect(str(isolated_db))
    cols = get_columns(conn, "bids")
    conn.close()
    for col in ["bid_id", "tender_id", "bidder_org_id", "submitted_by",
                "bid_amount", "submitted_at", "outcome", "product_category",
                "source_type", "notes"]:
        assert col in cols


def test_analysis_runs_columns(isolated_db):
    conn = sqlite3.connect(str(isolated_db))
    cols = get_columns(conn, "analysis_runs")
    conn.close()
    for col in ["run_id", "triggered_by", "bid_source", "score",
                "score_band", "created_at", "notes"]:
        assert col in cols


def test_risk_findings_columns(isolated_db):
    conn = sqlite3.connect(str(isolated_db))
    cols = get_columns(conn, "risk_findings")
    conn.close()
    for col in ["finding_id", "run_id", "rule", "tender_id",
                "bidder_ids_json", "evidence_json", "score",
                "source_type", "insufficient_data", "created_at"]:
        assert col in cols


def test_audit_log_columns(isolated_db):
    conn = sqlite3.connect(str(isolated_db))
    cols = get_columns(conn, "audit_log")
    conn.close()
    for col in ["log_id", "user_id", "action", "entity_type",
                "entity_id", "detail_json", "created_at"]:
        assert col in cols


# --------------------------------------------------------------------------- #
#  5. Indexes created                                                          #
# --------------------------------------------------------------------------- #

def test_key_indexes_exist(isolated_db):
    conn = sqlite3.connect(str(isolated_db))
    indexes = get_indexes(conn)
    conn.close()
    expected_indexes = [
        "idx_tenders_department", "idx_tenders_status", "idx_tenders_source_type",
        "idx_organisations_type",
        "idx_users_email", "idx_users_role", "idx_users_org",
        "idx_bids_tender", "idx_bids_bidder_org", "idx_bids_outcome",
        "idx_runs_created",
        "idx_findings_run", "idx_findings_rule", "idx_findings_tender",
        "idx_audit_user", "idx_audit_created",
    ]
    for idx in expected_indexes:
        assert idx in indexes, f"Index '{idx}' missing"


# --------------------------------------------------------------------------- #
#  6. Foreign-key enforcement                                                  #
# --------------------------------------------------------------------------- #

def test_fk_enforcement_on_bids(isolated_db):
    """Inserting a bid with a non-existent tender_id must fail."""
    conn = sqlite3.connect(str(isolated_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO bids (bid_id, tender_id, bidder_org_id, submitted_by, "
            "bid_amount, submitted_at, source_type) VALUES (?,?,?,?,?,?,?)",
            ("B1", "NONEXISTENT_TENDER", "ORG1", "U1",
             100000, "2024-01-01T10:00:00", "real")
        )
    conn.close()


def test_fk_enforcement_on_users(isolated_db):
    """Inserting a user with a non-existent org_id must fail."""
    conn = sqlite3.connect(str(isolated_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO users (user_id, email, password_hash, role, "
            "org_id, created_at) VALUES (?,?,?,?,?,?)",
            ("U1", "test@test.com", "hash", "bidder",
             "NONEXISTENT_ORG", "2024-01-01T00:00:00")
        )
    conn.close()


def test_fk_enforcement_on_risk_findings(isolated_db):
    """Inserting a finding with a non-existent run_id must fail."""
    conn = sqlite3.connect(str(isolated_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO risk_findings (finding_id, run_id, rule, "
            "evidence_json, source_type, created_at) VALUES (?,?,?,?,?,?)",
            ("F1", "NONEXISTENT_RUN", "A", "{}", "synthetic_demo",
             "2024-01-01T00:00:00")
        )
    conn.close()


# --------------------------------------------------------------------------- #
#  7. Constraint enforcement                                                   #
# --------------------------------------------------------------------------- #

def test_organisations_org_type_constraint(isolated_db):
    """org_type must be 'government' or 'bidder'."""
    conn = sqlite3.connect(str(isolated_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO organisations (org_id, name, org_type, created_at) "
            "VALUES (?,?,?,?)",
            ("O1", "Test Org", "invalid_type", "2024-01-01T00:00:00")
        )
    conn.close()


def test_users_role_constraint(isolated_db):
    """User role must be one of official/bidder/reviewer/admin."""
    # First insert a valid org
    conn = sqlite3.connect(str(isolated_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(
        "INSERT INTO organisations (org_id, name, org_type, created_at) "
        "VALUES (?,?,?,?)",
        ("O1", "Gov Dept", "government", "2024-01-01T00:00:00")
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO users (user_id, email, password_hash, role, "
            "org_id, created_at) VALUES (?,?,?,?,?,?)",
            ("U1", "a@b.com", "hash", "superuser", "O1", "2024-01-01T00:00:00")
        )
    conn.close()


def test_bids_amount_must_be_positive(isolated_db):
    """bid_amount CHECK(> 0) must reject zero and negative amounts."""
    import utils.database as db_mod

    # Set up prerequisites
    conn = sqlite3.connect(str(isolated_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(
        "INSERT INTO organisations (org_id, name, org_type, created_at) VALUES (?,?,?,?)",
        ("O1", "Bidder Co", "bidder", "2024-01-01T00:00:00")
    )
    conn.execute(
        "INSERT INTO users (user_id, email, password_hash, role, org_id, created_at) "
        "VALUES (?,?,?,?,?,?)",
        ("U1", "b@b.com", "hash", "bidder", "O1", "2024-01-01T00:00:00")
    )
    conn.commit()

    # Insert a valid tender
    db_mod.import_tenders_from_df(pd.DataFrame([{
        "tender_id": "T001", "item_name": "Widget",
        "department": "MoT", "status": "active",
        "source_type": "real_public_data",
    }]))

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO bids (bid_id, tender_id, bidder_org_id, submitted_by, "
            "bid_amount, submitted_at, source_type) VALUES (?,?,?,?,?,?,?)",
            ("B1", "T001", "O1", "U1", -1000, "2024-01-01T10:00:00", "real")
        )
    conn.close()


def test_user_email_unique_constraint(isolated_db):
    """Two users with the same email must be rejected."""
    conn = sqlite3.connect(str(isolated_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(
        "INSERT INTO organisations (org_id, name, org_type, created_at) "
        "VALUES (?,?,?,?)",
        ("O1", "Dept", "government", "2024-01-01T00:00:00")
    )
    conn.execute(
        "INSERT INTO users (user_id, email, password_hash, role, org_id, created_at) "
        "VALUES (?,?,?,?,?,?)",
        ("U1", "same@test.com", "hash", "official", "O1", "2024-01-01T00:00:00")
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO users (user_id, email, password_hash, role, org_id, created_at) "
            "VALUES (?,?,?,?,?,?)",
            ("U2", "same@test.com", "hash2", "reviewer", "O1", "2024-01-01T00:00:00")
        )
    conn.close()


# --------------------------------------------------------------------------- #
#  8. Successful valid inserts across all new tables                          #
# --------------------------------------------------------------------------- #

def test_full_chain_insert(isolated_db):
    """
    Insert a complete chain: org → user → tender → bid → run → finding → audit.
    All foreign keys must resolve. No exceptions expected.
    """
    import utils.database as db_mod

    conn = sqlite3.connect(str(isolated_db))
    conn.execute("PRAGMA foreign_keys = ON;")

    # Organisation
    conn.execute(
        "INSERT INTO organisations (org_id, name, org_type, created_at) "
        "VALUES (?,?,?,?)",
        ("ORGB1", "Acme Supplies", "bidder", "2024-01-01T00:00:00")
    )
    conn.execute(
        "INSERT INTO organisations (org_id, name, org_type, created_at) "
        "VALUES (?,?,?,?)",
        ("ORGG1", "Ministry of Finance", "government", "2024-01-01T00:00:00")
    )

    # Users
    conn.execute(
        "INSERT INTO users (user_id, email, password_hash, role, org_id, created_at) "
        "VALUES (?,?,?,?,?,?)",
        ("U_OFF", "official@gov.in", "hash1", "official", "ORGG1", "2024-01-01T00:00:00")
    )
    conn.execute(
        "INSERT INTO users (user_id, email, password_hash, role, org_id, created_at) "
        "VALUES (?,?,?,?,?,?)",
        ("U_BID", "bidder@acme.com", "hash2", "bidder", "ORGB1", "2024-01-01T00:00:00")
    )
    conn.commit()

    # Tender (use database layer for consistency)
    db_mod.import_tenders_from_df(pd.DataFrame([{
        "tender_id": "CHAIN001",
        "item_name": "Office Chairs",
        "department": "MoF",
        "status": "active",
        "source_type": "real_public_data",
    }]))

    # Bid
    conn.execute(
        "INSERT INTO bids (bid_id, tender_id, bidder_org_id, submitted_by, "
        "bid_amount, submitted_at, source_type) VALUES (?,?,?,?,?,?,?)",
        ("BID1", "CHAIN001", "ORGB1", "U_BID",
         500000, "2024-01-10T10:00:00", "real")
    )

    # Analysis run
    conn.execute(
        "INSERT INTO analysis_runs (run_id, triggered_by, bid_source, "
        "score, score_band, created_at) VALUES (?,?,?,?,?,?)",
        ("RUN1", "U_OFF", "real", 35, "Moderate", "2024-01-11T09:00:00")
    )

    # Risk finding
    conn.execute(
        "INSERT INTO risk_findings (finding_id, run_id, rule, tender_id, "
        "evidence_json, score, source_type, created_at) VALUES (?,?,?,?,?,?,?,?)",
        ("FND1", "RUN1", "A", "CHAIN001", '{"pairs":[]}',
         35, "real", "2024-01-11T09:01:00")
    )

    # Audit log
    conn.execute(
        "INSERT INTO audit_log (log_id, user_id, action, entity_type, "
        "entity_id, created_at) VALUES (?,?,?,?,?,?)",
        ("LOG1", "U_OFF", "run_analysis", "analysis_run",
         "RUN1", "2024-01-11T09:02:00")
    )

    conn.commit()
    conn.close()

    # Verify counts
    conn2 = sqlite3.connect(str(isolated_db))
    assert conn2.execute("SELECT COUNT(*) FROM organisations").fetchone()[0] == 2
    assert conn2.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2
    assert conn2.execute("SELECT COUNT(*) FROM bids").fetchone()[0] == 1
    assert conn2.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0] == 1
    assert conn2.execute("SELECT COUNT(*) FROM risk_findings").fetchone()[0] == 1
    assert conn2.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 1
    conn2.close()


# --------------------------------------------------------------------------- #
#  9. WAL mode enabled                                                         #
# --------------------------------------------------------------------------- #

def test_wal_mode_enabled(isolated_db):
    conn = sqlite3.connect(str(isolated_db))
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode == "wal", f"Expected WAL mode, got '{mode}'"
