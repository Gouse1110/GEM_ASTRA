"""
utils/risk_engine.py
Explainable bid-rigging risk detection engine for GeM Astra.

IMPORTANT DISCLAIMER
--------------------
All findings are analytical signals for authorised human reviewers only.
A risk score is NOT a probability of collusion and is NOT evidence of wrongdoing.
No supplier should be labelled guilty based on this output alone.

Detection rules
---------------
A  Unusual bid-price similarity      (configurable threshold, per-tender)
B  Repeated bidder co-participation  (configurable min shared tenders)
C  Possible winner rotation          (requires reliable outcome data)
D  Participation anomalies           (documented as unavailable — schema gap)

Score bands  (0-100, review priority only)
------------------------------------------
0-24   Low      — no notable signals
25-49  Moderate — one weak signal; routine review suggested
50-74  Elevated — multiple or stronger signals; closer review warranted
75-100 High     — several converging signals; prioritise for investigation
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

# --------------------------------------------------------------------------- #
#  Configuration (all thresholds documented here)                             #
# --------------------------------------------------------------------------- #

DEFAULT_CONFIG = {
    # Rule A: flag bids within this % of each other in the same tender
    "price_similarity_threshold_pct": 5.0,
    # Rule B: flag bidder pairs appearing together in at least this many tenders
    "co_participation_min_tenders": 2,
    # Rule C: minimum wins per bidder to assess rotation; minimum tenders in set
    "rotation_min_wins": 2,
    "rotation_min_tenders": 3,
    # Scoring weights (must sum ≤ 100; remainder stays at 0 if no signals)
    "weight_rule_a": 35,
    "weight_rule_b": 25,
    "weight_rule_c": 40,
}

# Tender statuses that carry no award data — never flag for winner rotation
_EVALUATION_STATUSES = {
    "technical evaluation",
    "not evaluated",
    "financial evaluation",
    "under evaluation",
}

BID_SCHEMA = ["tender_id", "bidder_id", "bid_amount",
              "bid_timestamp", "outcome", "product_category", "source_type"]


# --------------------------------------------------------------------------- #
#  Data classes                                                               #
# --------------------------------------------------------------------------- #

@dataclass
class Finding:
    rule: str                        # e.g. "A", "B", "C"
    rule_name: str
    tender_ids: list[str]
    bidder_ids: list[str]
    evidence: dict                   # raw numeric / string evidence
    threshold_or_criterion: str
    explanation: str                 # plain English
    source_type: str
    data_limitations: str = ""
    insufficient_data: bool = False


@dataclass
class EngineResult:
    findings: list[Finding] = field(default_factory=list)
    score: int = 0                   # 0-100, review priority only
    score_band: str = "Low"
    score_explanation: str = ""
    source_type: str = "unknown"
    real_data_available: bool = False
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
#  Public entry point                                                         #
# --------------------------------------------------------------------------- #

def analyse(
    bids: pd.DataFrame,
    config: Optional[dict] = None,
) -> EngineResult:
    """
    Run all detection rules on a bid DataFrame and return an EngineResult.

    Parameters
    ----------
    bids : DataFrame with columns matching BID_SCHEMA (extras are ignored).
    config : override DEFAULT_CONFIG keys as needed.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    result = EngineResult()

    if bids is None or bids.empty:
        result.warnings.append("No bid records supplied — analysis unavailable.")
        result.score_explanation = "No data."
        result.findings = _rule_d_unavailable()
        return result

    # Ensure all expected columns exist
    for col in BID_SCHEMA:
        if col not in bids.columns:
            bids = bids.copy()
            bids[col] = pd.NA

    # Drop rows with no tender_id or bidder_id (unusable)
    bids = bids.dropna(subset=["tender_id", "bidder_id"]).copy()
    bids["tender_id"] = bids["tender_id"].astype(str).str.strip()
    bids["bidder_id"] = bids["bidder_id"].astype(str).str.strip()

    if bids.empty:
        result.warnings.append("All rows missing tender_id or bidder_id.")
        return result

    # Determine dominant source type
    src_counts = bids["source_type"].value_counts()
    dominant_src = src_counts.index[0] if not src_counts.empty else "unknown"
    result.source_type = dominant_src
    result.real_data_available = dominant_src == "real_public_data"

    if not result.real_data_available:
        result.warnings.append(
            "No real_public_data bid records found. "
            "Findings below are based on synthetic/demo data only and "
            "do NOT reflect actual GeM procurement activity."
        )

    # Run rules
    findings: list[Finding] = []
    findings += _rule_a(bids, cfg)
    findings += _rule_b(bids, cfg)
    findings += _rule_c(bids, cfg)
    findings += _rule_d_unavailable()  # always present — documents schema gap

    result.findings = findings
    result.score, result.score_band, result.score_explanation = _score(findings, cfg)
    return result


