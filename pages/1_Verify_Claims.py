"""Verify Claims page - Mode A (Manual Source Verification) and Mode B (Gemini Preliminary)."""

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
from fact_checker.gemini_service import (  # noqa: E402
    GeminiAuthenticationError,
    GeminiMissingKeyError,
    GeminiRateLimitError,
    GeminiResponseError,
    GeminiServiceError,
    GeminiTimeoutError,
)
from fact_checker.models import (  # noqa: E402
    ManualEvidenceInput,
    VerificationMode,
    VerificationReport,
)
from fact_checker.report_generator import (  # noqa: E402
    export_reports_csv,
    export_reports_json,
    run_verification_pipeline,
)
from fact_checker.ui_helpers import (  # noqa: E402
    gemini_status_label,
    get_database,
    init_app_environment,
    inject_custom_css,
    render_report_preview,
)

init_app_environment()

st.set_page_config(
    page_title="Verify Claims | Fact Verification System",
    page_icon="✅",
    layout="wide",
)
inject_custom_css()

st.title("Verify Factual Claims with Gemini")
st.markdown(
    "Choose **Manual Source Verification** to compare your claim against explicit sources, or "
    "**Gemini Knowledge-Based Preliminary Analysis** for an AI-generated initial screening."
)

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

gemini_ok, gemini_status = gemini_status_label()
if gemini_ok:
    st.success(gemini_status)
else:
    st.warning(
        f"{gemini_status}. Configure `GEMINI_API_KEY` in your `.env` file to run Gemini analysis."
    )

with st.expander("Load Sample Claim & Source Scenarios", expanded=False):
    preset_choice = st.selectbox("Select a scenario", list(SAMPLE_PRESETS.keys()))
    if st.button("Load Selected Scenario", type="secondary"):
        preset = SAMPLE_PRESETS[preset_choice]
        st.session_state["claims_input_text"] = preset["claims"]
        st.session_state["manual_sources_state"] = [dict(s) for s in preset["sources"]]
        st.rerun()

col_left, col_right = st.columns([1.2, 1.0])

with col_left:
    st.subheader("1. Enter Factual Claims")
    claims_text = st.text_area(
        "Enter one or more claims (or a paragraph to split into claims)",
        key="claims_input_text",
        height=150,
        placeholder=(
            "Example:\n"
            "Water boils at 100 degrees Celsius at standard atmospheric pressure.\n"
            "The Eiffel Tower was completed in 1889."
        ),
    )
    use_gemini_split = st.checkbox(
        "Use Gemini to extract individual factual claims from long text",
        value=False,
        help="Breaks multi-sentence prose into concise claims before verification.",
    )

with col_right:
    st.subheader("2. Verification Mode")
    selected_mode_label = st.radio(
        "Select how claims should be evaluated",
        [
            VerificationMode.MANUAL_SOURCE.value,
            VerificationMode.PRELIMINARY_KNOWLEDGE.value,
        ],
        index=0,
    )
    selected_mode = VerificationMode(selected_mode_label)

    if selected_mode == VerificationMode.PRELIMINARY_KNOWLEDGE:
        st.warning(
            "**Warning — Preliminary AI Analysis Only:** Gemini will evaluate the claim using its "
            "training knowledge without checking external URLs or live sources. Do NOT treat this "
            "as live fact verification."
        )
        fetch_manual_urls = False
    else:
        fetch_manual_urls = st.checkbox(
            "Fetch public webpage text automatically for URLs with blank evidence text",
            value=False,
            help=(
                "Respects HTTP restrictions (401/403/429) and discloses inaccessible pages "
                "without claiming unread URLs were verified."
            ),
        )

manual_entries_ui: list[dict[str, str]] = st.session_state["manual_sources_state"]

if selected_mode == VerificationMode.MANUAL_SOURCE:
    st.subheader("3. Source URLs & Evidence")
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
                "Source Evidence / Excerpt",
                value=src.get("text", ""),
                key=f"src_text_{idx}",
                height=100,
                placeholder="Paste relevant source text or leave blank to fetch public URL if enabled.",
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
    manual_entries_ui = updated_sources

st.divider()

if st.button("Run Gemini Analysis", type="primary", width="stretch"):
    manual_entries: list[ManualEvidenceInput] = []
    input_validation_errors: list[str] = []

    if selected_mode == VerificationMode.MANUAL_SOURCE:
        for idx, src in enumerate(manual_entries_ui, start=1):
            has_any = any(v.strip() for v in src.values())
            if not has_any:
                continue
            if not src["url"].strip():
                input_validation_errors.append(f"Source #{idx} is missing a URL.")
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
    elif selected_mode == VerificationMode.MANUAL_SOURCE and not manual_entries:
        st.error(
            "Please add at least one source URL and evidence text in Manual Source Verification mode, "
            "or switch to Gemini Knowledge-Based Preliminary Analysis."
        )
    else:
        progress_bar = st.progress(0.0, text="Starting Gemini verification pipeline...")

        def _update_progress(pct: float, msg: str) -> None:
            progress_bar.progress(min(max(pct, 0.0), 1.0), text=msg)

        try:
            timeout_sec = max(1, int(os.getenv("REQUEST_TIMEOUT_SECONDS", "15")))
        except ValueError:
            timeout_sec = 15

        try:
            session_id, mode_name, reports = run_verification_pipeline(
                claims_text,
                verification_mode=selected_mode,
                manual_entries=manual_entries,
                fetch_manual_urls=fetch_manual_urls,
                timeout_seconds=timeout_sec,
                use_gemini=True,
                use_gemini_claim_splitting=use_gemini_split,
                progress_callback=_update_progress,
            )
            st.session_state["latest_reports"] = reports
            try:
                get_database().save_session_and_reports(
                    session_id=session_id,
                    raw_input=claims_text,
                    search_mode=mode_name,
                    reports=reports,
                )
                st.success(
                    f"Completed Gemini analysis for {len(reports)} claim(s) and saved session "
                    f"`{session_id}` to SQLite history."
                )
            except DatabaseError as db_exc:
                st.warning(
                    f"Analysis completed, but saving to SQLite failed: {db_exc}"
                )
        except ClaimValidationError as exc:
            progress_bar.empty()
            st.error(f"Claim validation error: {exc}")
        except GeminiMissingKeyError as exc:
            progress_bar.empty()
            st.error(f"Missing Gemini API Key: {exc}")
        except GeminiAuthenticationError as exc:
            progress_bar.empty()
            st.error(f"Invalid Gemini API Key: {exc}")
        except GeminiRateLimitError as exc:
            progress_bar.empty()
            st.error(f"Gemini Rate Limit: {exc}")
        except GeminiTimeoutError as exc:
            progress_bar.empty()
            st.error(f"Gemini Timeout: {exc}")
        except (GeminiResponseError, GeminiServiceError) as exc:
            progress_bar.empty()
            st.error(f"Gemini Service Error: {exc}")
        except Exception as exc:  # noqa: BLE001
            progress_bar.empty()
            st.error(f"Unexpected error during analysis: {exc}")

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
