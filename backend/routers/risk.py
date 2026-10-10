"""
backend/routers/risk.py
Risk Analysis API — exposes existing engine results over FastAPI.

DISCLAIMER
----------
All current findings come from the synthetic_demo dataset (demo_bids.csv).
A risk score is a review-priority signal ONLY — not a probability of collusion.
No supplier should be labelled guilty based on this output alone.
All findings require expert human review before any action is taken.
"""

from __future__ import annotations

from typing import Optional, Any
from fastapi import APIRouter
from pydantic import BaseModel

from utils.data_loader import load_bids
from utils.risk_analysis_helpers import run_analysis_safe

router = APIRouter(prefix="/api/risk", tags=["risk"])


# --------------------------------------------------------------------------- #
#  Response models                                                             #
# --------------------------------------------------------------------------- #

class FindingModel(BaseModel):
    rule: str
    rule_name: str
    tender_ids: list[str]
    bidder_ids: list[str]
    evidence: dict[str, Any]
    threshold_or_criterion: str
    explanation: str
    source_type: str
    data_limitations: str
    insufficient_data: bool


class RiskSummary(BaseModel):
    score: int                          # 0–100 review-priority, not collusion probability
    score_band: str                     # Low / Moderate / Elevated / High
    score_explanation: str
    total_bids_analysed: int
    actionable_findings_count: int
    rules_fired: list[str]
    source_type: str
    real_data_available: bool
    warnings: list[str]


class RiskResponse(BaseModel):
    summary: RiskSummary
    findings: list[FindingModel]        # all findings incl. insufficient_data
    source_label: str
    disclaimer: str


# --------------------------------------------------------------------------- #
#  Pre-compute at startup (demo_bids.csv is static)                           #
# --------------------------------------------------------------------------- #

DISCLAIMER = (
    "Risk scores are review-priority indicators (0–100) only. "
    "They are NOT a probability of collusion, fraud, or wrongdoing. "
    "All findings require expert human review and corroborating evidence "
    "before any conclusion or action is taken."
)


def _build_risk_response() -> RiskResponse:
    bids = load_bids()
    result, error = run_analysis_safe(bids if not bids.empty else None)

    if error or result is None:
        return RiskResponse(
            summary=RiskSummary(
                score=0, score_band="Low",
                score_explanation="Engine error — analysis unavailable.",
                total_bids_analysed=0,
                actionable_findings_count=0,
                rules_fired=[],
                source_type="unknown",
                real_data_available=False,
                warnings=[error or "Analysis returned no result."],
            ),
            findings=[],
            source_label="unknown",
            disclaimer=DISCLAIMER,
        )

    total_bids = len(bids) if not bids.empty else 0
    actionable = [f for f in result.findings if not f.insufficient_data]
    rules_fired = sorted({f.rule for f in actionable})

    findings_out = [
        FindingModel(
            rule=f.rule,
            rule_name=f.rule_name,
            tender_ids=f.tender_ids,
            bidder_ids=f.bidder_ids,
            evidence=f.evidence,
            threshold_or_criterion=f.threshold_or_criterion,
            explanation=f.explanation,
            source_type=f.source_type,
            data_limitations=f.data_limitations,
            insufficient_data=f.insufficient_data,
        )
        for f in result.findings
    ]

    dominant_src = result.source_type
    source_label = (
        "Synthetic demo data (demo_bids.csv)"
        if "synthetic" in dominant_src
        else dominant_src
    )

    return RiskResponse(
        summary=RiskSummary(
            score=result.score,
            score_band=result.score_band,
            score_explanation=result.score_explanation,
            total_bids_analysed=total_bids,
            actionable_findings_count=len(actionable),
            rules_fired=rules_fired,
            source_type=dominant_src,
            real_data_available=result.real_data_available,
            warnings=result.warnings,
        ),
        findings=findings_out,
        source_label=source_label,
        disclaimer=DISCLAIMER,
    )


# Pre-computed once at startup
_RISK: RiskResponse = _build_risk_response()


# --------------------------------------------------------------------------- #
#  Endpoints                                                                   #
# --------------------------------------------------------------------------- #

@router.get("", response_model=RiskResponse)
def get_risk_analysis() -> RiskResponse:
    """
    Return risk-analysis results from the existing detection engine.
    Pre-computed at server startup from demo_bids.csv.
    """
    return _RISK


@router.get("/findings", response_model=list[FindingModel])
def get_findings(
    rule: Optional[str] = None,
    include_insufficient: bool = False,
) -> list[FindingModel]:
    """Return findings filtered by rule and/or insufficient_data flag."""
    findings = _RISK.findings
    if not include_insufficient:
        findings = [f for f in findings if not f.insufficient_data]
    if rule:
        findings = [f for f in findings if f.rule == rule.upper()]
    return findings
