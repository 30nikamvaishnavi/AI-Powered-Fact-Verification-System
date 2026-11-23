"""Unit tests for claim validation, splitting, and feature extraction."""

from __future__ import annotations

import pytest

from fact_checker.claim_parser import (
    ClaimValidationError,
    contains_negation,
    extract_keywords,
    extract_numbers,
    parse_claims,
)


def test_parse_claims_rejects_empty_and_whitespace() -> None:
    with pytest.raises(ClaimValidationError, match="at least one factual claim"):
        parse_claims("")
    with pytest.raises(ClaimValidationError, match="at least one factual claim"):
        parse_claims("   \n\t  ")


def test_parse_claims_rejects_too_short_claim() -> None:
    with pytest.raises(ClaimValidationError, match="too short"):
        parse_claims("Hi.")


def test_parse_claims_rejects_excessively_long_claim_and_batch() -> None:
    long_claim = "Water boils quickly. " + ("word " * 130)
    with pytest.raises(ClaimValidationError, match="exceeds the maximum length"):
        parse_claims(long_claim)

    huge_input = "a" * 5001
    with pytest.raises(ClaimValidationError, match="Input is too long"):
        parse_claims(huge_input)


def test_parse_claims_rejects_too_many_claims() -> None:
    claims = "\n".join(f"{i}. Claim number {i} is factual." for i in range(1, 13))
    with pytest.raises(ClaimValidationError, match="Too many claims"):
        parse_claims(claims)


def test_parse_claims_splits_bullets_and_preserves_decimals_and_abbreviations() -> None:
    raw = (
        "- Dr. Smith measured pi as 3.14 in the U.S. laboratory.\n"
        "2) Water boils at 100 degrees Celsius at sea level."
    )
    parsed = parse_claims(raw)
    assert len(parsed) == 2
    assert parsed[0].text == "Dr. Smith measured pi as 3.14 in the U.S. laboratory."
    assert parsed[1].text == "Water boils at 100 degrees Celsius at sea level."
    assert "3.14" in parsed[0].numbers
    assert "100" in parsed[1].numbers


def test_feature_helpers_extract_keywords_numbers_and_negation() -> None:
    assert "vaccines" in extract_keywords("Vaccines do not cause autism.")
    assert extract_numbers("Population reached 1,250,000 or 42.5% in 2024.") == [
        "1250000",
        "42.5%",
        "2024",
    ]
    assert contains_negation("Vaccines do not cause autism.") is True
    assert contains_negation("Water boils at 100 degrees.") is False
