"""Extracts clean, verbatim candidate evidence statements from retrieved sources."""

from __future__ import annotations

import re

from .claim_parser import _protect_abbreviations, _restore_abbreviations
from .models import CandidateStatement, RetrievedSource

MIN_STATEMENT_CHARS = 20
MAX_STATEMENT_CHARS = 450
MAX_STATEMENTS_PER_SOURCE = 40

_BOILERPLATE_PATTERNS = (
    "accept cookies",
    "cookie policy",
    "privacy policy",
    "terms of service",
    "terms of use",
    "all rights reserved",
    "subscribe to our newsletter",
    "sign up for our",
    "javascript is required",
    "skip to main content",
    "read more about",
)


def _is_boilerplate(sentence: str) -> bool:
    lowered = sentence.lower()
    if any(pattern in lowered for pattern in _BOILERPLATE_PATTERNS):
        return True
    # Filter strings with very few alphabetic characters
    alpha_count = sum(1 for ch in sentence if ch.isalpha())
    return alpha_count < 12


def split_into_statements(text: str) -> list[str]:
    """Split retrieved source text into clean, verbatim candidate statements."""
    if not text or not text.strip():
        return []

    statements: list[str] = []
    seen: set[str] = set()

    for paragraph in text.splitlines():
        para = re.sub(r"\s+", " ", paragraph).strip()
        if len(para) < MIN_STATEMENT_CHARS:
            continue

        protected = _protect_abbreviations(para)
        raw_sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", protected)
        for raw_sent in raw_sentences:
            sentence = _restore_abbreviations(raw_sent).strip()
            if len(sentence) < MIN_STATEMENT_CHARS:
                continue
            if len(sentence) > MAX_STATEMENT_CHARS:
                sentence = sentence[: MAX_STATEMENT_CHARS - 3].rstrip() + "..."
            if _is_boilerplate(sentence):
                continue
            norm_key = sentence.lower()
            if norm_key in seen:
                continue
            seen.add(norm_key)
            statements.append(sentence)
            if len(statements) >= MAX_STATEMENTS_PER_SOURCE:
                return statements

    return statements


def extract_candidate_statements(sources: list[RetrievedSource]) -> list[CandidateStatement]:
    """Extract candidate evidence statements across all retrieved sources."""
    candidates: list[CandidateStatement] = []
    for source in sources:
        usable = source.usable_text
        if not usable:
            continue
        for statement in split_into_statements(usable):
            candidates.append(
                CandidateStatement(
                    source_id=source.source_id,
                    source_title=source.title,
                    url=source.url,
                    publisher=source.publisher,
                    publication_date=source.publication_date,
                    statement=statement,
                    retrieval_status=source.retrieval_status,
                )
            )
    return candidates
