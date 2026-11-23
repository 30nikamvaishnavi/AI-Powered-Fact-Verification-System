"""Verify Claims page - submit claims, configure evidence sources, and inspect reports."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from fact_checker.claim_parser import ClaimValidationError  # noqa: E402
from fact_checker.database import DatabaseError  # noqa: E402
from fact_checker.models import ManualEvidenceInput, VerificationReport  # noqa: E402
from fact_checker.report_generator import (  # noqa: E402
    export_reports_csv,
    export_reports_json,
    run_verification_pipeline,
)
from fact_checker.search_provider import NullSearchProvider, get_search_provider  # noqa: E402
from fact_checker.ui_helpers import (  # noqa: E402
    get_database,
    init_app_environment,
    inject_custom_css,
    provider_status_label,
    render_report_preview,
)

init_app_environment()

st.set_page_config(
    page_title="Verify Claims | Fact Verification System",
    page_icon="✅",
    layout="wide",
)
inject_custom_css()

st.title("Verify Factual Claims")
st.markdown(
    "Enter one or more factual claims below. Each claim is checked against retrieved or "
    "manually entered sources and labeled **SUPPORTED**, **CONTRADICTED**, or **UNVERIFIED**."
)

# Initialize session state for manual sources and active reports
if "manual_sources_state" not in st.session_state:
    st.session_state["manual_sources_state"] = [
        {"title": "", "url": "", "publication_date": "", "text": ""}
    ]
if "claims_input_text" not in st.session_state:
    st.session_state["claims_input_text"] = ""
if "latest_reports" not in st.session_state:
    st.session_state["latest_reports"] = []

SAMPLE_PRESETS = {
    "Supported Claim (Multi-Source)": {
        "claims": "Water boils at 100 degrees Celsius at standard atmospheric pressure.",
        "sources": [
            {
                "title": "Properties of Water - Boiling Point",
                "url": "https://example.org/chemistry/water-boiling-point",
                "publication_date": "2024-05-12",
                "text": (
                    "At standard atmospheric pressure (1 atm), pure water boils at 100 degrees "
                    "Celsius (212 degrees Fahrenheit)."
                ),
            },
            {
                "title": "Thermodynamics Reference Handbook",
                "url": "https://physics-notes.example.edu/phase-changes",
                "publication_date": "2023-11-03",
                "text": (
                    "Under standard atmospheric pressure, liquid water transitions to steam at "
                    "100 degrees Celsius."
                ),
            },
        ],
    },
    "Contradicted Claim (Numeric & Refutation)": {
        "claims": "The Apollo 11 Moon landing took place in 1975.",
        "sources": [
            {
                "title": "Apollo 11 Mission Summary",
                "url": "https://space-archive.example.org/apollo-11",
                "publication_date": "2024-07-20",
                "text": (
                    "The Apollo 11 Moon landing took place in July 1969, when astronauts Neil "
                    "Armstrong and Buzz Aldrin walked on the lunar surface. Claims that Apollo 11 "
                    "occurred in 1975 are incorrect."
                ),
            },
        ],
    },
    "Conflicting Sources (Disagreement Flagged)": {
        "claims": "Moderate daily coffee consumption increases heart disease risk.",
        "sources": [
            {
                "title": "Observational Nutrition Brief",
                "url": "https://nutrition-journal.example.org/coffee-study-a",
                "publication_date": "2022-03-14",
                "text": (
                    "An older subgroup analysis suggested moderate daily coffee consumption "
                    "increases heart disease risk among heavy smokers."
                ),
            },
            {
                "title": "Cardiology Meta-Analysis Review",
                "url": "https://cardio-review.example.org/coffee-meta-analysis",
                "publication_date": "2025-01-19",
                "text": (
                    "Large prospective meta-analyses show moderate daily coffee consumption does "
                    "not increase heart disease risk in healthy adults."
                ),
            },
        ],
    },
    "Insufficient Evidence (Unverified)": {
        "claims": "Project Aurora launched a commercial fusion reactor in 2026.",
        "sources": [
            {
                "title": "Energy Conference Agenda",
                "url": "https://energy-forum.example.org/2026-agenda",
                "publication_date": "2026-02-01",
                "text": (
                    "The annual energy conference covered solar storage, grid resilience, and "
                    "preliminary fusion research milestones."
                ),
            },
        ],
    },
}

with st.expander("Try Sample Verification Scenarios (No API Key Required)", expanded=False):
    preset_choice = st.selectbox("Select a scenario", list(SAMPLE_PRESETS.keys()))
    if st.button("Load Selected Scenario", type="secondary"):
        preset = SAMPLE_PRESETS[preset_choice]
        st.session_state["claims_input_text"] = preset["claims"]
        st.session_state["manual_sources_state"] = [dict(s) for s in preset["sources"]]
        st.rerun()

api_configured, provider_label = provider_status_label()

col_left, col_right = st.columns([1.2, 1.0])

with col_left:
    st.subheader("1. Enter Factual Claims")
    claims_text = st.text_area(
        "Enter one claim per line (or multiple sentences, max 10 claims)",
        key="claims_input_text",
        height=150,
        placeholder=(
            "Example:\n"
            "Water boils at 100 degrees Celsius at standard atmospheric pressure.\n"
            "The Eiffel Tower was completed in 1889."
        ),
    )
    st.caption(
        "Validation rules: non-empty text, 5–500 characters per claim, max 5,000 total characters."
    )

with col_right:
    st.subheader("2. Source Discovery Mode")
    st.markdown(f"**Status:** {provider_label}")
    use_live_search = st.checkbox(
        "Use configured Search API to discover sources automatically",
        value=api_configured,
        disabled=not api_configured,
        help="Only enabled when TAVILY_API_KEY or SERPER_API_KEY is configured in .env.",
    )
    if not api_configured:
        st.info(
            "No search API key is configured. Add `TAVILY_API_KEY` or `SERPER_API_KEY` to `.env` "
            "for live search, or provide evidence manually below."
        )

    fetch_manual_urls = st.checkbox(
        "Fetch public webpage text automatically for manual URLs with blank text",
        value=False,
        help="Respects website restrictions and never bypasses paywalls or HTTP 403/429 blocks.",
    )

st.subheader("3. Manual Evidence Sources (Optional when Search API is active)")
btn_add, btn_clear, _ = st.columns([1, 1, 4])
with btn_add:
    if st.button("Add Source Row", width="stretch"):
        st.session_state["manual_sources_state"].append(
            {"title": "", "url": "", "publication_date": "", "text": ""}
        )
        st.rerun()
with btn_clear:
    if st.button("Reset Sources", width="stretch"):
        st.session_state["manual_sources_state"] = [
            {"title": "", "url": "", "publication_date": "", "text": ""}
        ]
        st.rerun()

updated_sources: list[dict[str, str]] = []
for idx, src in enumerate(st.session_state["manual_sources_state"]):
    with st.expander(
        f"Source #{idx + 1}" + (f" — {src['title']}" if src.get("title") else ""),
        expanded=(idx == 0 or bool(src.get("title") or src.get("url") or src.get("text"))),
    ):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            title_val = st.text_input(
                "Source Title", value=src.get("title", ""), key=f"src_title_{idx}"
            )
        with c2:
            url_val = st.text_input(
                "Source URL (https://...)", value=src.get("url", ""), key=f"src_url_{idx}"
            )
        with c3:
            date_val = st.text_input(
                "Publication Date (optional)",
                value=src.get("publication_date", ""),
                key=f"src_date_{idx}",
                placeholder="YYYY-MM-DD",
            )
        text_val = st.text_area(
            "Supporting or Relevant Excerpt / Page Text",
            value=src.get("text", ""),
            key=f"src_text_{idx}",
            height=100,
            placeholder="Paste publicly accessible source text or leave blank to fetch URL if enabled.",
        )
        updated_sources.append(
            {
                "title": title_val,
                "url": url_val,
                "publication_date": date_val,
                "text": text_val,
            }
        )

st.session_state["manual_sources_state"] = updated_sources

st.divider()

if st.button("Run Fact Verification", type="primary", width="stretch"):
    manual_entries: list[ManualEvidenceInput] = []
    input_validation_errors: list[str] = []

    for idx, src in enumerate(updated_sources, start=1):
        has_any = any(v.strip() for v in src.values())
        if not has_any:
            continue
        if not src["url"].strip():
            input_validation_errors.append(f"Manual source #{idx} is missing a URL.")
            continue
        title_clean = src["title"].strip() or src["url"].strip()
        manual_entries.append(
            ManualEvidenceInput(
                title=title_clean,
                url=src["url"].strip(),
                text=src["text"].strip(),
                publication_date=src["publication_date"].strip() or None,
            )
        )

    if input_validation_errors:
        for err in input_validation_errors:
            st.error(err)
    elif not use_live_search and not manual_entries:
        st.error(
            "Please add at least one manual evidence source (URL + text) or configure a Search API key."
        )
    else:
        progress_bar = st.progress(0.0, text="Starting verification pipeline...")

        def _update_progress(pct: float, msg: str) -> None:
            progress_bar.progress(min(max(pct, 0.0), 1.0), text=msg)

        provider = get_search_provider() if use_live_search else NullSearchProvider()
        timeout_sec = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "8"))
        max_results = int(os.getenv("MAX_SEARCH_RESULTS", "5"))

        try:
            session_id, search_mode, reports = run_verification_pipeline(
                claims_text,
                search_provider=provider,
                manual_entries=manual_entries,
                fetch_manual_urls=fetch_manual_urls,
                max_search_results=max_results,
                timeout_seconds=timeout_sec,
                progress_callback=_update_progress,
            )
            st.session_state["latest_reports"] = reports
            try:
                get_database().save_session_and_reports(
                    session_id=session_id,
                    raw_input=claims_text,
                    search_mode=search_mode,
                    reports=reports,
                )
                st.success(
                    f"Verified {len(reports)} claim(s) and saved session `{session_id}` to SQLite history."
                )
            except DatabaseError as db_exc:
                st.warning(
                    f"Verification completed, but saving to SQLite failed: {db_exc}"
                )
        except ClaimValidationError as exc:
            progress_bar.empty()
            st.error(f"Claim validation error: {exc}")
        except Exception as exc:  # noqa: BLE001
            progress_bar.empty()
            st.error(f"Unexpected error during verification: {exc}")

latest_reports: list[VerificationReport] = st.session_state.get("latest_reports", [])
if latest_reports:
    st.divider()
    st.header("Verification Results")

    if len(latest_reports) > 1:
        b1, b2, _ = st.columns([1, 1, 3])
        with b1:
            st.download_button(
                "Export All (JSON)",
                data=export_reports_json(latest_reports),
                file_name="verification_session.json",
                mime="application/json",
                width="stretch",
            )
        with b2:
            st.download_button(
                "Export All (CSV)",
                data=export_reports_csv(latest_reports),
                file_name="verification_session.csv",
                mime="text/csv",
                width="stretch",
            )

    for idx, report in enumerate(latest_reports):
        render_report_preview(report, key_prefix=f"verify_{idx}")
