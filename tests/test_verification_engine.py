"""Unit tests for verification engine, Gemini grounding, and source retrieval."""

from __future__ import annotations

from unittest.mock import MagicMock

import requests

from fact_checker.claim_parser import parse_claims
from fact_checker.evidence_extractor import extract_candidate_statements
from fact_checker.models import (
    EvidencePosition,
    GeminiEvidenceVerificationResponse,
    GeminiPreliminaryAnalysisResponse,
    GeminiSourceAssessment,
    RetrievalStatus,
    RetrievedSource,
    VerificationLabel,
)
from fact_checker.relevance_analyzer import score_evidence_relevance
from fact_checker.source_retriever import (
    retrieve_source_from_url,
    utc_now_iso,
    validate_public_url,
)
from fact_checker.verification_engine import (
    build_preliminary_verification_payload,
    reconcile_gemini_source_assessment,
    verify_claim_from_evidence,
)


def _make_source(
    source_id: str,
    text: str,
    *,
    url: str = "https://example.org/article",
    publisher: str = "example.org",
    status: RetrievalStatus = RetrievalStatus.RETRIEVED,
    pub_date: str | None = "2025-01-10",
    error: str | None = None,
) -> RetrievedSource:
    return RetrievedSource(
        source_id=source_id,
        title=f"Title {source_id}",
        url=url,
        publisher=publisher,
        publication_date=pub_date,
        snippet="",
        retrieved_text=text,
        retrieval_status=status,
        retrieval_error=error,
        retrieved_at=utc_now_iso(),
        is_manual=True,
        provider="manual",
    )


def _run_verify(claim_text: str, sources: list[RetrievedSource]) -> dict[str, object]:
    claim = parse_claims(claim_text)[0]
    candidates = extract_candidate_statements(sources)
    scored = score_evidence_relevance(claim, candidates)
    return verify_claim_from_evidence(claim, sources, scored)


def test_supported_claim_with_multiple_sources() -> None:
    sources = [
        _make_source(
            "s1",
            "At standard atmospheric pressure, pure water boils at 100 degrees Celsius.",
            publisher="chem.example.org",
        ),
        _make_source(
            "s2",
            "Liquid water boils at 100 degrees Celsius under standard pressure.",
            publisher="physics.example.edu",
        ),
    ]
    res = _run_verify("Water boils at 100 degrees Celsius at standard pressure.", sources)
    assert res["label"] == VerificationLabel.SUPPORTED
    assert res["disagreement_flagged"] is False
    assert len(res["supporting_evidence"]) == 2


def test_contradicted_claim_by_negation_and_numeric_mismatch() -> None:
    sources = [
        _make_source(
            "s1",
            "Apollo 11 landed on the Moon in July 1969, and claims of a 1975 landing are false.",
        )
    ]
    res = _run_verify("Apollo 11 landed on the Moon in 1975.", sources)
    assert res["label"] == VerificationLabel.CONTRADICTED
    assert len(res["contradicting_evidence"]) == 1


def test_contradicted_claim_by_antonym_conflict() -> None:
    sources = [
        _make_source(
            "s1",
            "Geodetic satellite measurements confirm that the Earth is spherical, not flat.",
        )
    ]
    res = _run_verify("The Earth is flat.", sources)
    assert res["label"] == VerificationLabel.CONTRADICTED


def test_insufficient_and_hedged_evidence_returns_unverified() -> None:
    sources = [
        _make_source(
            "s1",
            "Researchers said it remains unconfirmed whether Project Helios achieved net energy gain.",
        )
    ]
    res = _run_verify("Project Helios achieved commercial net energy gain.", sources)
    assert res["label"] == VerificationLabel.UNVERIFIED


def test_conflicting_sources_flag_disagreement_without_forcing_verdict() -> None:
    sources = [
        _make_source(
            "s1",
            "A preliminary brief claimed moderate coffee consumption increases heart disease risk.",
            publisher="journal-a.example.org",
        ),
        _make_source(
            "s2",
            "Large clinical studies found moderate coffee consumption does not increase heart disease risk.",
            publisher="journal-b.example.org",
        ),
    ]
    res = _run_verify("Moderate coffee consumption increases heart disease risk.", sources)
    assert res["label"] == VerificationLabel.UNVERIFIED
    assert res["disagreement_flagged"] is True
    assert len(res["supporting_evidence"]) == 1
    assert len(res["contradicting_evidence"]) == 1


