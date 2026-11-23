"""Transparent NLP relevance scoring using TF-IDF cosine similarity and keyword overlap."""

from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .claim_parser import extract_keywords
from .models import CandidateStatement, ParsedClaim, ScoredEvidence


def _compute_tfidf_scores(claim_text: str, statements: list[str]) -> list[float]:
    """Compute TF-IDF cosine similarity between claim and each statement safely."""
    if not statements:
        return []
    corpus = [claim_text, *statements]
    try:
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        matrix = vectorizer.fit_transform(corpus)
        sims = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
        return [float(max(0.0, min(1.0, score))) for score in sims]
    except ValueError:
        # Happens if corpus consists solely of stopwords or empty vocabulary
        return [0.0 for _ in statements]


def score_evidence_relevance(
    claim: ParsedClaim,
    candidates: list[CandidateStatement],
) -> list[ScoredEvidence]:
    """Rank candidate evidence statements by topical relevance to the claim.

    Note: Relevance measures topical similarity only—it is NOT proof of factual
    correctness. Both supporting and contradicting evidence often have high relevance.
    """
    if not candidates:
        return []

    statement_texts = [c.statement for c in candidates]
    tfidf_scores = _compute_tfidf_scores(claim.text, statement_texts)
    claim_kw_set = set(claim.keywords)

    scored: list[ScoredEvidence] = []
    for candidate, tfidf in zip(candidates, tfidf_scores, strict=True):
        cand_kw_set = set(extract_keywords(candidate.statement))
        matched = sorted(claim_kw_set & cand_kw_set)
        kw_overlap = len(matched) / len(claim_kw_set) if claim_kw_set else 0.0
        combined = min(1.0, (0.55 * tfidf) + (0.45 * kw_overlap))

        scored.append(
            ScoredEvidence(
                candidate=candidate,
                tfidf_score=round(tfidf, 4),
                keyword_overlap_score=round(kw_overlap, 4),
                relevance_score=round(combined, 4),
                matched_terms=matched,
            )
        )

    scored.sort(key=lambda item: item.relevance_score, reverse=True)
    return scored