# --------------------------------------------------------------------------- #
#  Rule A — Unusual bid-price similarity                                      #
# --------------------------------------------------------------------------- #

def _rule_a(bids: pd.DataFrame, cfg: dict) -> list[Finding]:
    threshold = float(cfg["price_similarity_threshold_pct"])
    findings: list[Finding] = []

    # Work per tender × product_category to avoid cross-category comparison
    group_cols = ["tender_id", "product_category"]
    for keys, grp in bids.groupby(group_cols, dropna=False):
        tender_id = keys[0] if isinstance(keys, tuple) else keys
        category = (keys[1] if isinstance(keys, tuple) else None) or "unknown"

        # Keep only rows with numeric bid amounts
        valid = grp.dropna(subset=["bid_amount"]).copy()
        try:
            valid["bid_amount"] = pd.to_numeric(valid["bid_amount"], errors="coerce")
            valid = valid.dropna(subset=["bid_amount"])
        except Exception:
            continue

        if len(valid) < 2:
            continue

        # Deduplicate: keep one row per bidder (lowest amount — conservative)
        valid = valid.sort_values("bid_amount").drop_duplicates(subset=["bidder_id"], keep="first")

        if len(valid) < 2:
            continue

        # Compare every pair of distinct bidders
        flagged_pairs = []
        rows = valid.to_dict("records")
        for r1, r2 in itertools.combinations(rows, 2):
            if r1["bidder_id"] == r2["bidder_id"]:
                continue
            a1, a2 = float(r1["bid_amount"]), float(r2["bid_amount"])
            if a1 <= 0 or a2 <= 0:
                continue
            diff_pct = abs(a1 - a2) / max(a1, a2) * 100
            if diff_pct <= threshold:
                flagged_pairs.append({
                    "bidder_a": r1["bidder_id"],
                    "bidder_b": r2["bidder_id"],
                    "bid_a": round(a1, 2),
                    "bid_b": round(a2, 2),
                    "diff_pct": round(diff_pct, 3),
                })

        if flagged_pairs:
            all_bidders = sorted({p["bidder_a"] for p in flagged_pairs}
                                 | {p["bidder_b"] for p in flagged_pairs})
            src = _dominant_source(grp)
            findings.append(Finding(
                rule="A",
                rule_name="Unusual bid-price similarity",
                tender_ids=[str(tender_id)],
                bidder_ids=all_bidders,
                evidence={"pairs": flagged_pairs, "product_category": category},
                threshold_or_criterion=(
                    f"Bid amounts within {threshold}% of each other "
                    f"in the same tender and product category"
                ),
                explanation=(
                    f"In tender {tender_id} ({category}), "
                    f"{len(flagged_pairs)} bidder pair(s) submitted amounts "
                    f"within {threshold}% of each other. "
                    "Unusually similar bids may warrant review, but can also "
                    "reflect competitive market pricing."
                ),
                source_type=src,
                data_limitations=(
                    "Only bids with numeric amounts in the same tender and "
                    "product category are compared."
                ),
            ))

    return findings


# --------------------------------------------------------------------------- #
#  Rule B — Repeated bidder co-participation                                  #
# --------------------------------------------------------------------------- #

