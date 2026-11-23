"""Structured verification report builder, pipeline orchestrator, and JSON/CSV/Markdown exporters."""

from __future__ import annotations

import csv
import io
import json
import uuid
from collections.abc import Callable
from pathlib import Path

from .claim_parser import parse_claims
from .evidence_extractor import extract_candidate_statements
from .gemini_service import GeminiFactCheckService
from .models import (
    ManualEvidenceInput,
    ParsedClaim,
    RetrievedSource,
    VerificationMode,
    VerificationReport,
)
from .relevance_analyzer import score_evidence_relevance
from .source_comparator import build_source_comparison
from .source_retriever import (
    DEFAULT_TIMEOUT_SECONDS,
    build_manual_source,
    utc_now_iso,
)
from .verification_engine import (
    build_preliminary_verification_payload,
    reconcile_gemini_source_assessment,
    verify_claim_from_evidence,
)


def generate_verification_report(
    claim: ParsedClaim,
    sources: list[RetrievedSource],
    *,
    session_id: str | None = None,
    verification_mode: VerificationMode = VerificationMode.MANUAL_SOURCE,
    gemini_service: GeminiFactCheckService | None = None,
    use_gemini: bool = True,
) -> VerificationReport:
    """Generate a structured VerificationReport for one claim under Mode A or Mode B."""
    sess_id = session_id or f"sess-{uuid.uuid4().hex[:8]}"

    if verification_mode == VerificationMode.PRELIMINARY_KNOWLEDGE:
        service = gemini_service or GeminiFactCheckService()
        prelim_resp = service.analyze_claim_preliminary(claim.text)
        verdict = build_preliminary_verification_payload(claim, prelim_resp)
        comparison = build_source_comparison(claim.text, [], {})
        return VerificationReport(
            report_id=f"rep-{uuid.uuid4().hex[:10]}",
            session_id=sess_id,
            claim=claim.text,
            label=verdict["label"],  # type: ignore[arg-type]
            confidence_score=verdict["confidence_score"],  # type: ignore[arg-type]
            confidence_explanation=verdict["confidence_explanation"],  # type: ignore[arg-type]
            short_explanation=verdict["short_explanation"],  # type: ignore[arg-type]
            verification_mode=VerificationMode.PRELIMINARY_KNOWLEDGE,
            is_preliminary_ai_only=True,
            supporting_evidence=[],
            contradicting_evidence=[],
            unclear_evidence=[],
            unsupported_statements=verdict["unsupported_statements"],  # type: ignore[arg-type]
            preliminary_points_supporting=verdict["preliminary_points_supporting"],  # type: ignore[arg-type]
            preliminary_points_contradicting=verdict["preliminary_points_contradicting"],  # type: ignore[arg-type]
            unresolved_questions=verdict["unresolved_questions"],  # type: ignore[arg-type]
            source_comparison=comparison,
            sources=[],
            retrieval_timestamp=utc_now_iso(),
            limitations=verdict["limitations"],  # type: ignore[arg-type]
            disagreement_flagged=bool(verdict["disagreement_flagged"]),
            search_mode=VerificationMode.PRELIMINARY_KNOWLEDGE.value,
        )

    candidates = extract_candidate_statements(sources)
    scored = score_evidence_relevance(claim, candidates)
    accessible_sources = [s for s in sources if s.usable_text]

    if use_gemini and accessible_sources:
        service = gemini_service or GeminiFactCheckService()
        gemini_resp = service.analyze_claim_against_sources(claim.text, sources)
        verdict = reconcile_gemini_source_assessment(claim, sources, scored, gemini_resp)
    else:
        verdict = verify_claim_from_evidence(claim, sources, scored)

    comparison = build_source_comparison(
        claim.text,
        sources,
        verdict["best_by_source"],  # type: ignore[arg-type]
    )

    return VerificationReport(
        report_id=f"rep-{uuid.uuid4().hex[:10]}",
        session_id=sess_id,
        claim=claim.text,
        label=verdict["label"],  # type: ignore[arg-type]
        confidence_score=verdict["confidence_score"],  # type: ignore[arg-type]
        confidence_explanation=verdict["confidence_explanation"],  # type: ignore[arg-type]
        short_explanation=verdict["short_explanation"],  # type: ignore[arg-type]
        verification_mode=VerificationMode.MANUAL_SOURCE,
        is_preliminary_ai_only=False,
        supporting_evidence=verdict["supporting_evidence"],  # type: ignore[arg-type]
        contradicting_evidence=verdict["contradicting_evidence"],  # type: ignore[arg-type]
        unclear_evidence=verdict["unclear_evidence"],  # type: ignore[arg-type]
        unsupported_statements=verdict.get("unsupported_statements", []),  # type: ignore[arg-type]
        unresolved_questions=verdict["unresolved_questions"],  # type: ignore[arg-type]
        source_comparison=comparison,
        sources=sources,
        retrieval_timestamp=utc_now_iso(),
        limitations=verdict["limitations"],  # type: ignore[arg-type]
        disagreement_flagged=bool(verdict["disagreement_flagged"]),
        search_mode=VerificationMode.MANUAL_SOURCE.value,
    )


