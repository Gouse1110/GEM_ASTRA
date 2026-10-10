"""
backend/routers/network.py
Bidder Network API — bidder co-participation graph from demo_bids.csv.

DISCLAIMER
----------
All data comes from the synthetic_demo dataset (demo_bids.csv).
Relationships represent shared tender participation in synthetic records only.
This is NOT real GeM procurement data and does NOT imply collusion or fraud.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from utils.data_loader import load_bids

router = APIRouter(prefix="/api/network", tags=["network"])


# --------------------------------------------------------------------------- #
#  Response models                                                             #
# --------------------------------------------------------------------------- #

class BidderNode(BaseModel):
    bidder_id: str
    tender_count: int          # number of tenders this bidder participated in
    source_type: str


class BidderEdge(BaseModel):
    bidder_a: str
    bidder_b: str
    shared_tender_count: int
    shared_tender_ids: list[str]
    source_type: str


class NetworkResponse(BaseModel):
    nodes: list[BidderNode]
    edges: list[BidderEdge]
    source_label: str
    disclaimer: str
    total_bidders: int
    total_edges: int


# --------------------------------------------------------------------------- #
#  Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _build_network(bids) -> NetworkResponse:
    """Build node/edge graph from a bids DataFrame."""
    import pandas as pd

    DISCLAIMER = (
        "Relationships shown are based solely on shared participation in the same "
        "synthetic demo tender. Shared participation is a review signal only — "
        "it is NOT evidence of coordination, collusion, or fraud."
    )

    if bids is None or (hasattr(bids, "empty") and bids.empty):
        return NetworkResponse(
            nodes=[], edges=[],
            source_label="synthetic_demo",
            disclaimer=DISCLAIMER,
            total_bidders=0, total_edges=0,
        )

    # Drop rows with missing tender_id or bidder_id
    clean = bids.dropna(subset=["tender_id", "bidder_id"]).copy()
    clean["tender_id"] = clean["tender_id"].astype(str).str.strip()
    clean["bidder_id"] = clean["bidder_id"].astype(str).str.strip()
    clean = clean[clean["bidder_id"] != ""]
    clean = clean[clean["tender_id"] != ""]

    if clean.empty:
        return NetworkResponse(
            nodes=[], edges=[],
            source_label="synthetic_demo",
            disclaimer=DISCLAIMER,
            total_bidders=0, total_edges=0,
        )

    # Determine dominant source type
    dominant_src = (
        clean["source_type"].value_counts().index[0]
        if "source_type" in clean.columns
        else "unknown"
    )

    # --- Nodes ---
    bidder_tender_counts = (
        clean.groupby("bidder_id")["tender_id"].nunique().to_dict()
    )
    nodes = [
        BidderNode(
            bidder_id=bid,
            tender_count=int(cnt),
            source_type=dominant_src,
        )
        for bid, cnt in sorted(bidder_tender_counts.items())
    ]

    # --- Edges ---
    # Map tender_id → set of bidder_ids
    tender_bidders: dict[str, set[str]] = (
        clean.groupby("tender_id")["bidder_id"].apply(set).to_dict()
    )

    pair_tenders: dict[tuple[str, str], list[str]] = defaultdict(list)
    for tid, bidder_set in tender_bidders.items():
        for b1, b2 in itertools.combinations(sorted(bidder_set), 2):
            if b1 != b2:  # no self-edges
                pair_tenders[(b1, b2)].append(tid)

    edges = [
        BidderEdge(
            bidder_a=b1,
            bidder_b=b2,
            shared_tender_count=len(tids),
            shared_tender_ids=sorted(tids),
            source_type=dominant_src,
        )
        for (b1, b2), tids in sorted(pair_tenders.items())
    ]

    return NetworkResponse(
        nodes=nodes,
        edges=edges,
        source_label=dominant_src,
        disclaimer=DISCLAIMER,
        total_bidders=len(nodes),
        total_edges=len(edges),
    )


# Pre-compute at startup — demo_bids.csv is static
_NETWORK: NetworkResponse = _build_network(load_bids())


# --------------------------------------------------------------------------- #
#  Endpoints                                                                   #
# --------------------------------------------------------------------------- #

@router.get("", response_model=NetworkResponse)
def get_network() -> NetworkResponse:
    """Return bidder co-participation graph from the synthetic demo dataset."""
    return _NETWORK


@router.get("/bidder/{bidder_id}", response_model=dict)
def get_bidder_detail(bidder_id: str) -> dict:
    """Return edges and connected bidders for a specific bidder."""
    connected_edges = [
        e for e in _NETWORK.edges
        if e.bidder_a == bidder_id or e.bidder_b == bidder_id
    ]
    connected_bidders = sorted({
        (e.bidder_b if e.bidder_a == bidder_id else e.bidder_a)
        for e in connected_edges
    })
    node = next((n for n in _NETWORK.nodes if n.bidder_id == bidder_id), None)
    if node is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Bidder '{bidder_id}' not found")
    return {
        "bidder_id": bidder_id,
        "tender_count": node.tender_count,
        "connected_bidders": connected_bidders,
        "edges": [e.model_dump() for e in connected_edges],
        "source_type": node.source_type,
    }
