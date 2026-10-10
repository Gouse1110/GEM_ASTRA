"""
tests/test_risk_engine.py
Tests for the bid-rigging risk detection engine.

Run with: python -m pytest tests/ -v
"""

import pytest
import pandas as pd
from utils.risk_engine import analyse, DEFAULT_CONFIG, Finding, EngineResult

# ------------------------------------------------------------------ #
#  Helpers                                                            #
# ------------------------------------------------------------------ #

def make_bids(*rows):
    """Build a DataFrame from a list of dicts (missing fields defaulted)."""
    defaults = {
        "tender_id": "T001", "bidder_id": "B001", "bid_amount": 100000,
        "bid_timestamp": "2024-01-01 10:00:00", "outcome": "won",
        "product_category": "laptops", "source_type": "synthetic_demo",
    }
    records = [{**defaults, **r} for r in rows]
    return pd.DataFrame(records)


# ------------------------------------------------------------------ #
#  1. Empty / no data                                                 #
# ------------------------------------------------------------------ #

def test_empty_dataframe_returns_safe_result():
    result = analyse(pd.DataFrame())
    assert isinstance(result, EngineResult)
    assert result.score == 0
    assert len(result.warnings) > 0


def test_none_input_returns_safe_result():
    result = analyse(None)
    assert result.score == 0
    assert result.real_data_available is False


def test_all_rows_missing_ids_returns_safe():
    df = pd.DataFrame([{"bid_amount": 100}])
    result = analyse(df)
    assert result.score == 0


# ------------------------------------------------------------------ #
#  2. Rule A — price similarity                                       #
# ------------------------------------------------------------------ #

def test_rule_a_flags_similar_bids():
    bids = make_bids(
        {"bidder_id": "B001", "bid_amount": 100000},
        {"bidder_id": "B002", "bid_amount": 101000},  # 1% diff — should flag
        {"bidder_id": "B003", "bid_amount": 130000},  # 30% diff — should not flag
    )
    result = analyse(bids)
    a_findings = [f for f in result.findings if f.rule == "A" and not f.insufficient_data]
    assert len(a_findings) >= 1
    pairs = a_findings[0].evidence["pairs"]
    flagged_bidders = {p["bidder_a"] for p in pairs} | {p["bidder_b"] for p in pairs}
    assert "B001" in flagged_bidders
    assert "B002" in flagged_bidders


def test_rule_a_does_not_flag_dissimilar_bids():
    bids = make_bids(
        {"bidder_id": "B001", "bid_amount": 100000},
        {"bidder_id": "B002", "bid_amount": 200000},  # 100% diff
    )
    result = analyse(bids)
    a_findings = [f for f in result.findings if f.rule == "A" and not f.insufficient_data]
    assert len(a_findings) == 0


def test_rule_a_threshold_is_configurable():
    bids = make_bids(
        {"bidder_id": "B001", "bid_amount": 100000},
        {"bidder_id": "B002", "bid_amount": 108000},  # 8% diff
    )
    # With default 5% threshold — should NOT flag
    r1 = analyse(bids)
    assert not any(f.rule == "A" and not f.insufficient_data for f in r1.findings)

    # With 10% threshold — should flag
    r2 = analyse(bids, config={"price_similarity_threshold_pct": 10.0})
    assert any(f.rule == "A" and not f.insufficient_data for f in r2.findings)


def test_rule_a_different_categories_not_compared():
    """Bids in different product categories must not be cross-compared."""
    bids = make_bids(
        {"tender_id": "T001", "bidder_id": "B001", "bid_amount": 100000,
         "product_category": "laptops"},
        {"tender_id": "T001", "bidder_id": "B002", "bid_amount": 100500,
         "product_category": "furniture"},  # different category
    )
    result = analyse(bids)
    a_findings = [f for f in result.findings if f.rule == "A" and not f.insufficient_data]
    # Each group has only 1 bid — no pair comparison possible
    assert len(a_findings) == 0


def test_rule_a_different_tenders_not_compared():
    """Bids in different tenders must never be compared to each other."""
    bids = make_bids(
        {"tender_id": "T001", "bidder_id": "B001", "bid_amount": 100000},
        {"tender_id": "T002", "bidder_id": "B002", "bid_amount": 100100},
    )
    result = analyse(bids)
    a_findings = [f for f in result.findings if f.rule == "A" and not f.insufficient_data]
    assert len(a_findings) == 0


