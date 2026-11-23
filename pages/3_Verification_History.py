"""Verification History page - browse, filter, reopen, export, and manage past reports."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from fact_checker.database import DatabaseError  # noqa: E402
from fact_checker.ui_helpers import (  # noqa: E402
    get_database,
    init_app_environment,
    inject_custom_css,
    label_badge_html,
    render_report_preview,
)

init_app_environment()

st.set_page_config(
    page_title="Verification History | Fact Verification System",
    page_icon="🗂️",
    layout="wide",
)
inject_custom_css()

st.title("Verification History")
st.markdown(
    "Browse previous verification sessions stored in SQLite, reopen full reports, and export "
    "JSON, CSV, or Markdown documentation."
)

f1, f2 = st.columns([1, 2])
with f1:
    label_filter = st.selectbox(
        "Filter by verdict",
        ["ALL", "SUPPORTED", "CONTRADICTED", "UNVERIFIED"],
    )
with f2:
    search_query = st.text_input(
        "Search claims",
        placeholder="Filter by keyword in claim text...",
    )

try:
    db = get_database()
    records = db.list_reports(
        limit=100,
        label_filter=label_filter,
        search_query=search_query,
    )
except DatabaseError as exc:
    st.error(f"Database error while loading history: {exc}")
    records = []

if not records:
    st.info("No matching verification records found.")
else:
    st.caption(f"Showing {len(records)} verification record(s).")

    if "selected_history_report_id" not in st.session_state:
        st.session_state["selected_history_report_id"] = records[0].report_id

    for rec in records:
        with st.container(border=True):
            c_badge, c_claim, c_meta, c_open, c_del = st.columns([1.4, 3.5, 2.0, 0.9, 0.8])
            with c_badge:
                st.markdown(
                    label_badge_html(
                        rec.label,
                        is_preliminary=("Preliminary" in rec.search_mode),
                    ),
                    unsafe_allow_html=True,
                )
                if rec.disagreement_flagged:
                    st.caption("Conflict flagged")
            with c_claim:
                st.markdown(f"**{rec.claim}**")
                st.caption(f"Report ID: `{rec.report_id}` · Mode: {rec.search_mode}")
            with c_meta:
                st.caption(
                    f"Confidence: `{rec.confidence_score:.2f}`\n\n"
                    f"Sources: `{rec.source_count}` · {rec.retrieval_timestamp}"
                )
            with c_open:
                if st.button("Open", key=f"open_{rec.report_id}", width="stretch"):
                    st.session_state["selected_history_report_id"] = rec.report_id
            with c_del:
                if st.button("Delete", key=f"del_{rec.report_id}", width="stretch"):
                    try:
                        deleted = db.delete_report(rec.report_id)
                        if deleted:
                            if st.session_state.get("selected_history_report_id") == rec.report_id:
                                st.session_state.pop("selected_history_report_id", None)
                            st.rerun()
                    except DatabaseError as exc:
                        st.error(f"Failed to delete record: {exc}")

    selected_id = st.session_state.get("selected_history_report_id")
    if selected_id:
        try:
            loaded = db.get_report(selected_id)
            if loaded is not None:
                st.divider()
                st.subheader("Selected Report Details")
                render_report_preview(loaded, key_prefix="hist")
        except DatabaseError as exc:
            st.error(f"Could not open selected report: {exc}")
