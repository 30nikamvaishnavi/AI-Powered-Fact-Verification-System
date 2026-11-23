"""Evidence stance evaluation, Gemini reconciliation, and conservative verification logic."""

from __future__ import annotations

import re

from .claim_parser import contains_negation, extract_numbers
from .models import (
    EvidencePosition,
    EvidenceSnippet,
    GeminiEvidenceVerificationResponse,
    GeminiPreliminaryAnalysisResponse,
    ParsedClaim,
    RetrievalStatus,
    RetrievedSource,
    ScoredEvidence,
    VerificationLabel,
)

MIN_RELEVANCE_FOR_STANCE = 0.14
MIN_RELEVANCE_FOR_SUPPORT = 0.20

_REFUTATION_PHRASES = (
    "false",
    "debunked",
    "myth",
    "hoax",
    "incorrect",
    "inaccurate",
    "misleading",
    "contrary to",
    "refutes",
    "refuted",
    "disproved",
    "disproven",
    "not true",
    "untrue",
    "no evidence that",
    "does not cause",
    "do not cause",
    "did not happen",
    "never happened",
    "contrary to the claim",
)

_UNCERTAINTY_PHRASES = (
    "unconfirmed",
    "allegedly",
    "rumor",
    "rumour",
    "inconclusive",
    "insufficient evidence",
    "unclear whether",
    "not yet proven",
    "unverified",
    "remains disputed",
    "experts disagree",
    "no consensus",
)

_ANTONYM_PAIRS: tuple[tuple[set[str], set[str]], ...] = (
    ({"flat"}, {"spherical", "sphere", "round", "oblate", "spheroid", "globe"}),
    (
        {"increase", "increased", "increases", "rise", "rose", "risen", "higher", "grew"},
        {"decrease", "decreased", "decreases", "fell", "fall", "fallen", "lower", "declined", "dropped"},
    ),
    ({"legal", "lawful", "allowed", "permitted"}, {"illegal", "unlawful", "banned", "prohibited", "forbidden"}),
    ({"safe", "harmless"}, {"unsafe", "dangerous", "hazardous", "harmful"}),
    ({"largest", "biggest", "tallest", "longest", "highest"}, {"smallest", "shortest", "lowest", "tiniest"}),
    ({"oldest", "earliest"}, {"newest", "youngest", "latest"}),
    ({"always", "every", "all"}, {"never", "none"}),
    ({"true", "accurate", "confirmed"}, {"false", "inaccurate", "debunked", "incorrect"}),
)


def _detect_antonym_conflict(claim_text: str, evidence_text: str) -> str | None:
    claim_tokens = set(re.findall(r"[a-zA-Z]+", claim_text.lower()))
    ev_tokens = set(re.findall(r"[a-zA-Z]+", evidence_text.lower()))

    for side_a, side_b in _ANTONYM_PAIRS:
        if (claim_tokens & side_a) and (ev_tokens & side_b):
            c_word = sorted(claim_tokens & side_a)[0]
            e_word = sorted(ev_tokens & side_b)[0]
            return f"Antonym conflict ('{c_word}' vs '{e_word}')"
        if (claim_tokens & side_b) and (ev_tokens & side_a):
            c_word = sorted(claim_tokens & side_b)[0]
            e_word = sorted(ev_tokens & side_a)[0]
            return f"Antonym conflict ('{c_word}' vs '{e_word}')"
    return None


def _detect_numeric_conflict(claim: ParsedClaim, evidence_text: str) -> str | None:
    if not claim.numbers:
        return None
    ev_numbers = extract_numbers(evidence_text)
    if not ev_numbers:
        return None

    claim_num_set = set(claim.numbers)
    ev_num_set = set(ev_numbers)

    missing_from_evidence = [n for n in claim.numbers if n not in ev_num_set]
    different_in_evidence = [n for n in ev_numbers if n not in claim_num_set]
    if missing_from_evidence and different_in_evidence:
        return (
            f"Numeric/date mismatch: claim states {missing_from_evidence[0]} "
            f"while evidence states {different_in_evidence[0]}"
        )
    return None


