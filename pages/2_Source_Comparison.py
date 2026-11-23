"""Source Comparison page - inspect multi-source agreements, conflicts, and access gaps."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from fact_checker.database import DatabaseError  # noqa: E402
from fact_checker.models import VerificationReport  # noqa: E402
from fact_checker.ui_helpers import (  # noqa: E402
    get_database,
    init_app_environment,
    inject_custom_css,
    label_badge_html,
    render_comparison_table,
)

init_app_environment()

st.set_page_config(
    page_title="Source Comparison | Fact Verification System",
    page_icon="⚖️",
    layout="wide",
)
inject_custom_css()

st.title("Multiple-Source Comparison")
st.markdown(
    "Compare retrieved sources side-by-side to inspect where publishers agree, where they "
    "conflict, and which URLs could not be accessed."
)

selected_report: VerificationReport | None = None
session_reports: list[VerificationReport] = st.session_state.get("latest_reports", [])

source_origin = st.radio(
    "Choose report source",
    ["Active Session Results", "Saved Verification History (SQLite)"],
    horizontal=True,
)

if source_origin == "Active Session Results":
    if not session_reports:
        st.info(
            "No active session reports found. Run a check in **Verify Claims** or switch to "
            "**Saved Verification History**."
        )
    else:
        labels = [
            f"[{r.label.value}] {r.claim[:90]}" for r in session_reports
        ]
        chosen_idx = st.selectbox(
            "Select a claim from the current session",
            range(len(session_reports)),
            format_func=lambda i: labels[i],
        )
        selected_report = session_reports[chosen_idx]
else:
    try:
        summaries = get_database().list_reports(limit=50)
        if not summaries:
            st.info("No saved verification reports found in SQLite history.")
        else:
            chosen_id = st.selectbox(
                "Select a saved report",
                [s.report_id for s in summaries],
                format_func=lambda rid: next(
                    f"[{s.label.value}] {s.claim[:85]} ({s.retrieval_timestamp})"
                    for s in summaries
                    if s.report_id == rid
                ),
            )
            selected_report = get_database().get_report(chosen_id)
    except DatabaseError as exc:
        st.error(f"Could not read verification history: {exc}")

if selected_report is not None:
    st.divider()
    st.markdown(label_badge_html(selected_report.label), unsafe_allow_html=True)
    st.subheader(selected_report.claim)

    comp = selected_report.source_comparison
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Supports", comp.supports_count)
    m2.metric("Contradicts", comp.contradicts_count)
    m3.metric("Unclear", comp.unclear_count)
    m4.metric("Inaccessible", comp.inaccessible_count)

    if comp.has_disagreement:
        st.warning(
            "Disagreement Flagged: Sources conflict on this claim. Inspect the excerpts and "
            "primary source links below."
        )

    render_comparison_table(comp)

    inaccessible = [s for s in selected_report.sources if not s.usable_text]
    if inaccessible:
        st.subheader("Inaccessible or Restricted Sources Disclosure")
        for src in inaccessible:
            st.markdown(
                f"- **{src.title}** (`{src.url}`): `{src.retrieval_status.value}` — "
                f"{src.retrieval_error or 'No readable text available.'}"
            )