def run_verification_pipeline(
    raw_claims_text: str,
    *,
    verification_mode: VerificationMode = VerificationMode.MANUAL_SOURCE,
    manual_entries: list[ManualEvidenceInput] | None = None,
    fetch_manual_urls: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    gemini_service: GeminiFactCheckService | None = None,
    use_gemini: bool = True,
    use_gemini_claim_splitting: bool = False,
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[str, str, list[VerificationReport]]:
    """Validate claims, process sources (Mode A) or preliminary AI analysis (Mode B), and return reports."""
    if progress_callback:
        progress_callback(0.1, "Validating and parsing factual claims...")

    service = gemini_service or (GeminiFactCheckService(timeout_seconds=timeout_seconds) if use_gemini else None)

    effective_claims_input = raw_claims_text
    if use_gemini and use_gemini_claim_splitting and service is not None and raw_claims_text.strip():
        if progress_callback:
            progress_callback(0.18, "Using Gemini to decompose text into individual claims...")
        extracted_claims = service.split_claims(raw_claims_text)
        if extracted_claims:
            effective_claims_input = "\n".join(extracted_claims)

    parsed_claims = parse_claims(effective_claims_input)
    session_id = f"sess-{uuid.uuid4().hex[:10]}"

    manual_sources: list[RetrievedSource] = []
    if verification_mode == VerificationMode.MANUAL_SOURCE and manual_entries:
        if progress_callback:
            progress_callback(0.3, "Processing submitted source URLs and evidence...")
        for entry in manual_entries:
            manual_sources.append(
                build_manual_source(
                    entry,
                    fetch_if_text_missing=fetch_manual_urls,
                    timeout=timeout_seconds,
                )
            )

    reports: list[VerificationReport] = []
    total = len(parsed_claims)
    for idx, claim in enumerate(parsed_claims, start=1):
        if progress_callback:
            step_label = (
                f"Running Gemini preliminary analysis for claim {idx}/{total}..."
                if verification_mode == VerificationMode.PRELIMINARY_KNOWLEDGE
                else f"Comparing sources against claim {idx}/{total} with Gemini..."
            )
            progress_callback(0.35 + 0.55 * ((idx - 1) / max(total, 1)), step_label)

        report = generate_verification_report(
            claim,
            list(manual_sources),
            session_id=session_id,
            verification_mode=verification_mode,
            gemini_service=service,
            use_gemini=use_gemini,
        )
        reports.append(report)

    if progress_callback:
        progress_callback(1.0, "Verification complete.")

    return session_id, verification_mode.value, reports


def export_report_json(report: VerificationReport) -> str:
    """Serialize a single VerificationReport as pretty-printed JSON."""
    return json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False)


def export_reports_json(reports: list[VerificationReport]) -> str:
    """Serialize a list of VerificationReports as pretty-printed JSON."""
    payload = [r.model_dump(mode="json") for r in reports]
    return json.dumps(payload, indent=2, ensure_ascii=False)


