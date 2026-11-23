"""Unit tests for Google Gemini API integration and error handling."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from google.genai import errors as genai_errors

from fact_checker.gemini_service import (
    GeminiAuthenticationError,
    GeminiFactCheckService,
    GeminiMissingKeyError,
    GeminiRateLimitError,
    GeminiResponseError,
    GeminiTimeoutError,
    get_gemini_model,
    is_gemini_configured,
)
from fact_checker.models import RetrievalStatus, RetrievedSource, VerificationLabel
from fact_checker.source_retriever import utc_now_iso


def _sample_source() -> RetrievedSource:
    return RetrievedSource(
        source_id="src-11111111",
        title="Chemistry Reference",
        url="https://chem.example.org/water",
        publisher="chem.example.org",
        publication_date="2024-05-01",
        snippet="",
        retrieved_text="Pure water boils at 100 degrees Celsius at standard atmospheric pressure.",
        retrieval_status=RetrievalStatus.RETRIEVED,
        retrieved_at=utc_now_iso(),
        is_manual=True,
        provider="manual",
    )


def test_missing_and_placeholder_api_key_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    assert is_gemini_configured() is False
    assert get_gemini_model() == "gemini-2.5-flash"

    service = GeminiFactCheckService()
    with pytest.raises(GeminiMissingKeyError, match="GEMINI_API_KEY is not configured"):
        service.analyze_claim_preliminary("Water boils at 100 degrees Celsius.")

    monkeypatch.setenv("GEMINI_API_KEY", "your_google_ai_studio_api_key")
    assert is_gemini_configured() is False
    with pytest.raises(GeminiMissingKeyError):
        GeminiFactCheckService().split_claims("Water boils at 100C.")


def test_invalid_api_key_does_not_leak_secret_and_raises_auth_error() -> None:
    secret = "AIzaSyFakeSecretDoNotExpose123"
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = genai_errors.APIError(
        403, {"error": {"message": "PERMISSION_DENIED: API_KEY_INVALID"}}
    )
    service = GeminiFactCheckService(api_key=secret, client=mock_client)

    with pytest.raises(GeminiAuthenticationError) as exc_info:
        service.analyze_claim_preliminary("Water boils at 100 degrees Celsius.")

    assert secret not in str(exc_info.value)


def test_rate_limit_timeout_and_malformed_json_errors() -> None:
    mock_client = MagicMock()
    service = GeminiFactCheckService(api_key="fake-key", client=mock_client)

    mock_client.models.generate_content.side_effect = genai_errors.APIError(
        429, {"error": {"message": "RESOURCE_EXHAUSTED"}}
    )
    with pytest.raises(GeminiRateLimitError, match="429"):
        service.analyze_claim_preliminary("Test claim.")

    mock_client.models.generate_content.side_effect = httpx.ReadTimeout("timed out")
    with pytest.raises(GeminiTimeoutError, match="timed out"):
        service.analyze_claim_preliminary("Test claim.")

    mock_client.models.generate_content.side_effect = None
    bad_resp = MagicMock()
    bad_resp.text = "{not valid json"
    mock_client.models.generate_content.return_value = bad_resp
    with pytest.raises(GeminiResponseError, match="malformed"):
        service.analyze_claim_preliminary("Test claim.")

    empty_resp = MagicMock()
    empty_resp.text = "   "
    mock_client.models.generate_content.return_value = empty_resp
    with pytest.raises(GeminiResponseError, match="empty"):
        service.analyze_claim_preliminary("Test claim.")


def test_structured_pydantic_responses_for_split_sources_and_preliminary() -> None:
    mock_client = MagicMock()
    service = GeminiFactCheckService(api_key="fake-key", model="gemini-2.5-flash", client=mock_client)

    split_resp = MagicMock()
    split_resp.text = '{"claims": ["Water boils at 100 degrees Celsius.", "Ice melts at 0 degrees Celsius."]}'
    mock_client.models.generate_content.return_value = split_resp
    claims = service.split_claims("Water boils at 100C and ice melts at 0C.")
    assert len(claims) == 2

    src_resp = MagicMock()
    src_resp.text = (
        '{"label": "SUPPORTED", "confidence_score": 0.9, '
        '"confidence_explanation": "Directly confirmed by provided source.", '
        '"short_explanation": "The provided chemistry reference confirms the boiling point.", '
        '"source_assessments": [{"source_id": "src-11111111", '
        '"evidence_excerpt": "Pure water boils at 100 degrees Celsius at standard atmospheric pressure.", '
        '"position": "Supports", "rationale": "Exact match."}], '
        '"unsupported_statements": [], "unresolved_questions": [], "disagreement_summary": ""}'
    )
    mock_client.models.generate_content.return_value = src_resp
    assessed = service.analyze_claim_against_sources(
        "Water boils at 100 degrees Celsius.", [_sample_source()]
    )
    assert assessed.label == VerificationLabel.SUPPORTED
    assert assessed.source_assessments[0].source_id == "src-11111111"

    prelim_resp = MagicMock()
    prelim_resp.text = (
        '{"label": "UNVERIFIED", "confidence_score": 0.4, '
        '"confidence_explanation": "Requires external primary source verification.", '
        '"short_explanation": "Preliminary knowledge suggests further verification is needed.", '
        '"supporting_points": ["General principle aligns."], '
        '"contradicting_points": [], '
        '"unsupported_statements": ["Specific 2026 figure not checked."], '
        '"unresolved_questions": ["What do primary statistics show?"]}'
    )
    mock_client.models.generate_content.return_value = prelim_resp
    prelim = service.analyze_claim_preliminary("Specific 2026 figure claim.")
    assert prelim.label == VerificationLabel.UNVERIFIED
    assert prelim.unsupported_statements == ["Specific 2026 figure not checked."]
