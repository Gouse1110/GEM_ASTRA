"""
utils/database.py
Primary storage layer for GeM Astra.  SQLite-backed, parameterised queries only.
"""

import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "gem_astra.db"

TENDER_COLUMNS = [
    "tender_id", "item_name", "department", "start_date", "end_date",
    "status", "quantity", "official_url", "source_type", "source_document",
]

# --------------------------------------------------------------------------- #
#  Connection                                                                  #
# --------------------------------------------------------------------------- #

def get_connection() -> sqlite3.Connection:
    """Return a connection with foreign-key enforcement and row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------------------------------- #
#  Schema initialisation                                                       #
# --------------------------------------------------------------------------- #

def init_db() -> None:
    """
    Create tables and indexes if they do not already exist.
    Also runs safe, repeatable migrations (ALTER TABLE ADD COLUMN).
    Idempotent — safe to call on every startup.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        # ------------------------------------------------------------------ #
        #  Enable WAL mode for better write concurrency                       #
        # ------------------------------------------------------------------ #
        conn.execute("PRAGMA journal_mode=WAL;")

        # ------------------------------------------------------------------ #
        #  Core tables                                                        #
        # ------------------------------------------------------------------ #
        conn.executescript(
            """
            -- ---------------------------------------------------------------
            -- tenders (existing table — preserved exactly)
            -- ---------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS tenders (
                tender_id       TEXT PRIMARY KEY,
                item_name       TEXT,
                department      TEXT,
                start_date      TEXT,
                end_date        TEXT,
                status          TEXT,
                quantity        REAL,
                official_url    TEXT,
                source_type     TEXT NOT NULL DEFAULT 'unknown',
                source_document TEXT,
                created_at      TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tenders_department
                ON tenders (department);
            CREATE INDEX IF NOT EXISTS idx_tenders_status
                ON tenders (status);
            CREATE INDEX IF NOT EXISTS idx_tenders_source_type
                ON tenders (source_type);

            -- ---------------------------------------------------------------
            -- organisations — government departments and bidder companies
            -- ---------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS organisations (
                org_id    TEXT PRIMARY KEY,
                name      TEXT NOT NULL,
                org_type  TEXT NOT NULL CHECK(org_type IN ('government','bidder')),
                gstin     TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_organisations_type
                ON organisations (org_type);

            -- ---------------------------------------------------------------
            -- users — officials, bidders, reviewers
            -- ---------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS users (
                user_id       TEXT PRIMARY KEY,
                email         TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL
                    CHECK(role IN ('official','bidder','reviewer','admin')),
                org_id        TEXT REFERENCES organisations(org_id),
                is_active     INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
                ON users (email);
            CREATE INDEX IF NOT EXISTS idx_users_role
                ON users (role);
            CREATE INDEX IF NOT EXISTS idx_users_org
                ON users (org_id);

            -- ---------------------------------------------------------------
            -- bids — submitted bid records (separate from demo_bids.csv)
            -- ---------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS bids (
                bid_id           TEXT PRIMARY KEY,
                tender_id        TEXT NOT NULL
                    REFERENCES tenders(tender_id),
                bidder_org_id    TEXT NOT NULL
                    REFERENCES organisations(org_id),
                submitted_by     TEXT NOT NULL
                    REFERENCES users(user_id),
                bid_amount       REAL NOT NULL CHECK(bid_amount > 0),
                submitted_at     TEXT NOT NULL,
                outcome          TEXT
                    CHECK(outcome IN ('won','lost','pending','disqualified') OR outcome IS NULL),
                product_category TEXT,
                source_type      TEXT NOT NULL DEFAULT 'real',
                notes            TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_bids_tender
                ON bids (tender_id);
            CREATE INDEX IF NOT EXISTS idx_bids_bidder_org
                ON bids (bidder_org_id);
            CREATE INDEX IF NOT EXISTS idx_bids_submitted_at
                ON bids (submitted_at);
            CREATE INDEX IF NOT EXISTS idx_bids_outcome
                ON bids (outcome);

            -- One bid per bidder organisation per tender
            CREATE UNIQUE INDEX IF NOT EXISTS uq_bids_tender_bidder_org
                ON bids (tender_id, bidder_org_id);

            -- ---------------------------------------------------------------
            -- analysis_runs — records of each engine execution
            -- ---------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS analysis_runs (
                run_id       TEXT PRIMARY KEY,
                triggered_by TEXT REFERENCES users(user_id),
                bid_source   TEXT NOT NULL
                    CHECK(bid_source IN ('real','synthetic_demo','mixed')),
                score        INTEGER CHECK(score BETWEEN 0 AND 100),
                score_band   TEXT
                    CHECK(score_band IN ('Low','Moderate','Elevated','High') OR score_band IS NULL),
                created_at   TEXT NOT NULL,
                notes        TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_runs_created
                ON analysis_runs (created_at);

            -- ---------------------------------------------------------------
            -- risk_findings — persisted engine findings per run
            -- ---------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS risk_findings (
                finding_id     TEXT PRIMARY KEY,
                run_id         TEXT NOT NULL
                    REFERENCES analysis_runs(run_id),
                rule           TEXT NOT NULL,
                tender_id      TEXT REFERENCES tenders(tender_id),
                bidder_ids_json TEXT,
                evidence_json  TEXT NOT NULL DEFAULT '{}',
                score          INTEGER,
                source_type    TEXT NOT NULL DEFAULT 'unknown',
                insufficient_data INTEGER NOT NULL DEFAULT 0,
                created_at     TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_findings_run
                ON risk_findings (run_id);
            CREATE INDEX IF NOT EXISTS idx_findings_rule
                ON risk_findings (rule);
            CREATE INDEX IF NOT EXISTS idx_findings_tender
                ON risk_findings (tender_id);

            -- ---------------------------------------------------------------
            -- audit_log — immutable record of all write actions
            -- ---------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS audit_log (
                log_id      TEXT PRIMARY KEY,
                user_id     TEXT REFERENCES users(user_id),
                action      TEXT NOT NULL,
                entity_type TEXT,
                entity_id   TEXT,
                detail_json TEXT,
                created_at  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_audit_user
                ON audit_log (user_id);
            CREATE INDEX IF NOT EXISTS idx_audit_created
                ON audit_log (created_at);
            CREATE INDEX IF NOT EXISTS idx_audit_entity
                ON audit_log (entity_type, entity_id);
            """
        )

        # ------------------------------------------------------------------ #
        #  Safe repeatable migration: add columns to tenders if missing       #
        # ------------------------------------------------------------------ #
        _migrate_tenders(conn)


