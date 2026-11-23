"""Multi-source comparison builder that highlights agreements, conflicts, and access gaps."""

from __future__ import annotations

from .models import (
    ComparisonSummary,
    EvidencePosition,
    EvidenceSnippet,
    RetrievalStatus,
    RetrievedSource,
    SourceComparisonRow,
)


def _credibility_note_for_source(source: RetrievedSource) -> str:
    if source.retrieval_status == RetrievalStatus.INVALID_URL:
        return "URL failed validation; not fetched."
    if source.retrieval_status == RetrievalStatus.INACCESSIBLE:
        return f"Source inaccessible ({source.retrieval_error or 'retrieval failed'})."
    if source.retrieval_status == RetrievalStatus.SNIPPET_ONLY:
        return (
            f"Domain '{source.publisher}' shown for attribution only (not auto-trusted); "
            "analyzed search snippet only because full page was restricted."
        )
    if source.is_manual:
        return (
            f"User-provided source ('{source.publisher}'); "
            "reliability depends on independent review of the cited origin."
        )
    return (
        f"Domain '{source.publisher}' shown for attribution only; "
        "domain name alone does not verify factual authority."
    )


def build_source_comparison(
    claim_text: str,
    sources: list[RetrievedSource],
    best_by_source: dict[str, EvidenceSnippet],
) -> ComparisonSummary:
    """Create a structured ComparisonSummary across all retrieved/attempted sources."""
    rows: list[SourceComparisonRow] = []
    supports_count = 0
    contradicts_count = 0
    unclear_count = 0
    inaccessible_count = 0

    for source in sources:
        snippet = best_by_source.get(source.source_id)
        if not source.usable_text:
            inaccessible_count += 1

        if snippet is not None:
            position = snippet.position
            excerpt = snippet.excerpt
            relevance = snippet.relevance_score
        else:
            position = EvidencePosition.UNCLEAR
            excerpt = (
                source.retrieval_error
                or source.snippet
                or "No readable evidence text was extracted from this source."
            )
            relevance = 0.0

        if position == EvidencePosition.SUPPORTS:
            supports_count += 1
        elif position == EvidencePosition.CONTRADICTS:
            contradicts_count += 1
        else:
            unclear_count += 1

        rows.append(
            SourceComparisonRow(
                source_title=source.title,
                publisher=source.publisher,
                url=source.url,
                publication_date=source.publication_date,
                evidence_excerpt=excerpt,
                evidence_position=position,
                retrieval_status=source.retrieval_status.value,
                relevance_score=relevance,
                credibility_note=_credibility_note_for_source(source),
            )
        )

    has_disagreement = supports_count > 0 and contradicts_count > 0

    if not rows:
        agreement_summary = "No sources were available to compare."
        disagreement_summary = "No disagreements detected because no sources were provided."
    elif has_disagreement:
        supporting_names = [
            r.publisher for r in rows if r.evidence_position == EvidencePosition.SUPPORTS
        ]
        contradicting_names = [
            r.publisher for r in rows if r.evidence_position == EvidencePosition.CONTRADICTS
        ]
        agreement_summary = (
            f"{supports_count} source(s) ({', '.join(supporting_names)}) align with the claim, "
            f"while {contradicts_count} source(s) ({', '.join(contradicting_names)}) conflict with it."
        )
        disagreement_summary = (
            "Direct source conflict detected: retrieved evidence contains both supporting "
            "and contradicting statements. Review the excerpts and primary origins carefully."
        )
    elif supports_count > 1:
        agreement_summary = (
            f"All {supports_count} decisive source(s) agree in supporting the claim."
        )
        disagreement_summary = "No contradictions found among retrieved sources."
    elif contradicts_count > 1:
        agreement_summary = (
            f"All {contradicts_count} decisive source(s) agree in contradicting the claim."
        )
        disagreement_summary = "Sources consistently conflict with the claim."
    elif supports_count == 1:
        agreement_summary = "One source supports the claim; no corroborating second source yet."
        disagreement_summary = "No contradicting evidence observed in available sources."
    elif contradicts_count == 1:
        agreement_summary = "One source contradicts the claim."
        disagreement_summary = "Claim conflicts with the retrieved source."
    else:
        agreement_summary = "Available sources do not provide decisive agreement."
        disagreement_summary = (
            "No clear support or contradiction could be established from accessible text."
        )

    return ComparisonSummary(
        claim_text=claim_text,
        rows=rows,
        supports_count=supports_count,
        contradicts_count=contradicts_count,
        unclear_count=unclear_count,
        inaccessible_count=inaccessible_count,
        has_disagreement=has_disagreement,
        agreement_summary=agreement_summary,
        disagreement_summary=disagreement_summary,
    )