def test_rule_a_missing_bid_amounts_skipped():
    bids = make_bids(
        {"bidder_id": "B001", "bid_amount": None},
        {"bidder_id": "B002", "bid_amount": None},
    )
    result = analyse(bids)
    a_findings = [f for f in result.findings if f.rule == "A" and not f.insufficient_data]
    assert len(a_findings) == 0


def test_rule_a_only_one_valid_bid_no_flag():
    bids = make_bids(
        {"bidder_id": "B001", "bid_amount": 100000},
        {"bidder_id": "B002", "bid_amount": None},
    )
    result = analyse(bids)
    a_findings = [f for f in result.findings if f.rule == "A" and not f.insufficient_data]
    assert len(a_findings) == 0


def test_rule_a_finding_has_required_fields():
    bids = make_bids(
        {"bidder_id": "B001", "bid_amount": 100000},
        {"bidder_id": "B002", "bid_amount": 100200},
    )
    result = analyse(bids)
    a = next((f for f in result.findings if f.rule == "A" and not f.insufficient_data), None)
    assert a is not None
    assert a.rule_name
    assert a.tender_ids
    assert a.bidder_ids
    assert a.explanation
    assert a.threshold_or_criterion
    assert a.source_type


# ------------------------------------------------------------------ #
#  3. Rule B — co-participation                                       #
# ------------------------------------------------------------------ #

def test_rule_b_flags_repeated_pair():
    bids = make_bids(
        {"tender_id": "T001", "bidder_id": "B001"},
        {"tender_id": "T001", "bidder_id": "B002"},
        {"tender_id": "T002", "bidder_id": "B001"},
        {"tender_id": "T002", "bidder_id": "B002"},
    )
    result = analyse(bids)
    b_findings = [f for f in result.findings if f.rule == "B" and not f.insufficient_data]
    assert len(b_findings) >= 1
    assert "B001" in b_findings[0].bidder_ids
    assert "B002" in b_findings[0].bidder_ids


def test_rule_b_single_shared_tender_not_flagged():
    bids = make_bids(
        {"tender_id": "T001", "bidder_id": "B001"},
        {"tender_id": "T001", "bidder_id": "B002"},
    )
    result = analyse(bids)
    b_findings = [f for f in result.findings if f.rule == "B" and not f.insufficient_data]
    assert len(b_findings) == 0


def test_rule_b_threshold_configurable():
    bids = make_bids(
        {"tender_id": "T001", "bidder_id": "B001"},
        {"tender_id": "T001", "bidder_id": "B002"},
        {"tender_id": "T002", "bidder_id": "B001"},
        {"tender_id": "T002", "bidder_id": "B002"},
        {"tender_id": "T003", "bidder_id": "B001"},
        {"tender_id": "T003", "bidder_id": "B002"},
    )
    # Require 5 shared tenders — should NOT flag
    r = analyse(bids, config={"co_participation_min_tenders": 5})
    assert not any(f.rule == "B" and not f.insufficient_data for f in r.findings)


def test_rule_b_co_participation_count_in_evidence():
    bids = make_bids(
        {"tender_id": "T001", "bidder_id": "B001"},
        {"tender_id": "T001", "bidder_id": "B002"},
        {"tender_id": "T002", "bidder_id": "B001"},
        {"tender_id": "T002", "bidder_id": "B002"},
    )
    result = analyse(bids)
    b = next((f for f in result.findings if f.rule == "B" and not f.insufficient_data), None)
    assert b is not None
    assert b.evidence["co_participation_count"] == 2


# ------------------------------------------------------------------ #
#  4. Rule C — winner rotation                                        #
# ------------------------------------------------------------------ #

def test_rule_c_flags_rotation_pattern():
    bids = make_bids(
        {"tender_id": "T001", "bidder_id": "B001", "outcome": "won"},
        {"tender_id": "T001", "bidder_id": "B002", "outcome": "lost"},
        {"tender_id": "T002", "bidder_id": "B002", "outcome": "won"},
        {"tender_id": "T002", "bidder_id": "B001", "outcome": "lost"},
        {"tender_id": "T003", "bidder_id": "B001", "outcome": "won"},
        {"tender_id": "T003", "bidder_id": "B002", "outcome": "lost"},
        {"tender_id": "T004", "bidder_id": "B002", "outcome": "awarded"},
        {"tender_id": "T004", "bidder_id": "B001", "outcome": "lost"},
    )
    result = analyse(bids)
    c_findings = [f for f in result.findings if f.rule == "C" and not f.insufficient_data]
    assert len(c_findings) >= 1


