"""Shared Streamlit UI components, styling, and environment helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from .database import DatabaseError, VerificationDatabase
from .gemini_service import get_gemini_model, is_gemini_configured
from .models import (
    ComparisonSummary,
    EvidenceSnippet,
    VerificationLabel,
    VerificationReport,
)
from .report_generator import (
    export_report_csv,
    export_report_json,
    export_report_markdown,
    save_report_to_exports,
)


def init_app_environment() -> None:
    """Load environment variables from .env if present."""
    load_dotenv(override=False)


def get_database() -> VerificationDatabase:
    """Return configured VerificationDatabase instance."""
    return VerificationDatabase(os.getenv("DATABASE_PATH"))


def inject_custom_css() -> None:
    """Apply clean, readable styling to Streamlit cards and verdict badges."""
    st.markdown(
        """
        <style>
        .fv-badge {
            display: inline-block;
            padding: 0.25rem 0.65rem;
            border-radius: 6px;
            font-weight: 700;
            font-size: 0.85rem;
            letter-spacing: 0.04em;
            margin-right: 0.4rem;
        }
        .fv-supported {
            background-color: #dcfce7;
            color: #166534;
            border: 1px solid #86efac;
        }
        .fv-contradicted {
            background-color: #fee2e2;
            color: #991b1b;
            border: 1px solid #fca5a5;
        }
        .fv-unverified {
            background-color: #fef3c7;
            color: #92400e;
            border: 1px solid #fcd34d;
        }
        .fv-prelim {
            background-color: #e0f2fe;
            color: #075985;
            border: 1px solid #7dd3fc;
        }
        .fv-card {
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-radius: 10px;
            padding: 1rem 1.2rem;
            margin-bottom: 1rem;
            background-color: rgba(128, 128, 128, 0.04);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def label_badge_html(label: VerificationLabel, *, is_preliminary: bool = False) -> str:
    """Return HTML span for a verification verdict badge (and optional preliminary tag)."""
    css_map = {
        VerificationLabel.SUPPORTED: "fv-supported",
        VerificationLabel.CONTRADICTED: "fv-contradicted",
        VerificationLabel.UNVERIFIED: "fv-unverified",
    }
    css_class = css_map.get(label, "fv-unverified")
    badge = f'<span class="fv-badge {css_class}">{label.value}</span>'
    if is_preliminary:
        badge += '<span class="fv-badge fv-prelim">AI-GENERATED PRELIMINARY ANALYSIS</span>'
    return badge


def gemini_status_label() -> tuple[bool, str]:
    """Return (is_configured, status_text) without exposing any API key."""
    model = get_gemini_model()
    if is_gemini_configured():
        return True, f"Gemini API Configured (Model: {model})"
    return False, f"GEMINI_API_KEY not configured in .env (Default model: {model})"


def render_evidence_list(items: list[EvidenceSnippet], empty_message: str) -> None:
    """Render a list of supporting or contradicting evidence items."""
    if not items:
        st.caption(empty_message)
        return
    for item in items:
        date_str = f" · Published: {item.publication_date}" if item.publication_date else ""
        st.markdown(
            f"- **[{item.source_title}]({item.url})** (`{item.publisher}`{date_str}) — "
            f"Relevance: `{item.relevance_score:.2f}` · Status: `{item.retrieval_status.value}`"
        )
        st.markdown(f"  > \"{item.excerpt}\"")
        st.caption(f"Analysis: {item.rationale}")


def render_comparison_table(comparison: ComparisonSummary) -> None:
    """Render the multi-source comparison table and agreement/disagreement summaries."""
    if not comparison.rows:
        st.info("No external sources were compared for this report.")
        return

    df = pd.DataFrame(
        [
            {
                "Source Title": row.source_title,
                "Publisher / Domain": row.publisher,
                "URL": row.url,
                "Publication Date": row.publication_date or "Unavailable",
                "Evidence Excerpt": row.evidence_excerpt,
                "Evidence Position": row.evidence_position.value,
                "Retrieval Status": row.retrieval_status,
                "Relevance": round(row.relevance_score, 2),
                "Credibility Note": row.credibility_note,
            }
            for row in comparison.rows
        ]
    )

    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config={
            "URL": st.column_config.LinkColumn("Source URL", display_text="Open link"),
            "Relevance": st.column_config.NumberColumn("Relevance", format="%.2f"),
        },
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Where Sources Agree**")
        st.write(comparison.agreement_summary)
    with col2:
        st.markdown("**Disagreements & Gaps**")
        if comparison.has_disagreement:
            st.warning(comparison.disagreement_summary)
        else:
            st.write(comparison.disagreement_summary)


def render_report_preview(report: VerificationReport, *, key_prefix: str = "rep") -> None:
    """Render a complete interactive verification report card with export controls."""
    st.markdown('<div class="fv-card">', unsafe_allow_html=True)
    header_col, metric_col = st.columns([4, 1])
    with header_col:
        st.markdown(
            label_badge_html(report.label, is_preliminary=report.is_preliminary_ai_only),
            unsafe_allow_html=True,
        )
        st.markdown(f"### {report.claim}")
    with metric_col:
        st.metric("Confidence", f"{report.confidence_score:.2f}")

    if report.is_preliminary_ai_only:
        st.warning(
            "**AI-Generated Preliminary Analysis (Not Live Source Verification):** "
            "This assessment reflects Gemini's internal model knowledge only. No external "
            "sources, URLs, or live webpages were checked."
        )

    if report.disagreement_flagged:
        st.warning(
            "Source Disagreement Flagged: Provided evidence contains conflicting statements. "
            "Review the comparison table before drawing a conclusion."
        )

    st.write(report.short_explanation)
    st.caption(
        f"{report.confidence_explanation} | Timestamp (UTC): {report.retrieval_timestamp} | "
        f"Mode: {report.verification_mode.value}"
    )

    if report.is_preliminary_ai_only:
        p1, p2 = st.columns(2)
        with p1:
            st.markdown("#### Preliminary Supporting Considerations")
            if report.preliminary_points_supporting:
                for pt in report.preliminary_points_supporting:
                    st.markdown(f"- {pt}")
            else:
                st.caption("None noted.")
        with p2:
            st.markdown("#### Preliminary Contradicting Considerations")
            if report.preliminary_points_contradicting:
                for pt in report.preliminary_points_contradicting:
                    st.markdown(f"- {pt}")
            else:
                st.caption("None noted.")
    else:
        ev_col1, ev_col2 = st.columns(2)
        with ev_col1:
            st.markdown("#### Supporting Evidence")
            render_evidence_list(
                report.supporting_evidence, "No supporting evidence identified."
            )
        with ev_col2:
            st.markdown("#### Contradicting Evidence")
            render_evidence_list(
                report.contradicting_evidence, "No contradicting evidence identified."
            )

        with st.expander("Evidence Comparison Table", expanded=True):
            render_comparison_table(report.source_comparison)

    if report.unsupported_statements:
        st.markdown("#### Unsupported or Unverified Statements")
        for stmt in report.unsupported_statements:
            st.markdown(f"- {stmt}")

    q_col, l_col = st.columns(2)
    with q_col:
        st.markdown("#### Unresolved Questions")
        if report.unresolved_questions:
            for question in report.unresolved_questions:
                st.markdown(f"- {question}")
        else:
            st.caption("No open questions recorded.")
    with l_col:
        st.markdown("#### Limitations & Safeguards")
        for limitation in report.limitations:
            st.markdown(f"- {limitation}")

    st.markdown("#### Export Report")
    dl1, dl2, dl3, dl4 = st.columns(4)
    with dl1:
        st.download_button(
            "Download JSON",
            data=export_report_json(report),
            file_name=f"{report.report_id}.json",
            mime="application/json",
            key=f"{key_prefix}_json_{report.report_id}",
            width="stretch",
        )
    with dl2:
        st.download_button(
            "Download CSV",
            data=export_report_csv(report),
            file_name=f"{report.report_id}.csv",
            mime="text/csv",
            key=f"{key_prefix}_csv_{report.report_id}",
            width="stretch",
        )
    with dl3:
        st.download_button(
            "Download Markdown",
            data=export_report_markdown(report),
            file_name=f"{report.report_id}.md",
            mime="text/markdown",
            key=f"{key_prefix}_md_{report.report_id}",
            width="stretch",
        )
    with dl4:
        if st.button(
            "Save to exports/",
            key=f"{key_prefix}_save_{report.report_id}",
            width="stretch",
        ):
            exports_dir = Path(os.getenv("EXPORTS_DIR", "exports"))
            saved_json = save_report_to_exports(report, "json", exports_dir)
            saved_csv = save_report_to_exports(report, "csv", exports_dir)
            saved_md = save_report_to_exports(report, "md", exports_dir)
            st.success(f"Saved: {saved_json.name}, {saved_csv.name}, {saved_md.name}")

    st.markdown("</div>", unsafe_allow_html=True)


def safe_db_stats() -> tuple[dict[str, int] | None, str | None]:
    """Fetch aggregate SQLite stats without crashing the UI on DB errors."""
    try:
        db = get_database()
        return db.get_stats(), None
    except DatabaseError as exc:
        return None, str(exc)
