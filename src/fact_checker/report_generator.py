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
from .models import (
    ManualEvidenceInput,
    ParsedClaim,
    RetrievedSource,
    VerificationReport,
)
from .relevance_analyzer import score_evidence_relevance
from .search_provider import NullSearchProvider, SearchProvider, SearchProviderError
from .source_comparator import build_source_comparison
from .source_retriever import (
    build_manual_source,
    retrieve_sources_from_search_results,
    utc_now_iso,
)
from .verification_engine import verify_claim_from_evidence


def generate_verification_report(
    claim: ParsedClaim,
    sources: list[RetrievedSource],
    *,
    session_id: str | None = None,
    search_mode: str = "Manual Evidence Mode",
) -> VerificationReport:
    """Run extraction, relevance scoring, verification, and comparison for one claim."""
    candidates = extract_candidate_statements(sources)
    scored = score_evidence_relevance(claim, candidates)
    verdict = verify_claim_from_evidence(claim, sources, scored)
    comparison = build_source_comparison(
        claim.text,
        sources,
        verdict["best_by_source"],  # type: ignore[arg-type]
    )

    return VerificationReport(
        report_id=f"rep-{uuid.uuid4().hex[:10]}",
        session_id=session_id or f"sess-{uuid.uuid4().hex[:8]}",
        claim=claim.text,
        label=verdict["label"],  # type: ignore[arg-type]
        confidence_score=verdict["confidence_score"],  # type: ignore[arg-type]
        confidence_explanation=verdict["confidence_explanation"],  # type: ignore[arg-type]
        short_explanation=verdict["short_explanation"],  # type: ignore[arg-type]
        supporting_evidence=verdict["supporting_evidence"],  # type: ignore[arg-type]
        contradicting_evidence=verdict["contradicting_evidence"],  # type: ignore[arg-type]
        unclear_evidence=verdict["unclear_evidence"],  # type: ignore[arg-type]
        unresolved_questions=verdict["unresolved_questions"],  # type: ignore[arg-type]
        source_comparison=comparison,
        sources=sources,
        retrieval_timestamp=utc_now_iso(),
        limitations=verdict["limitations"],  # type: ignore[arg-type]
        disagreement_flagged=bool(verdict["disagreement_flagged"]),
        search_mode=search_mode,
    )


def run_verification_pipeline(
    raw_claims_text: str,
    *,
    search_provider: SearchProvider | None = None,
    manual_entries: list[ManualEvidenceInput] | None = None,
    fetch_manual_urls: bool = False,
    max_search_results: int = 5,
    timeout_seconds: int = 8,
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[str, str, list[VerificationReport]]:
    """Validate claims, gather sources, and generate VerificationReports for a session.

    Returns:
        Tuple of (session_id, search_mode_label, reports).
    """
    if progress_callback:
        progress_callback(0.1, "Validating and parsing factual claims...")

    parsed_claims = parse_claims(raw_claims_text)
    session_id = f"sess-{uuid.uuid4().hex[:10]}"
    provider = search_provider or NullSearchProvider()

    manual_sources: list[RetrievedSource] = []
    if manual_entries:
        if progress_callback:
            progress_callback(0.25, "Processing manually supplied evidence sources...")
        for entry in manual_entries:
            manual_sources.append(
                build_manual_source(
                    entry,
                    fetch_if_text_missing=fetch_manual_urls,
                    timeout=timeout_seconds,
                )
            )

    use_search = provider.is_configured()
    search_mode = (
        f"Search API ({provider.name}) + Manual"
        if (use_search and manual_sources)
        else (f"Search API ({provider.name})" if use_search else "Manual Evidence Mode")
    )

    reports: list[VerificationReport] = []
    total = len(parsed_claims)
    for idx, claim in enumerate(parsed_claims, start=1):
        claim_sources = list(manual_sources)
        search_warning: str | None = None

        if use_search:
            if progress_callback:
                progress_callback(
                    0.3 + 0.4 * ((idx - 1) / max(total, 1)),
                    f"Discovering sources for claim {idx}/{total} via {provider.name}...",
                )
            try:
                results = provider.search(claim.text, max_results=max_search_results)
                fetched = retrieve_sources_from_search_results(
                    results, timeout=timeout_seconds
                )
                seen_urls = {s.url for s in claim_sources}
                for src in fetched:
                    if src.url not in seen_urls:
                        claim_sources.append(src)
                        seen_urls.add(src.url)
            except SearchProviderError as exc:
                search_warning = str(exc)

        if progress_callback:
            progress_callback(
                0.35 + 0.55 * (idx / max(total, 1)),
                f"Analyzing evidence and generating report {idx}/{total}...",
            )

        report = generate_verification_report(
            claim,
            claim_sources,
            session_id=session_id,
            search_mode=search_mode,
        )
        if search_warning:
            report.limitations.append(f"Search API warning: {search_warning}")
        reports.append(report)

    if progress_callback:
        progress_callback(1.0, "Verification complete.")

    return session_id, search_mode, reports


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
            "confidence_score",
            "disagreement_flagged",
            "retrieval_timestamp",
            "search_mode",
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
                    report.confidence_score,
                    report.disagreement_flagged,
                    report.retrieval_timestamp,
                    report.search_mode,
                    "",
                    "",
                    "",
                    "",
                    "No Sources",
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
                    report.confidence_score,
                    report.disagreement_flagged,
                    report.retrieval_timestamp,
                    report.search_mode,
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
        f"- **Report ID:** `{report.report_id}`",
        f"- **Session ID:** `{report.session_id}`",
        f"- **Retrieval Timestamp (UTC):** {report.retrieval_timestamp}",
        f"- **Discovery Mode:** {report.search_mode}",
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
        "## Supporting Evidence",
    ]

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
