"""Claim validation, normalization, splitting, and feature extraction."""

from __future__ import annotations

import re
import uuid

from .models import ParsedClaim

MIN_CLAIM_LENGTH = 5
MAX_CLAIM_LENGTH = 500
MAX_INPUT_LENGTH = 5000
MAX_CLAIMS_PER_SUBMISSION = 10

STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "he",
        "her",
        "hers",
        "him",
        "his",
        "how",
        "i",
        "in",
        "into",
        "is",
        "it",
        "its",
        "may",
        "might",
        "more",
        "most",
        "of",
        "on",
        "or",
        "our",
        "out",
        "over",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "under",
        "up",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "will",
        "with",
        "would",
        "you",
        "your",
    }
)

NEGATION_WORDS: frozenset[str] = frozenset(
    {
        "no",
        "not",
        "never",
        "none",
        "neither",
        "nor",
        "cannot",
        "can't",
        "won't",
        "don't",
        "doesn't",
        "didn't",
        "isn't",
        "aren't",
        "wasn't",
        "weren't",
        "hasn't",
        "haven't",
        "hadn't",
        "without",
    }
)

_ABBREVIATIONS = (
    "Dr.",
    "Mr.",
    "Mrs.",
    "Ms.",
    "Prof.",
    "Inc.",
    "Ltd.",
    "U.S.",
    "U.K.",
    "E.U.",
    "e.g.",
    "i.e.",
    "vs.",
    "approx.",
    "et al.",
)


class ClaimValidationError(ValueError):
    """Raised when user claim input fails validation rules."""


def _protect_abbreviations(text: str) -> str:
    protected = text
    for abbr in _ABBREVIATIONS:
        safe = abbr.replace(".", "<DOT>")
        protected = protected.replace(abbr, safe)
    # Protect decimal numbers such as 3.14 or 98.6
    protected = re.sub(r"(\d)\.(\d)", r"\1<DOT>\2", protected)
    return protected


def _restore_abbreviations(text: str) -> str:
    return text.replace("<DOT>", ".")


def split_claims(raw_text: str) -> list[str]:
    """Split raw user input into clean individual claim strings."""
    cleaned_lines: list[str] = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Strip leading list markers like "- ", "* ", "1. ", "2) "
        stripped = re.sub(r"^(?:[-*•]+|\d+[.)])\s+", "", stripped).strip()
        if stripped:
            cleaned_lines.append(stripped)

    claims: list[str] = []
    for line in cleaned_lines:
        protected = _protect_abbreviations(line)
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", protected)
        for part in parts:
            restored = _restore_abbreviations(part).strip()
            if restored:
                claims.append(restored)
    return claims


def extract_keywords(text: str) -> list[str]:
    """Extract normalized, deduplicated non-stopword tokens from text."""
    tokens = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'-]*", text.lower())
    seen: set[str] = set()
    keywords: list[str] = []
    for token in tokens:
        clean = token.strip("'-")
        if len(clean) < 2 and not clean.isdigit():
            continue
        if clean in STOPWORDS:
            continue
        if clean not in seen:
            seen.add(clean)
            keywords.append(clean)
    return keywords


def extract_numbers(text: str) -> list[str]:
    """Extract numeric quantities, years, and percentages from text."""
    matches = re.findall(r"\b\d+(?:,\d{3})*(?:\.\d+)?%?", text)
    return [m.replace(",", "") for m in matches]


def contains_negation(text: str) -> bool:
    """Return True if the text contains an explicit negation cue."""
    tokens = set(re.findall(r"[a-zA-Z']+", text.lower()))
    return bool(tokens & NEGATION_WORDS)


def parse_claims(
    raw_input: str,
    *,
    max_claims: int = MAX_CLAIMS_PER_SUBMISSION,
    max_claim_length: int = MAX_CLAIM_LENGTH,
    max_input_length: int = MAX_INPUT_LENGTH,
) -> list[ParsedClaim]:
    """Validate and parse raw user text into structured ParsedClaim objects.

    Args:
        raw_input: Raw text entered by the user containing one or more claims.
        max_claims: Maximum number of claims allowed per submission.
        max_claim_length: Maximum allowed character length of a single claim.
        max_input_length: Maximum total character length of raw_input.

    Returns:
        A list of validated ParsedClaim instances.

    Raises:
        ClaimValidationError: If input is empty, too short, too long, or has too many claims.
    """
    if not isinstance(raw_input, str) or not raw_input.strip():
        raise ClaimValidationError("Please enter at least one factual claim to verify.")

    normalized_raw = raw_input.strip()
    if len(normalized_raw) > max_input_length:
        raise ClaimValidationError(
            f"Input is too long ({len(normalized_raw)} characters). "
            f"Maximum allowed input is {max_input_length} characters."
        )

    raw_claims = split_claims(normalized_raw)
    if not raw_claims:
        raise ClaimValidationError("No valid factual claims were detected in your input.")

    if len(raw_claims) > max_claims:
        raise ClaimValidationError(
            f"Too many claims submitted ({len(raw_claims)}). "
            f"Please submit at most {max_claims} claims at once."
        )

    parsed: list[ParsedClaim] = []
    for idx, claim_text in enumerate(raw_claims, start=1):
        if len(claim_text) < MIN_CLAIM_LENGTH:
            raise ClaimValidationError(
                f"Claim #{idx} is too short ('{claim_text}'). "
                f"Each claim must be at least {MIN_CLAIM_LENGTH} characters."
            )
        if len(claim_text) > max_claim_length:
            raise ClaimValidationError(
                f"Claim #{idx} exceeds the maximum length of {max_claim_length} characters "
                f"({len(claim_text)} characters)."
            )
        normalized = re.sub(r"\s+", " ", claim_text).strip()
        parsed.append(
            ParsedClaim(
                claim_id=f"claim-{uuid.uuid4().hex[:8]}",
                text=normalized,
                normalized_text=normalized.lower(),
                keywords=extract_keywords(normalized),
                numbers=extract_numbers(normalized),
                has_negation=contains_negation(normalized),
            )
        )

    return parsed
