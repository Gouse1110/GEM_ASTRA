import streamlit as st
from utils.database import count_tenders
from utils.data_loader import load_bids


def render():
    st.markdown("## Welcome to GeM Astra")
    st.markdown(
        """
        **GeM Astra** is an AI-driven analytics tool designed to help authorised procurement reviewers
        identify potentially suspicious bidding patterns in Government e-Marketplace (GeM) tenders.

        > ⚠️ **Disclaimer:** Risk indicators surfaced by this tool are analytical signals only —
        > not evidence of wrongdoing. All findings require expert human review before any action is taken.
        """
    )

    st.divider()

    total_tenders = count_tenders()
    bids = load_bids()

    if total_tenders == 0 and bids.empty:
        st.info(
            "📂 No data loaded yet.\n\n"
            "Upload verified tender records via **Tender Explorer** to begin analysis. "
            "The dashboard will populate once real data is available."
        )
        st.markdown("### How it works")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(
                """
                **1. Import Tenders**
                Load verified GeM tender metadata into the Tender Explorer.
                """
            )
        with col2:
            st.markdown(
                """
                **2. Run Risk Analysis**
                The detection engine screens bids for collusion indicators such as
                cover bidding, bid rotation, and price convergence.
                """
            )
        with col3:
            st.markdown(
                """
                **3. Review & Report**
                Investigators examine flagged tenders, review the evidence,
                and generate structured reports for compliance teams.
                """
            )
        return

    # --- Summary cards (only shown when data is present) ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Tenders", total_tenders)
    col2.metric("Total Bids", len(bids))
    col3.metric("Unique Bidders", bids["bidder_id"].nunique() if not bids.empty else 0)