def evaluate_evidence_item(claim: ParsedClaim, scored: ScoredEvidence) -> EvidenceSnippet:
    """Assess whether a single scored evidence statement supports, contradicts, or is unclear."""
    cand = scored.candidate
    text_lower = cand.statement.lower()
    signals: list[str] = []

    min_terms = 1 if len(claim.keywords) <= 2 else 2
    if (
        scored.relevance_score < MIN_RELEVANCE_FOR_STANCE
        or len(scored.matched_terms) < min_terms
    ):
        return EvidenceSnippet(
            source_id=cand.source_id,
            source_title=cand.source_title,
            url=cand.url,
            publisher=cand.publisher,
            publication_date=cand.publication_date,
            excerpt=cand.statement,
            relevance_score=scored.relevance_score,
            position=EvidencePosition.UNCLEAR,
            rationale=(
                "Low topical overlap with the claim; relevance is insufficient to confirm "
                "or refute the statement."
            ),
            matched_terms=scored.matched_terms,
            signals=["insufficient_overlap"],
            retrieval_status=cand.retrieval_status,
        )

    matched_uncertainty = [p for p in _UNCERTAINTY_PHRASES if p in text_lower]
    if matched_uncertainty:
        return EvidenceSnippet(
            source_id=cand.source_id,
            source_title=cand.source_title,
            url=cand.url,
            publisher=cand.publisher,
            publication_date=cand.publication_date,
            excerpt=cand.statement,
            relevance_score=scored.relevance_score,
            position=EvidencePosition.UNCLEAR,
            rationale=(
                f"Evidence expresses uncertainty or lack of consensus "
                f"('{matched_uncertainty[0]}')."
            ),
            matched_terms=scored.matched_terms,
            signals=[f"uncertainty:{matched_uncertainty[0]}"],
            retrieval_status=cand.retrieval_status,
        )

    matched_refutations = [p for p in _REFUTATION_PHRASES if p in text_lower]
    ev_negation = contains_negation(cand.statement)
    polarity_mismatch = claim.has_negation != ev_negation
    antonym_conflict = _detect_antonym_conflict(claim.text, cand.statement)
    numeric_conflict = (
        _detect_numeric_conflict(claim, cand.statement)
        if scored.keyword_overlap_score >= 0.30 or len(scored.matched_terms) >= 2
        else None
    )

    contradiction_reasons: list[str] = []
    if matched_refutations:
        signals.append(f"refutation:{matched_refutations[0]}")
        contradiction_reasons.append(f"contains refutation cue '{matched_refutations[0]}'")
    if polarity_mismatch:
        signals.append("negation_mismatch")
        contradiction_reasons.append("negation polarity conflicts with the claim")
    if antonym_conflict:
        signals.append("antonym_conflict")
        contradiction_reasons.append(antonym_conflict.lower())
    if numeric_conflict:
        signals.append("numeric_conflict")
        contradiction_reasons.append(numeric_conflict.lower())

    if contradiction_reasons:
        return EvidenceSnippet(
            source_id=cand.source_id,
            source_title=cand.source_title,
            url=cand.url,
            publisher=cand.publisher,
            publication_date=cand.publication_date,
            excerpt=cand.statement,
            relevance_score=scored.relevance_score,
            position=EvidencePosition.CONTRADICTS,
            rationale="Evidence conflicts with the claim: " + "; ".join(contradiction_reasons) + ".",
            matched_terms=scored.matched_terms,
            signals=signals,
            retrieval_status=cand.retrieval_status,
        )

    ev_numbers = set(extract_numbers(cand.statement))
    numbers_confirmed = bool(claim.numbers) and all(n in ev_numbers for n in claim.numbers)
    if numbers_confirmed:
        signals.append("numeric_match")

    strong_coverage = (
        scored.relevance_score >= MIN_RELEVANCE_FOR_SUPPORT
        and (scored.keyword_overlap_score >= 0.35 or len(scored.matched_terms) >= 2)
    )
    if strong_coverage and (not claim.numbers or numbers_confirmed):
        signals.append("aligned_terms")
        if cand.retrieval_status == RetrievalStatus.SNIPPET_ONLY:
            signals.append("snippet_only")
        rationale = (
            f"Matches {len(scored.matched_terms)} key claim term(s) "
            f"({', '.join(scored.matched_terms[:5])}) with consistent polarity"
            + (" and matching numeric/date values." if numbers_confirmed else ".")
        )
        return EvidenceSnippet(
            source_id=cand.source_id,
            source_title=cand.source_title,
            url=cand.url,
            publisher=cand.publisher,
            publication_date=cand.publication_date,
            excerpt=cand.statement,
            relevance_score=scored.relevance_score,
            position=EvidencePosition.SUPPORTS,
            rationale=rationale,
            matched_terms=scored.matched_terms,
            signals=signals,
            retrieval_status=cand.retrieval_status,
        )

    return EvidenceSnippet(
        source_id=cand.source_id,
        source_title=cand.source_title,
        url=cand.url,
        publisher=cand.publisher,
        publication_date=cand.publication_date,
        excerpt=cand.statement,
        relevance_score=scored.relevance_score,
        position=EvidencePosition.UNCLEAR,
        rationale=(
            "Topically related statement, but does not confirm all key details "
            "or quantities required to verify the claim."
        ),
        matched_terms=scored.matched_terms,
        signals=["partial_overlap"],
        retrieval_status=cand.retrieval_status,
    )


