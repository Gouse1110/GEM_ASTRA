"""
backend/routers/contracts.py
Contract management endpoints — official-only write operations.

POST   /api/contracts          — create DRAFT tender
PATCH  /api/contracts/{id}     — edit draft (official who owns it)
POST   /api/contracts/{id}/publish — publish draft
GET    /api/contracts          — list contracts created by this official
GET    /api/contracts/{id}     — detail + bid count (no amounts)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

import utils.database as db
from backend.auth import get_current_user, require_role

router = APIRouter(prefix="/api/contracts", tags=["contracts"])

# --------------------------------------------------------------------------- #
#  Models                                                                      #
# --------------------------------------------------------------------------- #

class ContractCreate(BaseModel):
    item_name: str = Field(..., min_length=2, max_length=300)
    department: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    quantity: Optional[float] = Field(None, gt=0)
    budget_amount: Optional[float] = Field(None, gt=0)
    deadline: str = Field(..., description="ISO-8601 datetime, must be in the future")
    product_category: Optional[str] = Field(None, max_length=100)


class ContractEdit(BaseModel):
    item_name: Optional[str] = Field(None, min_length=2, max_length=300)
    department: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    quantity: Optional[float] = Field(None, gt=0)
    budget_amount: Optional[float] = Field(None, gt=0)
    deadline: Optional[str] = None
    product_category: Optional[str] = Field(None, max_length=100)


class ContractResponse(BaseModel):
    tender_id: str
    item_name: Optional[str]
    department: Optional[str]
    status: Optional[str]
    quantity: Optional[float]
    budget_amount: Optional[float]
    deadline: Optional[str]
    published_by: Optional[str]
    source_type: str
    created_at: str
    bid_count: int = 0   # number of bids received — no amounts exposed


# --------------------------------------------------------------------------- #
#  Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _validate_deadline(deadline: str) -> None:
    try:
        dt = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, "deadline must be a valid ISO-8601 datetime.")
    if dt <= datetime.now(timezone.utc):
        raise HTTPException(422, "deadline must be in the future.")


def _row_to_response(row: dict, bid_count: int = 0) -> ContractResponse:
    return ContractResponse(
        tender_id=row["tender_id"],
        item_name=row.get("item_name"),
        department=row.get("department"),
        status=row.get("status"),
        quantity=row.get("quantity"),
        budget_amount=row.get("budget_amount"),
        deadline=row.get("deadline"),
        published_by=row.get("published_by"),
        source_type=row.get("source_type", "official_workflow"),
        created_at=row["created_at"],
        bid_count=bid_count,
    )


# --------------------------------------------------------------------------- #
#  Endpoints                                                                   #
# --------------------------------------------------------------------------- #

@router.post("", response_model=ContractResponse, status_code=201)
def create_contract(
    body: ContractCreate,
    user: dict = Depends(require_role("official", "admin")),
):
    """Create a DRAFT contract. Only officials may create contracts."""
    _validate_deadline(body.deadline)

    now = datetime.now(timezone.utc).isoformat()
    # IDs for official-workflow contracts use a different prefix to avoid
    # colliding with imported GeM IDs (e.g. GEM/2026/B/…)
    tender_id = f"DRAFT-{uuid.uuid4().hex[:10].upper()}"

    conn = db.get_connection()
    try:
        conn.execute(
            """INSERT INTO tenders
               (tender_id, item_name, department, status, quantity,
                budget_amount, deadline, published_by, source_type,
                source_document, created_at)
               VALUES (?, ?, ?, 'draft', ?, ?, ?, ?, 'official_workflow', NULL, ?)""",
            (
                tender_id, body.item_name, body.department,
                body.quantity, body.budget_amount, body.deadline,
                user["user_id"], now,
            ),
        )
        db.write_audit_log(
            conn, user["user_id"], "create_draft_contract",
            "tender", tender_id,
            json.dumps({"item_name": body.item_name, "department": body.department}),
        )
        conn.commit()
    finally:
        conn.close()

    row = db.fetch_tender_by_id(tender_id)
    return _row_to_response(row)


@router.patch("/{tender_id}", response_model=ContractResponse)
def edit_contract(
    tender_id: str,
    body: ContractEdit,
    user: dict = Depends(require_role("official", "admin")),
):
    """Edit a DRAFT contract. Only the creating official may edit."""
    row = db.fetch_tender_by_id(tender_id)
    if not row:
        raise HTTPException(404, "Contract not found.")
    if row.get("status") != "draft":
        raise HTTPException(409, "Only DRAFT contracts can be edited.")
    if row.get("published_by") != user["user_id"] and user["role"] != "admin":
        raise HTTPException(403, "You may only edit your own contracts.")

    if body.deadline:
        _validate_deadline(body.deadline)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(422, "No fields provided to update.")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [tender_id]

    conn = db.get_connection()
    try:
        conn.execute(
            f"UPDATE tenders SET {set_clause} WHERE tender_id = ?", values
        )
        db.write_audit_log(
            conn, user["user_id"], "edit_draft_contract",
            "tender", tender_id, json.dumps(updates),
        )
        conn.commit()
    finally:
        conn.close()

    row = db.fetch_tender_by_id(tender_id)
    return _row_to_response(row)


@router.post("/{tender_id}/publish", response_model=ContractResponse)
def publish_contract(
    tender_id: str,
    user: dict = Depends(require_role("official", "admin")),
):
    """Publish a DRAFT contract so bidders can see and bid on it."""
    row = db.fetch_tender_by_id(tender_id)
    if not row:
        raise HTTPException(404, "Contract not found.")
    if row.get("status") != "draft":
        raise HTTPException(409, "Only DRAFT contracts can be published.")
    if row.get("published_by") != user["user_id"] and user["role"] != "admin":
        raise HTTPException(403, "You may only publish your own contracts.")

    # Re-validate deadline at publish time
    deadline = row.get("deadline")
    if not deadline:
        raise HTTPException(422, "A deadline must be set before publishing.")
    _validate_deadline(deadline)

    conn = db.get_connection()
    try:
        conn.execute(
            "UPDATE tenders SET status = 'published' WHERE tender_id = ?",
            (tender_id,),
        )
        db.write_audit_log(
            conn, user["user_id"], "publish_contract",
            "tender", tender_id, None,
        )
        conn.commit()
    finally:
        conn.close()

    row = db.fetch_tender_by_id(tender_id)
    conn2 = db.get_connection()
    bid_count = conn2.execute(
        "SELECT COUNT(*) FROM bids WHERE tender_id = ?", (tender_id,)
    ).fetchone()[0]
    conn2.close()
    return _row_to_response(row, bid_count)


@router.get("", response_model=list[ContractResponse])
def list_my_contracts(user: dict = Depends(require_role("official", "admin"))):
    """List all contracts created by this official."""
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT * FROM tenders WHERE published_by = ? ORDER BY created_at DESC",
        (user["user_id"],),
    ).fetchall()
    tender_ids = [r["tender_id"] for r in rows]
    bid_counts = {}
    for tid in tender_ids:
        bid_counts[tid] = conn.execute(
            "SELECT COUNT(*) FROM bids WHERE tender_id = ?", (tid,)
        ).fetchone()[0]
    conn.close()
    return [_row_to_response(dict(r), bid_counts.get(r["tender_id"], 0)) for r in rows]


@router.get("/{tender_id}", response_model=ContractResponse)
def get_contract(
    tender_id: str,
    user: dict = Depends(get_current_user),
):
    """Detail view + bid count. Available to authenticated users."""
    row = db.fetch_tender_by_id(tender_id)
    if not row:
        raise HTTPException(404, "Contract not found.")
    conn = db.get_connection()
    bid_count = conn.execute(
        "SELECT COUNT(*) FROM bids WHERE tender_id = ?", (tender_id,)
    ).fetchone()[0]
    conn.close()
    return _row_to_response(row, bid_count)
