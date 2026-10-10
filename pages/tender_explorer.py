"""
pages/tender_explorer.py
Tender Explorer — browse, search, filter, and import GeM tender records.
"""

import streamlit as st
import pandas as pd
from utils.database import (
    fetch_tenders_filtered,
    fetch_distinct,
    count_tenders,
    fetch_tender_by_id,
    import_tenders_from_df,
)

REQUIRED_COLUMNS = {"tender_id"}
EXPECTED_COLUMNS = [
    "tender_id", "item_name", "department", "start_date", "end_date",
    "status", "quantity", "official_url", "source_type", "source_document",
]

DISPLAY_COLUMNS = [
    "tender_id", "item_name", "department", "status",
    "start_date", "end_date", "source_type",
]

SOURCE_TYPE_LABELS = {
    "real_public_data": "✅ Verified public data",
    "synthetic":        "🧪 Synthetic / demo",
    "unknown":          "❓ Unknown",
}


# --------------------------------------------------------------------------- #
#  Validation                                                                  #
# --------------------------------------------------------------------------- #

def _validate_csv(df: pd.DataFrame) -> tuple[bool, str]:
    """Check required columns are present. Returns (ok, message)."""
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        return False, f"Missing required column(s): {', '.join(sorted(missing))}"
    if df.empty:
        return False, "The uploaded file contains no data rows."
    return True, ""


# --------------------------------------------------------------------------- #
#  Sub-sections                                                                #
# --------------------------------------------------------------------------- #

def _render_import():
    st.markdown("### Import Tenders")
    st.markdown(
        "Upload a CSV file containing GeM tender metadata. "
        "Only `tender_id` is required — all other fields are optional."
    )

    with st.expander("Expected CSV schema", expanded=False):
        st.code(", ".join(EXPECTED_COLUMNS), language="text")
        st.caption(
            "Source type values: `real_public_data` · `synthetic` · `unknown`. "
            "Anything else is stored as `unknown`."
        )

    uploaded = st.file_uploader(
        "Choose a CSV file", type=["csv"], key="tender_csv_upload"
    )

    source_override = st.selectbox(
        "Confirm source type for this file",
        options=["Use value from CSV column", "real_public_data", "synthetic", "unknown"],
        help=(
            "Override the source_type column in the CSV. "
            "Select 'real_public_data' only for verified, official GeM exports. "
            "Never classify synthetic data as real."
        ),
        key="source_type_override",
    )

    if uploaded is None:
        return

    try:
        df = pd.read_csv(uploaded)
    except Exception as e:
        st.error(f"Could not parse CSV: {e}")
        return

    ok, msg = _validate_csv(df)
    if not ok:
        st.error(f"Validation failed — {msg}")
        return

    # Add any missing expected columns as NaN so downstream code is consistent
    for col in EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    st.success(f"File parsed — {len(df):,} row(s) found. Review before importing.")

    # Preview (first 5 rows)
    st.dataframe(df[EXPECTED_COLUMNS].head(5), use_container_width=True)

    override_val = None if source_override == "Use value from CSV column" else source_override

    if st.button("Import into database", type="primary", key="do_import"):
        with st.spinner("Importing…"):
            result = import_tenders_from_df(df, source_type_override=override_val)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Inserted", result["inserted"])
        col2.metric("Duplicates skipped", result["skipped_duplicate"])
        col3.metric("Rejected (no ID)", result["rejected"])
        col4.metric("Errors", len(result["errors"]))

        if result["inserted"] > 0:
            st.success(f"{result['inserted']} tender(s) imported successfully.")
        if result["skipped_duplicate"] > 0:
            st.info(
                f"{result['skipped_duplicate']} row(s) skipped — "
                "tender_id already exists in the database. Existing records are not overwritten."
            )
        if result["errors"]:
            with st.expander("Import errors / warnings"):
                for err in result["errors"]:
                    st.warning(err)

        st.rerun()


def _render_browser():
    total = count_tenders()

    if total == 0:
        st.info(
            "📂 No tender records in the database yet.\n\n"
            "Use the **Import Tenders** section above to load a CSV file."
        )
        return

    st.markdown("### Browse Tenders")

    # --- Search + filters ---
    col1, col2, col3 = st.columns([3, 2, 2])
    with col1:
        search = st.text_input(
            "Search by tender ID or item name", placeholder="e.g. GEM-123 or laptop"
        )
    with col2:
        depts = ["All"] + fetch_distinct("department")
        dept = st.selectbox("Department", depts)
    with col3:
        statuses = ["All"] + fetch_distinct("status")
        status = st.selectbox("Status", statuses)

    dept_filter = None if dept == "All" else dept
    status_filter = None if status == "All" else status

    df = fetch_tenders_filtered(
        search=search.strip(),
        department=dept_filter,
        status=status_filter,
    )

    st.markdown(f"Showing **{len(df):,}** of **{total:,}** tenders")

    if df.empty:
        st.warning("No tenders match the current filters.")
        return

    # Show condensed table
    display_df = df[[c for c in DISPLAY_COLUMNS if c in df.columns]].copy()
    display_df["source_type"] = display_df["source_type"].map(
        lambda x: SOURCE_TYPE_LABELS.get(x, x)
    )

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # --- Detail view ---
    st.markdown("### Tender Detail")
    tender_ids = df["tender_id"].tolist()
    selected_id = st.selectbox("Select a tender to view full record", ["—"] + tender_ids)

    if selected_id and selected_id != "—":
        record = fetch_tender_by_id(selected_id)
        if record:
            _render_detail(record)


def _render_detail(record: dict):
    st.divider()
    st.markdown(f"#### {record.get('item_name') or 'Tender'} · `{record['tender_id']}`")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Department:** {record.get('department') or '—'}")
        st.markdown(f"**Status:** {record.get('status') or '—'}")
        st.markdown(f"**Quantity:** {record.get('quantity') or '—'}")
        src = record.get("source_type", "unknown")
        st.markdown(f"**Source type:** {SOURCE_TYPE_LABELS.get(src, src)}")
    with col2:
        st.markdown(f"**Start date:** {record.get('start_date') or '—'}")
        st.markdown(f"**End date:** {record.get('end_date') or '—'}")
        st.markdown(f"**Source document:** {record.get('source_document') or '—'}")
        st.markdown(f"**Imported at:** {record.get('created_at') or '—'}")

    url = record.get("official_url")
    if url and str(url).startswith("http"):
        st.link_button("Open official source ↗", url)
    else:
        st.caption("No official URL available for this record.")


# --------------------------------------------------------------------------- #
#  Entry point                                                                 #
# --------------------------------------------------------------------------- #

def render():
    st.markdown("Browse, search, and import verified GeM tender records.")

    tab1, tab2 = st.tabs(["📋 Browse", "⬆️ Import"])

    with tab1:
        _render_browser()

    with tab2:
        _render_import()
