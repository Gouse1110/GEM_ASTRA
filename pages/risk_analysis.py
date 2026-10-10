"""
pages/risk_analysis.py
Risk Analysis dashboard — connects the existing risk engine to the UI.

IMPORTANT
---------
Findings are review-priority signals only.
A high score does NOT establish collusion, guilt, or fraud.
All findings require expert human review and corroborating evidence.
"""

import streamlit as st
import pandas as pd
from utils.data_loader import load_bids
from utils.risk_analysis_helpers import (
    filter_bids_by_source,
    has_real_bids,
    has_synthetic_bids,
    findings_to_table,
    filter_findings_table,
    summarise_result,
    run_analysis_safe,
    BAND_COLOURS,
)

# --------------------------------------------------------------------------- #
#  Constants                                                                   #
# --------------------------------------------------------------------------- #

SOURCE_OPTIONS = {
    "Synthetic demo data":   "synthetic",
    "Verified public data":  "real_public_data",
    "All available data":    "all",
}

BAND_EMOJI = {
    "Low":      "🟢",
    "Moderate": "🟡",
    "Elevated": "🟠",
    "High":     "🔴",
}

RULE_LABELS = {
    "A": "A — Bid-price similarity",
    "B": "B — Bidder co-participation",
    "C": "C — Winner rotation",
    "D": "D — Participation anomalies",
}


# --------------------------------------------------------------------------- #
#  Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _disclaimer_banner():
    st.info(
        "⚠️ **Review-priority indicators only.** "
        "Findings highlight patterns that warrant closer examination — "
        "they are not evidence of collusion, fraud, or wrongdoing. "
        "A score of 0–100 represents analytical review priority, "
        "**not** a probability of collusion. "
        "Human review and corroborating evidence are required before drawing any conclusions."
    )


def _synthetic_warning():
    st.warning(
        "🧪 **SYNTHETIC DEMO DATA — NOT REAL GeM EVIDENCE.** "
        "The findings below are generated from artificial data created for testing purposes. "
        "They do not represent actual GeM procurement activity, real suppliers, "
        "or real tender outcomes."
    )


def _band_badge(band: str) -> str:
    emoji = BAND_EMOJI.get(band, "⚪")
    return f"{emoji} {band}"