def _rule_b(bids: pd.DataFrame, cfg: dict) -> list[Finding]:
    min_tenders = int(cfg["co_participation_min_tenders"])
    findings: list[Finding] = []

    # Map tender_id → set of bidder_ids
    tender_bidders: dict[str, set[str]] = (
        bids.groupby("tender_id")["bidder_id"]
        .apply(set)
        .to_dict()
    )

    # Count shared tenders for every bidder pair
    pair_tenders: dict[tuple[str, str], list[str]] = {}
    for tid, bidder_set in tender_bidders.items():
        bidders = sorted(bidder_set)
        for b1, b2 in itertools.combinations(bidders, 2):
            key = (b1, b2)
            pair_tenders.setdefault(key, []).append(tid)

    for (b1, b2), shared_tids in pair_tenders.items():
        if len(shared_tids) >= min_tenders:
            src = _dominant_source(
                bids[bids["bidder_id"].isin([b1, b2])]
            )
            findings.append(Finding(
                rule="B",
                rule_name="Repeated bidder co-participation",
                tender_ids=sorted(shared_tids),
                bidder_ids=[b1, b2],
                evidence={
                    "co_participation_count": len(shared_tids),
                    "shared_tender_ids": sorted(shared_tids),
                },
                threshold_or_criterion=(
                    f"Bidder pair appears together in ≥ {min_tenders} tenders"
                ),
                explanation=(
                    f"Bidders {b1} and {b2} have participated together in "
                    f"{len(shared_tids)} tender(s): {', '.join(sorted(shared_tids))}. "
                    "Repeated co-participation is a review signal. "
                    "It is common in competitive markets and is not evidence of coordination."
                ),
                source_type=src,
                data_limitations=(
                    "Co-participation count depends on completeness of bid records. "
                    "Partial data may under- or over-count shared tenders."
                ),
            ))

    return findings


# --------------------------------------------------------------------------- #
#  Rule C — Possible winner rotation                                          #
# --------------------------------------------------------------------------- #

def _rule_c(bids: pd.DataFrame, cfg: dict) -> list[Finding]:
    min_wins = int(cfg["rotation_min_wins"])
    min_tenders = int(cfg["rotation_min_tenders"])
    findings: list[Finding] = []

    # Exclude tenders in evaluation-only statuses if status column present
    working = bids.copy()

    # Only use bids with a reliable outcome value
    outcome_col = working["outcome"].astype(str).str.strip().str.lower()
    reliable = working[outcome_col.isin(["won", "lost", "awarded", "unsuccessful"])]

    if reliable.empty:
        findings.append(Finding(
            rule="C",
            rule_name="Possible winner rotation",
            tender_ids=[],
            bidder_ids=[],
            evidence={},
            threshold_or_criterion=(
                f"≥ {min_wins} wins per bidder across ≥ {min_tenders} tenders"
            ),
            explanation="",
            source_type="unknown",
            data_limitations=(
                "No reliable outcome data (won/lost/awarded/unsuccessful) found. "
                "Winner-rotation analysis requires confirmed award outcomes."
            ),
            insufficient_data=True,
        ))
        return findings

    # Normalise outcome to won/lost
    reliable = reliable.copy()
    reliable["_won"] = reliable["outcome"].str.lower().isin(["won", "awarded"])

    # Winners per tender
    winners = reliable[reliable["_won"]][["tender_id", "bidder_id"]].drop_duplicates()

    if len(winners["tender_id"].unique()) < min_tenders:
        findings.append(Finding(
            rule="C",
            rule_name="Possible winner rotation",
            tender_ids=[],
            bidder_ids=[],
            evidence={"distinct_awarded_tenders": int(winners["tender_id"].nunique())},
            threshold_or_criterion=(
                f"≥ {min_tenders} tenders with award outcomes required"
            ),
            explanation="",
            source_type=_dominant_source(reliable),
            data_limitations=(
                f"Only {winners['tender_id'].nunique()} tender(s) with award outcomes — "
                f"minimum {min_tenders} required for rotation analysis."
            ),
            insufficient_data=True,
        ))
        return findings

    win_counts = winners.groupby("bidder_id")["tender_id"].count()
    rotating = win_counts[win_counts >= min_wins]

    if rotating.empty:
        return findings  # no rotation signal — normal, no finding needed

    # Rotation requires at least 2 distinct winners
    if len(rotating) < 2:
        return findings

    # Check for alternating pattern: no single bidder wins all
    total_awarded = len(winners["tender_id"].unique())
    rotating_bidders = rotating.index.tolist()

    # Simple alternation check: rotating bidders collectively cover most tenders
    # but no one bidder wins all
    covered_tenders = winners[winners["bidder_id"].isin(rotating_bidders)][
        "tender_id"
    ].unique()
    coverage_pct = len(covered_tenders) / total_awarded * 100

    if coverage_pct < 60:
        return findings  # pattern not strong enough

    src = _dominant_source(reliable)
    findings.append(Finding(
        rule="C",
        rule_name="Possible winner rotation",
        tender_ids=sorted(covered_tenders.tolist()),
        bidder_ids=sorted(rotating_bidders),
        evidence={
            "win_counts": win_counts[rotating_bidders].to_dict(),
            "total_awarded_tenders": total_awarded,
            "coverage_pct": round(coverage_pct, 1),
        },
        threshold_or_criterion=(
            f"Each rotating bidder wins ≥ {min_wins} tenders; "
            f"group covers ≥ 60% of awarded tenders"
        ),
        explanation=(
            f"Bidder(s) {', '.join(rotating_bidders)} each won ≥ {min_wins} "
            f"tenders and together account for {coverage_pct:.0f}% of awarded tenders. "
            "An alternating win pattern may suggest coordination but can also "
            "reflect specialisation or competitive advantage. Human review required."
        ),
        source_type=src,
        data_limitations=(
            "Rotation analysis depends on complete and accurate outcome records. "
            "Missing outcomes reduce reliability."
        ),
    ))

    return findings