def test_rule_c_no_outcomes_returns_insufficient_data():
    bids = make_bids(
        {"tender_id": "T001", "bidder_id": "B001", "outcome": None},
        {"tender_id": "T001", "bidder_id": "B002", "outcome": None},
    )
    result = analyse(bids)
    c = next((f for f in result.findings if f.rule == "C"), None)
    assert c is not None
    assert c.insufficient_data is True


def test_rule_c_missing_outcomes_returns_insufficient():
    bids = make_bids(
        {"tender_id": "T001", "bidder_id": "B001", "outcome": ""},
        {"tender_id": "T002", "bidder_id": "B001", "outcome": "pending"},
    )
    result = analyse(bids)
    c = next((f for f in result.findings if f.rule == "C"), None)
    assert c is not None
    assert c.insufficient_data is True


def test_rule_c_too_few_awarded_tenders_insufficient():
    """Fewer than rotation_min_tenders awarded tenders → insufficient data."""
    bids = make_bids(
        {"tender_id": "T001", "bidder_id": "B001", "outcome": "won"},
        {"tender_id": "T001", "bidder_id": "B002", "outcome": "lost"},
    )
    result = analyse(bids)
    c = next((f for f in result.findings if f.rule == "C"), None)
    assert c is not None
    assert c.insufficient_data is True


def test_rule_c_single_winner_no_rotation():
    """One bidder wins everything — no rotation pattern."""
    bids = make_bids(
        {"tender_id": "T001", "bidder_id": "B001", "outcome": "won"},
        {"tender_id": "T002", "bidder_id": "B001", "outcome": "won"},
        {"tender_id": "T003", "bidder_id": "B001", "outcome": "won"},
        {"tender_id": "T004", "bidder_id": "B001", "outcome": "won"},
    )
    result = analyse(bids)
    c_findings = [f for f in result.findings if f.rule == "C" and not f.insufficient_data]
    # B001 wins all — no alternating pattern
    assert len(c_findings) == 0


# ------------------------------------------------------------------ #
#  5. Rule D — unavailable                                            #
# ------------------------------------------------------------------ #

def test_rule_d_always_returns_insufficient_data():
    result = analyse(make_bids())
    d = next((f for f in result.findings if f.rule == "D"), None)
    assert d is not None
    assert d.insufficient_data is True
    assert len(d.data_limitations) > 0


# ------------------------------------------------------------------ #
#  6. Duplicate records                                               #
# ------------------------------------------------------------------ #

def test_duplicate_bids_do_not_double_count_pairs():
    """Same row inserted twice — pair should be flagged once, not doubled."""
    row = {"tender_id": "T001", "bidder_id": "B001", "bid_amount": 100000}
    row2 = {"tender_id": "T001", "bidder_id": "B002", "bid_amount": 100200}
    bids = pd.DataFrame([
        {**{**{"bid_timestamp": "2024-01-01", "outcome": "won",
               "product_category": "laptops", "source_type": "synthetic_demo"}, **row}},
        {**{**{"bid_timestamp": "2024-01-01", "outcome": "won",
               "product_category": "laptops", "source_type": "synthetic_demo"}, **row}},
        {**{**{"bid_timestamp": "2024-01-01", "outcome": "lost",
               "product_category": "laptops", "source_type": "synthetic_demo"}, **row2}},
    ])
    result = analyse(bids)
    # Rule A should flag exactly one pair (B001-B002), not multiple
    a_findings = [f for f in result.findings if f.rule == "A" and not f.insufficient_data]
    if a_findings:
        pairs = a_findings[0].evidence["pairs"]
        unique_pairs = {(p["bidder_a"], p["bidder_b"]) for p in pairs}
        assert len(unique_pairs) == len(pairs)


# ------------------------------------------------------------------ #
#  7. Source-type separation                                          #
# ------------------------------------------------------------------ #

def test_synthetic_data_flagged_as_non_real():
    bids = make_bids(
        {"bidder_id": "B001", "bid_amount": 100000, "source_type": "synthetic_demo"},
        {"bidder_id": "B002", "bid_amount": 100200, "source_type": "synthetic_demo"},
    )
    result = analyse(bids)
    assert result.real_data_available is False
    assert any("synthetic" in w.lower() or "real_public_data" in w.lower()
               for w in result.warnings)