def export_reports_csv(reports: list[VerificationReport]) -> str:
    """Export one or more VerificationReports into a flat, spreadsheet-friendly CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "report_id",
            "session_id",
            "claim",
            "final_label",
            "verification_mode",
            "is_preliminary_ai_only",
            "confidence_score",
            "disagreement_flagged",
            "retrieval_timestamp",
            "source_title",
            "publisher",
            "url",
            "publication_date",
            "retrieval_status",
            "evidence_position",
            "relevance_score",
            "evidence_excerpt",
            "short_explanation",
        ]
    )

    for report in reports:
        rows = report.source_comparison.rows
        if not rows:
            writer.writerow(
                [
                    report.report_id,
                    report.session_id,
                    report.claim,
                    report.label.value,
                    report.verification_mode.value,
                    report.is_preliminary_ai_only,
                    report.confidence_score,
                    report.disagreement_flagged,
                    report.retrieval_timestamp,
                    "",
                    "",
                    "",
                    "",
                    "Preliminary AI Only" if report.is_preliminary_ai_only else "No Sources",
                    "Unclear",
                    0.0,
                    "",
                    report.short_explanation,
                ]
            )
            continue

        for row in rows:
            writer.writerow(
                [
                    report.report_id,
                    report.session_id,
                    report.claim,
                    report.label.value,
                    report.verification_mode.value,
                    report.is_preliminary_ai_only,
                    report.confidence_score,
                    report.disagreement_flagged,
                    report.retrieval_timestamp,
                    row.source_title,
                    row.publisher,
                    row.url,
                    row.publication_date or "",
                    row.retrieval_status,
                    row.evidence_position.value,
                    row.relevance_score,
                    row.evidence_excerpt,
                    report.short_explanation,
                ]
            )

    return output.getvalue()


def export_report_csv(report: VerificationReport) -> str:
    """Export a single VerificationReport as CSV."""
    return export_reports_csv([report])


def export_report_markdown(report: VerificationReport) -> str:
    """Render a clean, human-readable Markdown verification report."""
    lines: list[str] = [
        f"# Verification Report: `{report.label.value}`",
        "",
    ]
    if report.is_preliminary_ai_only:
        lines.extend(
            [
                "> **WARNING — AI-GENERATED PRELIMINARY ANALYSIS:** This report is based solely "
                "on Gemini model knowledge. No external sources or live webpages were verified.",
                "",
            ]
        )

    lines.extend(
        [
            f"- **Report ID:** `{report.report_id}`",
            f"- **Session ID:** `{report.session_id}`",
            f"- **Verification Mode:** {report.verification_mode.value}",
            f"- **Retrieval Timestamp (UTC):** {report.retrieval_timestamp}",
            f"- **Confidence Score:** {report.confidence_score:.2f}",
            f"- **Disagreement Flagged:** {'Yes' if report.disagreement_flagged else 'No'}",
            "",
            "## Original Claim",
            f"> {report.claim}",
            "",
            "## Summary & Confidence Explanation",
            report.short_explanation,
            "",
            f"*{report.confidence_explanation}*",
            "",
        ]
    )

    if report.is_preliminary_ai_only:
        lines.append("## Preliminary Knowledge Points (Unverified by Live Sources)")
        lines.append("### Points Supporting Claim")
        if report.preliminary_points_supporting:
            for pt in report.preliminary_points_supporting:
                lines.append(f"- {pt}")
        else:
            lines.append("- None noted.")
        lines.append("")
        lines.append("### Points Contradicting Claim")
        if report.preliminary_points_contradicting:
            for pt in report.preliminary_points_contradicting:
                lines.append(f"- {pt}")
        else:
            lines.append("- None noted.")
        lines.append("")
    else:
        lines.append("## Supporting Evidence")
        if report.supporting_evidence:
            for item in report.supporting_evidence:
                date_part = f" ({item.publication_date})" if item.publication_date else ""
                lines.append(
                    f"- **[{item.source_title}]({item.url})** — `{item.publisher}`{date_part} "
                    f"| Relevance: `{item.relevance_score:.2f}`"
                )
                lines.append(f"  - Excerpt: \"{item.excerpt}\"")
                lines.append(f"  - Rationale: {item.rationale}")
        else:
            lines.append("- None identified.")

        lines.extend(["", "## Contradicting Evidence"])
        if report.contradicting_evidence:
            for item in report.contradicting_evidence:
                date_part = f" ({item.publication_date})" if item.publication_date else ""
                lines.append(
                    f"- **[{item.source_title}]({item.url})** — `{item.publisher}`{date_part} "
                    f"| Relevance: `{item.relevance_score:.2f}`"
                )
                lines.append(f"  - Excerpt: \"{item.excerpt}\"")
                lines.append(f"  - Rationale: {item.rationale}")
        else:
            lines.append("- None identified.")

        lines.extend(["", "## Multiple-Source Comparison"])
        if report.source_comparison.rows:
            lines.append(
                "| Source Title | Publisher | Publication Date | Position | Retrieval Status | Relevance | URL |"
            )
            lines.append("| --- | --- | --- | --- | --- | --- | --- |")
            for row in report.source_comparison.rows:
                safe_title = row.source_title.replace("|", "\\|")
                pub_date = row.publication_date or "Unavailable"
                lines.append(
                    f"| {safe_title} | {row.publisher} | {pub_date} | "
                    f"{row.evidence_position.value} | {row.retrieval_status} | "
                    f"{row.relevance_score:.2f} | [Link]({row.url}) |"
                )
            lines.append("")
            lines.append(f"**Agreement:** {report.source_comparison.agreement_summary}")
            lines.append("")
            lines.append(f"**Disagreement:** {report.source_comparison.disagreement_summary}")
        else:
            lines.append("No sources were compared.")

    lines.extend(["", "## Unsupported or Unverified Statements"])
    if report.unsupported_statements:
        for stmt in report.unsupported_statements:
            lines.append(f"- {stmt}")
    else:
        lines.append("- None highlighted.")

    lines.extend(["", "## Unresolved Questions"])
    if report.unresolved_questions:
        for q in report.unresolved_questions:
            lines.append(f"- {q}")
    else:
        lines.append("- None.")

    lines.extend(["", "## Limitations"])
    for lim in report.limitations:
        lines.append(f"- {lim}")

    lines.append("")
    return "\n".join(lines)


def save_report_to_exports(
    report: VerificationReport,
    fmt: str,
    exports_dir: str | Path = "exports",
) -> Path:
    """Write a VerificationReport export file to disk and return its Path."""
    target_dir = Path(exports_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    normalized_fmt = fmt.strip().lower()

    if normalized_fmt == "json":
        content = export_report_json(report)
        ext = "json"
    elif normalized_fmt == "csv":
        content = export_report_csv(report)
        ext = "csv"
    elif normalized_fmt in {"md", "markdown"}:
        content = export_report_markdown(report)
        ext = "md"
    else:
        raise ValueError(f"Unsupported export format: {fmt}")

    out_path = target_dir / f"{report.report_id}.{ext}"
    out_path.write_text(content, encoding="utf-8")
    return out_path
