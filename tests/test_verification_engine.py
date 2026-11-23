"""Unit tests for verification engine, source retrieval errors, and search providers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from fact_checker.claim_parser import parse_claims
from fact_checker.evidence_extractor import extract_candidate_statements
from fact_checker.models import RetrievalStatus, RetrievedSource, VerificationLabel
from fact_checker.relevance_analyzer import score_evidence_relevance
from fact_checker.search_provider import (
    NullSearchProvider,
    SerperSearchProvider,
    TavilySearchProvider,
    get_search_provider,
)
from fact_checker.source_retriever import (
    retrieve_source_from_url,
    utc_now_iso,
    validate_public_url,
)
from fact_checker.verification_engine import verify_claim_from_evidence


def _make_source(
    source_id: str,
    text: str,
    *,
    url: str = "https://example.org/article",
    publisher: str = "example.org",
    status: RetrievalStatus = RetrievalStatus.RETRIEVED,
    pub_date: str | None = "2025-01-10",
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
        retrieval_error=None,
        retrieved_at=utc_now_iso(),
        is_manual=False,
        provider="test",
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
        snippet="Short snippet from search API.",
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


def test_search_provider_selection_and_mocked_apis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.setenv("SEARCH_PROVIDER", "auto")

    assert isinstance(get_search_provider(), NullSearchProvider)

    with patch("fact_checker.search_provider.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "results": [
                {
                    "title": "NASA Apollo 11",
                    "url": "https://nasa.example.gov/apollo-11",
                    "content": "Apollo 11 landed on the Moon in 1969.",
                    "published_date": "2024-07-20",
                }
            ]
        }
        mock_post.return_value = mock_resp

        tavily = TavilySearchProvider(api_key="test-key-not-logged")
        results = tavily.search("Apollo 11 landing", max_results=3)
        assert len(results) == 1
        assert results[0].publisher == "nasa.example.gov"
        assert results[0].publication_date == "2024-07-20"

    with patch("fact_checker.search_provider.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "organic": [
                {
                    "title": "Serper Result",
                    "link": "https://www.example.org/fact",
                    "snippet": "Sample snippet text.",
                }
            ]
        }
        mock_post.return_value = mock_resp

        serper = SerperSearchProvider(api_key="test-serper-key")
        results = serper.search("test query")
        assert len(results) == 1
        assert results[0].publisher == "example.org"
        assert results[0].publication_date is None
