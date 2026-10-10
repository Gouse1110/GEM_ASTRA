import streamlit as st


def render(title: str, description: str):
    st.markdown(f"## {title}")
    st.markdown(
        f"""
        <div style="
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            padding: 48px 32px;
            text-align: center;
            background: #f8f9fb;
            margin-top: 24px;
        ">
            <div style="font-size: 48px; margin-bottom: 12px;">🔬</div>
            <h3 style="color: #2c3e50; margin-bottom: 8px;">Coming Soon</h3>
            <p style="color: #6c757d; max-width: 520px; margin: 0 auto;">{description}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
