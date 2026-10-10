"""
tests/test_database.py
Tests for the SQLite database layer.
Run with: python -m pytest tests/ -v
"""

import pytest
import sqlite3
import pandas as pd
import tempfile
import os
from pathlib import Path
from unittest.mock import patch


# ------------------------------------------------------------------ #
#  Fixture: redirect DB_PATH to a temp file for every test            #
# ------------------------------------------------------------------ #

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Each test gets its own fresh SQLite database."""
    tmp_db = tmp_path / "test_gem_astra.db"
    import utils.database as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_db)
    db_mod.init_db()
    yield tmp_db


# ------------------------------------------------------------------ #
#  Helpers                                                            #
# ------------------------------------------------------------------ #

def make_df(**overrides):
    row = {
        "tender_id": "T001",
        "item_name": "Laptop",
        "department": "MoE",
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
        "status": "active",
        "quantity": 100,
        "official_url": "https://gem.gov.in/T001",
        "source_type": "real_public_data",
        "source_document": "doc1.pdf",
    }
    row.update(overrides)
    return pd.DataFrame([row])


# ------------------------------------------------------------------ #
#  1. Database initialisation                                         #
# ------------------------------------------------------------------ #

def test_init_creates_tenders_table(isolated_db):
    import utils.database as db_mod
    conn = db_mod.get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = [t[0] for t in tables]
    assert "tenders" in names


def test_init_is_idempotent(isolated_db):
    """Calling init_db() twice must not raise."""
    import utils.database as db_mod
    db_mod.init_db()  # second call
    assert db_mod.count_tenders() == 0


def test_indexes_created(isolated_db):
    import utils.database as db_mod
    conn = db_mod.get_connection()
    indexes = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ).fetchall()
    names = [i[0] for i in indexes]
    assert any("department" in n for n in names)
    assert any("status" in n for n in names)


# ------------------------------------------------------------------ #
#  2. Valid import                                                     #
# ------------------------------------------------------------------ #

def test_valid_import_inserts_row():
    import utils.database as db_mod
    df = make_df()
    result = db_mod.import_tenders_from_df(df)
    assert result["inserted"] == 1
    assert result["skipped_duplicate"] == 0
    assert result["rejected"] == 0
    assert db_mod.count_tenders() == 1


def test_imported_row_fields():
    import utils.database as db_mod
    df = make_df()
    db_mod.import_tenders_from_df(df)
    record = db_mod.fetch_tender_by_id("T001")
    assert record is not None
    assert record["item_name"] == "Laptop"
    assert record["department"] == "MoE"
    assert record["source_type"] == "real_public_data"
    assert record["official_url"] == "https://gem.gov.in/T001"


# ------------------------------------------------------------------ #
#  3. Duplicate tender IDs                                            #
# ------------------------------------------------------------------ #

def test_duplicate_is_skipped():
    import utils.database as db_mod
    df = make_df()
    db_mod.import_tenders_from_df(df)
    result = db_mod.import_tenders_from_df(df)  # second insert, same ID
    assert result["inserted"] == 0
    assert result["skipped_duplicate"] == 1
    assert db_mod.count_tenders() == 1  # still only 1 row


# ------------------------------------------------------------------ #
#  4. Invalid / missing rows                                          #
# ------------------------------------------------------------------ #

def test_row_without_tender_id_is_rejected():
    import utils.database as db_mod
    df = make_df(tender_id="")
    result = db_mod.import_tenders_from_df(df)
    assert result["rejected"] == 1
    assert result["inserted"] == 0
    assert db_mod.count_tenders() == 0


def test_missing_optional_columns_allowed():
    import utils.database as db_mod
    df = pd.DataFrame([{"tender_id": "T002"}])  # only mandatory field
    result = db_mod.import_tenders_from_df(df)
    assert result["inserted"] == 1
    record = db_mod.fetch_tender_by_id("T002")
    assert record["item_name"] is None
    assert record["department"] is None


def test_unknown_source_type_stored_as_unknown():
    import utils.database as db_mod
    df = make_df(source_type="random_value")
    db_mod.import_tenders_from_df(df)
    record = db_mod.fetch_tender_by_id("T001")
    assert record["source_type"] == "unknown"


# ------------------------------------------------------------------ #
#  5. Source-type override                                            #
# ------------------------------------------------------------------ #

def test_source_type_override():
    import utils.database as db_mod
    df = make_df(source_type="unknown")
    db_mod.import_tenders_from_df(df, source_type_override="synthetic")
    record = db_mod.fetch_tender_by_id("T001")
    assert record["source_type"] == "synthetic"


def test_synthetic_not_overridden_to_real_without_explicit_flag():
    import utils.database as db_mod
    df = make_df(source_type="synthetic")
    db_mod.import_tenders_from_df(df)  # no override
    record = db_mod.fetch_tender_by_id("T001")
    assert record["source_type"] == "synthetic"


# ------------------------------------------------------------------ #
#  6. Transaction rollback on failure                                 #
# ------------------------------------------------------------------ #

def test_rollback_on_insert_error(monkeypatch):
    """If the DB raises mid-batch, no rows must be committed."""
    import utils.database as db_mod

    original_get = db_mod.get_connection

    call_count = {"n": 0}

    class FaultyConn:
        def __init__(self, real_conn):
            self._conn = real_conn
        def execute(self, sql, params=()):
            call_count["n"] += 1
            if "INSERT" in sql and call_count["n"] > 1:
                raise sqlite3.OperationalError("Simulated failure")
            return self._conn.execute(sql, params)
        def __enter__(self): return self
        def __exit__(self, *a): self._conn.close()

    def patched_get():
        return FaultyConn(original_get())

    monkeypatch.setattr(db_mod, "get_connection", patched_get)

    df = pd.DataFrame([
        {"tender_id": "T010", "item_name": "Widget"},
        {"tender_id": "T011", "item_name": "Gadget"},
    ])
    result = db_mod.import_tenders_from_df(df)
    assert result["inserted"] == 0
    assert len(result["errors"]) > 0


# ------------------------------------------------------------------ #
#  7. Search and filters                                              #
# ------------------------------------------------------------------ #

def test_search_by_tender_id():
    import utils.database as db_mod
    db_mod.import_tenders_from_df(make_df(tender_id="T001", item_name="Laptop"))
    db_mod.import_tenders_from_df(make_df(tender_id="T002", item_name="Printer"))
    result = db_mod.fetch_tenders_filtered(search="T001")
    assert len(result) == 1
    assert result.iloc[0]["tender_id"] == "T001"


def test_search_by_item_name():
    import utils.database as db_mod
    db_mod.import_tenders_from_df(make_df(tender_id="T001", item_name="Laptop"))
    db_mod.import_tenders_from_df(make_df(tender_id="T002", item_name="Printer"))
    result = db_mod.fetch_tenders_filtered(search="print")
    assert len(result) == 1
    assert result.iloc[0]["item_name"] == "Printer"


def test_filter_by_department():
    import utils.database as db_mod
    db_mod.import_tenders_from_df(make_df(tender_id="T001", department="MoE"))
    db_mod.import_tenders_from_df(make_df(tender_id="T002", department="MoH"))
    result = db_mod.fetch_tenders_filtered(department="MoE")
    assert len(result) == 1
    assert result.iloc[0]["department"] == "MoE"


def test_filter_by_status():
    import utils.database as db_mod
    db_mod.import_tenders_from_df(make_df(tender_id="T001", status="active"))
    db_mod.import_tenders_from_df(make_df(tender_id="T002", status="closed"))
    result = db_mod.fetch_tenders_filtered(status="closed")
    assert len(result) == 1


def test_combined_search_and_filter():
    import utils.database as db_mod
    db_mod.import_tenders_from_df(make_df(tender_id="T001", item_name="Laptop", department="MoE"))
    db_mod.import_tenders_from_df(make_df(tender_id="T002", item_name="Laptop", department="MoH"))
    result = db_mod.fetch_tenders_filtered(search="laptop", department="MoE")
    assert len(result) == 1


# ------------------------------------------------------------------ #
#  8. Empty database behaviour                                        #
# ------------------------------------------------------------------ #

def test_fetch_all_empty_db():
    import utils.database as db_mod
    df = db_mod.fetch_all_tenders()
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_count_empty_db():
    import utils.database as db_mod
    assert db_mod.count_tenders() == 0


def test_fetch_by_id_missing():
    import utils.database as db_mod
    result = db_mod.fetch_tender_by_id("NONEXISTENT")
    assert result is None


def test_fetch_distinct_empty_db():
    import utils.database as db_mod
    assert db_mod.fetch_distinct("department") == []