def select_representative_evidence(
    snippets: list[EvidenceSnippet],
) -> dict[str, EvidenceSnippet]:
    """Select the strongest representative snippet per source_id."""
    priority = {
        EvidencePosition.CONTRADICTS: 3,
        EvidencePosition.SUPPORTS: 2,
        EvidencePosition.UNCLEAR: 1,
    }
    best_by_source: dict[str, EvidenceSnippet] = {}
    for snippet in snippets:
        existing = best_by_source.get(snippet.source_id)
        if existing is None:
            best_by_source[snippet.source_id] = snippet
            continue
        cur_rank = (priority[snippet.position], snippet.relevance_score)
        prev_rank = (priority[existing.position], existing.relevance_score)
        if cur_rank > prev_rank:
            best_by_source[snippet.source_id] = snippet
    return best_by_source


def _standard_limitations(sources: list[RetrievedSource]) -> list[str]:
    accessible_sources = [s for s in sources if s.usable_text]
    inaccessible_sources = [s for s in sources if not s.usable_text]
    snippet_only_sources = [
        s for s in sources if s.retrieval_status == RetrievalStatus.SNIPPET_ONLY
    ]

    limitations: list[str] = [
        "Text similarity alone does not prove factual correctness; verdicts depend strictly on "
        "the quality and completeness of the provided sources.",
        "Domain names are recorded for attribution only and do not automatically "
        "establish source authority.",
    ]

    if inaccessible_sources:
        limitations.append(
            f"{len(inaccessible_sources)} source(s) could not be accessed (e.g., HTTP restrictions, "
            "timeout, blank text, or invalid URL) and were excluded from evidence verification."
        )
    if snippet_only_sources:
        limitations.append(
            f"{len(snippet_only_sources)} source(s) relied only on partial snippets because full "
            "page text could not be retrieved."
        )
    missing_dates = [s for s in accessible_sources if not s.publication_date]
    if missing_dates:
        limitations.append(
            f"Publication date was unavailable for {len(missing_dates)} source(s); "
            "timeliness could not be fully evaluated."
        )
    return limitations


