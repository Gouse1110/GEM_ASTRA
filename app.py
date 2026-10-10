import streamlit as st
from utils.database import init_db

# Initialise database schema on every cold start (idempotent)
init_db()

st.set_page_config(
    page_title="GeM Astra",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom CSS for government-procurement aesthetic ---
st.markdown(
    """
    <style>
    /* Sidebar brand header */
    .gem-brand {
        text-align: center;
        padding: 12px 0 24px 0;
    }
    .gem-brand h1 {
        font-size: 1.6rem;
        font-weight: 700;
        color: #1a3c6e;
        margin: 0;
    }
    .gem-brand p {
        font-size: 0.72rem;
        color: #6c757d;
        margin: 2px 0 0 0;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }

    /* Nav button styling */
    div[data-testid="stSidebarNav"] { display: none; }

    /* Top header bar */
    .top-bar {
        background: linear-gradient(90deg, #1a3c6e 0%, #2563a8 100%);
        padding: 14px 28px;
        border-radius: 8px;
        margin-bottom: 24px;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .top-bar h2 {
        color: white;
        margin: 0;
        font-size: 1.3rem;
        font-weight: 600;
    }
    .top-bar span {
        color: #a8c4e8;
        font-size: 0.8rem;
    }

    /* Metric card overrides */
    div[data-testid="metric-container"] {
        background: #f0f4fb;
        border: 1px solid #d0dff0;
        border-radius: 8px;
        padding: 12px 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Sidebar navigation ---
with st.sidebar:
    st.markdown(
        """
        <div class="gem-brand">
            <h1>🔍 GeM Astra</h1>
            <p>Procurement Intelligence Platform</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()

    pages = [
        "Overview",
        "Tender Explorer",
        "Risk Analysis",
        "Bidder Network",
        "Investigation Reports",
        "About",
    ]
    page = st.radio("Navigation", pages, label_visibility="collapsed")

    st.divider()
    st.caption("GeM Astra v0.1 · Prototype")

# --- Page header bar ---
page_icons = {
    "Overview": "🏠",
    "Tender Explorer": "📋",
    "Risk Analysis": "⚠️",
    "Bidder Network": "🕸️",
    "Investigation Reports": "📄",
    "About": "ℹ️",
}
st.markdown(
    f"""
    <div class="top-bar">
        <span style="font-size:1.6rem">{page_icons[page]}</span>
        <div>
            <h2>{page}</h2>
            <span>GeM Astra · AI-Driven Public Procurement Analytics</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- Route to pages ---
if page == "Overview":
    from pages.overview import render
    render()

elif page == "Tender Explorer":
    from pages.tender_explorer import render
    render()

elif page == "Risk Analysis":
    from pages.risk_analysis import render
    render()

elif page == "Bidder Network":
    from pages.coming_soon import render
    render(
        "Bidder Network",
        "The graph-based relationship explorer is under development. "
        "It will map connections between bidders across tenders to help "
        "investigators spot coordinated behaviour.",
    )

elif page == "Investigation Reports":
    from pages.coming_soon import render
    render(
        "Investigation Reports",
        "The report builder is under development. "
        "Investigators will be able to document findings, attach evidence, "
        "and export structured reports for compliance teams.",
    )

elif page == "About":
    from pages.about import render
    render()