def _migrate_tenders(conn: sqlite3.Connection) -> None:
    """
    Add new columns to the tenders table if they do not already exist.
    Uses ALTER TABLE ADD COLUMN which is always safe on existing rows
    (new columns default to NULL).

    Columns added:
      published_by  — FK to users(user_id), nullable (imported records have none)
      deadline      — ISO-8601 text, the bid submission deadline
      budget_amount — REAL, indicative budget
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(tenders)").fetchall()}

    migrations = [
        ("published_by",  "TEXT REFERENCES users(user_id)"),
        ("deadline",      "TEXT"),
        ("budget_amount", "REAL"),
    ]

    for col_name, col_def in migrations:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE tenders ADD COLUMN {col_name} {col_def}")
            conn.commit()


# --------------------------------------------------------------------------- #
#  Read helpers                                                                #
# --------------------------------------------------------------------------- #

def fetch_all_tenders() -> pd.DataFrame:
    """Return all tenders as a DataFrame."""
    try:
        with get_connection() as conn:
            df = pd.read_sql_query(
                "SELECT * FROM tenders ORDER BY created_at DESC", conn
            )
        return df
    except Exception:
        return pd.DataFrame(columns=TENDER_COLUMNS + ["created_at"])


def fetch_tenders_filtered(
    search: str = "",
    department: Optional[str] = None,
    status: Optional[str] = None,
) -> pd.DataFrame:
    """Return tenders matching optional search text and filters."""
    clauses: list[str] = []
    params: list = []

    if search:
        clauses.append(
            "(tender_id LIKE ? OR item_name LIKE ?)"
        )
        like = f"%{search}%"
        params.extend([like, like])

    if department:
        clauses.append("department = ?")
        params.append(department)

    if status:
        clauses.append("status = ?")
        params.append(status)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM tenders {where} ORDER BY created_at DESC"

    try:
        with get_connection() as conn:
            df = pd.read_sql_query(sql, conn, params=params)
        return df
    except Exception:
        return pd.DataFrame(columns=TENDER_COLUMNS + ["created_at"])


def fetch_distinct(column: str) -> list[str]:
    """Return sorted distinct non-null values for a column."""
    allowed = {"department", "status", "source_type"}
    if column not in allowed:
        return []
    try:
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT DISTINCT {column} FROM tenders "  # column is allow-listed
                f"WHERE {column} IS NOT NULL AND {column} != '' "
                f"ORDER BY {column}"
            ).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []


def count_tenders() -> int:
    try:
        with get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM tenders").fetchone()[0]
    except Exception:
        return 0


def fetch_tender_by_id(tender_id: str) -> Optional[dict]:
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM tenders WHERE tender_id = ?", (tender_id,)
            ).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
#  Import                                                                      #
# --------------------------------------------------------------------------- #

ALLOWED_SOURCE_TYPES = {"real_public_data", "synthetic", "synthetic_demo", "unknown"}


def import_tenders_from_df(
    df: pd.DataFrame,
    source_type_override: Optional[str] = None,
) -> dict:
    """
    Insert rows from a DataFrame into the tenders table.

    Duplicate tender_ids are skipped (not overwritten) unless the caller
    explicitly uses upsert=True (not exposed in UI — safety default).

    Returns a result dict: inserted, skipped_duplicate, rejected, errors.
    """
    result = {
        "inserted": 0,
        "skipped_duplicate": 0,
        "rejected": 0,
        "errors": [],
    }

    now = datetime.now(timezone.utc).isoformat()

    rows_to_insert: list[tuple] = []

    for idx, row in df.iterrows():
        tender_id = str(row.get("tender_id", "")).strip()
        if not tender_id:
            result["rejected"] += 1
            result["errors"].append(f"Row {idx + 1}: missing tender_id — skipped.")
            continue

        # Determine source_type
        raw_src = str(row.get("source_type", "")).strip().lower()
        if source_type_override:
            src = source_type_override
        elif raw_src in ALLOWED_SOURCE_TYPES:
            src = raw_src
        else:
            src = "unknown"

        rows_to_insert.append((
            tender_id,
            _clean(row, "item_name"),
            _clean(row, "department"),
            _clean(row, "start_date"),
            _clean(row, "end_date"),
            _clean(row, "status"),
            _to_float(row.get("quantity")),
            _clean(row, "official_url"),
            src,
            _clean(row, "source_document"),
            now,
        ))

    if not rows_to_insert:
        return result

    sql = """
        INSERT OR IGNORE INTO tenders
            (tender_id, item_name, department, start_date, end_date,
             status, quantity, official_url, source_type, source_document, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    try:
        with get_connection() as conn:
            conn.execute("BEGIN")
            try:
                for row_tuple in rows_to_insert:
                    cur = conn.execute(sql, row_tuple)
                    if cur.rowcount == 1:
                        result["inserted"] += 1
                    else:
                        result["skipped_duplicate"] += 1
                conn.execute("COMMIT")
            except Exception as e:
                conn.execute("ROLLBACK")
                result["errors"].append(f"Transaction rolled back: {e}")
                result["inserted"] = 0
    except Exception as e:
        result["errors"].append(f"Connection error: {e}")

    return result


# --------------------------------------------------------------------------- #
#  Audit log                                                                  #
# --------------------------------------------------------------------------- #

def write_audit_log(
    conn: sqlite3.Connection,
    user_id: Optional[str],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    detail_json: Optional[str] = None,
) -> None:
    """Insert one immutable audit-log entry. Call inside an open connection."""
    import uuid as _uuid
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO audit_log (log_id, user_id, action, entity_type, "
        "entity_id, detail_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (_uuid.uuid4().hex, user_id, action, entity_type, entity_id, detail_json, now),
    )


# --------------------------------------------------------------------------- #
#  Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _clean(row, key: str) -> Optional[str]:
    val = row.get(key, None)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return s if s else None


def _to_float(val) -> Optional[float]:
    try:
        f = float(val)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None