def verify_claim_from_evidence(
    claim: ParsedClaim,
    sources: list[RetrievedSource],
    scored_evidence: list[ScoredEvidence],
) -> dict[str, object]:
    """Deterministic fallback verification across sources without calling an LLM."""
    evaluated = [evaluate_evidence_item(claim, item) for item in scored_evidence]
    best_by_source = select_representative_evidence(evaluated)

    supporting = [e for e in best_by_source.values() if e.position == EvidencePosition.SUPPORTS]
    contradicting = [
        e for e in best_by_source.values() if e.position == EvidencePosition.CONTRADICTS
    ]
    unclear = [e for e in best_by_source.values() if e.position == EvidencePosition.UNCLEAR]

    supporting.sort(key=lambda e: e.relevance_score, reverse=True)
    contradicting.sort(key=lambda e: e.relevance_score, reverse=True)
    unclear.sort(key=lambda e: e.relevance_score, reverse=True)

    accessible_sources = [s for s in sources if s.usable_text]
    inaccessible_sources = [s for s in sources if not s.usable_text]

    disagreement_flagged = bool(supporting and contradicting)
    unresolved_questions: list[str] = []
    unsupported_statements: list[str] = []
    limitations = _standard_limitations(sources)

    if not sources:
        label = VerificationLabel.UNVERIFIED
        confidence = 0.0
        short_explanation = (
            "No sources were provided for this claim, so it cannot be verified."
        )
        confidence_explanation = (
            "Confidence is 0.00 because zero evidence sources were supplied."
        )
        unsupported_statements.append(claim.text)
        unresolved_questions.append("Which verifiable sources address this claim?")
    elif not accessible_sources:
        label = VerificationLabel.UNVERIFIED
        confidence = 0.05
        short_explanation = (
            f"All {len(sources)} source(s) were inaccessible, blank, or invalid; "
            "no evidence text could be analyzed."
        )
        confidence_explanation = (
            "Confidence is 0.05 because all source retrieval attempts lacked readable text."
        )
        unsupported_statements.append(claim.text)
        unresolved_questions.append(
            "Can alternative publicly accessible sources or pasted excerpts be provided?"
        )
    elif disagreement_flagged:
        label = VerificationLabel.UNVERIFIED
        total_decisive = len(supporting) + len(contradicting)
        confidence = round(min(0.45, 0.25 + 0.05 * total_decisive), 2)
        short_explanation = (
            f"Sources disagree: {len(supporting)} source(s) support the claim while "
            f"{len(contradicting)} source(s) contradict it. Because conflicting evidence exists, "
            "the claim is labeled UNVERIFIED rather than forcing a verdict."
        )
        confidence_explanation = (
            f"Confidence is low ({confidence:.2f}) due to direct disagreement across sources."
        )
        unresolved_questions.append(
            "Why do the supporting and contradicting sources conflict, and which source "
            "provides primary documentation?"
        )
    elif contradicting and not supporting:
        label = VerificationLabel.CONTRADICTED
        avg_rel = sum(e.relevance_score for e in contradicting) / len(contradicting)
        multi_bonus = min(0.25, 0.12 * (len(contradicting) - 1))
        confidence = round(min(0.92, 0.48 + 0.30 * avg_rel + multi_bonus), 2)
        short_explanation = (
            f"{len(contradicting)} provided source(s) directly conflict with the claim."
        )
        if len(contradicting) == 1:
            confidence = min(confidence, 0.72)
            confidence_explanation = (
                f"Moderate confidence ({confidence:.2f}) based on a single contradicting source; "
                "additional independent sources would strengthen verification."
            )
            unresolved_questions.append(
                "Do additional independent sources corroborate this contradiction?"
            )
        else:
            confidence_explanation = (
                f"Confidence is {confidence:.2f}, backed by {len(contradicting)} "
                "independent contradicting sources."
            )
    elif supporting and not contradicting:
        label = VerificationLabel.SUPPORTED
        avg_rel = sum(e.relevance_score for e in supporting) / len(supporting)
        multi_bonus = min(0.25, 0.12 * (len(supporting) - 1))
        confidence = round(min(0.92, 0.48 + 0.30 * avg_rel + multi_bonus), 2)
        short_explanation = (
            f"{len(supporting)} provided source(s) contain evidence consistent with the claim "
            "with no contradicting evidence found."
        )
        if len(supporting) == 1:
            confidence = min(confidence, 0.72)
            confidence_explanation = (
                f"Moderate confidence ({confidence:.2f}) because only one supporting source "
                "was analyzed; independent corroboration is recommended."
            )
            unresolved_questions.append(
                "Is this claim corroborated by a second independent source?"
            )
        else:
            confidence_explanation = (
                f"Confidence is {confidence:.2f}, corroborated across {len(supporting)} "
                "sources without observed contradictions."
            )
    else:
        label = VerificationLabel.UNVERIFIED
        confidence = 0.18
        short_explanation = (
            f"Reviewed {len(accessible_sources)} accessible source(s), but the provided text "
            "was insufficient or too ambiguous to confirm or refute the claim."
        )
        confidence_explanation = (
            f"Confidence is low ({confidence:.2f}) because no provided statement decisively "
            "supports or contradicts all elements of the claim."
        )
        unsupported_statements.append(claim.text)
        unresolved_questions.append(
            "What primary evidence directly confirms or refutes the specific entities, dates, "
            "or quantities in this claim?"
        )

    if inaccessible_sources:
        unresolved_questions.append(
            f"Could the {len(inaccessible_sources)} inaccessible source(s) contain relevant context?"
        )

    matched_union = {term for item in evaluated for term in item.matched_terms}
    unmatched_kw = [kw for kw in claim.keywords if kw not in matched_union]
    if unmatched_kw and label == VerificationLabel.UNVERIFIED:
        unresolved_questions.append(
            f"No provided evidence addressed key claim term(s): {', '.join(unmatched_kw[:5])}."
        )

    return {
        "label": label,
        "confidence_score": confidence,
        "confidence_explanation": confidence_explanation,
        "short_explanation": short_explanation,
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting,
        "unclear_evidence": unclear,
        "unsupported_statements": unsupported_statements,
        "unresolved_questions": unresolved_questions,
        "limitations": limitations,
        "disagreement_flagged": disagreement_flagged,
        "best_by_source": best_by_source,
    }


