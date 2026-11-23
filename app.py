"""AI-Powered Fact Verification System - Home Dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Ensure `src/` is importable when running `streamlit run app.py` directly
_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from fact_checker.ui_helpers import (  # noqa: E402
    get_database,
    init_app_environment,
    inject_custom_css,
    label_badge_html,
    provider_status_label,
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
    "Verify factual claims against retrieved or user-supplied sources, detect conflicting "
    "evidence across publishers, and generate transparent, exportable verification reports."
)

api_configured, provider_label = provider_status_label()
stats, db_error = safe_db_stats()

st.divider()

# System status & metrics row
col_mode, col_total, col_sup, col_con, col_unv = st.columns([2, 1, 1, 1, 1])
with col_mode:
    st.markdown("**Source Discovery Mode**")
    if api_configured:
        st.success(provider_label)
    else:
        st.info(provider_label)
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

st.subheader("How Verification Works")
step1, step2, step3, step4 = st.columns(4)
with step1:
    st.markdown("#### 1. Parse Claims")
    st.write(
        "Validates non-empty claims, splits multi-claim inputs, and extracts keywords and numbers."
    )
with step2:
    st.markdown("#### 2. Gather Sources")
    st.write(
        "Queries a configured Search API or uses Manual Evidence Mode with safe HTML extraction."
    )
with step3:
    st.markdown("#### 3. Analyze Evidence")
    st.write(
        "Scores topical relevance with TF-IDF + keyword overlap, then evaluates support vs. conflict."
    )
with step4:
    st.markdown("#### 4. Report & Compare")
    st.write(
        "Flags disagreements, discloses access errors, stores history in SQLite, and exports JSON/CSV/MD."
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
        "**SUPPORTED**: Reliable retrieved evidence aligns with the claim and no contradicting "
        "evidence was found."
    )
with d2:
    st.error(
        "**CONTRADICTED**: Reliable retrieved evidence directly conflicts with the claim "
        "(e.g., negation, antonym, or numeric/date mismatch)."
    )
with d3:
    st.warning(
        "**UNVERIFIED**: Evidence is insufficient, inaccessible, inconclusive, or sources "
        "directly disagree."
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
                c1, c2, c3 = st.columns([1, 4, 2])
                with c1:
                    st.markdown(label_badge_html(item.label), unsafe_allow_html=True)
                with c2:
                    st.write(item.claim)
                with c3:
                    st.caption(
                        f"Conf: {item.confidence_score:.2f} · Sources: {item.source_count} · "
                        f"{item.retrieval_timestamp}"
                    )
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not load recent verification records: {exc}")
