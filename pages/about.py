import streamlit as st


def render():
    st.markdown("## About GeM Astra")

    st.markdown(
        """
        ### Purpose
        GeM Astra is a procurement analytics tool that helps authorised reviewers detect
        potentially suspicious bidding patterns in Government e-Marketplace (GeM) tenders.
        It applies statistical and graph-based signals — such as cover bidding, bid rotation,
        and price convergence — to surface tenders that may warrant closer human scrutiny.

        ### What it is not
        - GeM Astra is **not** a judicial or legal determination system.
        - A risk flag is **not** evidence of collusion or fraud.
        - The tool does **not** automatically blacklist suppliers or issue compliance decisions.
        - All findings must be reviewed, validated, and acted upon exclusively by qualified
          procurement officers, compliance investigators, or legal authorities.

        ### Data integrity
        - Only verified, official GeM tender records should be loaded.
        - Synthetic or demonstration data is clearly labelled and must not be
          treated as real procurement information.
        - Raw data files are never modified by the application.

        ### Human review requirement
        Every risk indicator produced by this tool is an analytical signal that requires
        expert human judgement before any conclusion is drawn or action is taken.
        No automated output from GeM Astra should be used as the sole basis for
        regulatory, legal, or administrative decisions.

        ### Built for
        This tool is intended for use by authorised procurement auditors, anti-corruption
        investigators, and government oversight bodies operating within the applicable
        legal and regulatory framework.
        """
    )

    st.divider()
    st.caption("GeM Astra — Hackathon prototype. Not for production use without further validation.")
