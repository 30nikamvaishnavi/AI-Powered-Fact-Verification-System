"""Unit tests for multi-source comparison and missing-field handling."""

from __future__ import annotations

from fact_checker.models import (
    EvidencePosition,
    EvidenceSnippet,
    RetrievalStatus,
    RetrievedSource,
)
from fact_checker.source_comparator import build_source_comparison
from fact_checker.source_retriever import utc_now_iso


def test_source_comparator_flags_disagreement_and_discloses_missing_fields() -> None:
    s_sup = RetrievedSource(
        source_id="s1",
        title="Study A",
        url="https://a.example.org/study",
        publisher="a.example.org",
        publication_date=None,  # Missing publication date must stay None
        snippet="",
        retrieved_text="Electric buses reduce urban tailpipe emissions significantly.",
        retrieval_status=RetrievalStatus.RETRIEVED,
        retrieved_at=utc_now_iso(),
        provider="manual",
    )
    s_con = RetrievedSource(
        source_id="s2",
        title="Report B",
        url="https://b.example.org/report",
        publisher="b.example.org",
        publication_date="2025-02-01",
        snippet="",
        retrieved_text="Electric buses do not reduce lifecycle emissions in coal-heavy grids.",
        retrieval_status=RetrievalStatus.RETRIEVED,
        retrieved_at=utc_now_iso(),
        provider="manual",
    )
    s_inacc = RetrievedSource(
        source_id="s3",
        title="Paywalled Outlet",
        url="https://c.example.org/paywall",
        publisher="c.example.org",
        publication_date=None,
        snippet="",
        retrieved_text="",
        retrieval_status=RetrievalStatus.INACCESSIBLE,
        retrieval_error="Access restricted (HTTP 403) — website restrictions respected.",
        retrieved_at=utc_now_iso(),
        provider="web",
    )

    best = {
        "s1": EvidenceSnippet(
            source_id="s1",
            source_title="Study A",
            url=s_sup.url,
            publisher="a.example.org",
            publication_date=None,
            excerpt=s_sup.retrieved_text,
            relevance_score=0.65,
            position=EvidencePosition.SUPPORTS,
            rationale="Matches terms.",
            retrieval_status=RetrievalStatus.RETRIEVED,
        ),
        "s2": EvidenceSnippet(
            source_id="s2",
            source_title="Report B",
            url=s_con.url,
            publisher="b.example.org",
            publication_date="2025-02-01",
            excerpt=s_con.retrieved_text,
            relevance_score=0.62,
            position=EvidencePosition.CONTRADICTS,
            rationale="Negation mismatch.",
            retrieval_status=RetrievalStatus.RETRIEVED,
        ),
    }

    summary = build_source_comparison(
        "Electric buses reduce urban emissions.", [s_sup, s_con, s_inacc], best
    )
    assert summary.has_disagreement is True
    assert summary.supports_count == 1
    assert summary.contradicts_count == 1
    assert summary.inaccessible_count == 1
    assert len(summary.rows) == 3
    assert summary.rows[0].publication_date is None
    assert "domain name alone does not verify" in summary.rows[0].credibility_note.lower()
    assert "HTTP 403" in summary.rows[2].evidence_excerpt
