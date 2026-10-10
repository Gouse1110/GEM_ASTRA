"""
backend/routers/summary.py
Overview dashboard summary endpoint.

Provides actual counts from the SQLite tenders table, the synthetic bid
dataset (demo_bids.csv), and the risk-analysis engine.

IMPORTANT: Bid records and findings are currently sourced from the
synthetic_demo dataset (data/demo_bids.csv). They are clearly labelled
as such and must NOT be presented as real GeM procurement data.

Performance note
----------------
Bid statistics and risk-engine findings are pre-computed once at module
load time (server startup). demo_bids.csv is a static read-only file;
re-running the engine on every HTTP request is unnecessary and expensive.
Only the tender_count is fetched live from SQLite per request, because
tenders can be imported at any time through the Tender Explorer.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

import utils.database as db
from utils.data_loader import load_bids
from utils.risk_analysis_helpers import run_analysis_safe

router = APIRouter(prefix="/api/summary", tags=["summary"])


# --------------------------------------------------------------------------- #
#  Pre-computed bid statistics (computed once at startup)                     #
# --------------------------------------------------------------------------- #

def _compute_bid_stats() -> dict:
    """
    Load demo_bids.csv and run the risk engine once at import time.
    Returns a dict with bid_record_count, unique_bidder_count,
    active_findings_count, bid_source, bid_source_label,
    findings_source, findings_source_label.
    """
    bids = load_bids()

    if bids.empty:
        bid_record_count = 0
        unique_bidder_count = 0
        dominant = "unknown"
    else:
        bid_record_count = len(bids)
        valid_bidders = (
            bids["bidder_id"]
            .dropna()
            .astype(str)
            .str.strip()
            .replace("", None)
            .dropna()
        )
        unique_bidder_count = int(valid_bidders.nunique())
        dominant = (
            bids["source_type"].value_counts().index[0]
            if "source_type" in bids.columns
            else "unknown"
        )

    bid_source = dominant
    bid_source_label = (
        "Synthetic demo data (demo_bids.csv)"
        if "synthetic" in dominant
        else dominant
    )

    # Run risk engine
    result, engine_error = run_analysis_safe(bids if not bids.empty else None)

    if engine_error or result is None:
        active_findings_count = None
        findings_source = "unavailable"
        findings_source_label = "Engine error — findings unavailable"
    else:
        actionable = [f for f in result.findings if not f.insufficient_data]
        active_findings_count = len(actionable)
        findings_source = bid_source
        findings_source_label = (
            "Synthetic demo analysis — not real GeM data"
            if "synthetic" in bid_source
            else bid_source
        )

    return {
        "bid_record_count": bid_record_count,
        "unique_bidder_count": unique_bidder_count,
        "bid_source": bid_source,
        "bid_source_label": bid_source_label,
        "active_findings_count": active_findings_count,
        "findings_source": findings_source,
        "findings_source_label": findings_source_label,
    }


# Computed once when the module is first imported (server startup).
# Re-computed only if the module is reloaded (e.g. uvicorn --reload on
# demo_bids.csv change).
_BID_STATS: dict = _compute_bid_stats()


# --------------------------------------------------------------------------- #
#  Response model                                                              #
# --------------------------------------------------------------------------- #

class SummaryResponse(BaseModel):
    tender_count: int
    tender_source: str
    bid_record_count: Optional[int]
    unique_bidder_count: Optional[int]
    bid_source: str
    bid_source_label: str
    active_findings_count: Optional[int]
    findings_source: str
    findings_source_label: str


# --------------------------------------------------------------------------- #
#  Endpoint                                                                    #
# --------------------------------------------------------------------------- #

@router.get("", response_model=SummaryResponse)
def get_summary() -> SummaryResponse:
    """
    Return current platform summary metrics for the Overview dashboard.

    tender_count is fetched live (tenders can be imported at any time).
    All bid/findings stats come from the pre-computed startup cache.
    """
    return SummaryResponse(
        tender_count=db.count_tenders(),
        tender_source="sqlite_db",
        **_BID_STATS,
    )