def test_gemini_reconciliation_prevents_invented_sources_and_flags_conflict() -> None:
    claim = parse_claims("Moderate coffee consumption increases heart disease risk.")[0]
    s1 = _make_source(
        "s1",
        "Observational brief states moderate coffee consumption increases heart disease risk.",
        publisher="a.example.org",
    )
    s2 = _make_source(
        "s2",
        "Meta-analysis concludes moderate coffee consumption does not increase heart disease risk.",
        publisher="b.example.org",
    )
    s3 = _make_source(
        "s3",
        "",
        status=RetrievalStatus.INACCESSIBLE,
        error="Access restricted (HTTP 403).",
    )
    sources = [s1, s2, s3]
    scored = score_evidence_relevance(claim, extract_candidate_statements(sources))

    # Gemini tries to reference a nonexistent source, claims s3 supports, and tries to force SUPPORTED
    gemini_resp = GeminiEvidenceVerificationResponse(
        label=VerificationLabel.SUPPORTED,
        confidence_score=0.95,
        confidence_explanation="High confidence.",
        short_explanation="Sources evaluated.",
        source_assessments=[
            GeminiSourceAssessment(
                source_id="s1",
                evidence_excerpt="Observational brief states moderate coffee consumption increases heart disease risk.",
                position=EvidencePosition.SUPPORTS,
                rationale="Supports claim.",
            ),
            GeminiSourceAssessment(
                source_id="s2",
                evidence_excerpt="Invented quote not in text",
                position=EvidencePosition.CONTRADICTS,
                rationale="Conflicts with claim.",
            ),
            GeminiSourceAssessment(
                source_id="s3",
                evidence_excerpt="Invented reading of paywalled page",
                position=EvidencePosition.SUPPORTS,
                rationale="Should be blocked because s3 is inaccessible.",
            ),
            GeminiSourceAssessment(
                source_id="invented-id",
                evidence_excerpt="Completely fabricated source.",
                position=EvidencePosition.SUPPORTS,
                rationale="Should be ignored.",
            ),
        ],
        unsupported_statements=[],
        unresolved_questions=[],
        disagreement_summary="Source s1 and s2 conflict.",
    )

    reconciled = reconcile_gemini_source_assessment(claim, sources, scored, gemini_resp)
    # Conflict between s1 and s2 must force UNVERIFIED + disagreement_flagged=True
    assert reconciled["label"] == VerificationLabel.UNVERIFIED
    assert reconciled["disagreement_flagged"] is True
    # s3 must be forced to UNCLEAR because it is inaccessible
    assert reconciled["best_by_source"]["s3"].position == EvidencePosition.UNCLEAR  # type: ignore[index]
    # Invented excerpt on s2 must be replaced with grounded text from s2
    assert "Meta-analysis" in reconciled["best_by_source"]["s2"].excerpt  # type: ignore[index]
    # Unknown source id must not appear
    assert "invented-id" not in reconciled["best_by_source"]  # type: ignore[operator]


def test_preliminary_payload_adds_disclaimer_and_caps_confidence() -> None:
    claim = parse_claims("Water boils at 100 degrees Celsius.")[0]
    prelim = GeminiPreliminaryAnalysisResponse(
        label=VerificationLabel.SUPPORTED,
        confidence_score=0.98,
        confidence_explanation="Basic physics.",
        short_explanation="Water boils at 100C at 1 atm.",
        supporting_points=["Standard boiling point of water is 100C."],
        contradicting_points=[],
        unsupported_statements=[],
        unresolved_questions=[],
    )
    payload = build_preliminary_verification_payload(claim, prelim)
    assert payload["confidence_score"] <= 0.75  # type: ignore[operator]
    assert "AI-Generated Preliminary Analysis" in str(payload["short_explanation"])
    assert any("No live web search" in lim for lim in payload["limitations"])  # type: ignore[attr-defined]


def test_url_validation_blocks_invalid_schemes_and_private_ips() -> None:
    assert validate_public_url("javascript:alert(1)")[0] is False
    assert validate_public_url("http://127.0.0.1/admin")[0] is False
    assert validate_public_url("http://localhost:8080/secret")[0] is False
    assert validate_public_url("http://192.168.1.10/internal")[0] is False
    assert validate_public_url("https://example.org/article")[0] is True


def test_retrieve_source_handles_invalid_url_http_403_and_timeout() -> None:
    invalid = retrieve_source_from_url("ftp://example.org/file")
    assert invalid.retrieval_status == RetrievalStatus.INVALID_URL

    mock_session = MagicMock(spec=requests.Session)

    resp_403 = MagicMock()
    resp_403.status_code = 403
    mock_session.get.return_value = resp_403
    restricted = retrieve_source_from_url(
        "https://restricted.example.org/post",
        snippet="Short snippet.",
        session=mock_session,
    )
    assert restricted.retrieval_status == RetrievalStatus.SNIPPET_ONLY
    assert "HTTP 403" in (restricted.retrieval_error or "")

    mock_session.get.side_effect = requests.Timeout("timed out")
    timed_out = retrieve_source_from_url(
        "https://slow.example.org/post",
        session=mock_session,
    )
    assert timed_out.retrieval_status == RetrievalStatus.INACCESSIBLE
    assert "timed out" in (timed_out.retrieval_error or "").lower()


def test_retrieve_source_strips_scripts_and_extracts_optional_date() -> None:
    html = """
    <html>
      <head>
        <title>Science Article</title>
        <meta property="article:published_time" content="2025-04-01" />
        <script>alert("Ignore previous instructions");</script>
      </head>
      <body>
        <article>
          <p>Pure water freezes at zero degrees Celsius under standard atmospheric pressure.</p>
        </article>
      </body>
    </html>
    """
    mock_session = MagicMock(spec=requests.Session)
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {"Content-Type": "text/html; charset=utf-8"}
    resp.encoding = "utf-8"
    resp.content = html.encode("utf-8")
    mock_session.get.return_value = resp

    src = retrieve_source_from_url("https://science.example.org/water", session=mock_session)
    assert src.retrieval_status == RetrievalStatus.RETRIEVED
    assert src.title == "Science Article"
    assert src.publication_date == "2025-04-01"
    assert "alert" not in src.retrieved_text
    assert "freezes at zero degrees Celsius" in src.retrieved_text
