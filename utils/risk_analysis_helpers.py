"""
utils/risk_analysis_helpers.py

Pure data-preparation helpers for the Risk Analysis page.
No Streamlit imports — fully unit-testable.

These functions sit between the raw bid CSV / data_loader and the
risk_engine, handling source-type filtering, findings flattening,
and findings-table construction without touching any UI code.
"""

from __future__ import annotations

from typing import Optional
import pandas as pd

from utils.risk_engine import EngineResult, Finding, analyse

# Source-type values that are considered real public procurement data
REAL_SOURCE_TYPES = {"real_public_data"}

# Source-type values that are synthetic / demo only
SYNTHETIC_SOURCE_TYPES = {"synthetic_demo", "synthetic"}

SCORE_BAND_ORDER = ["Low", "Moderate", "Elevated", "High"]

BAND_COLOURS = {
    "Low":      "#28a745",
    "Moderate": "#fd7e14",
    "Elevated": "#dc3545",
    "High":     "#6f1e3f",
}


# --------------------------------------------------------------------------- #
#  Source-type filtering                                                       #
# --------------------------------------------------------------------------- #

def filter_bids_by_source(
    bids: pd.DataFrame,
    source_filter: str,
) -> pd.DataFrame:
    """
    Return only rows that match the requested source_filter.

    source_filter values:
      "all"              — return everything
      "real_public_data" — return only rows whose source_type is real_public_data
      "synthetic"        — return rows whose source_type is synthetic_demo or synthetic
    """
    if bids is None or bids.empty:
        return bids if bids is not None else pd.DataFrame()

    if source_filter == "all":
        return bids.copy()

    if source_filter == "real_public_data":
        return bids[bids["source_type"].isin(REAL_SOURCE_TYPES)].copy()

    if source_filter == "synthetic":
        return bids[bids["source_type"].isin(SYNTHETIC_SOURCE_TYPES)].copy()

    # Unknown filter value — return empty rather than leaking wrong data
    return pd.DataFrame(columns=bids.columns)


def has_real_bids(bids: pd.DataFrame) -> bool:
    """Return True if the DataFrame contains any real_public_data rows."""
    if bids is None or bids.empty:
        return False
    return bids["source_type"].isin(REAL_SOURCE_TYPES).any()


def has_synthetic_bids(bids: pd.DataFrame) -> bool:
    """Return True if the DataFrame contains any synthetic rows."""
    if bids is None or bids.empty:
        return False
    return bids["source_type"].isin(SYNTHETIC_SOURCE_TYPES).any()


# --------------------------------------------------------------------------- #
#  Findings → flat table                                                       #
# --------------------------------------------------------------------------- #

def findings_to_table(findings: list[Finding]) -> pd.DataFrame:
    """
    Convert a list of Finding objects into a flat DataFrame suitable
    for display in a Streamlit table.

    Includes both actionable and insufficient-data findings.
    Callers can filter by `insufficient_data` column.
    """
    rows = []
    for f in findings:
        rows.append({
            "rule": f.rule,
            "rule_name": f.rule_name,
            "tender_ids": ", ".join(f.tender_ids) if f.tender_ids else "—",
            "bidder_ids": ", ".join(f.bidder_ids) if f.bidder_ids else "—",
            "source_type": f.source_type,
            "explanation": f.explanation if not f.insufficient_data else "",
            "data_limitations": f.data_limitations,
            "insufficient_data": f.insufficient_data,
            "threshold_or_criterion": f.threshold_or_criterion,
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
        "rule", "rule_name", "tender_ids", "bidder_ids", "source_type",
        "explanation", "data_limitations", "insufficient_data", "threshold_or_criterion",
    ])


def filter_findings_table(
    df: pd.DataFrame,
    rule_filter: Optional[str] = None,
    tender_search: str = "",
    source_filter: Optional[str] = None,
    include_insufficient: bool = False,
) -> pd.DataFrame:
    """
    Filter a findings table produced by findings_to_table().

    Parameters
    ----------
    rule_filter        : e.g. "A", "B", "C" — None means all
    tender_search      : substring match against tender_ids column
    source_filter      : exact match on source_type column — None means all
    include_insufficient: if False, drop rows where insufficient_data is True
    """
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    result = df.copy()

    if not include_insufficient:
        result = result[result["insufficient_data"] == False]

    if rule_filter and rule_filter != "All":
        result = result[result["rule"] == rule_filter]

    if tender_search.strip():
        mask = result["tender_ids"].str.contains(
            tender_search.strip(), case=False, na=False
        )
        result = result[mask]

    if source_filter and source_filter != "All":
        result = result[result["source_type"] == source_filter]

    return result.reset_index(drop=True)


# --------------------------------------------------------------------------- #
#  Summary metrics                                                             #
# --------------------------------------------------------------------------- #

def summarise_result(result: EngineResult, total_bids: int) -> dict:
    """
    Produce a summary dict from an EngineResult for display as metric cards.
    Returns only values that are directly supported by the engine output.
    """
    actionable = [f for f in result.findings if not f.insufficient_data]
    rules_fired = sorted({f.rule for f in actionable})

    return {
        "total_bids_analysed": total_bids,
        "actionable_findings": len(actionable),
        "rules_fired": rules_fired,
        "score": result.score,
        "score_band": result.score_band,
        "real_data_available": result.real_data_available,
    }


# --------------------------------------------------------------------------- #
#  Engine wrapper with error handling                                          #
# --------------------------------------------------------------------------- #

def run_analysis_safe(
    bids: pd.DataFrame,
    config: Optional[dict] = None,
) -> tuple[Optional[EngineResult], Optional[str]]:
    """
    Call analyse() and catch any unexpected exception.
    Returns (result, error_message).  On success error_message is None.
    """
    try:
        return analyse(bids, config=config), None
    except Exception as exc:
        return None, f"Analysis failed: {exc}"
