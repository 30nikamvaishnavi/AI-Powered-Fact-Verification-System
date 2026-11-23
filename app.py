"""AI-Powered Fact Verification System - Home Dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from fact_checker.ui_helpers import (  # noqa: E402
    gemini_status_label,
    get_database,
    init_app_environment,
    inject_custom_css,
    label_badge_html,
    safe_db_stats,
)

init_app_environment()

st.set_page_config(
    page_title="AI-Powered Fact Verification System",
    page_icon="🔍",
    layout="wide",
)
inject_custom_css()

st.title("AI-Powered Fact Verification System")
st.markdown(
    "Analyze factual claims using **Google Gemini** (`google-genai`), compare multiple "
    "user-supplied sources side by side, flag conflicting evidence, and export structured reports."
)

gemini_ok, gemini_label = gemini_status_label()
stats, db_error = safe_db_stats()

st.divider()

col_mode, col_total, col_sup, col_con, col_unv = st.columns([2.2, 1, 1, 1, 1])
with col_mode:
    st.markdown("**AI Provider Status**")
    if gemini_ok:
        st.success(gemini_label)
    else:
        st.warning(gemini_label)
with col_total:
    st.metric("Total Verified", stats["total"] if stats else 0)
with col_sup:
    st.metric("SUPPORTED", stats["SUPPORTED"] if stats else 0)
with col_con:
    st.metric("CONTRADICTED", stats["CONTRADICTED"] if stats else 0)
with col_unv:
    st.metric("UNVERIFIED", stats["UNVERIFIED"] if stats else 0)

if db_error:
    st.error(f"Database notice: {db_error}")

st.divider()

st.subheader("Two Verification Modes")
m1, m2 = st.columns(2)
with m1:
    st.info(
        "**Mode A — Manual Source Verification**\n\n"
        "Provide source URLs and excerpts (or safely fetch accessible public webpages). "
        "Gemini compares the submitted evidence strictly against your claim without inventing "
        "sources or citations."
    )
with m2:
    st.warning(
        "**Mode B — Gemini Knowledge-Based Preliminary Analysis**\n\n"
        "Uses Gemini's existing model knowledge for an initial screening when you have not "
        "gathered sources yet. Clearly labeled as AI-generated preliminary analysis—not live "
        "fact verification."
    )

st.divider()

st.subheader("Navigate")
nav1, nav2, nav3, nav4 = st.columns(4)
with nav1:
    st.page_link("pages/1_Verify_Claims.py", label="Verify Claims", icon="✅", width="stretch")
with nav2:
    st.page_link("pages/2_Source_Comparison.py", label="Source Comparison", icon="⚖️", width="stretch")
with nav3:
    st.page_link("pages/3_Verification_History.py", label="Verification History", icon="🗂️", width="stretch")
with nav4:
    st.page_link("pages/4_About.py", label="About & Methodology", icon="📘", width="stretch")

st.divider()
st.subheader("Verdict Definitions")
d1, d2, d3 = st.columns(3)
with d1:
    st.success(
        "**SUPPORTED**: Provided evidence supports the claim with no contradicting evidence."
    )
with d2:
    st.error(
        "**CONTRADICTED**: Provided evidence directly conflicts with the claim."
    )
with d3:
    st.warning(
        "**UNVERIFIED**: Evidence is insufficient, inconclusive, inaccessible, or sources disagree."
    )

st.divider()
st.subheader("Recent Verification Activity")
if not db_error:
    try:
        recent = get_database().list_reports(limit=5)
        if not recent:
            st.caption("No verification sessions stored yet. Open **Verify Claims** to get started.")
        else:
            for item in recent:
                c1, c2, c3 = st.columns([1.4, 3.6, 2])
                with c1:
                    st.markdown(
                        label_badge_html(
                            item.label,
                            is_preliminary=("Preliminary" in item.search_mode),
                        ),
                        unsafe_allow_html=True,
                    )
                with c2:
                    st.write(item.claim)
                with c3:
                    st.caption(
                        f"Conf: {item.confidence_score:.2f} · Sources: {item.source_count} · "
                        f"{item.retrieval_timestamp}"
                    )
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not load recent verification records: {exc}")