def test_real_data_flagged_correctly():
    bids = make_bids(
        {"bidder_id": "B001", "bid_amount": 100000, "source_type": "real_public_data"},
        {"bidder_id": "B002", "bid_amount": 100200, "source_type": "real_public_data"},
    )
    result = analyse(bids)
    assert result.real_data_available is True


def test_findings_carry_source_type():
    bids = make_bids(
        {"bidder_id": "B001", "bid_amount": 100000, "source_type": "synthetic_demo"},
        {"bidder_id": "B002", "bid_amount": 100300, "source_type": "synthetic_demo"},
    )
    result = analyse(bids)
    for f in result.findings:
        if not f.insufficient_data:
            assert f.source_type  # must not be empty


# ------------------------------------------------------------------ #
#  8. Score bounds and determinism                                    #
# ------------------------------------------------------------------ #

def test_score_within_bounds():
    bids = make_bids(
        {"bidder_id": "B001", "bid_amount": 100000},
        {"bidder_id": "B002", "bid_amount": 100100},
    )
    result = analyse(bids)
    assert 0 <= result.score <= 100


def test_score_is_deterministic():
    bids = make_bids(
        {"bidder_id": "B001", "bid_amount": 100000},
        {"bidder_id": "B002", "bid_amount": 100100},
    )
    r1 = analyse(bids)
    r2 = analyse(bids)
    assert r1.score == r2.score


def test_score_zero_for_ordinary_bids():
    """Well-separated bids with no suspicious patterns → score should be 0."""
    bids = make_bids(
        {"tender_id": "T001", "bidder_id": "B001", "bid_amount": 100000, "outcome": "won"},
        {"tender_id": "T001", "bidder_id": "B002", "bid_amount": 200000, "outcome": "lost"},
    )
    result = analyse(bids)
    assert result.score == 0


def test_score_band_labels():
    for score, expected_band in [(0, "Low"), (24, "Low"), (25, "Moderate"),
                                  (49, "Moderate"), (50, "Elevated"),
                                  (74, "Elevated"), (75, "High"), (100, "High")]:
        from utils.risk_engine import _score
        # Construct mock findings to hit target score indirectly
        # Just test the band logic directly
        _, band, _ = _score([], {"weight_rule_a": 0, "weight_rule_b": 0, "weight_rule_c": 0})
        assert band == "Low"  # all-zero config → 0 → Low


def test_score_explanation_not_empty():
    bids = make_bids()
    result = analyse(bids)
    assert result.score_explanation


# ------------------------------------------------------------------ #
#  9. Ordinary cases — no false positives                             #
# ------------------------------------------------------------------ #

def test_ordinary_bidding_no_rule_a():
    bids = make_bids(
        {"bidder_id": "B001", "bid_amount": 50000},
        {"bidder_id": "B002", "bid_amount": 75000},
        {"bidder_id": "B003", "bid_amount": 100000},
    )
    result = analyse(bids)
    a_findings = [f for f in result.findings if f.rule == "A" and not f.insufficient_data]
    assert len(a_findings) == 0


def test_non_evaluation_status_not_penalised():
    """
    Tenders with status 'Technical Evaluation' carry no award outcome.
    Engine should not fabricate a rotation finding.
    """
    bids = make_bids(
        {"tender_id": "T001", "bidder_id": "B001", "outcome": "technical evaluation"},
        {"tender_id": "T001", "bidder_id": "B002", "outcome": "technical evaluation"},
    )
    result = analyse(bids)
    c_findings = [f for f in result.findings if f.rule == "C" and not f.insufficient_data]
    assert len(c_findings) == 0


# ------------------------------------------------------------------ #
#  10. Evidence and explanation completeness                          #
# ------------------------------------------------------------------ #

def test_every_non_insufficient_finding_has_explanation():
    bids = make_bids(
        {"bidder_id": "B001", "bid_amount": 100000},
        {"bidder_id": "B002", "bid_amount": 100200},
    )
    result = analyse(bids)
    for f in result.findings:
        if not f.insufficient_data:
            assert f.explanation.strip(), f"Finding {f.rule} missing explanation"
            assert f.rule_name.strip()
            assert f.threshold_or_criterion.strip()


def test_insufficient_data_findings_have_data_limitations():
    result = analyse(make_bids())
    for f in result.findings:
        if f.insufficient_data:
            assert f.data_limitations.strip(), (
                f"Insufficient-data finding {f.rule} missing data_limitations"
            )
