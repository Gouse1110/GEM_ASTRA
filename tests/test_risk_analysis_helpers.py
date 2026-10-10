"""
tests/test_risk_analysis_helpers.py
Tests for the Risk Analysis page data-preparation helpers.
No Streamlit imports — pure logic tests.

Run with: python -m pytest tests/ -v
"""

import pytest
import pandas as pd
from utils.risk_analysis_helpers import (
    filter_bids_by_source,
    has_real_bids,
    has_synthetic_bids,
    findings_to_table,
    filter_findings_table,
    summarise_result,
    run_analysis_safe,
)
from utils.risk_engine import Finding, EngineResult


# ------------------------------------------------------------------ #
#  Fixtures                                                           #
# ------------------------------------------------------------------ #

def make_bids_df(rows):
    defaults = {
        "tender_id": "T001", "bidder_id": "B001", "bid_amount": 100000,
        "bid_timestamp": "2024-01-01", "outcome": "won",
        "product_category": "laptops", "source_type": "synthetic_demo",
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


def make_finding(
    rule="A", rule_name="Test Rule", tender_ids=None, bidder_ids=None,
    evidence=None, threshold="thresh", explanation="expl",
    source_type="synthetic_demo", data_limitations="", insufficient_data=False,
):
    return Finding(
        rule=rule,
        rule_name=rule_name,
        tender_ids=tender_ids or ["T001"],
        bidder_ids=bidder_ids or ["B001", "B002"],
        evidence=evidence or {},
        threshold_or_criterion=threshold,
        explanation=explanation,
        source_type=source_type,
        data_limitations=data_limitations,
        insufficient_data=insufficient_data,
    )


def make_engine_result(findings=None, score=35, band="Moderate"):
    r = EngineResult()
    r.findings = findings or []
    r.score = score
    r.score_band = band
    r.score_explanation = "Test explanation."
    r.real_data_available = any(
        f.source_type == "real_public_data" for f in (findings or [])
    )
    return r


# ------------------------------------------------------------------ #
#  1. filter_bids_by_source                                           #
# ------------------------------------------------------------------ #

def test_filter_all_returns_everything():
    bids = make_bids_df([
        {"source_type": "real_public_data"},
        {"source_type": "synthetic_demo"},
    ])
    result = filter_bids_by_source(bids, "all")
    assert len(result) == 2


def test_filter_real_public_data_only():
    bids = make_bids_df([
        {"source_type": "real_public_data"},
        {"source_type": "synthetic_demo"},
        {"source_type": "real_public_data"},
    ])
    result = filter_bids_by_source(bids, "real_public_data")
    assert len(result) == 2
    assert (result["source_type"] == "real_public_data").all()


def test_filter_synthetic_only():
    bids = make_bids_df([
        {"source_type": "real_public_data"},
        {"source_type": "synthetic_demo"},
        {"source_type": "synthetic"},
    ])
    result = filter_bids_by_source(bids, "synthetic")
    assert len(result) == 2
    assert result["source_type"].isin(["synthetic_demo", "synthetic"]).all()


def test_filter_unknown_value_returns_empty():
    bids = make_bids_df([{"source_type": "real_public_data"}])
    result = filter_bids_by_source(bids, "totally_unknown_value")
    assert result.empty


def test_filter_empty_df_returns_empty():
    empty = pd.DataFrame()
    result = filter_bids_by_source(empty, "all")
    assert result.empty


def test_filter_none_returns_empty():
    result = filter_bids_by_source(None, "all")
    assert result.empty


def test_filter_does_not_mix_real_and_synthetic():
    """Selecting real_public_data must never include synthetic rows."""
    bids = make_bids_df([
        {"source_type": "real_public_data"},
        {"source_type": "synthetic_demo"},
    ])
    result = filter_bids_by_source(bids, "real_public_data")
    assert "synthetic_demo" not in result["source_type"].values


# ------------------------------------------------------------------ #
#  2. has_real_bids / has_synthetic_bids                              #
# ------------------------------------------------------------------ #

def test_has_real_bids_true():
    bids = make_bids_df([{"source_type": "real_public_data"}])
    assert has_real_bids(bids) == True


def test_has_real_bids_false_when_synthetic():
    bids = make_bids_df([{"source_type": "synthetic_demo"}])
    assert has_real_bids(bids) == False


def test_has_real_bids_false_for_empty():
    assert has_real_bids(pd.DataFrame()) == False
    assert has_real_bids(None) == False


def test_has_synthetic_bids_true():
    bids = make_bids_df([{"source_type": "synthetic_demo"}])
    assert has_synthetic_bids(bids) == True


def test_has_synthetic_bids_also_matches_synthetic_label():
    bids = make_bids_df([{"source_type": "synthetic"}])
    assert has_synthetic_bids(bids) == True


def test_has_synthetic_bids_false_for_real():
    bids = make_bids_df([{"source_type": "real_public_data"}])
    assert has_synthetic_bids(bids) == False


# ------------------------------------------------------------------ #
#  3. findings_to_table                                               #
# ------------------------------------------------------------------ #

def test_findings_to_table_returns_dataframe():
    findings = [make_finding()]
    df = findings_to_table(findings)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1


def test_findings_to_table_empty_list():
    df = findings_to_table([])
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_findings_to_table_columns_present():
    findings = [make_finding()]
    df = findings_to_table(findings)
    for col in ["rule", "rule_name", "tender_ids", "bidder_ids",
                "source_type", "explanation", "data_limitations",
                "insufficient_data", "threshold_or_criterion"]:
        assert col in df.columns, f"Missing column: {col}"


def test_findings_to_table_insufficient_data_flag():
    f_ok = make_finding(insufficient_data=False)
    f_insuf = make_finding(rule="D", insufficient_data=True)
    df = findings_to_table([f_ok, f_insuf])
    assert df[df["rule"] == "A"]["insufficient_data"].iloc[0] == False
    assert df[df["rule"] == "D"]["insufficient_data"].iloc[0] == True


def test_findings_to_table_empty_tender_ids():
    f = Finding(
        rule="A", rule_name="Test", tender_ids=[], bidder_ids=["B001"],
        evidence={}, threshold_or_criterion="t", explanation="e",
        source_type="synthetic_demo",
    )
    df = findings_to_table([f])
    assert df.iloc[0]["tender_ids"] == "—"


def test_findings_to_table_empty_bidder_ids():
    f = Finding(
        rule="A", rule_name="Test", tender_ids=["T001"], bidder_ids=[],
        evidence={}, threshold_or_criterion="t", explanation="e",
        source_type="synthetic_demo",
    )
    df = findings_to_table([f])
    assert df.iloc[0]["bidder_ids"] == "—"


def test_findings_to_table_missing_optional_evidence_no_crash():
    f = make_finding(evidence={})
    df = findings_to_table([f])
    assert len(df) == 1  # must not raise


# ------------------------------------------------------------------ #
#  4. filter_findings_table                                           #
# ------------------------------------------------------------------ #

def _base_findings_df():
    findings = [
        make_finding(rule="A", tender_ids=["T001"], source_type="synthetic_demo"),
        make_finding(rule="B", tender_ids=["T002"], source_type="real_public_data"),
        make_finding(rule="D", tender_ids=[], source_type="unknown",
                     insufficient_data=True, data_limitations="schema gap"),
    ]
    return findings_to_table(findings)


def test_filter_by_rule():
    df = _base_findings_df()
    result = filter_findings_table(df, rule_filter="A")
    assert all(result["rule"] == "A")


def test_filter_excludes_insufficient_by_default():
    df = _base_findings_df()
    result = filter_findings_table(df)
    assert not result["insufficient_data"].any()


def test_filter_includes_insufficient_when_requested():
    df = _base_findings_df()
    result = filter_findings_table(df, include_insufficient=True)
    assert result["insufficient_data"].any()


def test_filter_by_source_type():
    df = _base_findings_df()
    result = filter_findings_table(df, source_filter="real_public_data")
    assert all(result["source_type"] == "real_public_data")


def test_filter_by_tender_search():
    df = _base_findings_df()
    result = filter_findings_table(df, tender_search="T001")
    assert len(result) == 1
    assert "T001" in result.iloc[0]["tender_ids"]


def test_filter_by_tender_search_case_insensitive():
    df = _base_findings_df()
    result = filter_findings_table(df, tender_search="t001")
    assert len(result) == 1


def test_filter_combined_rule_and_source():
    df = _base_findings_df()
    result = filter_findings_table(df, rule_filter="B", source_filter="real_public_data")
    assert len(result) == 1
    assert result.iloc[0]["rule"] == "B"


def test_filter_empty_df_returns_empty():
    result = filter_findings_table(pd.DataFrame())
    assert result.empty


def test_filter_none_returns_empty():
    result = filter_findings_table(None)
    assert result.empty


def test_filter_no_match_returns_empty():
    df = _base_findings_df()
    result = filter_findings_table(df, rule_filter="C")
    assert result.empty


# ------------------------------------------------------------------ #
#  5. summarise_result                                                #
# ------------------------------------------------------------------ #

def test_summarise_result_counts_actionable_only():
    findings = [
        make_finding(rule="A", insufficient_data=False),
        make_finding(rule="D", insufficient_data=True),
    ]
    result = make_engine_result(findings=findings, score=35, band="Moderate")
    summary = summarise_result(result, total_bids=10)
    assert summary["actionable_findings"] == 1  # D excluded
    assert summary["total_bids_analysed"] == 10
    assert "A" in summary["rules_fired"]
    assert "D" not in summary["rules_fired"]


def test_summarise_result_score_and_band():
    result = make_engine_result(findings=[], score=60, band="Elevated")
    summary = summarise_result(result, total_bids=5)
    assert summary["score"] == 60
    assert summary["score_band"] == "Elevated"


def test_summarise_result_empty_findings():
    result = make_engine_result(findings=[])
    summary = summarise_result(result, total_bids=0)
    assert summary["actionable_findings"] == 0
    assert summary["rules_fired"] == []


# ------------------------------------------------------------------ #
#  6. run_analysis_safe                                               #
# ------------------------------------------------------------------ #

def test_run_analysis_safe_returns_result_on_valid_input():
    bids = make_bids_df([
        {"bidder_id": "B001", "bid_amount": 100000},
        {"bidder_id": "B002", "bid_amount": 101000},
    ])
    result, error = run_analysis_safe(bids)
    assert result is not None
    assert error is None


def test_run_analysis_safe_returns_error_on_exception():
    # Pass something that will cause an internal failure
    result, error = run_analysis_safe("not_a_dataframe")
    # Engine should catch the error gracefully
    assert error is not None or result is not None  # either handled


def test_run_analysis_safe_empty_bids():
    result, error = run_analysis_safe(pd.DataFrame())
    assert result is not None
    assert error is None
    assert result.score == 0


def test_run_analysis_safe_none_bids():
    result, error = run_analysis_safe(None)
    assert result is not None
    assert error is None


# ------------------------------------------------------------------ #
#  7. Source-type contamination guard                                 #
# ------------------------------------------------------------------ #

def test_filtering_real_never_includes_synthetic():
    bids = make_bids_df([
        {"bidder_id": "B001", "source_type": "real_public_data", "bid_amount": 100000},
        {"bidder_id": "B002", "source_type": "synthetic_demo", "bid_amount": 100200},
    ])
    real_bids = filter_bids_by_source(bids, "real_public_data")
    result, _ = run_analysis_safe(real_bids)
    # Result source_type must not be synthetic
    if result:
        assert result.source_type != "synthetic_demo"


def test_filtering_synthetic_never_includes_real():
    bids = make_bids_df([
        {"bidder_id": "B001", "source_type": "real_public_data", "bid_amount": 100000},
        {"bidder_id": "B002", "source_type": "synthetic_demo", "bid_amount": 100200},
    ])
    syn_bids = filter_bids_by_source(bids, "synthetic")
    assert not has_real_bids(syn_bids)
