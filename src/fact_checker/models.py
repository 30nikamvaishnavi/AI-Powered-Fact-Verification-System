"""Shared Pydantic v2 data models and enums for the Fact Verification System."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class VerificationLabel(StrEnum):
    """Primary verification verdicts."""

    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNVERIFIED = "UNVERIFIED"


class EvidencePosition(StrEnum):
    """Stance of an individual evidence statement relative to a claim."""

    SUPPORTS = "Supports"
    CONTRADICTS = "Contradicts"
    UNCLEAR = "Unclear"


class RetrievalStatus(StrEnum):
    """Outcome of retrieving content from a source."""

    RETRIEVED = "Retrieved"
    SNIPPET_ONLY = "Snippet Only (Full page inaccessible)"
    INACCESSIBLE = "Inaccessible"
    INVALID_URL = "Invalid URL"
    MANUAL = "Manual Entry"


class ParsedClaim(BaseModel):
    """Validated and normalized factual claim ready for verification."""

    claim_id: str
    text: str
    normalized_text: str
    keywords: list[str] = Field(default_factory=list)
    numbers: list[str] = Field(default_factory=list)
    has_negation: bool = False


class SearchResult(BaseModel):
    """Standardized search result returned by any configured SearchProvider."""

    title: str
    url: str
    publisher: str
    publication_date: str | None = None
    snippet: str = ""
    provider: str = "unknown"


class ManualEvidenceInput(BaseModel):
    """User-supplied evidence source when running in Manual Evidence Mode."""

    title: str = Field(..., min_length=1, max_length=300)
    url: str = Field(..., min_length=1, max_length=2000)
    text: str = Field(default="", max_length=20000)
    publication_date: str | None = Field(default=None, max_length=64)


class RetrievedSource(BaseModel):
    """Source metadata and retrieved text with explicit retrieval status."""

    source_id: str
    title: str
    url: str
    publisher: str
    publication_date: str | None = None
    snippet: str = ""
    retrieved_text: str = ""
    retrieval_status: RetrievalStatus
    retrieval_error: str | None = None
    retrieved_at: str
    is_manual: bool = False
    provider: str = "manual"

    @property
    def usable_text(self) -> str:
        """Return retrieved text if available, otherwise fall back to snippet."""
        return self.retrieved_text.strip() or self.snippet.strip()


class CandidateStatement(BaseModel):
    """A single candidate evidence statement extracted from a source."""

    source_id: str
    source_title: str
    url: str
    publisher: str
    publication_date: str | None = None
    statement: str
    retrieval_status: RetrievalStatus


class ScoredEvidence(BaseModel):
    """A candidate statement annotated with transparent NLP relevance metrics."""

    candidate: CandidateStatement
    tfidf_score: float = Field(ge=0.0, le=1.0)
    keyword_overlap_score: float = Field(ge=0.0, le=1.0)
    relevance_score: float = Field(ge=0.0, le=1.0)
    matched_terms: list[str] = Field(default_factory=list)


class EvidenceSnippet(BaseModel):
    """Analyzed evidence excerpt with stance and transparent explanation."""

    source_id: str
    source_title: str
    url: str
    publisher: str
    publication_date: str | None = None
    excerpt: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    position: EvidencePosition
    rationale: str
    matched_terms: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)
    retrieval_status: RetrievalStatus


class SourceComparisonRow(BaseModel):
    """One row in the multi-source comparison table."""

    source_title: str
    publisher: str
    url: str
    publication_date: str | None = None
    evidence_excerpt: str
    evidence_position: EvidencePosition
    retrieval_status: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    credibility_note: str


class ComparisonSummary(BaseModel):
    """Cross-source agreement and disagreement analysis."""

    claim_text: str
    rows: list[SourceComparisonRow] = Field(default_factory=list)
    supports_count: int = 0
    contradicts_count: int = 0
    unclear_count: int = 0
    inaccessible_count: int = 0
    has_disagreement: bool = False
    agreement_summary: str = ""
    disagreement_summary: str = ""


class VerificationReport(BaseModel):
    """Complete structured verification report for a single factual claim."""

    report_id: str
    session_id: str
    claim: str
    label: VerificationLabel
    confidence_score: float = Field(ge=0.0, le=1.0)
    confidence_explanation: str
    short_explanation: str
    supporting_evidence: list[EvidenceSnippet] = Field(default_factory=list)
    contradicting_evidence: list[EvidenceSnippet] = Field(default_factory=list)
    unclear_evidence: list[EvidenceSnippet] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    source_comparison: ComparisonSummary
    sources: list[RetrievedSource] = Field(default_factory=list)
    retrieval_timestamp: str
    limitations: list[str] = Field(default_factory=list)
    disagreement_flagged: bool = False
    search_mode: str = "Manual Evidence Mode"


class VerificationHistorySummary(BaseModel):
    """Lightweight summary record for listing historical verifications."""

    report_id: str
    session_id: str
    claim: str
    label: VerificationLabel
    confidence_score: float
    disagreement_flagged: bool
    retrieval_timestamp: str
    search_mode: str
    source_count: int = 0
