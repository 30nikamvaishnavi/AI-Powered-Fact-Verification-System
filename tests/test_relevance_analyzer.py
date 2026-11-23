"""Unit tests for TF-IDF and keyword overlap relevance analysis."""

from __future__ import annotations

from fact_checker.claim_parser import parse_claims
from fact_checker.models import CandidateStatement, RetrievalStatus
from fact_checker.relevance_analyzer import score_evidence_relevance


def _candidate(source_id: str, statement: str) -> CandidateStatement:
    return CandidateStatement(
        source_id=source_id,
        source_title=f"Source {source_id}",
        url=f"https://example.org/{source_id}",
        publisher="example.org",
        publication_date=None,
        statement=statement,
        retrieval_status=RetrievalStatus.RETRIEVED,
    )


def test_relevance_ranks_topical_statement_above_unrelated_statement() -> None:
    claim = parse_claims("Water boils at 100 degrees Celsius at standard pressure.")[0]
    candidates = [
        _candidate("s1", "The stock market closed higher on Tuesday after tech earnings."),
        _candidate("s2", "Pure water boils at 100 degrees Celsius under standard atmospheric pressure."),
    ]
    scored = score_evidence_relevance(claim, candidates)
    assert len(scored) == 2
    assert scored[0].candidate.source_id == "s2"
    assert scored[0].relevance_score > scored[1].relevance_score
    assert "water" in scored[0].matched_terms


def test_relevance_scores_contradicting_text_as_topically_relevant() -> None:
    claim = parse_claims("The Earth is flat.")[0]
    candidates = [
        _candidate("s1", "Scientific observations show the Earth is not flat; it is spherical."),
    ]
    scored = score_evidence_relevance(claim, candidates)
    assert len(scored) == 1
    assert scored[0].relevance_score > 0.3


def test_relevance_handles_empty_and_stopword_only_inputs_safely() -> None:
    claim = parse_claims("Water boils at 100 degrees.")[0]
    assert score_evidence_relevance(claim, []) == []

    stopword_only = [_candidate("s1", "the and or of to in on")]
    scored = score_evidence_relevance(claim, stopword_only)
    assert len(scored) == 1
    assert scored[0].relevance_score == 0.0