def _score_gauge(score: int, band: str):
    colour = BAND_COLOURS.get(band, "#6c757d")
    st.markdown(
        f"""
        <div style="
            background: {colour}18;
            border: 2px solid {colour};
            border-radius: 10px;
            padding: 16px 24px;
            text-align: center;
        ">
            <div style="font-size: 2.4rem; font-weight: 700; color: {colour};">{score}</div>
            <div style="font-size: 0.85rem; color: {colour}; font-weight: 600;">
                {_band_badge(band)} priority
            </div>
            <div style="font-size: 0.72rem; color: #6c757d; margin-top: 4px;">
                Review-priority score (0–100) · not a probability of collusion
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
#  Detail view for one finding                                                 #
# --------------------------------------------------------------------------- #

def _render_finding_detail(finding_row: pd.Series, all_findings: list):
    """Render full evidence for a selected finding row."""
    rule = finding_row["rule"]

    # Locate the original Finding object for richer evidence
    orig = next(
        (f for f in all_findings
         if f.rule == rule
         and (not f.tender_ids or finding_row["tender_ids"] in (
             ", ".join(f.tender_ids), f.tender_ids[0] if f.tender_ids else "—"
         ))),
        None,
    )

    st.divider()
    st.markdown(f"#### Rule {rule} — {finding_row['rule_name']}")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Tender(s):** {finding_row['tender_ids']}")
        st.markdown(f"**Affected bidder(s):** {finding_row['bidder_ids']}")
        st.markdown(f"**Source type:** `{finding_row['source_type']}`")
    with col2:
        st.markdown(f"**Criterion:** {finding_row['threshold_or_criterion']}")

    st.markdown(f"**Explanation:** {finding_row['explanation']}")

    if finding_row.get("data_limitations"):
        st.caption(f"ℹ️ Data limitations: {finding_row['data_limitations']}")

    # Show structured evidence from original Finding object
    if orig and orig.evidence:
        with st.expander("Supporting evidence values", expanded=True):
            evidence = orig.evidence

            if rule == "A" and "pairs" in evidence:
                pairs_df = pd.DataFrame(evidence["pairs"])
                pairs_df.columns = [
                    "Bidder A", "Bidder B", "Bid A (₹)", "Bid B (₹)", "Diff %"
                ]
                st.dataframe(pairs_df, use_container_width=True, hide_index=True)
                st.caption(
                    f"Product category: {evidence.get('product_category', '—')}"
                )

            elif rule == "B":
                st.markdown(
                    f"**Co-participation count:** "
                    f"{evidence.get('co_participation_count', '—')}"
                )
                shared = evidence.get("shared_tender_ids", [])
                if shared:
                    st.markdown(f"**Shared tenders:** {', '.join(shared)}")

            elif rule == "C":
                win_counts = evidence.get("win_counts", {})
                if win_counts:
                    wc_df = pd.DataFrame(
                        list(win_counts.items()), columns=["Bidder", "Wins"]
                    )
                    st.dataframe(wc_df, use_container_width=True, hide_index=True)
                st.markdown(
                    f"**Total awarded tenders:** "
                    f"{evidence.get('total_awarded_tenders', '—')}"
                )
                st.markdown(
                    f"**Coverage by rotating bidders:** "
                    f"{evidence.get('coverage_pct', '—')}%"
                )

            else:
                st.json(evidence)


# --------------------------------------------------------------------------- #
#  Main sections                                                               #
# --------------------------------------------------------------------------- #

def _render_no_data(source_label: str):
    st.markdown(
        f"""
        <div style="
            border: 1px solid #dee2e6;
            border-radius: 10px;
            padding: 40px 32px;
            text-align: center;
            background: #f8f9fb;
            margin-top: 16px;
        ">
            <div style="font-size: 40px;">📂</div>
            <h4 style="color: #2c3e50; margin: 12px 0 8px;">No bid records available</h4>
            <p style="color: #6c757d; max-width: 480px; margin: 0 auto;">
                No <strong>{source_label}</strong> bid-level records were found.
                Load bid data into <code>data/demo_bids.csv</code> using the expected schema,
                then return here to run the analysis.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_analysis(bids: pd.DataFrame, source_filter: str, source_label: str):
    """Run engine and render results."""
    if source_filter != "all" and not bids.empty:
        if source_filter == "real_public_data" and not has_real_bids(bids):
            st.error(
                "🔒 **Real-world bid-pattern analysis is currently unavailable.** "
                "No verified `real_public_data` bid records are loaded. "
                "Load official GeM bid data to enable real-data analysis."
            )
            return
        if source_filter == "synthetic" and not has_synthetic_bids(bids):
            st.info("No synthetic demo bid records found.")
            return

    filtered_bids = filter_bids_by_source(bids, source_filter)

    if filtered_bids is None or filtered_bids.empty:
        _render_no_data(source_label)
        return

    # Show synthetic warning before any results
    if source_filter in ("synthetic", "all") and has_synthetic_bids(filtered_bids):
        if not has_real_bids(filtered_bids):
            _synthetic_warning()

    with st.spinner("Running analysis…"):
        result, error = run_analysis_safe(filtered_bids)

    if error:
        st.error(f"Analysis error: {error}")
        return

    if result is None:
        st.error("Analysis returned no result.")
        return

    summary = summarise_result(result, len(filtered_bids))

    # --- Engine warnings ---
    if result.warnings:
        for w in result.warnings:
            if "real_public_data" in w.lower() or "synthetic" in w.lower():
                st.warning(w)

    # --- Summary metrics ---
    st.markdown("### Summary")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Bid records analysed", summary["total_bids_analysed"])
    col2.metric("Actionable findings", summary["actionable_findings"])
    col3.metric("Rules fired", len(summary["rules_fired"]) or "—")
    col4.metric(
        "Review priority",
        f"{summary['score']}/100",
        delta=summary["score_band"],
        delta_color="off",
    )

    st.markdown("---")

    # --- Score gauge ---
    gcol, ecol = st.columns([1, 2])
    with gcol:
        _score_gauge(result.score, result.score_band)
    with ecol:
        st.markdown(f"**Score breakdown**")
        st.caption(result.score_explanation)

    st.markdown("---")

    # --- Build findings table ---
    all_findings = result.findings
    findings_df = findings_to_table(all_findings)

    # --- Filters ---
    st.markdown("### Findings")
    rule_options = ["All"] + sorted(
        {f.rule for f in all_findings if not f.insufficient_data}
    )
    source_vals = ["All"] + sorted(
        {f.source_type for f in all_findings
         if f.source_type and not f.insufficient_data}
    )

    fc1, fc2, fc3 = st.columns([2, 2, 3])
    with fc1:
        rule_sel = st.selectbox(
            "Filter by rule",
            rule_options,
            format_func=lambda r: RULE_LABELS.get(r, r),
            key="ra_rule_filter",
        )
    with fc2:
        src_sel = st.selectbox(
            "Filter by source type",
            source_vals,
            key="ra_src_filter",
        )
    with fc3:
        tender_search = st.text_input(
            "Search by tender ID",
            placeholder="e.g. T001",
            key="ra_tender_search",
        )

    show_insufficient = st.checkbox(
        "Show unavailable / insufficient-data rules",
        value=False,
        key="ra_show_insuf",
    )

    filtered_df = filter_findings_table(
        findings_df,
        rule_filter=rule_sel if rule_sel != "All" else None,
        tender_search=tender_search,
        source_filter=src_sel if src_sel != "All" else None,
        include_insufficient=show_insufficient,
    )

    if filtered_df.empty:
        st.info(
            "No actionable findings match the current filters. "
            "This may mean no suspicious patterns were detected, or the filters "
            "are too narrow. Check 'Show unavailable rules' to see all engine output."
        )
    else:
        display_cols = [
            "rule", "rule_name", "tender_ids", "bidder_ids",
            "source_type", "explanation",
        ]
        if show_insufficient:
            display_cols += ["data_limitations", "insufficient_data"]

        display_df = filtered_df[
            [c for c in display_cols if c in filtered_df.columns]
        ].copy()

        # Rename for readability
        display_df = display_df.rename(columns={
            "rule":                   "Rule",
            "rule_name":              "Detection Rule",
            "tender_ids":             "Tender(s)",
            "bidder_ids":             "Bidder(s)",
            "source_type":            "Source",
            "explanation":            "Explanation",
            "data_limitations":       "Limitations",
            "insufficient_data":      "Insufficient Data",
        })

        st.dataframe(display_df, use_container_width=True, hide_index=True)
        st.caption(
            f"Showing {len(filtered_df)} finding(s). "
            "Select a finding below to view full evidence."
        )

        # --- Detail view ---
        if not filtered_df.empty:
            st.markdown("### Finding detail")
            select_options = ["— select a finding —"]
            for _, row in filtered_df.iterrows():
                label = (
                    f"Rule {row['rule']} · {row['rule_name']} "
                    f"· {row['tender_ids']}"
                )
                select_options.append(label)

            chosen = st.selectbox(
                "Select finding",
                select_options,
                key="ra_detail_select",
            )

            if chosen != "— select a finding —":
                idx = select_options.index(chosen) - 1
                if 0 <= idx < len(filtered_df):
                    row = filtered_df.iloc[idx]
                    _render_finding_detail(row, all_findings)

    # --- Unavailable rules note ---
    insuf_rules = [
        f for f in all_findings if f.insufficient_data
    ]
    if insuf_rules and not show_insufficient:
        with st.expander(
            f"ℹ️ {len(insuf_rules)} rule(s) returned insufficient data or are unavailable"
        ):
            for f in insuf_rules:
                st.markdown(f"**Rule {f.rule} — {f.rule_name}**")
                st.caption(f.data_limitations)


# --------------------------------------------------------------------------- #
#  Entry point                                                                 #
# --------------------------------------------------------------------------- #

def render():
    st.markdown(
        "Screen bid-level records for analytical risk signals. "
        "Findings indicate review priorities — not proven misconduct."
    )

    _disclaimer_banner()
    st.markdown("---")

    # --- Data source selector ---
    all_bids = load_bids()

    has_real = has_real_bids(all_bids)
    has_syn = has_synthetic_bids(all_bids)

    st.markdown("### Data source")

    available = {}
    if has_syn:
        available["Synthetic demo data"] = "synthetic"
    if has_real:
        available["Verified public data"] = "real_public_data"
    if has_real and has_syn:
        available["All available data"] = "all"

    if not available:
        _render_no_data("any")
        return

    source_label = st.selectbox(
        "Select data source to analyse",
        list(available.keys()),
        help=(
            "Synthetic demo data is clearly separated from verified public records. "
            "Never select 'Verified public data' unless you have imported "
            "official GeM bid records."
        ),
        key="ra_source_select",
    )
    source_filter = available[source_label]

    st.markdown("---")
    _render_analysis(all_bids, source_filter, source_label)
