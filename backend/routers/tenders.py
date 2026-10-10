"""
backend/routers/tenders.py
Tender Explorer API endpoints.

All database access goes through utils/database.py — no raw SQL here.
Import logic reuses import_tenders_from_df() exactly as-is.
"""

from __future__ import annotations

import io
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field

# Lazy-import the database layer so this module doesn't break anything
# if imported in a non-database context.
import utils.database as db

router = APIRouter(prefix="/api/tenders", tags=["tenders"])

# --------------------------------------------------------------------------- #
#  Response models                                                             #
# --------------------------------------------------------------------------- #

class TenderRecord(BaseModel):
    tender_id: str
    item_name: Optional[str] = None
    department: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None
    quantity: Optional[float] = None
    official_url: Optional[str] = None
    source_type: str
    source_document: Optional[str] = None
    created_at: Optional[str] = None


class TenderListResponse(BaseModel):
    items: list[TenderRecord]
    total: int
    page: int
    page_size: int
    pages: int


class FilterOptionsResponse(BaseModel):
    departments: list[str]
    statuses: list[str]
    source_types: list[str]


class ImportResult(BaseModel):
    inserted: int
    skipped_duplicate: int
    rejected: int
    errors: list[str]


# Allowed source_type values for the override param
ALLOWED_SOURCE_OVERRIDES = {"real_public_data", "synthetic", "unknown"}

# --------------------------------------------------------------------------- #
#  Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _df_to_records(df: pd.DataFrame) -> list[TenderRecord]:
    """Convert a DataFrame (from database layer) to a list of TenderRecord."""
    records = []
    for row in df.to_dict("records"):
        # Replace NaN with None for JSON serialisation
        cleaned = {k: (None if (isinstance(v, float) and pd.isna(v)) else v)
                   for k, v in row.items()}
        records.append(TenderRecord(**{
            k: cleaned.get(k)
            for k in TenderRecord.model_fields
            if k in cleaned
        }))
    return records


# --------------------------------------------------------------------------- #
#  GET /api/tenders — list with search, filter, pagination                    #
# --------------------------------------------------------------------------- #

@router.get("", response_model=TenderListResponse)
def list_tenders(
    search: str = Query("", max_length=200, description="Search tender ID or item name"),
    department: Optional[str] = Query(None, max_length=200),
    status: Optional[str] = Query(None, max_length=200),
    source_type: Optional[str] = Query(None, max_length=50),
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(25, ge=1, le=100, description="Rows per page (max 100)"),
):
    # If source_type filter supplied, apply it after the existing filtered fetch
    df = db.fetch_tenders_filtered(
        search=search.strip(),
        department=department or None,
        status=status or None,
    )

    # Source-type filter (not in existing db helper — apply in-memory safely)
    if source_type:
        df = df[df["source_type"] == source_type]

    total = len(df)
    pages = max(1, -(-total // page_size))  # ceiling division
    offset = (page - 1) * page_size
    page_df = df.iloc[offset : offset + page_size]

    return TenderListResponse(
        items=_df_to_records(page_df),
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


# --------------------------------------------------------------------------- #
#  GET /api/tenders/filters — available filter options                        #
# --------------------------------------------------------------------------- #

@router.get("/filters", response_model=FilterOptionsResponse)
def get_filter_options():
    return FilterOptionsResponse(
        departments=db.fetch_distinct("department"),
        statuses=db.fetch_distinct("status"),
        source_types=db.fetch_distinct("source_type"),
    )


# --------------------------------------------------------------------------- #
#  GET /api/tenders/{tender_id} — single record                              #
# --------------------------------------------------------------------------- #

@router.get("/{tender_id:path}", response_model=TenderRecord)
def get_tender(tender_id: str):
    if len(tender_id) > 200:
        raise HTTPException(status_code=400, detail="tender_id too long")
    record = db.fetch_tender_by_id(tender_id.strip())
    if record is None:
        raise HTTPException(status_code=404, detail=f"Tender '{tender_id}' not found")
    cleaned = {k: (None if (isinstance(v, float) and pd.isna(v)) else v)
               for k, v in record.items()}
    return TenderRecord(**{k: cleaned.get(k) for k in TenderRecord.model_fields if k in cleaned})


# --------------------------------------------------------------------------- #
#  POST /api/tenders/import — CSV upload                                      #
# --------------------------------------------------------------------------- #

@router.post("/import", response_model=ImportResult)
async def import_tenders(
    file: UploadFile = File(..., description="CSV file with tender records"),
    source_type_override: Optional[str] = Query(
        None,
        description="Override source_type for all rows. "
                    "Allowed: real_public_data, synthetic, unknown",
    ),
):
    # Validate source_type_override before touching the file
    if source_type_override and source_type_override not in ALLOWED_SOURCE_OVERRIDES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid source_type_override '{source_type_override}'. "
                   f"Allowed values: {sorted(ALLOWED_SOURCE_OVERRIDES)}",
        )

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10 MB hard limit
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}")

    if "tender_id" not in df.columns:
        raise HTTPException(
            status_code=422,
            detail="CSV must contain a 'tender_id' column",
        )

    if df.empty:
        raise HTTPException(status_code=422, detail="CSV contains no data rows")

    # Guard: reject bid-level CSVs masquerading as tender metadata.
    # A valid tender CSV must have at least one row with a value in one of
    # the core tender metadata fields. A bid-only CSV (e.g. demo_bids.csv)
    # has tender_id but none of these fields, producing stub records with
    # all-NULL metadata. We detect this by checking whether the CSV contains
    # ANY of the tender-specific columns at all.
    TENDER_METADATA_COLS = {"item_name", "department", "status", "start_date", "end_date"}
    present_metadata_cols = TENDER_METADATA_COLS & set(df.columns)
    if not present_metadata_cols:
        raise HTTPException(
            status_code=422,
            detail=(
                "This CSV does not appear to be a tender metadata file. "
                "It contains no tender-specific columns "
                f"({', '.join(sorted(TENDER_METADATA_COLS))}). "
                "Bid-level files such as demo_bids.csv must not be imported "
                "into the tender database."
            ),
        )

    result = db.import_tenders_from_df(df, source_type_override=source_type_override)
    return ImportResult(**result)