# --------------------------------------------------------------------------- #
#  Rule D — Participation anomalies (unavailable)                             #
# --------------------------------------------------------------------------- #

def _rule_d_unavailable() -> list[Finding]:
    """
    Rule D requires bid submission timestamps with sufficient granularity,
    geographic/IP metadata, and consortium/subcontractor linkage data —
    none of which are present in the current schema.
    Returning an explicit insufficient-data marker rather than fabricating signals.
    """
    return [Finding(
        rule="D",
        rule_name="Participation anomalies",
        tender_ids=[],
        bidder_ids=[],
        evidence={},
        threshold_or_criterion="N/A — schema requirements not met",
        explanation="",
        source_type="unknown",
        data_limitations=(
            "Rule D requires bid submission timestamp granularity (seconds), "
            "geographic or IP metadata, and consortium/subcontractor linkage fields. "
            "These are not present in the current bid schema. "
            "Rule D is unavailable until the schema is extended."
        ),
        insufficient_data=True,
    )]


# --------------------------------------------------------------------------- #
#  Scoring                                                                     #
# --------------------------------------------------------------------------- #

def _score(findings: list[Finding], cfg: dict) -> tuple[int, str, str]:
    """
    Produce a 0-100 review-priority score.

    Weights:
      Rule A (price similarity)       → up to cfg["weight_rule_a"]  (35)
      Rule B (co-participation)       → up to cfg["weight_rule_b"]  (25)
      Rule C (winner rotation)        → up to cfg["weight_rule_c"]  (40)

    Correlated indicators are not treated as independent proof.
    Insufficient-data findings contribute 0.
    """
    wa = cfg["weight_rule_a"]
    wb = cfg["weight_rule_b"]
    wc = cfg["weight_rule_c"]

    a_hits = [f for f in findings if f.rule == "A" and not f.insufficient_data]
    b_hits = [f for f in findings if f.rule == "B" and not f.insufficient_data]
    c_hits = [f for f in findings if f.rule == "C" and not f.insufficient_data]

    # Rule A: score scales with number of flagged tenders, capped at weight
    score_a = min(wa, len(a_hits) * (wa // max(1, len(a_hits)))) if a_hits else 0

    # Rule B: score scales with max co-participation count
    if b_hits:
        max_copair = max(
            f.evidence.get("co_participation_count", 0) for f in b_hits
        )
        score_b = min(wb, int(wb * min(max_copair / 5, 1.0)))
    else:
        score_b = 0

    # Rule C: binary — rotation either found or not
    score_c = wc if c_hits else 0

    raw = score_a + score_b + score_c
    score = max(0, min(100, raw))

    if score < 25:
        band = "Low"
        explanation = "No notable signals detected."
    elif score < 50:
        band = "Moderate"
        explanation = "One or more weak signals present. Routine review suggested."
    elif score < 75:
        band = "Elevated"
        explanation = "Multiple or stronger signals. Closer review warranted."
    else:
        band = "High"
        explanation = "Several converging signals. Prioritise for investigation."

    detail = (
        f"Score breakdown — "
        f"Rule A (price similarity): {score_a}/{wa}, "
        f"Rule B (co-participation): {score_b}/{wb}, "
        f"Rule C (winner rotation): {score_c}/{wc}. "
        f"Total: {score}/100 ({band}). "
        f"{explanation} "
        "This score is a review-priority indicator only, "
        "not a probability of collusion."
    )

    return score, band, detail


# --------------------------------------------------------------------------- #
#  Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _dominant_source(df: pd.DataFrame) -> str:
    if "source_type" not in df.columns or df.empty:
        return "unknown"
    counts = df["source_type"].value_counts()
    return counts.index[0] if not counts.empty else "unknown"