def _ground_excerpt(candidate_excerpt: str, source: RetrievedSource, fallback_excerpt: str) -> str:
    """Verify excerpt comes from the actual source text rather than being invented."""
    usable = source.usable_text
    if not usable:
        return source.retrieval_error or "No readable text available."
    clean_cand = re.sub(r"\s+", " ", (candidate_excerpt or "")).strip()
    clean_usable = re.sub(r"\s+", " ", usable).strip()
    if clean_cand and len(clean_cand) >= 12 and clean_cand.lower() in clean_usable.lower():
        return clean_cand
    return fallback_excerpt or clean_usable[:320]


def reconcile_gemini_source_assessment(
    claim: ParsedClaim,
    sources: list[RetrievedSource],
    scored_evidence: list[ScoredEvidence],
    gemini_resp: GeminiEvidenceVerificationResponse,
) -> dict[str, object]:
    """Ground Gemini's structured analysis strictly in the actual retrieved sources.

    Ignores any unknown source_id, forbids fabricated excerpts or inaccessible-page claims,
    and enforces UNVERIFIED whenever sources disagree.
    """
    source_map = {s.source_id: s for s in sources}
    top_scored_by_source: dict[str, ScoredEvidence] = {}
    for item in scored_evidence:
        sid = item.candidate.source_id
        if sid not in top_scored_by_source:
            top_scored_by_source[sid] = item

    best_by_source: dict[str, EvidenceSnippet] = {}
    for assessment in gemini_resp.source_assessments:
        source = source_map.get(assessment.source_id)
        if source is None:
            continue
        top_scored = top_scored_by_source.get(source.source_id)
        rel_score = top_scored.relevance_score if top_scored else 0.0
        matched_terms = top_scored.matched_terms if top_scored else []

        # Never allow an inaccessible/invalid source to count as Supports or Contradicts
        if not source.usable_text:
            position = EvidencePosition.UNCLEAR
            excerpt = source.retrieval_error or "Source was inaccessible; content was not read."
            rationale = "Source could not be read and was excluded from factual verification."
        else:
            position = assessment.position
            fallback_ex = top_scored.candidate.statement if top_scored else source.usable_text[:320]
            excerpt = _ground_excerpt(assessment.evidence_excerpt, source, fallback_ex)
            rationale = assessment.rationale.strip() or "Evaluated by Gemini against provided text."

        best_by_source[source.source_id] = EvidenceSnippet(
            source_id=source.source_id,
            source_title=source.title,
            url=source.url,
            publisher=source.publisher,
            publication_date=source.publication_date,
            excerpt=excerpt,
            relevance_score=rel_score,
            position=position,
            rationale=rationale,
            matched_terms=matched_terms,
            signals=["gemini_source_analysis"],
            retrieval_status=source.retrieval_status,
        )

    # Ensure every source has an entry even if Gemini omitted one
    for source in sources:
        if source.source_id in best_by_source:
            continue
        top_scored = top_scored_by_source.get(source.source_id)
        best_by_source[source.source_id] = EvidenceSnippet(
            source_id=source.source_id,
            source_title=source.title,
            url=source.url,
            publisher=source.publisher,
            publication_date=source.publication_date,
            excerpt=(
                top_scored.candidate.statement
                if top_scored
                else (source.retrieval_error or source.usable_text[:320] or "No readable text.")
            ),
            relevance_score=top_scored.relevance_score if top_scored else 0.0,
            position=EvidencePosition.UNCLEAR,
            rationale=(
                source.retrieval_error
                if not source.usable_text
                else "Source was not clearly aligned or conflicting in Gemini's assessment."
            ),
            matched_terms=top_scored.matched_terms if top_scored else [],
            signals=["unassessed_fallback"],
            retrieval_status=source.retrieval_status,
        )

    supporting = [e for e in best_by_source.values() if e.position == EvidencePosition.SUPPORTS]
    contradicting = [
        e for e in best_by_source.values() if e.position == EvidencePosition.CONTRADICTS
    ]
    unclear = [e for e in best_by_source.values() if e.position == EvidencePosition.UNCLEAR]

    disagreement_flagged = bool(supporting and contradicting)
    label = gemini_resp.label
    confidence = float(gemini_resp.confidence_score)
    short_explanation = gemini_resp.short_explanation.strip()
    confidence_explanation = gemini_resp.confidence_explanation.strip()

    accessible_sources = [s for s in sources if s.usable_text]
    if not accessible_sources:
        label = VerificationLabel.UNVERIFIED
        confidence = 0.05
        short_explanation = (
            f"None of the {len(sources)} source(s) contained readable text; the claim cannot be "
            "verified from the provided sources."
        )
        confidence_explanation = "Confidence is 0.05 because no readable evidence text was available."
    elif disagreement_flagged:
        label = VerificationLabel.UNVERIFIED
        confidence = min(confidence, 0.49)
        disagree_note = (
            gemini_resp.disagreement_summary.strip()
            or f"{len(supporting)} source(s) support while {len(contradicting)} source(s) contradict."
        )
        if "disagree" not in short_explanation.lower() and "conflict" not in short_explanation.lower():
            short_explanation = f"Sources disagree: {disagree_note} {short_explanation}".strip()
    elif label == VerificationLabel.SUPPORTED and not supporting:
        label = VerificationLabel.UNVERIFIED
        confidence = min(confidence, 0.35)
        short_explanation = (
            "No accessible source was confirmed to directly support the claim; marked UNVERIFIED."
        )
    elif label == VerificationLabel.CONTRADICTED and not contradicting:
        label = VerificationLabel.UNVERIFIED
        confidence = min(confidence, 0.35)
        short_explanation = (
            "No accessible source was confirmed to directly contradict the claim; marked UNVERIFIED."
        )

    limitations = _standard_limitations(sources)
    limitations.append(
        "Evidence analysis was assisted by Google Gemini strictly over user-provided/retrieved "
        "sources; no live web search was performed."
    )

    unresolved_questions = [q.strip() for q in gemini_resp.unresolved_questions if q.strip()]
    unsupported_statements = [u.strip() for u in gemini_resp.unsupported_statements if u.strip()]
    if label == VerificationLabel.UNVERIFIED and not unsupported_statements:
        unsupported_statements.append(claim.text)

    return {
        "label": label,
        "confidence_score": round(max(0.0, min(1.0, confidence)), 2),
        "confidence_explanation": confidence_explanation
        or "Confidence reflects alignment and completeness of the provided sources.",
        "short_explanation": short_explanation,
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting,
        "unclear_evidence": unclear,
        "unsupported_statements": unsupported_statements,
        "unresolved_questions": unresolved_questions,
        "limitations": limitations,
        "disagreement_flagged": disagreement_flagged,
        "best_by_source": best_by_source,
    }


def build_preliminary_verification_payload(
    claim: ParsedClaim,
    gemini_prelim: GeminiPreliminaryAnalysisResponse,
) -> dict[str, object]:
    """Build Mode B verification payload clearly marked as AI-generated preliminary analysis."""
    supporting_pts = [p.strip() for p in gemini_prelim.supporting_points if p.strip()]
    contradicting_pts = [p.strip() for p in gemini_prelim.contradicting_points if p.strip()]
    unsupported = [u.strip() for u in gemini_prelim.unsupported_statements if u.strip()]
    unresolved = [q.strip() for q in gemini_prelim.unresolved_questions if q.strip()]

    disagreement_flagged = bool(supporting_pts and contradicting_pts)
    label = gemini_prelim.label
    if disagreement_flagged:
        label = VerificationLabel.UNVERIFIED

    short_explanation = (
        "[AI-Generated Preliminary Analysis — Not Live Source Verification] "
        + gemini_prelim.short_explanation.strip()
    )
    confidence = round(min(float(gemini_prelim.confidence_score), 0.75), 2)
    confidence_explanation = (
        "Preliminary model-knowledge estimate only (capped at 0.75 because no external sources "
        "were retrieved or verified). " + gemini_prelim.confidence_explanation.strip()
    )

    limitations = [
        "AI-GENERATED PRELIMINARY ANALYSIS: Generated from Gemini's training knowledge only.",
        "No live web search, external databases, URLs, or retrieved documents were checked.",
        "Do not treat this preliminary output as verified fact; corroborate with primary sources.",
    ]

    if not unresolved:
        unresolved.append(
            f"Which primary, independently verifiable sources confirm or refute: '{claim.text}'?"
        )

    return {
        "label": label,
        "confidence_score": confidence,
        "confidence_explanation": confidence_explanation,
        "short_explanation": short_explanation,
        "supporting_evidence": [],
        "contradicting_evidence": [],
        "unclear_evidence": [],
        "unsupported_statements": unsupported,
        "preliminary_points_supporting": supporting_pts,
        "preliminary_points_contradicting": contradicting_pts,
        "unresolved_questions": unresolved,
        "limitations": limitations,
        "disagreement_flagged": disagreement_flagged,
        "best_by_source": {},
    }
